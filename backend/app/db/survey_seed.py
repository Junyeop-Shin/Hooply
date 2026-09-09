"""온보딩 설문 v1 시드 데이터 (survey-feature-spec 4절 · 설계서 8.3절 14문항).

문항·선택지는 코드가 아니라 **데이터**다 (앵커 재보정으로 배점이 바뀌기 때문). 그래서 마이그레이션
`0002` 가 이 모듈의 `seed_survey_v1(conn)` 를 불러 `survey_templates / questions / options` 에 넣는다.
테스트(conftest)도 테이블을 비운 뒤 같은 함수로 되살린다.

ORM 모델을 import 하지 않고 `sa.table()` 로 컬럼만 선언한 이유: 마이그레이션은 "그 시점의 스키마" 에
묶여야 하는데, ORM 모델은 앞으로 계속 바뀐다. 컬럼 목록을 여기 고정해 두면 모델이 바뀌어도 이
시드는 그대로 돌아간다.

`code` 는 서비스(`survey_service`) 가 문항·선택지를 찾는 열쇠이므로 바꾸면 안 된다. 문구(label)는
자유롭게 고쳐도 된다.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

templates_t = sa.table(
    "survey_templates",
    sa.column("id", sa.BigInteger),
    sa.column("version", sa.Integer),
    sa.column("name", sa.String),
    sa.column("is_active", sa.Boolean),
)
questions_t = sa.table(
    "survey_questions",
    sa.column("id", sa.BigInteger),
    sa.column("template_id", sa.BigInteger),
    sa.column("section", sa.String),
    sa.column("code", sa.String),
    sa.column("question_text", sa.Text),
    sa.column("answer_type", sa.String),
    sa.column("display_order", sa.SmallInteger),
    sa.column("prior_weight", sa.Numeric),
    sa.column("help_text", sa.Text),
    sa.column("group_label", sa.String),
)
options_t = sa.table(
    "survey_options",
    sa.column("question_id", sa.BigInteger),
    sa.column("code", sa.String),
    sa.column("option_order", sa.SmallInteger),
    sa.column("label", sa.Text),
    sa.column("score_value", sa.Numeric),
)


def _opts(*pairs: tuple[str, str], scores: list[float] | None = None) -> list[dict[str, Any]]:
    """(code, label) 목록 → 선택지 dict 목록. scores 를 주지 않으면 순서대로 0,1,2,… 균등 배점."""
    return [
        {"code": code, "label": label, "score_value": (scores[i] if scores else float(i))}
        for i, (code, label) in enumerate(pairs)
    ]


POSITIONS = [("PG", "PG (1번)"), ("SG", "SG (2번)"), ("SF", "SF (3번)"), ("PF", "PF (4번)"), ("C", "C (5번)")]
TRIO_OPTS = _opts(
    ("CAN_PREFER", "가능하고 선호함"), ("CAN_NO_PREFER", "가능하지만 선호하지 않음"), ("CANNOT", "불가"),
    scores=[1.0, 0.5, 0.0],
)

# 표시 순서대로. prior_weight 는 스펙 5절 가중치를 문항 단위로 나눈 참고값이다.
SURVEY_V1: list[dict[str, Any]] = [
    # ── 섹션 A 기본 ──
    {"section": "A", "code": "A1", "answer_type": "STEPPER", "question_text": "키가 몇 cm인가요?",
     "help_text": "골밑 적성 계산에만 쓰이고 다른 팀원에게 보이지 않아요.", "options": []},
    {"section": "A", "code": "A2", "answer_type": "ANCHOR_4", "prior_weight": 0.10,
     "question_text": "농구를 해온 기간은 얼마나 되나요?",
     "options": _opts(("LT_1Y", "1년 미만"), ("Y1_3", "1~3년"), ("Y3_7", "3~7년"), ("GT_7Y", "7년 이상"))},
    {"section": "A", "code": "A3", "answer_type": "ANCHOR_4", "prior_weight": 0.10,
     "question_text": "경험한 가장 높은 경기 수준은?",
     "options": _opts(("PE", "체육시간·친구들끼리"), ("CLUB", "동호회·아마추어"),
                      ("SCHOOL", "학교 대표·클럽팀"), ("PRO", "선수 출신"))},
    # ── 섹션 B 공격 ──
    {"section": "B", "code": "B1", "answer_type": "MULTI_CHIP", "prior_weight": 0.10,
     "question_text": "실제 경기에서 자주 쓰는 공격 옵션을 모두 고르세요",
     "help_text": "고른 개수와 조합이 공격 다재다능성과 포지션 프로파일이 돼요.",
     "options": _opts(("CATCH_SHOOT", "캐치앤슛 3점"), ("PULLUP", "풀업·미들 점퍼"),
                      ("DRIVE_FINISH", "드라이브 후 마무리"), ("PNR_HANDLER", "픽앤롤 핸들러"),
                      ("PNR_ROLL_POP", "픽앤롤 롤·팝"), ("POST_UP", "포스트업"),
                      ("OFFBALL_CUT", "오프볼 컷인"), ("PUTBACK", "공격 리바운드 풋백"),
                      scores=[1.0] * 8)},
    {"section": "B", "code": "B2", "answer_type": "ORDINAL_5", "prior_weight": 0.10,
     "question_text": "경기에서 안정적으로 넣을 수 있는 최대 거리는?",
     "options": _opts(("LAYUP", "골밑 레이업"), ("FLOATER", "페인트존 훅·플로터"), ("FT_LINE", "자유투 라인"),
                      ("THREE", "3점 라인"), ("DEEP_THREE", "3점 라인 밖"))},
    {"section": "B", "code": "B3", "answer_type": "ANCHOR_4", "prior_weight": 0.15,
     "question_text": "볼 운반과 돌파는 어느 정도인가요?",
     "options": _opts(("NO_DRIVE", "드리블 돌파를 시도하지 않음"), ("LIGHT_PRESS", "가벼운 압박은 벗겨냄"),
                      ("HALF_COURT", "하프코트 압박에서도 볼을 운반함"),
                      ("FULL_COURT", "풀코트 압박에서도 안정적으로 가져감"))},
    # ── 섹션 C 수비 ──
    {"section": "C", "code": "C1", "answer_type": "ANCHOR_4", "prior_weight": 0.075,
     "question_text": "상대가 스크린을 걸었을 때 나는",
     "options": _opts(("UNAWARE", "스크린이 뭔지 잘 모르거나 그냥 따라간다"),
                      ("CHASE", "피해서 따라가려 하지만 자주 놓친다"),
                      ("SWITCH", "스위치를 부르고 바꿔 막는다"),
                      ("READ", "상황에 따라 스위치·헤지·언더를 구분해서 쓴다"))},
    {"section": "C", "code": "C2", "answer_type": "ANCHOR_4", "prior_weight": 0.075,
     "question_text": "동료 매치업이 뚫렸을 때 나는",
     "options": _opts(("OWN_ONLY", "내 사람만 본다"),
                      ("HELP_NO_RECOVER", "헬프는 가지만 이후 내 자리로 못 돌아온다"),
                      ("HELP_RECOVER", "헬프 후 내 매치업으로 복귀한다"),
                      ("ROTATE_EARLY", "헬프 사이드까지 읽고 미리 로테이션을 돈다"))},
    # ── 섹션 D 포지션 ──
    {"section": "D", "code": "D1", "answer_type": "MULTI_CHIP",
     "question_text": "수행 가능한 포지션을 모두 고르세요",
     "options": _opts(*POSITIONS, scores=[0.0] * 5)},
    {"section": "D", "code": "D2", "answer_type": "SINGLE_CHOICE",
     "question_text": "가장 선호하는 포지션은?",
     "options": _opts(*POSITIONS, scores=[0.0] * 5)},
    {"section": "D", "code": "D3A", "answer_type": "TRIO", "group_label": "희소 자원 확인",
     "question_text": "1번(볼 운반)을 맡을 수 있나요?",
     "help_text": "1번·5번은 팀당 최소 1명이 필요해서 따로 여쭤봐요.", "options": TRIO_OPTS},
    {"section": "D", "code": "D3B", "answer_type": "TRIO", "group_label": "희소 자원 확인",
     "question_text": "5번(골밑)을 맡을 수 있나요?", "options": TRIO_OPTS},
    # ── 섹션 E 성향·상대평가 ──
    {"section": "E", "code": "E1", "answer_type": "ANCHOR_4",
     "question_text": "플레이 성향은 어느 쪽에 가깝나요?",
     "help_text": "온볼 = 내가 만들어감, 오프볼 = 움직여서 받음",
     "options": _opts(("ONBALL", "온볼 — 내가 볼을 잡고 만들어간다"), ("MOSTLY_ONBALL", "온볼에 가깝다"),
                      ("MOSTLY_OFFBALL", "오프볼에 가깝다"), ("OFFBALL", "오프볼 — 움직여서 받는다"))},
    {"section": "E", "code": "E2", "answer_type": "ANCHOR_4",
     "question_text": "체력은 어느 정도인가요?",
     "options": _opts(("Q1", "1쿼터도 벅참"), ("Q2", "2쿼터"), ("Q3_4", "3~4쿼터"),
                      ("FULL", "계속 뛰어도 페이스 유지"))},
    {"section": "E", "code": "E3", "answer_type": "ORDINAL_5", "prior_weight": 0.30,
     "question_text": "이 동호회에서 본인의 실력 위치는?",
     "help_text": "절대 점수가 아니라 클럽 안에서의 위치예요. 가장 중요한 문항이에요.",
     "options": _opts(("TOP10", "상위 10%"), ("TOP30", "상위 30%"), ("MID", "중간"),
                      ("BOT30", "하위 30%"), ("BOT10", "하위 10%"), scores=[4, 3, 2, 1, 0])},
]


# ---------------------------------------------------------------------------
# v2 — 사용자 피드백 반영 (2026-09-08)
#   · 키(A1) 삭제: 가입 시 받는 users.height_cm 을 쓴다
#   · A3 경기 수준 5단계로 세분화 (ORDINAL_5)
#   · D2 삭제, D1 을 "선호하는 순서대로" 고르는 순서 있는 다중선택으로 (선택 순서 = preference_rank)
#   · E1 성향·E2 체력 문구를 구체적·통일된 형식으로
#   · E3(동호회 내 상대 위치) 설문에서 제거 → 팀 가입 후 팀별로 묻는다 (player_profiles.self_rank_level)
# ---------------------------------------------------------------------------

SURVEY_V2: list[dict[str, Any]] = [
    # ── 섹션 A 기본 ──
    {"section": "A", "code": "A2", "answer_type": "ANCHOR_4", "prior_weight": 0.10,
     "question_text": "농구를 해온 기간은 얼마나 되나요?",
     "options": _opts(("LT_1Y", "1년 미만"), ("Y1_3", "1~3년"), ("Y3_7", "3~7년"), ("GT_7Y", "7년 이상"))},
    {"section": "A", "code": "A3", "answer_type": "ORDINAL_5", "prior_weight": 0.10,
     "question_text": "경험한 가장 높은 경기 수준은?",
     "options": _opts(("PE", "체육시간"), ("STREET", "동네 야외 농구장"), ("CLUB", "동호회 혹은 동아리"),
                      ("AMATEUR", "아마추어 대회"), ("PRO", "선수 출신"))},
    # ── 섹션 B 공격 ──
    {"section": "B", "code": "B1", "answer_type": "MULTI_CHIP", "prior_weight": 0.10,
     "question_text": "실제 경기에서 자주 쓰는 공격 옵션을 모두 고르세요",
     "help_text": "고른 개수와 조합이 공격 다재다능성과 포지션 프로파일이 돼요.",
     "options": _opts(("CATCH_SHOOT", "캐치앤슛 3점"), ("PULLUP", "풀업·미들 점퍼"),
                      ("DRIVE_FINISH", "드라이브 후 마무리"), ("PNR_HANDLER", "픽앤롤 핸들러"),
                      ("PNR_ROLL_POP", "픽앤롤 롤·팝"), ("POST_UP", "포스트업"),
                      ("OFFBALL_CUT", "오프볼 컷인"), ("PUTBACK", "공격 리바운드 풋백"),
                      scores=[1.0] * 8)},
    {"section": "B", "code": "B2", "answer_type": "ORDINAL_5", "prior_weight": 0.10,
     "question_text": "경기에서 안정적으로 넣을 수 있는 최대 거리는?",
     "options": _opts(("LAYUP", "골밑 레이업"), ("FLOATER", "페인트존 훅·플로터"), ("FT_LINE", "자유투 라인"),
                      ("THREE", "3점 라인"), ("DEEP_THREE", "3점 라인 밖"))},
    {"section": "B", "code": "B3", "answer_type": "ANCHOR_4", "prior_weight": 0.15,
     "question_text": "볼 운반과 돌파는 어느 정도인가요?",
     "options": _opts(("NO_DRIVE", "드리블 돌파를 시도하지 않음"), ("LIGHT_PRESS", "가벼운 압박은 벗겨냄"),
                      ("HALF_COURT", "하프코트 압박에서도 볼을 운반함"),
                      ("FULL_COURT", "풀코트 압박에서도 안정적으로 가져감"))},
    # ── 섹션 C 수비 ──
    {"section": "C", "code": "C1", "answer_type": "ANCHOR_4", "prior_weight": 0.075,
     "question_text": "상대가 스크린을 걸었을 때 나는",
     "options": _opts(("UNAWARE", "스크린이 뭔지 잘 모르거나 그냥 따라간다"),
                      ("CHASE", "피해서 따라가려 하지만 자주 놓친다"),
                      ("SWITCH", "스위치를 부르고 바꿔 막는다"),
                      ("READ", "상황에 따라 스위치·헤지·언더를 구분해서 쓴다"))},
    {"section": "C", "code": "C2", "answer_type": "ANCHOR_4", "prior_weight": 0.075,
     "question_text": "동료 매치업이 뚫렸을 때 나는",
     "options": _opts(("OWN_ONLY", "내 사람만 본다"),
                      ("HELP_NO_RECOVER", "헬프는 가지만 이후 내 자리로 못 돌아온다"),
                      ("HELP_RECOVER", "헬프 후 내 매치업으로 복귀한다"),
                      ("ROTATE_EARLY", "헬프 사이드까지 읽고 미리 로테이션을 돈다"))},
    # ── 섹션 D 포지션 ──
    {"section": "D", "code": "D1", "answer_type": "MULTI_CHIP",
     "question_text": "수행 가능한 포지션을 선호하는 순서대로 고르세요",
     "help_text": "먼저 고른 포지션이 가장 선호하는 포지션이 돼요. 나중에 프로필에서 바꿀 수 있어요.",
     "options": _opts(*POSITIONS, scores=[0.0] * 5)},
    {"section": "D", "code": "D3A", "answer_type": "TRIO", "group_label": "희소 자원 확인",
     "question_text": "1번(볼 운반)을 맡을 수 있나요?",
     "help_text": "1번·5번은 팀당 최소 1명이 필요해서 따로 여쭤봐요.", "options": TRIO_OPTS},
    {"section": "D", "code": "D3B", "answer_type": "TRIO", "group_label": "희소 자원 확인",
     "question_text": "5번(골밑)을 맡을 수 있나요?", "options": TRIO_OPTS},
    # ── 섹션 E 성향 ──
    {"section": "E", "code": "E1", "answer_type": "ANCHOR_4",
     "question_text": "경기 중 공격에는 주로 어떻게 참여하나요?",
     "options": _opts(("ONBALL", "내가 공을 잡고 드리블·패스로 공격을 만들어간다"),
                      ("MOSTLY_ONBALL", "공을 자주 잡지만, 동료가 만들어 준 기회도 많이 쓴다"),
                      ("MOSTLY_OFFBALL", "공 없이 움직이다 패스를 받아 슛이나 돌파로 마무리한다"),
                      ("OFFBALL", "거의 공 없이 움직이며, 받으면 바로 던지거나 마무리한다"))},
    {"section": "E", "code": "E2", "answer_type": "ANCHOR_4",
     "question_text": "체력은 어느 정도인가요?",
     "options": _opts(("Q1", "1쿼터를 뛰면 힘들다"), ("Q2", "2쿼터까지는 페이스를 유지한다"),
                      ("Q3_4", "3~4쿼터까지 페이스를 유지한다"), ("FULL", "경기 내내 페이스를 유지한다"))},
]


def _seed_template(conn: Connection, version: int, name: str, questions: list[dict[str, Any]]) -> int:
    existing = conn.execute(sa.select(templates_t.c.id).where(templates_t.c.version == version)).scalar()
    if existing:
        return int(existing)
    template_id = conn.execute(
        sa.insert(templates_t).values(version=version, name=name, is_active=False).returning(templates_t.c.id)
    ).scalar_one()
    for order, q in enumerate(questions, start=1):
        qid = conn.execute(
            sa.insert(questions_t).values(
                template_id=template_id, section=q["section"], code=q["code"],
                question_text=q["question_text"], answer_type=q["answer_type"], display_order=order,
                prior_weight=q.get("prior_weight"), help_text=q.get("help_text"),
                group_label=q.get("group_label"),
            ).returning(questions_t.c.id)
        ).scalar_one()
        for i, o in enumerate(q["options"]):
            conn.execute(sa.insert(options_t).values(question_id=qid, option_order=i, **o))
    return int(template_id)


def _activate(conn: Connection, template_id: int) -> None:
    conn.execute(sa.update(templates_t).values(is_active=False))
    conn.execute(sa.update(templates_t).where(templates_t.c.id == template_id).values(is_active=True))


def seed_survey_v2(conn: Connection) -> int:
    """v2 템플릿을 넣고 활성화한다 (v1 은 비활성). 이미 있으면 활성화만 보장."""
    tid = _seed_template(conn, 2, "온보딩 v2", SURVEY_V2)
    _activate(conn, tid)
    return tid


def seed_active_survey(conn: Connection) -> int:
    """현재 최신 버전(v2)을 시드·활성화한다. conftest 와 앞으로의 시드 진입점."""
    return seed_survey_v2(conn)


def seed_survey_v1(conn: Connection) -> int:
    """v1 템플릿이 없으면 넣고 활성화한다. 이미 있으면 아무것도 하지 않는다. 반환: template_id."""
    existing = conn.execute(sa.select(templates_t.c.id).where(templates_t.c.version == 1)).scalar()
    if existing:
        return int(existing)
    template_id = conn.execute(
        sa.insert(templates_t).values(version=1, name="온보딩 v1", is_active=True).returning(templates_t.c.id)
    ).scalar_one()
    for order, q in enumerate(SURVEY_V1, start=1):
        qid = conn.execute(
            sa.insert(questions_t).values(
                template_id=template_id, section=q["section"], code=q["code"],
                question_text=q["question_text"], answer_type=q["answer_type"], display_order=order,
                prior_weight=q.get("prior_weight"), help_text=q.get("help_text"),
                group_label=q.get("group_label"),
            ).returning(questions_t.c.id)
        ).scalar_one()
        for i, o in enumerate(q["options"]):
            conn.execute(sa.insert(options_t).values(question_id=qid, option_order=i, **o))
    return int(template_id)
