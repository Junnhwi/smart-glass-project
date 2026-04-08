from __future__ import annotations

from typing import Protocol, runtime_checkable

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - import failure is handled at runtime
    OpenAI = None


@runtime_checkable
class LLMProvider(Protocol):
    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Generate a grounded answer from prompts."""


class OpenAICompatibleProvider:
    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None,
        timeout_sec: float,
        temperature: float = 0.2,
        max_tokens: int = 192,
    ) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package is required for LLM generation")

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_sec,
        )

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream=False,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError("LLM response content must be a string")

        cleaned = content.strip()
        if not cleaned:
            raise ValueError("LLM returned an empty response")
        return cleaned
