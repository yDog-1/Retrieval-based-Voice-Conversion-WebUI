"""CPU integration checks; require the full packaged Python environment.

Unlike test_packaged_checks, these import the actual vendored ML runtime. Each
probe uses a fresh interpreter, with no Config, model downloads, or GPU work.
"""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PackagedResourceTests(unittest.TestCase):
    def run_probe(self, root):
        code = (
            "import importlib.util, sys;"
            f"spec = importlib.util.spec_from_file_location('doctor', {str(root / 'nix/doctor.py')!r});"
            "doctor = importlib.util.module_from_spec(spec);"
            "spec.loader.exec_module(doctor);"
            "doctor.check_vendored_pymss();"
            "assert 'configs.config' not in sys.modules;"
            "assert 'tools.pymss_webui' not in sys.modules;"
            "assert 'webui' not in sys.modules"
        )
        # An unrelated cwd and isolated sys.path prevent the checkout or a
        # caller's PYTHONPATH from accidentally making this probe pass.
        return subprocess.run(
            [sys.executable, "-I", "-c", code], cwd="/",
            capture_output=True, text=True, timeout=180,
        )

    def test_actual_vendored_apis_and_resources(self):
        result = self.run_probe(ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(ROOT / "tools/pymss/__init__.py"), result.stdout)
        self.assertIn(str(ROOT / "tools/pymss_core/__init__.py"), result.stdout)
        self.assertIn("OK: model_catalog.json (", result.stdout)
        self.assertIn("OK: VR modelparams (", result.stdout)

    def test_resource_failures_are_not_masked_by_site_packages(self):
        cases = (
            ("pymss/resources/model_catalog.json", "missing", "FileNotFoundError"),
            ("pymss/resources/model_catalog.json", "invalid", "JSONDecodeError"),
            ("pymss_core/resources/vr_modelparams/4band_v3.json", "invalid", "JSONDecodeError"),
        )
        for relative, failure, expected in cases:
            with self.subTest(resource=relative, failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "nix").mkdir()
                shutil.copyfile(ROOT / "nix/doctor.py", root / "nix/doctor.py")
                shutil.copytree(ROOT / "tools", root / "tools", ignore=shutil.ignore_patterns("__pycache__"))
                resource = root / "tools" / relative
                # copytree preserves the read-only modes of Nix store inputs.
                resource.parent.chmod(0o755)
                resource.chmod(0o644)
                if failure == "missing":
                    resource.unlink()
                else:
                    resource.write_text("{invalid", encoding="utf-8")
                result = self.run_probe(root)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(expected, result.stderr)
                self.assertIn(str(root / "tools"), result.stdout)


if __name__ == "__main__":
    unittest.main()
