"""Claude provider (official ``anthropic`` SDK, structured outputs)."""

import base64
import logging
from typing import TYPE_CHECKING, Any

from app.domain.schema import InvoiceExtraction
from app.llm.base import ExtractionRequest, ProviderError
from app.llm.prompt import SYSTEM_PROMPT, LLMInvoice, build_user_prompt, to_extraction
from app.ocr.base import IMAGE_TYPES, PDF_TYPES

if TYPE_CHECKING:
    import anthropic

log = logging.getLogger(__name__)

MAX_INLINE_BYTES = 30 * 1024 * 1024
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str | None,
        model: str = "claude-opus-5-5",
        timeout: float = 60.0,
        client: "anthropic.Anthropic | None" = None,
    ) -> None:
        if client is None:
            import anthropic

            if not api_key:
                raise ProviderError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
            client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self.client = client
        self.model = model

    def _content(self, request: ExtractionRequest) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        if len(request.data) <= MAX_INLINE_BYTES:
            data = base64.standard_b64encode(request.data).decode()
            if request.content_type in PDF_TYPES:
                blocks.append(
                    {
                        "type": "document",
                        "source": {"type": "base64", "media_type": "application/pdf", "data": data},
                    }
                )
            elif request.content_type in IMAGE_TYPES:
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": request.content_type,
                            "data": data,
                        },
                    }
                )
        blocks.append({"type": "text", "text": build_user_prompt(request)})
        return blocks

    def extract(self, request: ExtractionRequest) -> InvoiceExtraction:
        try:
            response = self.client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": self._content(request)}],  # type: ignore[typeddict-item]
                output_format=LLMInvoice,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except Exception as exc:
            raise ProviderError(f"Anthropic request failed: {exc}") from exc
        if response.stop_reason == "refusal":
            raise ProviderError("Claude declined to process this document")
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderError(
                f"Claude returned no structured output (stop={response.stop_reason})"
            )
        log.info(
            "anthropic extraction",
            extra={"model": response.model, "request_id": response._request_id},
        )
        return to_extraction(parsed)
