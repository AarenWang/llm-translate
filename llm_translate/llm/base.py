from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from ..prompt import Prompt


class LLMProvider(Protocol):
    name: str
    model_name: str

    def translate(self, prompt: Prompt) -> str:
        ...


@dataclass
class MockLLMProvider:
    model_name: str = "mock-translation-model"
    name: str = "mock"

    def translate(self, prompt: Prompt) -> str:
        text = prompt.user.split("Text to translate:", 1)[-1].strip()
        for source, target in self._glossary_pairs(prompt.user):
            text = re.sub(rf"\b{re.escape(source)}\b", target, text)
        return text

    def _glossary_pairs(self, user_prompt: str) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        for line in user_prompt.splitlines():
            if not line.startswith("- ") or "=>" not in line:
                continue
            source, target = line[2:].split("=>", 1)
            pairs.append((source.strip(), target.strip()))
        return pairs


@dataclass
class LiteLLMProvider:
    model_name: str
    api_base: str | None = None
    api_key: str | None = None
    name: str = "litellm"

    def translate(self, prompt: Prompt) -> str:
        try:
            from litellm import completion
        except ImportError as exc:
            raise RuntimeError(
                "LiteLLM is not installed. Install project dependencies or use --provider mock."
            ) from exc

        kwargs = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
        }
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        response = completion(**kwargs)
        return response.choices[0].message.content or ""


@dataclass
class DeepSeekProvider(LiteLLMProvider):
    name: str = "deepseek"


def provider_from_name(
    name: str,
    model_name: str | None = None,
    api_base: str | None = None,
    api_key: str | None = None,
) -> LLMProvider:
    if name == "mock":
        return MockLLMProvider()
    if name == "litellm":
        if not model_name:
            raise ValueError("--model is required when --provider litellm")
        return LiteLLMProvider(model_name=model_name, api_base=api_base, api_key=api_key)
    if name == "deepseek":
        resolved_model = model_name or "deepseek/deepseek-chat"
        return DeepSeekProvider(model_name=resolved_model, api_base=api_base, api_key=api_key)
    raise ValueError(f"unknown provider: {name}")
