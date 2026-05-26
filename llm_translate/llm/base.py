from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol

from ..prompt import Prompt


class LLMProvider(Protocol):
    name: str
    model_name: str

    def translate(self, prompt: Prompt) -> str:
        """Translate a single prompt."""
        ...

    def translate_batch(self, prompts: list[Prompt]) -> list[str]:
        """Translate multiple prompts efficiently (default implementation calls translate()).

        Args:
            prompts: List of prompts to translate

        Returns:
            List of translated texts (same order as input)
        """
        return [self.translate(prompt) for prompt in prompts]


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


@dataclass
class ChatGPTProvider(LiteLLMProvider):
    """ChatGPT 订阅 API 提供者，使用 OAuth 设备代码流程认证

    首次使用时会自动引导完成 OAuth 认证流程，token 会保存在本地。
    litellm 已经完成认证并本地存了认证 token，可直接使用。
    """
    name: str = "chatgpt"

    def translate(self, prompt: Prompt) -> str:
        try:
            from litellm import completion
        except ImportError as exc:
            raise RuntimeError(
                "LiteLLM is not installed. Install project dependencies or use --provider mock."
            ) from exc

        # 使用 Chat Completions API（会桥接到 Responses API）
        # ChatGPT 订阅不支持 max_tokens 等参数，litellm 会自动过滤这些参数
        kwargs = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
        }
        # ChatGPT 订阅使用 OAuth 认证，通常不需要 api_base 和 api_key
        # 但如果提供了这些参数，litellm 会优先使用它们而不是 OAuth 认证
        if self.api_base:
            kwargs["api_base"] = self.api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key

        try:
            response = completion(**kwargs)
            # 处理流式响应聚合的情况
            if hasattr(response, 'choices') and len(response.choices) > 0:
                message = response.choices[0].message
                if hasattr(message, 'content') and message.content:
                    return message.content
            # 如果没有 choices，可能是直接的响应对象
            if hasattr(response, 'content'):
                return response.content
            # 最后尝试转换为字符串
            return str(response)
        except Exception as e:
            # 如果 API 调用失败，提供更友好的错误信息
            raise RuntimeError(
                f"ChatGPT API 调用失败: {e}\n"
                f"提示：首次使用需要完成 OAuth 认证流程。\n"
                f"请确保已安装最新版本的 litellm: pip install --upgrade litellm"
            ) from e


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
    if name == "chatgpt":
        # ChatGPT 订阅默认模型
        resolved_model = model_name or "chatgpt/gpt-5.4"
        return ChatGPTProvider(model_name=resolved_model, api_base=api_base, api_key=api_key)
    raise ValueError(f"unknown provider: {name}")
