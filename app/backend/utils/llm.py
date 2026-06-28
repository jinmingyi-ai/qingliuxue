import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI   # xAI Grok 兼容 OpenAI 接口

load_dotenv()

def get_llm(model: str = "grok-2-latest", temperature: float = 0.7):
    """
    获取 LLM 实例
    xAI Grok 的接口和 OpenAI 兼容
    """
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise ValueError("XAI_API_KEY 未设置，请在 .env 文件中配置")

    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=api_key,
        base_url="https://api.x.ai/v1",   # xAI 的官方地址
    )
    return llm