"""LLM 가드레일 (docs/07 FR-48 ~ FR-50, 명세 9절, 수용 테스트 T7 ~ T12).

CI 에는 키가 없다 (NFR-06). 성공 경로는 모델 자리에 LangChain Runnable(RunnableLambda)을 끼워 고정 결과를 돌려주고,
폴백 경로는 키가 없는 실제 설정으로 확인한다.
"""

import time

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel
from sqlalchemy import func, select

from app.core import errors, ratelimit
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.llm import llm_guard as g
from app.llm import model as llm_model
from app.models import LlmResult


class Explain(BaseModel):
    summary: str
    reasons: list[str]


class Messages(BaseModel):
    class Item(BaseModel):
        player: str
        message: str

    messages: list[Item]


@pytest.fixture
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture
def fake_model(monkeypatch):
    """모델 자리에 고정 결과를 돌려주는 Runnable 을 끼운다. calls 로 실제 호출 횟수를 센다."""
    state = {"reply": None, "calls": 0, "sleep": 0.0}

    def respond(_messages):
        state["calls"] += 1
        if state["sleep"]:
            time.sleep(state["sleep"])
        r = state["reply"]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(llm_model, "structured", lambda schema: RunnableLambda(respond))
    return state


def _aliases() -> g.Aliases:
    a = g.Aliases()
    for pid, name in [(11, "허재"), (12, "강동희"), (13, "서장훈")]:
        a.player(pid, name)
    for i in range(4, 11):  # P4 … P10
        a.player(100 + i, f"선수{i}")
    a.squad(1, "블랙")
    a.squad(2, "화이트")
    return a


def _call(**over) -> g.ChainCall:
    base = {
        "chain": "A", "schema": Explain, "messages": [("human", "x")], "aliases": _aliases(),
        "payload": {"squad_avg_skill": {"A": 0.3, "B": 0.337}, "count": 6},
        "fallback": {"summary": "규칙 문장", "reasons": []}, "key_parts": {"candidate": 1, "roster": [[1, 11, "PG"]]},
    }
    base.update(over)
    return g.ChainCall(**base)


# ---------------------------------------------------------------------------
# T7 가명 복원
# ---------------------------------------------------------------------------


def test_restore_reads_whole_numbers():
    a = _aliases()
    # 조사는 실명 받침에 맞춘다 (명세 O6). 숫자로 끝나는 이름은 조사를 그대로 둔다
    assert a.restore("P1과 P10이 P3가 같은 팀") == "허재와 선수10이 서장훈이 같은 팀"
    assert a.restore("P3는 P1을 P2로") == "서장훈은 허재를 강동희로"
    assert a.restore("P1가드 역할") == "허재가드 역할"  # 뒤에 한글이 이어지면 조사가 아니다
    assert a.restore("A팀이 B보다") == "블랙팀이 화이트보다"
    assert a.restore("A와 B는") == "블랙과 화이트는"
    assert a.restore("PG 포지션 · APP") == "PG 포지션 · APP"  # 가명이 아닌 글자는 그대로


def test_unknown_alias_detected():
    assert g.unknown_aliases({"s": "P2와 P11"}, {"P1", "P2"}) == {"P11"}


# ---------------------------------------------------------------------------
# T8 숫자 검사
# ---------------------------------------------------------------------------


def test_numbers_same_value_and_terms_allowed():
    allowed = g.input_numbers({"x": 0.3, "tags": ["180cm 이상 3명"]})
    assert g.filter_numbers("차이가 30%예요.", allowed) == "차이가 30%예요."
    assert g.filter_numbers("0.30 차이예요.", allowed) == "0.30 차이예요."
    assert g.filter_numbers("3점 슛이 좋아요.", allowed) == "3점 슛이 좋아요."
    assert g.filter_numbers("1번과 5번이 있어요. 1-3-1 지역 수비예요.", allowed) is not None
    assert g.filter_numbers("180cm 이상이 3명이에요.", allowed) is not None


def test_sentence_with_unknown_number_is_dropped():
    allowed = g.input_numbers({"x": 0.3})
    out = g.filter_numbers("차이가 30%예요. 슛 성공률 0.7 이에요. 3점 슛도 좋아요.", allowed)
    assert out == "차이가 30%예요. 3점 슛도 좋아요."
    assert g.filter_numbers("0.7 이에요.", allowed) is None


def test_rounded_numbers_allowed():
    allowed = g.input_numbers({"x": 0.337})
    assert g.filter_numbers("34% 차이", allowed) is not None
    assert g.filter_numbers("0.34 차이", allowed) is not None
    assert g.filter_numbers("0.35 차이", allowed) is None


def test_alias_digits_are_not_numbers():
    assert g.filter_numbers("P7이 뛰어요.", set()) == "P7이 뛰어요."


# ---------------------------------------------------------------------------
# 실행 경로
# ---------------------------------------------------------------------------


def test_success_restores_names_and_drops_bad_sentence(db, fake_model):
    fake_model["reply"] = Explain(summary="A팀 P1이 볼을 운반해요.", reasons=["평균 차이 30%예요.", "슛 성공률 0.9 예요.", "P3가 골밑을 맡아요."])
    out = g.run(db, _call(), user_id=1)
    assert out.fallback is False and out.cached is False
    assert out.output == {"summary": "블랙팀 허재가 볼을 운반해요.", "reasons": ["평균 차이 30%예요.", "서장훈이 골밑을 맡아요."]}
    row = db.scalar(select(LlmResult))
    assert row.chain == "A" and row.fallback is False and "허재" in row.output["summary"]


def test_unknown_alias_falls_back(db, fake_model):
    fake_model["reply"] = Explain(summary="P42가 잘해요.", reasons=[])
    out = g.run(db, _call(), user_id=1)
    assert out.fallback is True and out.fail_reason == "unknown_alias" and out.output["summary"] == "규칙 문장"


def test_all_reasons_dropped_falls_back(db, fake_model):
    fake_model["reply"] = Explain(summary="", reasons=["0.9 차이", "7점 차이"])
    out = g.run(db, _call(usable=lambda o: bool(o["reasons"])), user_id=1)
    assert out.fallback is True and out.fail_reason == "unknown_number"


def test_extra_check_rejects_unknown_play(db, fake_model):
    fake_model["reply"] = Explain(summary="nope 전술", reasons=["x"])
    out = g.run(db, _call(extra_check=lambda o: "nope" not in o["summary"]), user_id=1)
    assert out.fail_reason == "unknown_alias"


# T9 누설 검사
def test_leak_in_member_message_falls_back(db, fake_model):
    fake_model["reply"] = Messages(messages=[Messages.Item(player="P1", message="P1은 등급이 높은 편이라 공을 많이 잡아요.")])
    call = _call(chain="B", schema=Messages, leak_check=True, fallback={"messages": []})
    out = g.run(db, call, user_id=1)
    assert out.fallback is True and out.fail_reason == "leak"


def test_schema_error_and_timeout_fall_back(db, fake_model, monkeypatch):
    from langchain_core.exceptions import OutputParserException

    fake_model["reply"] = OutputParserException("bad json")
    assert g.run(db, _call(key_parts={"k": 1}), user_id=1).fail_reason == "schema"
    fake_model["reply"] = {"summary": 3}  # dict 가 스키마를 어김
    assert g.run(db, _call(key_parts={"k": 2}), user_id=1).fail_reason == "schema"
    monkeypatch.setattr(get_settings(), "llm_timeout_seconds", 0.05)
    fake_model["reply"], fake_model["sleep"] = Explain(summary="늦음", reasons=[]), 0.3
    out = g.run(db, _call(key_parts={"k": 3}), user_id=1)
    assert out.fallback is True and out.fail_reason == "timeout"


def test_long_text_is_truncated(db, fake_model):
    fake_model["reply"] = Explain(summary="가" * 500, reasons=["나"])
    out = g.run(db, _call(max_chars=50), user_id=1)
    assert len(out.output["summary"]) == 50


# T10 키 없음
def test_no_key_returns_fallback_without_error(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert llm_model.available() is False and llm_model.structured(Explain) is None
    out = g.run(db, _call(), user_id=1)
    assert out.fallback is True and out.fail_reason == "disabled" and out.output["summary"] == "규칙 문장"
    assert db.scalar(select(func.count()).select_from(LlmResult)) == 0  # 키를 넣으면 바로 부르도록 남기지 않는다
    monkeypatch.setattr(get_settings(), "llm_api_key", "k")
    monkeypatch.setattr(get_settings(), "llm_enabled", False)
    assert llm_model.available() is False


# T11 캐시
def test_same_input_is_cached_and_changed_roster_calls_again(db, fake_model):
    fake_model["reply"] = Explain(summary="P1 좋아요.", reasons=["x"])
    first = g.run(db, _call(), user_id=1)
    second = g.run(db, _call(), user_id=1)
    assert fake_model["calls"] == 1 and first.cached is False and second.cached is True
    assert second.output == first.output
    # 게스트가 추가돼 명단이 바뀌면 새 키
    g.run(db, _call(key_parts={"candidate": 1, "roster": [[1, 11, "PG"], [1, 99, None]]}), user_id=1)
    assert fake_model["calls"] == 2


def test_fallback_result_is_retried_after_a_while(db, fake_model):
    fake_model["reply"] = Explain(summary="P77", reasons=[])
    assert g.run(db, _call(), user_id=1).fallback is True
    fake_model["reply"] = Explain(summary="P1 좋아요.", reasons=["x"])
    assert g.run(db, _call(), user_id=1).cached is True  # 곧바로는 다시 부르지 않는다
    row = db.scalar(select(LlmResult))
    row.created_at = row.created_at - g.RETRY_AFTER
    db.commit()
    out = g.run(db, _call(), user_id=1)
    assert out.fallback is False and fake_model["calls"] == 2


# T12 사용자당 분당 제한
def test_rate_limit_per_user(db, fake_model, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    ratelimit.reset()
    fake_model["reply"] = Explain(summary="P1 좋아요.", reasons=["x"])
    try:
        for i in range(5):
            g.run(db, _call(key_parts={"n": i}), user_id=7)
        g.run(db, _call(key_parts={"n": 0}), user_id=7)  # 캐시 적중은 세지 않는다
        with pytest.raises(errors.RateLimited):
            g.run(db, _call(key_parts={"n": 99}), user_id=7)
        g.run(db, _call(key_parts={"n": 100}), user_id=8)  # 다른 사람은 괜찮다
    finally:
        ratelimit.reset()


def test_cache_key_is_order_independent():
    assert g.cache_key("A", {"a": 1, "b": 2}) == g.cache_key("A", {"b": 2, "a": 1})
    assert g.cache_key("A", {"a": 1}) != g.cache_key("B", {"a": 1})


def test_model_factory_builds_langchain_model_from_settings(monkeypatch):
    """키만 있으면 LLM_MODEL 문자열로 LangChain 채팅 모델을 만든다 (네트워크 호출 없음). 공급자는 문자열 앞부분이 정한다."""
    monkeypatch.setattr(get_settings(), "llm_api_key", "test-key")
    monkeypatch.setattr(get_settings(), "llm_model", "google_genai:gemini-2.5-flash")
    llm_model._build.cache_clear()
    m = llm_model.chat_model()
    assert type(m).__name__ == "ChatGoogleGenerativeAI"
    assert m.temperature == llm_model.TEMPERATURE and m.max_retries == 0 and m.timeout == get_settings().llm_timeout_seconds
    assert llm_model.structured(Explain) is not None
    assert llm_model.provider_of("openai:gpt-5-mini") == "openai"
    llm_model._build.cache_clear()


def test_provider_error_reason_keeps_type_and_status(db, fake_model):
    class ClientError(Exception):
        code = 404

    fake_model["reply"] = ClientError("models/x is not found")
    out = g.run(db, _call(), user_id=1)
    assert out.fallback is True and out.fail_reason == "error:ClientError:404"
