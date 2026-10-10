import json
from pathlib import Path

from app.domain.rules import run_rules
from app.domain.validators import is_valid_iban, is_valid_vat_id
from app.llm.truth import load_truth, truth_to_extraction
from scripts.generate_invoices import fmt_amount, generate


def test_fmt_amount_styles() -> None:
    assert fmt_amount(1234.5, "fi") == "1 234,50"
    assert fmt_amount(1234.5, "de") == "1.234,50"
    assert fmt_amount(1234.5, "en") == "1,234.50"


def test_generated_fixtures_are_consistent(fixture_pdfs: list[Path]) -> None:
    assert len(fixture_pdfs) == 10
    edge_cases: set[str] = set()
    templates: set[str] = set()
    currencies: set[str] = set()
    for pdf in fixture_pdfs:
        truth = load_truth(pdf.with_name(pdf.stem + ".truth.json"))
        inv = truth_to_extraction(truth)
        edge_cases.update(truth["edge_cases"])
        templates.add(truth["template"])
        currencies.add(str(inv.currency.value))
        assert is_valid_iban(str(inv.iban.value))
        assert is_valid_vat_id(str(inv.vendor_vat_id.value))
        codes = {i.code for i in run_rules(inv)}
        if "totals_mismatch" in truth["edge_cases"]:
            assert codes == {"totals_mismatch"}
        else:
            assert codes == set(), pdf.name
        for _, fld in inv.iter_fields():
            if fld.value is not None:
                assert fld.bbox is not None
                assert fld.source_page is not None
    assert edge_cases == {"totals_mismatch", "missing_due_date", "rotated_scan", "multi_page"}
    assert templates == {"classic", "modern", "minimal"}
    assert currencies == {"EUR", "SEK", "USD"}


def test_generate_is_deterministic(tmp_path: Path) -> None:
    a = generate(3, tmp_path / "a", seed=7)
    b = generate(3, tmp_path / "b", seed=7)
    assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]
    truth = json.loads(a[0].with_name(a[0].stem + ".truth.json").read_text())
    assert truth["file"] == a[0].name
