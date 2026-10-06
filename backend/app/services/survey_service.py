"""온보딩 설문 서비스 — 문항 조회, 응답 저장, 응답 → 사전 실력값(prior) 변환 (설문 설계, 설계서 8.4절).

핵심 흐름
  1. `submit()`         : 응답 검증·저장 → users.onboarding_completed → 키 반영 → 포지션 반영
                          → 소속된 모든 팀의 prior 재계산
  2. `recompute_team_priors(team_id)` : 팀 안의 설문 응답자들끼리 z-score 를 내 prior_overall 을 갱신
                          (팀 가입·설문 제출·매니저 정렬 때마다 호출된다 — 상대 위치는 팀이 바뀔 때마다 달라지므로)

왜 팀 단위로 z-score 인가: 배정에 필요한 것은 절대 실력이 아니라 **그 클럽 안의 상대 순위**다 (8.1절).
같은 응답이라도 강한 클럽에서는 낮은 prior, 약한 클럽에서는 높은 prior 가 된다.

단위: `prior_overall` 은 "쿼터당 득실 기여도(점)" 다 (9.2절). z-score 에 `PRIOR_SCALE`(개인 실력 표준편차
2점, 9.3절 시뮬레이션 가정)을 곱해 점수 단위로 바꾼다. 6축 세부값은 0~10 척도(표시·포지션 매칭용).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from statistics import mean, pstdev

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core import errors
from app.core.errors import ErrorDetail
from app.db.session import lock_team_stats
from app.models import (
    Player,
    PlayerPosition,
    PlayerProfile,
    SkillRatingHistory,
    SurveyAnswer,
    SurveyOption,
    SurveyQuestion,
    SurveyResponse,
    SurveyTemplate,
    User,
)
from app.models.enums import (
    AnswerType,
    PlayerKind,
    PlayerStatus,
    Position,
    PriorSource,
    RatingSource,
    SelfRankLevel,
)
from app.schemas.survey import MyProfile, SurveyAnswerIn, SurveyResponseIn, TeamProfileSummary
from app.services.player_service import grade_of

PRIOR_SCALE = 2.0  # z 1.0 = 쿼터당 2점 (9.3절: 개인 실력 표준편차 2점)
SURVEY_CONFIDENCE = Decimal("0.40")  # 설문만 있는 회원의 skill_confidence (게스트 등급 0.25 보다 높게)
MIN_SAMPLE_FOR_Z = 5  # 스펙 5절: 표본이 5명 미만이면 z 를 계산하지 않고 0(클럽 평균)으로 둔다

# 팀별 자기 위치(구 E3, player_profiles.self_rank_level) → 0~4 점수. 상위일수록 높다
SELF_RANK_SCORE: dict[SelfRankLevel, int] = {
    SelfRankLevel.TOP10: 4, SelfRankLevel.TOP30: 3, SelfRankLevel.MID: 2, SelfRankLevel.BOT30: 1, SelfRankLevel.BOT10: 0,
}

# 스펙 5절 가중치. 각 성분은 0~1 로 정규화한 뒤 팀 내 z-score 를 낸다.
PRIOR_COMPONENTS: dict[str, float] = {
    "self_rank": 0.30,  # 팀별 자기 위치 (구 E3)
    "experience": 0.20,  # A2, A3
    "shooting": 0.20,  # B2, B1 개수
    "handling": 0.15,  # B3
    "defense": 0.15,  # C1, C2
}


@dataclass
class SurveyFeatures:
    """한 사람의 응답을 prior 계산에 쓰는 성분(0~1)과 6축(0~10), 포지션 정보로 요약한 것."""

    components: dict[str, float] = field(default_factory=dict)
    axes: dict[str, float] = field(default_factory=dict)
    playable: set[Position] = field(default_factory=set)
    preference_order: list[Position] = field(default_factory=list)  # D1 선택 순서 = 선호 순서 (v2)
    preferred: Position | None = None  # preference_order[0]
    pg_trio: float | None = None  # D3A: 1.0 가능+선호 / 0.5 가능 / 0.0 불가
    c_trio: float | None = None  # D3B
    height_cm: int | None = None
    # 전술 역할 점수(app/tactics/roles.py) 재료
    b1_codes: set[str] = field(default_factory=set)  # B1 에서 고른 공격 옵션 코드
    shot_range: float | None = None  # B2 최대 거리 0~1
    handle: float | None = None  # B3 볼 운반 0~1


# ---------------------------------------------------------------------------
# 템플릿
# ---------------------------------------------------------------------------


def get_active_template(db: Session) -> SurveyTemplate:
    """is_active 템플릿을 문항·선택지까지 로드해 돌려준다. 없으면 404 (시드 전)."""
    tpl = db.scalar(
        select(SurveyTemplate)
        .where(SurveyTemplate.is_active.is_(True))
        .options(selectinload(SurveyTemplate.questions).selectinload(SurveyQuestion.options))
        .order_by(SurveyTemplate.version.desc())
    )
    if tpl is None:
        raise errors.NotFound("설문을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.")
    return tpl


# ---------------------------------------------------------------------------
# 제출
# ---------------------------------------------------------------------------


def _validate_answers(tpl: SurveyTemplate, answers: list[SurveyAnswerIn]) -> dict[int, SurveyAnswerIn]:
    """문항 유형별 형식·필수 여부를 검사하고 question_id → 응답 매핑을 돌려준다. 위반은 400 + details[]."""
    q_by_id = {q.id: q for q in tpl.questions}
    details: list[ErrorDetail] = []
    seen: dict[int, SurveyAnswerIn] = {}
    for a in answers:
        q = q_by_id.get(a.question_id)
        if q is None:
            details.append(ErrorDetail(field=f"question_id={a.question_id}", reason="이 설문에 없는 질문이에요."))
            continue
        if a.question_id in seen:
            details.append(ErrorDetail(field=q.code, reason="같은 질문에 두 번 답했어요."))
            continue
        if q.answer_type == AnswerType.STEPPER:
            if a.numeric_value is None or a.selected_option_ids:
                details.append(ErrorDetail(field=q.code, reason="숫자로 답하는 질문이에요."))
            elif not (120 <= a.numeric_value <= 250):
                details.append(ErrorDetail(field=q.code, reason="키는 120~250cm 사이로 적어 주세요."))
        else:
            valid_ids = {o.id for o in q.options}
            if a.numeric_value is not None or not a.selected_option_ids:
                details.append(ErrorDetail(field=q.code, reason="선택지를 하나 이상 골라 주세요."))
            elif not set(a.selected_option_ids) <= valid_ids:
                details.append(ErrorDetail(field=q.code, reason="이 질문에 없는 선택지예요."))
            elif q.answer_type != AnswerType.MULTI_CHIP and len(a.selected_option_ids) != 1:
                details.append(ErrorDetail(field=q.code, reason="하나만 골라 주세요."))
        seen[a.question_id] = a
    missing = [q.code for q in tpl.questions if q.id not in seen]
    if missing:
        details.append(ErrorDetail(field=",".join(missing), reason="아직 답하지 않은 질문이 있어요."))
    if details:
        raise errors.ValidationError("설문 답변을 다시 확인해 주세요.", details=details)
    return seen


def submit(db: Session, user: User, body: SurveyResponseIn) -> SurveyResponse:
    """응답을 저장하고 프로필을 만든다. 1인 1회 — 두 번째 제출은 409 ALREADY_SUBMITTED.

    부수 효과: survey_responses/answers INSERT, users.onboarding_completed·height_cm UPDATE,
    소속 팀 전부의 player_positions 교체 + prior 재계산, commit.
    """
    if db.scalar(select(SurveyResponse.id).where(SurveyResponse.user_id == user.id)):
        raise errors.AlreadySubmitted("이미 설문을 제출했어요. 수정은 매니저·관리자 보정으로만 가능해요.")
    tpl = get_active_template(db)
    if body.template_id is not None and body.template_id != tpl.id:
        raise errors.ValidationError("설문 버전이 바뀌었어요. 화면을 새로고침해 주세요.")
    by_q = _validate_answers(tpl, body.answers)

    resp = SurveyResponse(template_id=tpl.id, user_id=user.id, submitted_at=datetime.now(UTC))
    for qid, a in by_q.items():
        resp.answers.append(
            SurveyAnswer(question_id=qid, selected_option_ids=list(a.selected_option_ids), numeric_value=a.numeric_value)
        )
    db.add(resp)
    try:
        db.flush()
    except IntegrityError:  # 두 번 눌러 동시에 제출 — uq_survey_responses_user 가 하나만 남긴다
        db.rollback()
        raise errors.AlreadySubmitted("이미 설문을 제출했어요. 수정은 매니저·관리자 보정으로만 가능해요.") from None
    user.onboarding_completed = True

    feats = extract_features(tpl, resp, height_cm=user.height_cm)
    user.position_prefs = [p.value for p in preference_from_features(feats)]  # 프로필 수정의 원본

    # 이미 소속된 팀이 있으면 포지션을 채우고 팀별 prior 를 다시 계산한다
    players = db.scalars(
        select(Player).where(Player.user_id == user.id, Player.status == PlayerStatus.ACTIVE)
    ).all()
    for p in players:
        apply_positions(db, p, feats)
    db.flush()
    for team_id in {p.team_id for p in players}:
        recompute_team_priors(db, team_id)
    db.commit()
    return resp


# ---------------------------------------------------------------------------
# 응답 → 성분·6축·포지션
# ---------------------------------------------------------------------------


def _picked(q: SurveyQuestion, ans: SurveyAnswer | None) -> list[SurveyOption]:
    if ans is None:
        return []
    by_id = {o.id: o for o in q.options}
    return [by_id[i] for i in ans.selected_option_ids if i in by_id]


def _score(q: SurveyQuestion, ans: SurveyAnswer | None) -> float | None:
    """단일선택 문항의 score_value (없으면 None)."""
    opts = _picked(q, ans)
    return float(opts[0].score_value) if opts else None


def _max_score(q: SurveyQuestion) -> float:
    return max((float(o.score_value) for o in q.options), default=1.0) or 1.0


def _norm(q: SurveyQuestion, ans: SurveyAnswer | None) -> float | None:
    s = _score(q, ans)
    return None if s is None else s / _max_score(q)


def extract_features(
    tpl: SurveyTemplate, resp: SurveyResponse, *, height_cm: int | None = None,
    self_rank: SelfRankLevel | None = None,
) -> SurveyFeatures:
    """응답 1건 → SurveyFeatures. 문항은 code 로 찾으므로 템플릿 버전이 달라도 동작한다.

    - `height_cm`: 가입 시 받은 users.height_cm (v2 부터 설문에서 키를 묻지 않는다. v1 응답의 A1 이 있으면 그것을 우선).
    - `self_rank`: 팀별 자기 위치(player_profiles.self_rank_level). v1 응답의 E3 가 있으면 그것으로 대체.
    """
    q_by_code = {q.code: q for q in tpl.questions}
    a_by_q = {a.question_id: a for a in resp.answers}

    def q(code: str) -> SurveyQuestion | None:
        return q_by_code.get(code)

    def ans(code: str) -> SurveyAnswer | None:
        qq = q(code)
        return a_by_q.get(qq.id) if qq else None

    def norm(code: str) -> float | None:
        qq = q(code)
        return _norm(qq, ans(code)) if qq else None

    def picked_codes(code: str) -> set[str]:
        qq = q(code)
        return {o.code for o in _picked(qq, ans(code))} if qq else set()

    def picked_codes_ordered(code: str) -> list[str]:
        """selected_option_ids 의 순서를 보존 (D1: 선택 순서 = 선호 순서)."""
        qq = q(code)
        return [o.code for o in _picked(qq, ans(code))] if qq else []

    def avg(*vals: float | None) -> float | None:
        xs = [v for v in vals if v is not None]
        return mean(xs) if xs else None

    f = SurveyFeatures()
    b1 = picked_codes("B1")
    f.b1_codes = b1
    f.shot_range = norm("B2")
    f.handle = norm("B3")
    b1_count = len(b1) / 8.0

    # --- prior 성분 (0~1) ---
    # 자기 위치: v2 는 팀별 self_rank_level, v1 응답은 설문 E3. 둘 다 없으면 성분 제외
    self_rank_norm = norm("E3")
    if self_rank_norm is None and self_rank is not None:
        self_rank_norm = SELF_RANK_SCORE[self_rank] / 4.0
    comp = {
        "self_rank": self_rank_norm,
        "experience": avg(norm("A2"), norm("A3")),
        "shooting": avg(norm("B2"), b1_count),
        "handling": norm("B3"),
        "defense": avg(norm("C1"), norm("C2")),
    }
    f.components = {k: v for k, v in comp.items() if v is not None}

    # --- 키 (v1 A1 > 가입 시 입력) ---
    a1 = ans("A1")
    if a1 is not None and a1.numeric_value is not None:
        f.height_cm = int(a1.numeric_value)
    elif height_cm:
        f.height_cm = height_cm
    height_norm = min(max(((f.height_cm or 175) - 160) / 40.0, 0.0), 1.0)

    # --- 포지션 ---
    f.preference_order = [Position(c) for c in picked_codes_ordered("D1") if c in Position.__members__]
    f.playable = set(f.preference_order)
    d2 = picked_codes("D2")  # v1 전용. v2 에는 없다
    f.preferred = Position(next(iter(d2))) if d2 else (f.preference_order[0] if f.preference_order else None)
    if f.preferred and f.preferred not in f.preference_order:
        f.preference_order.insert(0, f.preferred)
    f.pg_trio = norm("D3A")
    f.c_trio = norm("D3B")

    # --- 6축 (0~10) ---
    onball = norm("E1")  # 0 온볼 … 1 오프볼
    f.axes = {
        "shooting": 10 * (avg(norm("B2"), float("CATCH_SHOOT" in b1), float("PULLUP" in b1)) or 0),
        "ball_handling": 10 * (avg(norm("B3"), float("PNR_HANDLER" in b1)) or 0),
        "passing": 10 * (avg(float("PNR_HANDLER" in b1), float("PNR_ROLL_POP" in b1), None if onball is None else 1 - onball) or 0),
        "defense": 10 * (avg(norm("C1"), norm("C2")) or 0),
        "rebound_post": 10 * (avg(height_norm, mean([float(c in b1) for c in ("POST_UP", "PNR_ROLL_POP", "PUTBACK")]), f.c_trio) or 0),
        "stamina": 10 * (norm("E2") or 0),
    }
    return f


def preference_from_features(f: SurveyFeatures) -> list[Position]:
    """설문 응답 → 선호 순서 목록 (apply_positions 와 같은 규칙: D1 순서 + D3 보정)."""
    order = list(f.preference_order)
    for pos, trio in ((Position.PG, f.pg_trio), (Position.C, f.c_trio)):
        if trio is None:
            continue
        if trio <= 0 and pos in order:
            order.remove(pos)
        elif trio >= 1 and pos not in order:
            order.append(pos)
    return order


def apply_preference_list(db: Session, player: Player, prefs: list[Position]) -> None:
    """선호 순서 목록을 player_positions 로 교체한다 (1 = 가장 선호)."""
    for old in list(player.positions):
        db.delete(old)
    db.flush()
    player.positions = [
        PlayerPosition(player_id=player.id, position=pos, can_play=True, preference_rank=i + 1)
        for i, pos in enumerate(prefs)
    ]


def apply_positions(db: Session, player: Player, f: SurveyFeatures) -> None:
    """D1(선호 순서)·D3 응답을 player_positions 로 교체한다 (팀별 players 행마다 같은 값).

    preference_rank 는 D1 선택 순서(1 = 가장 선호). D3 에서 1번·5번을 "가능+선호" 로 답했는데 D1 에 없으면
    맨 뒤 순위로 추가하고, "불가" 면 D1 에 있어도 뺀다 (희소 자원은 명시 응답을 신뢰).
    """
    rows: dict[Position, PlayerPosition] = {}
    for rank, pos in enumerate(f.preference_order, start=1):
        rows[pos] = PlayerPosition(player_id=player.id, position=pos, can_play=True, preference_rank=rank)
    for pos, trio in ((Position.PG, f.pg_trio), (Position.C, f.c_trio)):
        if trio is None:
            continue
        if trio <= 0:
            rows.pop(pos, None)
            continue
        if pos not in rows:
            rows[pos] = PlayerPosition(
                player_id=player.id, position=pos, can_play=True,
                preference_rank=(len(rows) + 1) if trio >= 1 else None,
            )
    for old in list(player.positions):
        db.delete(old)
    db.flush()  # DELETE 를 먼저 내보내야 같은 포지션을 다시 넣을 때 UNIQUE 에 안 걸린다
    player.positions = list(rows.values())


# ---------------------------------------------------------------------------
# 팀 단위 prior 재계산
# ---------------------------------------------------------------------------


def members_with_features(db: Session, team_id: int, player_ids: list[int] | None = None) -> list[tuple[Player, SurveyFeatures]]:
    """팀 활성 회원의 설문 특성. `player_ids` 를 주면 그 사람들만 (전술 · AI 는 그날 배정 명단만 쓴다)."""
    tpl_cache: dict[int, SurveyTemplate] = {}
    q = (
        select(Player, SurveyResponse)
        .join(SurveyResponse, SurveyResponse.user_id == Player.user_id)
        .where(Player.team_id == team_id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE)
        .options(joinedload(Player.profile), joinedload(Player.user), selectinload(SurveyResponse.answers))
    )
    if player_ids is not None:
        q = q.where(Player.id.in_(player_ids))
    rows = db.execute(q).all()
    out = []
    for player, resp in rows:
        tpl = tpl_cache.get(resp.template_id)
        if tpl is None:
            tpl = db.scalar(
                select(SurveyTemplate).where(SurveyTemplate.id == resp.template_id)
                .options(selectinload(SurveyTemplate.questions).selectinload(SurveyQuestion.options))
            )
            tpl_cache[resp.template_id] = tpl
        out.append((
            player,
            extract_features(
                tpl, resp, height_cm=player.user.height_cm if player.user else None,
                self_rank=player.profile.self_rank_level if player.profile else None,
            ),
        ))
    return out


def survey_sample_size(db: Session, team_id: int) -> int:
    """팀에서 설문에 응답한 활성 회원 수. `members_with_features` 와 같은 조건이지만 응답 본문은 읽지 않는다
    (내 프로필 화면이 팀마다 부르므로 COUNT 한 번이어야 한다)."""
    return db.scalar(
        select(func.count()).select_from(Player)
        .join(SurveyResponse, SurveyResponse.user_id == Player.user_id)
        .where(Player.team_id == team_id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE)
    ) or 0


def _active_ranking_z(db: Session, team_id: int) -> dict[int, float]:
    """활성 매니저 정렬(F14)의 순위 → z-score (상위일수록 +). 정렬이 없으면 빈 dict."""
    from app.models import ManagerRanking  # 순환 import 회피

    ranking = db.scalar(
        select(ManagerRanking).where(ManagerRanking.team_id == team_id, ManagerRanking.is_active.is_(True))
        .options(selectinload(ManagerRanking.entries)).order_by(ManagerRanking.created_at.desc(), ManagerRanking.id.desc()).limit(1)
    )
    if ranking is None or len(ranking.entries) < 2:
        return {}
    ranks = [e.rank_no for e in ranking.entries]
    mu, sd = mean(ranks), pstdev(ranks)
    if sd == 0:
        return {}
    return {e.player_id: (mu - e.rank_no) / sd for e in ranking.entries}  # 1위가 가장 큰 z


def recompute_team_priors(db: Session, team_id: int) -> int:
    """팀 안 참가자들의 prior_overall·6축을 다시 계산한다. 반환: 설문 응답자 수.

    prior_z = 0.5 × 설문 z + 0.5 × 매니저 정렬 z (8.5절). 한쪽만 있으면 그쪽만 쓴다.
    - 설문 z: 응답자가 MIN_SAMPLE_FOR_Z 미만이면 0 (스펙 5절 — 클럽 평균).
    - 정렬 z: 활성 ManagerRanking 의 순위를 표준화. 정렬에 포함된 게스트도 값을 받는다.
    - skill_overall 은 경기 기록이 없는 동안(quarters_played == 0) prior (+ 관리자 보정 admin_adjust) 를 따라간다.
    - admin_adjust 는 읽기만 한다 — 관리자 보정이 설문 · 정렬 재계산에 지워지지 않게.
    - 값이 바뀐 사람만 skill_rating_history 를 남긴다.
    부수 효과: flush 까지. commit 은 호출자 책임.
    첫 줄에서 팀 잠금(lock_team_stats)을 건다 — player_profiles 를 먼저 쓰고 나서 안쪽 recompute_team 이 잠금을 걸면
    잠금을 먼저 잡은 다른 요청과 교착이 났다 (quarter_service 모듈 docstring 의 잠금 순서).
    """
    lock_team_stats(db, team_id)
    rows = members_with_features(db, team_id)
    n = len(rows)
    survey_z: dict[int, float] = {}
    if n >= MIN_SAMPLE_FOR_Z:
        for comp, w in PRIOR_COMPONENTS.items():
            vals = [f.components.get(comp) for _, f in rows]
            xs = [v for v in vals if v is not None]
            mu = mean(xs) if xs else 0.0
            sd = pstdev(xs) if len(xs) > 1 else 0.0
            for (p, f), v in zip(rows, vals, strict=True):
                z = 0.0 if v is None or sd == 0 else (v - mu) / sd
                survey_z[p.id] = survey_z.get(p.id, 0.0) + w * z
    else:
        for p, _ in rows:
            survey_z[p.id] = 0.0
    rank_z = _active_ranking_z(db, team_id)

    # 대상: 설문 응답자 ∪ 정렬에 포함된 활성 참가자
    feats = {p.id: f for p, f in rows}
    players = {p.id: p for p, _ in rows}
    if rank_z:
        for pl in db.scalars(
            select(Player).where(Player.id.in_(rank_z.keys()), Player.status == PlayerStatus.ACTIVE)
            .options(selectinload(Player.profile))
        ).all():
            players.setdefault(pl.id, pl)

    for pid, p in players.items():
        sz, rz = survey_z.get(pid), rank_z.get(pid)
        if sz is None and rz is None:
            continue
        z = (0.5 * sz + 0.5 * rz) if (sz is not None and rz is not None) else (sz if sz is not None else rz)
        source = PriorSource.SURVEY if sz is not None else PriorSource.MANAGER
        reason = "설문 + 매니저 정렬 결합" if (sz is not None and rz is not None) else ("설문 z-score 재계산" if sz is not None else "매니저 정렬 반영")
        prof = p.profile or PlayerProfile(player_id=p.id)
        if p.profile is None:
            p.profile = prof
        before = prof.prior_overall
        after = Decimal(str(round(z * PRIOR_SCALE, 1)))
        prof.prior_overall = after
        prof.prior_source = source
        f = feats.get(pid)
        if f is not None:
            prof.skill_shooting = Decimal(str(round(f.axes["shooting"], 1)))
            prof.skill_ball_handling = Decimal(str(round(f.axes["ball_handling"], 1)))
            prof.skill_passing = Decimal(str(round(f.axes["passing"], 1)))
            prof.skill_defense = Decimal(str(round(f.axes["defense"], 1)))
            prof.skill_rebound_post = Decimal(str(round(f.axes["rebound_post"], 1)))
            prof.skill_stamina = Decimal(str(round(f.axes["stamina"], 1)))
        if prof.quarters_played == 0:
            prof.skill_overall = after + (prof.admin_adjust or Decimal(0))  # 관리자 보정은 사전값과 따로 둔다 (admin_adjust 는 건드리지 않는다)
        floor = SURVEY_CONFIDENCE if sz is not None else Decimal("0.30")
        prof.skill_confidence = max(prof.skill_confidence, floor)
        if before != after:
            db.add(
                SkillRatingHistory(
                    player_id=p.id, source=RatingSource.MANAGER_SORT if sz is None else RatingSource.SURVEY,
                    before_value=before, after_value=after, delta=(after - (before or Decimal(0))),
                    ref_type="team_recompute", ref_id=team_id, reason=f"{reason} (응답자 {n}명)",
                )
            )
    db.flush()
    # 사전값이 바뀌면 Elo 출발점이 바뀌므로 쿼터 기록을 다시 재생한다 (쿼터가 없으면 skill_overall = prior)
    from app.services import rating_service  # 순환 import 회피

    rating_service.recompute_team(db, team_id)
    return n


def on_member_joined(db: Session, player: Player) -> None:
    """팀 가입 직후 호출: 이 사람의 설문 응답이 있으면 포지션을 채우고 팀 prior 를 재계산한다."""
    resp = db.scalar(
        select(SurveyResponse).where(SurveyResponse.user_id == player.user_id)
        .options(selectinload(SurveyResponse.answers))
    )
    if player.user is not None and player.user.position_prefs:
        # 프로필에서 수정한 선호 순서가 있으면 그것이 원본 (설문 → 프로필 수정 순으로 최신)
        apply_preference_list(db, player, [Position(x) for x in player.user.position_prefs])
        db.flush()
    elif resp is not None:
        tpl = db.scalar(
            select(SurveyTemplate).where(SurveyTemplate.id == resp.template_id)
            .options(selectinload(SurveyTemplate.questions).selectinload(SurveyQuestion.options))
        )
        apply_positions(db, player, extract_features(tpl, resp, height_cm=player.user.height_cm if player.user else None))
        db.flush()
    recompute_team_priors(db, player.team_id)


# ---------------------------------------------------------------------------
# 내 프로필
# ---------------------------------------------------------------------------


def my_profile(db: Session, user: User) -> MyProfile:
    resp = db.scalar(select(SurveyResponse).where(SurveyResponse.user_id == user.id))
    players = db.scalars(
        select(Player).where(Player.user_id == user.id, Player.status == PlayerStatus.ACTIVE)
        .options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user), selectinload(Player.team))
        .order_by(Player.joined_at.desc())
    ).all()
    playable: list[Position] = []
    primary: Position | None = None
    order = list(Position)
    if players:
        p0 = players[0]
        playable = ordered_positions(p0)
        primary = playable[0] if playable and p0.positions else None
        if not any(pp.preference_rank for pp in p0.positions):
            primary = None
    elif user.position_prefs:
        playable = [Position(x) for x in user.position_prefs]
        primary = playable[0] if playable else None
    elif resp is not None:
        # 팀도, 프로필 수정 이력도 없으면 설문 응답에서 직접 읽어 보여준다
        tpl = db.scalar(
            select(SurveyTemplate).where(SurveyTemplate.id == resp.template_id)
            .options(selectinload(SurveyTemplate.questions).selectinload(SurveyQuestion.options))
        )
        db.refresh(resp, attribute_names=["answers"])
        f = extract_features(tpl, resp, height_cm=user.height_cm)
        playable = f.preference_order + sorted(f.playable - set(f.preference_order), key=order.index)
        primary = f.preferred
    teams = []
    for p in players:
        prof = p.profile
        teams.append(
            TeamProfileSummary(
                team_id=p.team_id, team_name=p.team.name, player_id=p.id,
                # 내 등급은 나에게만 보여 준다 (다른 사람 카드에는 여전히 안 실린다 — 9.2절)
                skill_grade=grade_of(p),
                prior_source=prof.prior_source if prof else None,
                skill_confidence=prof.skill_confidence if prof else None,
                self_rank_level=prof.self_rank_level if prof else None,
                survey_sample_size=survey_sample_size(db, p.team_id),
                quarters_played=prof.quarters_played if prof else 0,
            )
        )
    return MyProfile(
        onboarding_completed=user.onboarding_completed,
        survey_submitted_at=resp.submitted_at if resp else None,
        height_cm=user.height_cm, primary_position=primary, playable_positions=playable, teams=teams,
    )


def ordered_positions(player: Player) -> list[Position]:
    """가능 포지션을 선호 순서(preference_rank 오름차순)로, 순위 없는 것은 PG→C 순으로 뒤에."""
    order = list(Position)
    rows = [pp for pp in player.positions if pp.can_play]
    ranked = sorted((pp for pp in rows if pp.preference_rank), key=lambda x: x.preference_rank)
    rest = sorted((pp for pp in rows if not pp.preference_rank), key=lambda x: order.index(x.position))
    return [pp.position for pp in ranked + rest]


def set_self_rank(db: Session, player: Player, level: SelfRankLevel) -> None:
    """팀 가입 후 "이 동호회에서 내 실력 위치" 를 저장하고 팀 prior 를 재계산한다. commit 포함."""
    lock_team_stats(db, player.team_id)  # 프로필을 쓰기 전에 (잠금 순서)
    prof = player.profile or PlayerProfile(player_id=player.id)
    if player.profile is None:
        player.profile = prof
    prof.self_rank_level = level
    db.flush()
    recompute_team_priors(db, player.team_id)
    db.commit()
