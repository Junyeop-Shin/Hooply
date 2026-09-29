"""채팅 모델 만들기 (docs/07 D1 · D2).

LangChain 의 `init_chat_model("<공급자>:<모델명>")` 한 곳에서만 모델을 만들고, 체인은 `with_structured_output` 만 쓴다.
공급자 전용 기능을 쓰지 않으므로 LLM_MODEL · LLM_API_KEY · 공급자 패키지만 바꾸면 Gemini 가 아닌 모델로도 그대로 돈다.

키가 없거나 LLM_ENABLED=false 면 None 을 돌려주고, 호출하는 쪽은 규칙 문장(폴백)을 쓴다 (NFR-02).
"""

import os
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable
from pydantic import BaseModel

from app.core.config import get_settings

# LLM_API_KEY 를 비웠을 때 볼 공급자 기본 환경 변수
PROVIDER_KEY_ENV = {
    "google_genai": "GOOGLE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
TEMPERATURE = 0.3
MIN_PROVIDER_DEADLINE = 10.0  # Gemini 는 이보다 짧은 요청 마감을 400 으로 거절한다. 실제 대기 상한은 llm_guard 가 따로 건다


def provider_of(model: str) -> str:
    return model.split(":", 1)[0] if ":" in model else ""


def _usable(model: str) -> bool:
    s = get_settings()
    if not s.llm_enabled or not model:
        return False
    env = PROVIDER_KEY_ENV.get(provider_of(model))
    return bool(s.llm_api_key or (env and os.environ.get(env)))


def available() -> bool:
    return _usable(get_settings().llm_model)


@lru_cache(maxsize=4)
def _build(model: str, api_key: str, timeout: float) -> BaseChatModel:
    from langchain.chat_models import init_chat_model

    kwargs: dict = {"temperature": TEMPERATURE, "timeout": timeout, "max_retries": 0}  # 재시도 대신 폴백
    if api_key:
        kwargs["api_key"] = api_key
    return init_chat_model(model, **kwargs)


def chat_model(*, fallback: bool = False) -> BaseChatModel | None:
    """기본 모델, 또는 fallback=True 면 예비 모델(LLM_FALLBACK_MODEL, 비었으면 기본 모델)."""
    s = get_settings()
    name = model_name(fallback=fallback)
    if not _usable(name):
        return None
    return _build(name, s.llm_api_key, max(s.llm_timeout_seconds, MIN_PROVIDER_DEADLINE))


def structured(schema: type[BaseModel], *, fallback: bool = False) -> Runnable | None:
    """스키마대로 답하는 Runnable. 모델을 쓸 수 없으면 None. 테스트는 이 함수를 가짜 Runnable 로 바꿔 끼운다."""
    m = chat_model(fallback=fallback)
    return m.with_structured_output(schema) if m is not None else None


def model_name(*, fallback: bool = False) -> str:
    s = get_settings()
    return (s.llm_fallback_model or s.llm_model) if fallback else s.llm_model
