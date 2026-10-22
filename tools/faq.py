"""Read bundled FAQ documents independently of the writable runtime directory."""

from pathlib import Path

from tools.file_io import read_text

_DOCS_DIR = Path(__file__).resolve().parents[1] / "docs"
_FAQ_PATHS = {
    "zh": "cn/faq.md",
    "en": "en/faq_en.md",
    "ja": "jp/faq_ja.md",
    "ko": "kr/faq_ko.md",
    "fr": "fr/faq_fr.md",
    "tr": "tr/faq_tr.md",
    "pt": "pt/faq_pt.md",
}


def load_faq(language):
    """Load the selected locale's FAQ, falling back to English if absent."""
    language = (language or "").replace("-", "_").split("_", 1)[0].lower()
    english = _DOCS_DIR / _FAQ_PATHS["en"]
    path = _DOCS_DIR / _FAQ_PATHS.get(language, _FAQ_PATHS["en"])
    try:
        return read_text(path)
    except FileNotFoundError:
        if path == english:
            raise
        return read_text(english)
