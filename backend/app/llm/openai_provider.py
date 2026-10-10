"""OpenAI provider (official ``openai`` SDK, structured outputs over OCR text)."""

from typing import TYPE_CHECKING

from app.domain.schema import InvoiceExtraction
from app.llm.base import ExtractionRequest, ProviderError
from app.llm.prompt import SYSTEM_PROMPT, LLMInvoice, build_user_prompt, to_extraction

if TYPE_CHECKING:
    import openai


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        api_key: str | None,
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
        client: "openai.OpenAI | None" = None,
    ) -> None:
        if client is None:
            import openai

            if not api_key:
                raise ProviderError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            client = openai.OpenAI(api_key=api_key, timeout=timeout)
        self.client = client
        self.model = model

    def extract(self, request: ExtractionRequest) -> InvoiceExtraction:
        if not request.ocr.pages:
            raise ProviderError("OpenAI provider needs OCR text; none could be extracted")
        try:
            completion = self.client.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(request)},
                ],
                response_format=LLMInvoice,
            )
        except Exception as exc:
            raise ProviderError(f"OpenAI request failed: {exc}") from exc
        message = completion.choices[0].message
        if message.parsed is None:
            raise ProviderError(f"OpenAI returned no structured output: {message.refusal}")
        return to_extraction(message.parsed)
