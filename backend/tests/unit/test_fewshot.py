from datetime import UTC, datetime, timedelta

from app.domain.fewshot import (
    Correction,
    build_fewshot_examples,
    known_fixes,
    render_fewshot_prompt,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def corr(doc: str, path: str, old: str | None, new: str | None, minutes: int) -> Correction:
    return Correction(doc, path, old, new, T0 + timedelta(minutes=minutes))


def test_groups_by_document_newest_first() -> None:
    examples = build_fewshot_examples(
        [
            corr("a", "iban", "FI00", "FI21", 1),
            corr("b", "invoice_number", "1NV-1", "INV-1", 5),
            corr("a", "currency", "EUP", "EUR", 2),
        ]
    )
    assert [e.document_id for e in examples] == ["b", "a"]
    assert [f.field for f in examples[1].fixes] == ["currency", "iban"]


def test_repeated_corrections_collapse_to_original_and_final() -> None:
    examples = build_fewshot_examples(
        [
            corr("a", "iban", "WRONG", "ALMOST", 1),
            corr("a", "iban", "ALMOST", "RIGHT", 2),
        ]
    )
    fix = examples[0].fixes[0]
    assert (fix.extracted, fix.corrected) == ("WRONG", "RIGHT")


def test_noop_corrections_and_limits() -> None:
    corrections = [corr("same", "iban", "X", "X", 0)] + [
        corr(f"d{i}", "currency", "EUP", "EUR", i) for i in range(1, 6)
    ]
    examples = build_fewshot_examples(corrections, max_examples=2)
    assert [e.document_id for e in examples] == ["d5", "d4"]
    assert build_fewshot_examples([corr("same", "iban", "X", "X", 0)]) == []


def test_known_fixes_and_prompt() -> None:
    examples = build_fewshot_examples(
        [corr("old", "iban", "A", "B", 1), corr("new", "iban", "C", "D", 2)]
    )
    assert known_fixes(examples)["iban"].corrected == "D"
    prompt = render_fewshot_prompt(examples)
    assert "Example 1" in prompt
    assert "iban: extracted 'C' -> correct 'D'" in prompt
    assert render_fewshot_prompt([]) == ""
