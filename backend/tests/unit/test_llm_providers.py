from dataclasses import dataclass
from typing import Any

import pytest

from app.core.config import Settings
from app.domain.fewshot import FewShotExample, FieldFix
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import ExtractionRequest, ProviderError
from app.llm.factory import build_provider
from app.llm.mock import MockProvider
from app.llm.openai_provider import OpenAIProvider
from app.llm.prompt import (
    LLMDate,
    LLMInvoice,
    LLMLineItem,
    LLMNumber,
    LLMString,
    build_user_prompt,
    to_extraction,
)
from app.ocr.base import OcrPage, OcrResult


def s(v: str | None, c: float = 0.9) -> LLMString:
    return LLMString(value=v, confidence=c, source_page=1)


def n(v: float | None, c: float = 0.9) -> LLMNumber:
    return LLMNumber(value=v, confidence=c, source_page=1)


def llm_invoice() -> LLMInvoice:
    return LLMInvoice(
        vendor_name=s(" ACME Oy "),
        vendor_vat_id=s("FI12345671"),
        invoice_number=s("INV-1"),
        invoice_date=LLMDate(value="2026-03-01", confidence=1.4, source_page=1),
        due_date=LLMDate(value="not a date", confidence=0.9, source_page=0),
        currency=s("EUR"),
        line_items=[
            LLMLineItem(
                description=s("Widget"),
                quantity=n(2),
                unit_price=n(50),
                vat_rate=n(24),
                line_total=n(100),
            )
        ],
        subtotal=n(100),
        vat_total=n(24),
        total=n(124),
        iban=s(""),
        payment_reference=s(None, -0.2),
    )


def request(pages: bool = True, content_type: str = "application/pdf") -> ExtractionRequest:
    ocr = OcrResult([OcrPage(1, 1, 1, "Invoice text")] if pages else [], "pdf_text")
    examples = [
        FewShotExample(
            document_id="d", fixes=[FieldFix(field="iban", extracted="X", corrected="Y")]
        )
    ]
    return ExtractionRequest("a.pdf", b"%PDF-1.4", content_type, "0" * 64, ocr, examples)


def test_to_extraction_normalizes() -> None:
    inv = to_extraction(llm_invoice())
    assert inv.vendor_name.value == "ACME Oy"
    assert inv.invoice_date.confidence == 1.0
    assert inv.due_date.value is None
    assert inv.due_date.confidence == 0.0
    assert inv.due_date.source_page is None
    assert inv.iban.value is None
    assert inv.payment_reference.confidence == 0.0
    assert inv.line_items[0].line_total.value == 100


def test_build_user_prompt() -> None:
    prompt = build_user_prompt(request())
    assert "--- page 1 ---" in prompt
    assert "iban: extracted 'X' -> correct 'Y'" in prompt
    assert "OCR text" not in build_user_prompt(request(pages=False))


@dataclass
class FakeAnthropicResponse:
    parsed_output: LLMInvoice | None
    stop_reason: str = "end_turn"
    model: str = "claude-opus-5-5"
    _request_id: str = "req_1"


class FakeAnthropic:
    def __init__(self, response: FakeAnthropicResponse | Exception) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}
        self.beta = self
        self.messages = self

    def parse(self, **kwargs: Any) -> FakeAnthropicResponse:
        self.kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_anthropic_provider_sends_document_and_parses() -> None:
    fake = FakeAnthropic(FakeAnthropicResponse(llm_invoice()))
    provider = AnthropicProvider(None, client=fake)  # type: ignore[arg-type]
    inv = provider.extract(request())
    assert inv.total.value == 124
    content = fake.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "document"
    assert content[-1]["type"] == "text"
    assert fake.kwargs["output_format"] is LLMInvoice
    assert fake.kwargs["fallbacks"] == "default"
    assert fake.kwargs["model"] == "claude-opus-5-5"


def test_anthropic_provider_sends_images() -> None:
    fake = FakeAnthropic(FakeAnthropicResponse(llm_invoice()))
    AnthropicProvider(None, client=fake).extract(request(content_type="image/png"))  # type: ignore[arg-type]
    assert fake.kwargs["messages"][0]["content"][0]["type"] == "image"


@pytest.mark.parametrize(
    "response",
    [
        FakeAnthropicResponse(None, stop_reason="refusal"),
        FakeAnthropicResponse(None, stop_reason="max_tokens"),
        RuntimeError("boom"),
    ],
)
def test_anthropic_provider_errors(response: FakeAnthropicResponse | Exception) -> None:
    with pytest.raises(ProviderError):
        AnthropicProvider(None, client=FakeAnthropic(response)).extract(request())  # type: ignore[arg-type]


def test_anthropic_requires_key() -> None:
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        AnthropicProvider(None)
    assert AnthropicProvider("sk-test").model == "claude-opus-5-5"


@dataclass
class FakeMessage:
    parsed: LLMInvoice | None
    refusal: str | None = None


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeCompletion:
    choices: list[FakeChoice]


class FakeOpenAI:
    def __init__(self, response: FakeCompletion | Exception) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}
        self.chat = self
        self.completions = self

    def parse(self, **kwargs: Any) -> FakeCompletion:
        self.kwargs = kwargs
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_openai_provider() -> None:
    fake = FakeOpenAI(FakeCompletion([FakeChoice(FakeMessage(llm_invoice()))]))
    inv = OpenAIProvider(None, client=fake).extract(request())  # type: ignore[arg-type]
    assert inv.currency.value == "EUR"
    assert fake.kwargs["response_format"] is LLMInvoice


@pytest.mark.parametrize(
    "response",
    [FakeCompletion([FakeChoice(FakeMessage(None, "no"))]), RuntimeError("boom")],
)
def test_openai_provider_errors(response: FakeCompletion | Exception) -> None:
    with pytest.raises(ProviderError):
        OpenAIProvider(None, client=FakeOpenAI(response)).extract(request())  # type: ignore[arg-type]


def test_openai_needs_ocr_and_key() -> None:
    fake = FakeOpenAI(RuntimeError("unused"))
    with pytest.raises(ProviderError, match="OCR"):
        OpenAIProvider(None, client=fake).extract(request(pages=False))  # type: ignore[arg-type]
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        OpenAIProvider(None)
    assert OpenAIProvider("sk-test").model == "gpt-4o-mini"


def test_factory() -> None:
    assert isinstance(build_provider(Settings(llm_provider="mock")), MockProvider)
    assert isinstance(
        build_provider(Settings(llm_provider="anthropic", anthropic_api_key="k")), AnthropicProvider
    )
    assert isinstance(
        build_provider(Settings(llm_provider="openai", openai_api_key="k")), OpenAIProvider
    )
