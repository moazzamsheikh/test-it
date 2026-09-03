"""M5 extraction tests — against a saved snapshot of the real
guichet.public.lu page (tests/fixtures/guichet_autorisation_batir.html), not
a live fetch. Live fetch behaviour is the ingestion script itself, run and
verified by hand (see DECISIONS.md) — a real government page can change at
any time, and this snapshot is what the extraction logic is actually written
against.
"""

from __future__ import annotations

from pathlib import Path

from ingestion.procedure_extraction import extract_procedure

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "guichet_autorisation_batir.html"


def test_extracts_real_title_and_date() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = extract_procedure(html)

    assert result.title == (
        "Demander une autorisation de bâtir pour toute construction, "
        "transformation ou démolition d'un bâtiment"
    )
    assert result.document_date_str == "16.06.2014"


def test_extracts_all_expected_sections_with_real_text() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = extract_procedure(html)

    headings = [s.heading for s in result.sections]
    assert headings == [
        "Personnes pouvant introduire une demande",
        "Travaux soumis à une autorisation de construire",
        "Introduction de la demande / de la déclaration",
        "Obligations",
        "Autres autorisations requises",
        "Durée de validité",
    ]
    exemption_section = result.sections[0]
    assert "6.197,34 euros" in exemption_section.text  # the real exemption threshold


def test_extracts_real_legilux_legal_references() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    result = extract_procedure(html)

    assert len(result.legal_references) == 5
    labels = {r.label for r in result.legal_references}
    assert "Loi du 19 juillet 2005" in labels
    for ref in result.legal_references:
        assert ref.url.startswith("http://legilux.public.lu/eli/")
