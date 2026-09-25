from __future__ import annotations

import sys
import types

from pytest import MonkeyPatch

from ingestion import pdf_extraction


class _FakePdfPage:
    def __init__(self, text: str) -> None:
        self.text = text

    def extract_text(self) -> str:
        return self.text


class _FakeRenderedPage:
    def __init__(self, page_number: int) -> None:
        self.page_number = page_number

    def render(self, *, scale: float) -> object:
        assert scale == pdf_extraction._OCR_SCALE
        return types.SimpleNamespace(to_pil=lambda: self.page_number)


class _FakeRenderedDocument:
    def __init__(self, _pdf_path: str) -> None:
        self.pages = [_FakeRenderedPage(0), _FakeRenderedPage(1)]

    def __getitem__(self, page_number: int) -> _FakeRenderedPage:
        return self.pages[page_number]


def test_embedded_text_does_not_load_ocr(monkeypatch: MonkeyPatch) -> None:
    pages = [
        _FakePdfPage(
            "Titre\nArt. 1 Une règle suffisamment longue pour être conservée dans le texte "
            "juridique de cette disposition."
        )
    ]
    monkeypatch.setattr(
        pdf_extraction, "PdfReader", lambda _path: types.SimpleNamespace(pages=pages)
    )

    def fail_if_called(_page: object) -> str:
        raise AssertionError("OCR should not run for an embedded-text PDF")

    monkeypatch.setattr(pdf_extraction, "_ocr_page", fail_if_called)
    title, articles = pdf_extraction.extract_pdf_bylaw("embedded.pdf")

    assert title == "Titre"
    assert articles[0].article_ref == "Art. 1"


def test_sparse_pages_use_french_german_english_ocr(monkeypatch: MonkeyPatch) -> None:
    pages = [_FakePdfPage("")]
    monkeypatch.setattr(
        pdf_extraction, "PdfReader", lambda _path: types.SimpleNamespace(pages=pages)
    )
    monkeypatch.setitem(
        sys.modules, "pypdfium2", types.SimpleNamespace(PdfDocument=_FakeRenderedDocument)
    )
    monkeypatch.setitem(
        sys.modules,
        "pytesseract",
        types.SimpleNamespace(
            image_to_string=lambda image, *, lang: (
                f"Titre OCR\nArt. 1 Texte OCR suffisamment long pour constituer une "
                f"disposition juridique complète et exploitable. ({image}, {lang})"
            )
        ),
    )

    title, articles = pdf_extraction.extract_pdf_bylaw("scanned.pdf")

    assert title == "Titre OCR"
    assert articles[0].article_ref == "Art. 1"
    assert "fra+deu+eng" in articles[0].text
