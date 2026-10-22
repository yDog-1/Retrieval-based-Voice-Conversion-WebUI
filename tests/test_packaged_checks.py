"""Stdlib-only checks of doctor import selection and provenance enforcement.

The real ML imports/resource APIs are exercised separately by rvc-doctor in the
heavy runtime check. Fixtures here deliberately need no installed ML packages.
"""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("packaged_doctor", ROOT / "nix/doctor.py")
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)


class OriginTests(unittest.TestCase):
    def test_vendored_core_aliases_are_allowed(self):
        module = types.ModuleType("pymss.modules.apollo_mlx")
        module.__file__ = str(ROOT / "tools/pymss_core/modules/apollo_mlx.py")
        with patch.dict(sys.modules, {"pymss.modules.apollo_mlx": module}):
            doctor.assert_vendored_origins(ROOT / "tools")

    def test_cached_site_package_and_transitive_mismatch_are_rejected(self):
        for name in ("pymss", "pymss_core", "pymss_core.config"):
            with self.subTest(name=name):
                module = types.ModuleType(name)
                module.__file__ = "/site-packages/" + name.replace(".", "/") + ".py"
                with patch.dict(sys.modules, {name: module}):
                    with self.assertRaisesRegex(RuntimeError, "Wrong vendored origin"):
                        doctor.assert_vendored_origins(ROOT / "tools")

    def test_package_search_path_cannot_escape_vendored_tree(self):
        module = types.ModuleType("pymss")
        module.__file__ = str(ROOT / "tools/pymss/__init__.py")
        module.__path__ = [str(ROOT / "tools/pymss"), "/site-packages/pymss"]
        with patch.dict(sys.modules, {"pymss": module}):
            with self.assertRaisesRegex(RuntimeError, "Wrong vendored package path"):
                doctor.assert_vendored_origins(ROOT / "tools")

    def test_missing_origin_is_rejected(self):
        with patch.dict(sys.modules, {"pymss": types.ModuleType("pymss")}):
            with self.assertRaisesRegex(RuntimeError, "Wrong vendored origin"):
                doctor.assert_vendored_origins(ROOT / "tools")

    def test_namespace_resources_require_vendored_search_paths(self):
        module = types.ModuleType("pymss.resources")
        module.__path__ = [str(ROOT / "tools/pymss/resources")]
        with patch.dict(sys.modules, {"pymss.resources": module}):
            doctor.assert_vendored_origins(ROOT / "tools")
            module.__path__.append("/site-packages/pymss/resources")
            with self.assertRaisesRegex(RuntimeError, "Wrong vendored package path"):
                doctor.assert_vendored_origins(ROOT / "tools")

    def test_resolved_symlink_outside_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools/pymss").mkdir(parents=True)
            (root / "outside.py").write_text("", encoding="utf-8")
            link = root / "tools/pymss/__init__.py"
            link.symlink_to(root / "outside.py")
            module = types.ModuleType("pymss")
            module.__file__ = str(link)
            with patch.dict(sys.modules, {"pymss": module}):
                with self.assertRaisesRegex(RuntimeError, "Wrong vendored origin"):
                    doctor.assert_vendored_origins(root / "tools")


class ImportSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "nix").mkdir()
        shutil.copyfile(ROOT / "nix/doctor.py", self.root / "nix/doctor.py")
        for parent in ("tools", "site"):
            for package in ("pymss", "pymss_core"):
                path = self.root / parent / package
                path.mkdir(parents=True)
                (path / "__init__.py").write_text(
                    f"raise RuntimeError('{parent} {package} selected')\n", encoding="utf-8"
                )

    def run_check(self, prelude=""):
        code = f"""
            import importlib.util, sys
            from pathlib import Path
            root = Path({str(self.root)!r})
            sys.path.insert(0, str(root / 'site'))
            spec = importlib.util.spec_from_file_location('doctor', root / 'nix/doctor.py')
            doctor = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(doctor)
            {prelude}
            doctor.check_vendored_pymss()
        """
        return subprocess.run(
            [sys.executable, "-I", "-c", textwrap.dedent(code)],
            cwd=self.root, capture_output=True, text=True, timeout=30,
        )

    def test_vendored_failure_is_not_hidden_by_installed_package(self):
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tools pymss selected", result.stderr)
        self.assertNotIn("site pymss selected", result.stderr)

    def test_cached_installed_package_is_rejected_in_fresh_process(self):
        (self.root / "site/pymss/__init__.py").write_text("", encoding="utf-8")
        result = self.run_check("import pymss")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Wrong vendored origin for pymss", result.stderr)


if __name__ == "__main__":
    unittest.main()
