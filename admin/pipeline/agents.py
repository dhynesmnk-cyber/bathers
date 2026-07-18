"""Harvester / Architect / Gatekeeper agent calls (TRD.md §7).

Prompts are loaded from PROMPTS/*.md at call time, never embedded here.
Two retry tiers, per UX.md §1.5:

- Transport tier: RateLimitError / 5xx / connection errors get one retry,
  then the call fails cleanly (raises AgentError).
- Content tier: output that fails `validate()` (malformed JSON, missing
  frontmatter, etc.) gets one re-ask with the validation error appended to
  the prompt, then raises MalformedOutput carrying the raw text so the
  caller can save it to temp_data/failed/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TypeVar

import anthropic

from admin.config import ANTHROPIC_API_KEY, PROMPTS_DIR

LogFn = Callable[[str, str], None]  # (text, level) -> None
T = TypeVar("T")


class AgentError(Exception):
    """Anthropic API call failed after the one transport-level retry."""


class MalformedOutput(Exception):
    """Agent output failed validation after the one content-level re-ask."""

    def __init__(self, raw_text: str, error: str):
        self.raw_text = raw_text
        self.error = error
        super().__init__(f"malformed output after retry: {error}")


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __iadd__(self, other: "Usage") -> "Usage":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        return self


def load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise AgentError("ANTHROPIC_API_KEY is not set in .env")
    # max_retries=0: we handle the single UX.md-mandated retry ourselves so
    # the log pane sees it, rather than letting the SDK retry silently.
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, max_retries=0)


def _raw_call(model: str, system: str, user_content: str, max_tokens: int) -> tuple[str, Usage]:
    client = _client()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_content}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    usage = Usage(response.usage.input_tokens, response.usage.output_tokens)
    return text, usage


def _call_with_transport_retry(
    model: str, system: str, user_content: str, max_tokens: int, log: LogFn
) -> tuple[str, Usage]:
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            return _raw_call(model, system, user_content, max_tokens)
        except anthropic.RateLimitError as exc:
            retry_after = exc.response.headers.get("retry-after", "unknown") if exc.response else "unknown"
            log(f"{model}: rate limited (retry-after {retry_after}s)", "error")
            last_exc = exc
        except anthropic.APIStatusError as exc:
            if exc.status_code < 500:
                raise AgentError(f"{model}: {exc.status_code} {exc.message}") from exc
            log(f"{model}: server error {exc.status_code}", "error")
            last_exc = exc
        except anthropic.APIConnectionError as exc:
            log(f"{model}: connection error — {exc}", "error")
            last_exc = exc
        if attempt == 1:
            log(f"{model}: retrying once", "warn")
    raise AgentError(f"{model}: failed after retry — {last_exc}") from last_exc


def call_agent(
    model: str,
    system: str,
    user_content: str,
    max_tokens: int,
    validate: Callable[[str], T],
    log: LogFn,
) -> tuple[T, Usage]:
    """Run one agent turn with both retry tiers. `validate` must raise
    ValueError on malformed output and return the parsed result on success."""
    total_usage = Usage()
    current_content = user_content
    last_text = ""
    last_error = ""

    for content_attempt in (1, 2):
        text, usage = _call_with_transport_retry(model, system, current_content, max_tokens, log)
        total_usage += usage
        last_text = text
        try:
            parsed = validate(text)
            log(f"{model}: ok — {usage.input_tokens} in / {usage.output_tokens} out tokens", "info")
            return parsed, total_usage
        except ValueError as exc:
            last_error = str(exc)
            if content_attempt == 1:
                log(f"{model}: malformed output — {last_error} — re-asking once", "error")
                current_content = (
                    f"{user_content}\n\n"
                    f"Your previous response failed validation: {last_error}\n"
                    "Return corrected output only — no commentary."
                )
            else:
                log(f"{model}: malformed output after retry — {last_error}", "error")

    raise MalformedOutput(raw_text=last_text, error=last_error)
