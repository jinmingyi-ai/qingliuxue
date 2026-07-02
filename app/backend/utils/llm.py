import os
from dataclasses import dataclass
from typing import Any
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # Keep deterministic tests usable before dependencies are installed.
    def load_dotenv(*_: Any, **__: Any) -> bool:
        return False

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - exercised only in minimal local envs.
    OpenAI = None

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)

DEFAULT_XAI_MODEL = "grok-4.3"


@dataclass
class ChatResponse:
    content: str
    citations: list[Any] | None = None
    tool_usage: Any | None = None
    raw_response: Any | None = None


class OpenAICompatibleChat:
    """Small invoke-compatible wrapper for xAI/OpenAI chat APIs."""

    def __init__(self, api_key: str, base_url: str, model: str, temperature: float):
        if OpenAI is None:
            raise ValueError("openai 依赖未安装，请先执行 python -m pip install -r requirements.txt")
        timeout = float(os.getenv("XAI_TIMEOUT_SECONDS", "60"))
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=0)
        self.model = model
        self.temperature = temperature

    def invoke(
        self,
        messages: list[dict[str, str]],
        web_search: bool = False,
        allowed_domains: list[str] | None = None,
    ) -> ChatResponse:
        if web_search:
            return self._invoke_responses_with_web_search(messages, allowed_domains=allowed_domains)
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
        )
        content = response.choices[0].message.content or ""
        return ChatResponse(content=content.strip())

    def _invoke_responses_with_web_search(
        self,
        messages: list[dict[str, str]],
        allowed_domains: list[str] | None = None,
    ) -> ChatResponse:
        tool: dict[str, Any] = {"type": "web_search"}
        if allowed_domains:
            tool["filters"] = {"allowed_domains": allowed_domains[:5]}
        response = self.client.responses.create(
            model=self.model,
            input=messages,
            tools=[tool],
            temperature=self.temperature,
        )
        content = _response_text(response)
        return ChatResponse(
            content=content.strip(),
            citations=getattr(response, "citations", None),
            tool_usage=getattr(response, "server_side_tool_usage", None),
            raw_response=response,
        )


def get_llm(model: str | None = None, temperature: float = 0.7):
    """
    获取 LLM 实例
    xAI Grok 的接口和 OpenAI 兼容
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY 未设置：本地请在项目根目录 .env 配置；Railway 请在 Variables 中配置 XAI_API_KEY")

    return OpenAICompatibleChat(
        api_key=api_key,
        base_url=os.getenv("XAI_BASE_URL", "https://api.x.ai/v1"),
        model=current_model(model),
        temperature=temperature,
    )


def current_model(model: str | None = None) -> str:
    return model or os.getenv("XAI_MODEL", DEFAULT_XAI_MODEL)


def _response_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", None)
            if text:
                chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    return str(response)
