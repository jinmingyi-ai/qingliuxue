import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


@dataclass
class ChatResponse:
    content: str


class OpenAICompatibleChat:
    """Small invoke-compatible wrapper for xAI/OpenAI chat APIs."""

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float):
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=20.0, max_retries=0)
        self.model = model
        self.temperature = temperature

    def invoke(self, messages: list[dict[str, str]]) -> ChatResponse:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        content = response.choices[0].message.content or ""
        return ChatResponse(content=content.strip())


def get_llm(model: str | None = None, temperature: float = 0.7):
    """
    获取 LLM 实例
    xAI Grok 的接口和 OpenAI 兼容
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY 未设置，请在 .env 文件中配置")

    return OpenAICompatibleChat(
        api_key=api_key,
        base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"),
        model=model or os.getenv("XAI_MODEL", "grok-2-latest"),
        temperature=temperature,
    )
