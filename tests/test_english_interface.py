"""Keep product copy English while speech and text processing remain multilingual."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_interface_declares_english_and_keeps_supported_languages() -> None:
    page = (ROOT / "static/index.html").read_text()
    assert '<html lang="en-US">' in page
    assert '<option value="chinese">Chinese</option>' in page
    assert '<option value="japanese">Japanese</option>' in page
    assert '<option value="korean">Korean</option>' in page
    assert '<option value="en">English</option>' in page
    assert 'DateTimeFormat("en-US"' in (ROOT / "static/app.js").read_text()


def test_maintained_source_and_documentation_have_no_han_copy() -> None:
    # Multilingual regression fixtures use Unicode escapes, not untranslated copy.
    han = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
    files = list(ROOT.glob("*.md")) + [ROOT / "app.py"]
    for folder in ("macos", "scripts", "static", "timbreloom", "docs", "tests", "packaging"):
        files.extend(path for path in (ROOT / folder).rglob("*")
                     if path.suffix in {".py", ".js", ".mjs", ".swift", ".html", ".json", ".md", ".sh"})
    untranslated = [str(path.relative_to(ROOT)) for path in files if han.search(path.read_text())]
    assert not untranslated, f"Untranslated copy in: {untranslated}"
