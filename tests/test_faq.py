"""FAQ resource tests; no WebUI or third-party dependencies are imported."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import faq
from tools.file_io import read_text


class FaqTests(unittest.TestCase):
    def test_bundled_locale_documents(self):
        docs = Path(faq.__file__).resolve().parents[1] / "docs"
        locales = {
            "zh_CN": "cn/faq.md",
            "zh_TW": "cn/faq.md",
            "zh_HK": "cn/faq.md",
            "zh_SG": "cn/faq.md",
            "en_US": "en/faq_en.md",
            "ja_JP": "jp/faq_ja.md",
            "ko_KR": "kr/faq_ko.md",
            "fr_FR": "fr/faq_fr.md",
            "tr_TR": "tr/faq_tr.md",
            "pt_BR": "pt/faq_pt.md",
            "pt_PT": "pt/faq_pt.md",
            "ZH-tw": "cn/faq.md",
            "ja": "jp/faq_ja.md",
        }
        for language, relative in locales.items():
            with self.subTest(language=language):
                expected = read_text(docs / relative)
                self.assertTrue(expected.strip())
                self.assertEqual(faq.load_faq(language), expected)

    def test_unsupported_locales_use_english(self):
        expected = faq.load_faq("en_US")
        for language in ("es_ES", "it_IT", "ru_RU", "unknown", "", None):
            with self.subTest(language=language):
                self.assertEqual(faq.load_faq(language), expected)

    def test_missing_localized_document_uses_english(self):
        with tempfile.TemporaryDirectory() as directory:
            docs = Path(directory)
            (docs / "en").mkdir()
            (docs / "en/faq_en.md").write_text("English fallback", encoding="utf-8")
            with patch.object(faq, "_DOCS_DIR", docs):
                self.assertEqual(faq.load_faq("ja_JP"), "English fallback")

    def test_missing_english_is_reported(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(faq, "_DOCS_DIR", Path(directory)),
        ):
            for language in ("en_US", "ja_JP", "es_ES"):
                with (
                    self.subTest(language=language),
                    self.assertRaises(FileNotFoundError),
                ):
                    faq.load_faq(language)

    def test_other_io_errors_are_not_hidden(self):
        with (
            patch.object(faq, "read_text", side_effect=PermissionError("unreadable")),
            self.assertRaises(PermissionError),
        ):
            faq.load_faq("ja_JP")

    def test_cwd_cannot_override_bundled_documents(self):
        expected = faq.load_faq("ja_JP")
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            (cwd / "docs/jp").mkdir(parents=True)
            (cwd / "docs/jp/faq_ja.md").write_text("Runtime override", encoding="utf-8")
            try:
                os.chdir(cwd)
                self.assertEqual(faq.load_faq("ja_JP"), expected)
            finally:
                os.chdir(previous)

    def test_managed_tools_symlink_resolves_source_documents(self):
        expected = faq.load_faq("fr_FR")
        with tempfile.TemporaryDirectory() as directory:
            tools = Path(directory) / "tools"
            tools.symlink_to(
                Path(faq.__file__).resolve().parent, target_is_directory=True
            )
            spec = importlib.util.spec_from_file_location(
                "linked_faq", tools / "faq.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertEqual(module.load_faq("fr_FR"), expected)


if __name__ == "__main__":
    unittest.main()
