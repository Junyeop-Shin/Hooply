"""팀이 직접 만든 전술 · 역할 자동 추출 · AI 역할 태깅 · 전술 댓글 (docs/07 FR-57 ~ FR-60).

편집기 흐름
  1. 매니저가 시작 위치 · 공 · 단계를 그린다 → `check()` 가 재생 가능성 검사와 규칙 역할 추출을 돌려준다 (저장하지 않음)
  2. "AI로 역할 붙이기" → `ai_roles()` (체인 D). 선수 정보 없이 전술 모양만 보낸다. 실패하면 규칙 결과
  3. 매니저가 역할을 고칠 수 있다 → 저장(`create` · `update`). 역할을 비워 보내면 규칙 결과로 채운다

저장한 전술은 프리셋과 똑같이 추천 후보가 되고(그 팀 일정만), 전술판 · 자리 배치 · AI 전술 설명이 그대로 동작한다.
play_key 는 "team:<id>".

권한
  목록 · 보기 · 댓글 읽기/쓰기   그 팀 활성 팀원 (ADMIN 은 읽기만 — 팀원이 아니면 댓글을 쓸 수 없다)
  만들기 · 고치기 · 지우기        매니저 · ADMIN
  댓글 지우기                     쓴 사람 · 매니저 · ADMIN
"""

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.core import errors, ratelimit
from app.llm import llm_guard
from app.llm.prompts import PROMPT_VERSION_D, SYSTEM_D, RolesD
from app.models import EventPlayAssignment, Player, TacticComment, TeamPlay, User
from app.models.enums import TeamRole
from app.schemas.tactic import (
    PlayCheck,
    RoleSuggestion,
    TacticCommentList,
    TacticCommentView,
    TeamPlayIn,
    TeamPlayList,
    TeamPlayView,
)
from app.services.tactic_service import find_play, team_play_to_play, team_plays
from app.tactics.court import zone_of
from app.tactics.extract import extract_roles, positions
from app.tactics.play import ACTION_LABEL, Play, Point, playability_errors
from app.tactics.presets import TEAM_KEY_PREFIX, play_key

DEFAULT_SUMMARY = "우리 팀이 만든 전술"
COMMENTS_PER_MINUTE = 10


def _is_manager(me: Player) -> bool:
    return me.role == TeamRole.MANAGER


def _to_play(body: TeamPlayIn, key: str = "draft") -> Play:
    """편집 중인 값 → Play. 이름·설명이 비어 있어도 검사할 수 있게 채운다. 형식이 틀리면 400."""
    try:
        return Play.model_validate({
            "key": key, "name": body.name.strip() or "새 전술", "summary": body.summary.strip() or DEFAULT_SUMMARY,
            "defense": body.defense, "situation": body.situation, "counter": body.counter.strip(),
            "start": [p.model_dump() for p in body.start], "ball": body.ball,
            "roles": body.roles or ["spacer"] * 5,
            "steps": [s.model_dump() for s in body.steps],
        })
    except ValidationError as e:
        raise errors.ValidationError(details=[errors.ErrorDetail(field="play", reason=err["msg"]) for err in e.errors()[:5]]) from e


def check(body: TeamPlayIn) -> PlayCheck:
    if not body.steps:
        return PlayCheck(playable=False, errors=["단계를 하나 이상 추가해 주세요"], roles=["spacer"] * 5, reasons=[""] * 5)
    play = _to_play(body)
    found = playability_errors(play)
    extracted = extract_roles(play)
    return PlayCheck(playable=not found, errors=found, roles=[r for r, _ in extracted], reasons=[w for _, w in extracted])


def _validated(body: TeamPlayIn) -> tuple[Play, list[str], str]:
    """저장용 검사 → (전술, 역할, 역할 출처)."""
    if not body.name.strip():
        raise errors.ValidationError("전술 이름을 적어 주세요.")
    if not body.steps:
        raise errors.ValidationError("단계를 하나 이상 추가해 주세요.")
    play = _to_play(body)
    found = playability_errors(play)
    if found:
        raise errors.PlayNotPlayable(details=[errors.ErrorDetail(field="steps", reason=m) for m in found])
    if body.roles:
        return play, list(body.roles), body.role_source
    return play, [r for r, _ in extract_roles(play)], "RULE"


def _view(tp: TeamPlay, me: Player, names: dict[int, str]) -> TeamPlayView:
    return TeamPlayView(
        id=tp.id, play_key=f"{TEAM_KEY_PREFIX}{tp.id}", play=team_play_to_play(tp), role_source=tp.role_source,  # type: ignore[arg-type]
        updated_at=tp.updated_at, updated_by_name=names.get(tp.updated_by or 0), can_edit=_is_manager(me),
    )


def _user_names(db: Session, ids: set[int | None]) -> dict[int, str]:
    real = {i for i in ids if i}
    if not real:
        return {}
    return {u.id: (u.nickname or u.name) for u in db.scalars(select(User).where(User.id.in_(real))).all()}


def list_plays(db: Session, team_id: int, me: Player) -> TeamPlayList:
    rows = team_plays(db, team_id)
    names = _user_names(db, {r.updated_by for r in rows})
    return TeamPlayList(items=[_view(r, me, names) for r in rows])


def _get(db: Session, team_id: int, play_id: int) -> TeamPlay:
    tp = db.get(TeamPlay, play_id)
    if tp is None or tp.team_id != team_id:
        raise errors.NotFound("없는 전술이에요.")
    return tp


def get(db: Session, team_id: int, play_id: int, me: Player) -> TeamPlayView:
    tp = _get(db, team_id, play_id)
    return _view(tp, me, _user_names(db, {tp.updated_by}))


def _fill(tp: TeamPlay, play: Play, roles: list[str], source: str, by: User) -> None:
    tp.name, tp.summary, tp.defense, tp.situation, tp.counter = play.name, play.summary, play.defense, play.situation, play.counter
    tp.body = {
        "start": [p.model_dump() for p in play.start], "ball": play.ball,
        "steps": [s.model_dump(exclude_none=False) for s in play.steps],
    }
    tp.roles = roles
    tp.role_source = source
    tp.updated_by = by.id


def create(db: Session, team_id: int, body: TeamPlayIn, by: User, me: Player) -> TeamPlayView:
    play, roles, source = _validated(body)
    tp = TeamPlay(team_id=team_id, created_by=by.id)
    _fill(tp, play, roles, source, by)
    db.add(tp)
    db.commit()
    db.refresh(tp)
    return _view(tp, me, _user_names(db, {tp.updated_by}))


def update(db: Session, team_id: int, play_id: int, body: TeamPlayIn, by: User, me: Player) -> TeamPlayView:
    tp = _get(db, team_id, play_id)
    play, roles, source = _validated(body)
    old_roles = list(tp.roles)
    _fill(tp, play, roles, source, by)
    # 역할이 바뀌면 그날 저장해 둔 자리 배치는 뜻이 달라지므로 지운다 (다시 자동 추천 배치로)
    if old_roles != roles:
        db.execute(delete(EventPlayAssignment).where(EventPlayAssignment.play_key == f"{TEAM_KEY_PREFIX}{tp.id}"))
    db.commit()
    db.refresh(tp)
    return _view(tp, me, _user_names(db, {tp.updated_by}))


def remove(db: Session, team_id: int, play_id: int) -> None:
    tp = _get(db, team_id, play_id)
    key = f"{TEAM_KEY_PREFIX}{tp.id}"
    db.execute(delete(EventPlayAssignment).where(EventPlayAssignment.play_key == key))
    db.execute(delete(TacticComment).where(TacticComment.team_id == team_id, TacticComment.play_key == key))
    db.delete(tp)
    db.commit()


# ---------------------------------------------------------------------------
# 체인 D — AI 역할 태깅
# ---------------------------------------------------------------------------


def spot_name(p: Point) -> str:
    """좌표 → "왼쪽 코너" 같은 자리 이름. LLM 에는 좌표 대신 이것만 보낸다."""
    if p.y < 0:
        return "베이스라인 밖"
    side = "왼쪽 " if p.x < 0.4 else "오른쪽 " if p.x > 0.6 else ""
    z = zone_of(p.x, p.y)
    if z == "three":
        return f"{side}코너" if p.y < 0.2 and side else "탑" if not side else f"{side}윙"
    if z == "paint":
        return f"{side}블록" if p.y < 0.25 and side else "골밑" if p.y < 0.25 else "페인트 위쪽"
    if 0.33 <= p.y <= 0.5:
        return f"{side}엘보" if side else "자유투 라인"
    return f"{side}미드레인지"


def _describe(play: Play) -> dict[str, Any]:
    pos = positions(play)
    steps = []
    for k, st in enumerate(play.steps):
        acts = []
        for a in st.actions:
            label = ACTION_LABEL[a.type]
            if a.type == "screen":
                acts.append(f"{a.slot}번 {label} → {a.target}번에게 ({spot_name(a.to)})")  # type: ignore[arg-type]
            elif a.type in ("pass", "handoff"):
                acts.append(f"{a.slot}번 {label} → {a.target}번 ({spot_name(pos[k][a.target - 1])})")  # type: ignore[index]
            elif a.type == "shot":
                acts.append(f"{a.slot}번 {label} ({spot_name(pos[k][a.slot - 1])})")
            else:
                acts.append(f"{a.slot}번 {label} → {spot_name(a.to)}")  # type: ignore[arg-type]
        steps.append({"step": k + 1, "caption": st.caption, "actions": acts})
    rule = extract_roles(play)
    return {
        "situation": "인바운드" if play.situation == "inbound" else "하프코트",
        "slots": [{"slot": i + 1, "start": spot_name(p), "ball": i + 1 == play.ball} for i, p in enumerate(play.start)],
        "steps": steps,
        "rule_roles": [{"slot": i + 1, "role": r, "why": w} for i, (r, w) in enumerate(rule)],
    }


def ai_roles(db: Session, body: TeamPlayIn, user: User) -> RoleSuggestion:
    """직접 그린 전술의 자리마다 역할을 AI 가 붙인다. 재생할 수 없는 전술이면 422 (먼저 고치게)."""
    if not body.steps:
        raise errors.ValidationError("단계를 하나 이상 추가해 주세요.")
    play = _to_play(body)
    found = playability_errors(play)
    if found:
        raise errors.PlayNotPlayable(details=[errors.ErrorDetail(field="steps", reason=m) for m in found])
    rule = extract_roles(play)
    payload = _describe(play)
    fallback = {"slots": [{"slot": i + 1, "role": r, "reason": w} for i, (r, w) in enumerate(rule)]}

    def ordered(o: dict[str, Any]) -> dict[str, Any]:
        got = {it["slot"]: it for it in o.get("slots", [])}
        return {"slots": [got[i] for i in range(1, 6)]}

    call = llm_guard.ChainCall(
        chain="D", schema=RolesD,
        messages=[("system", SYSTEM_D), ("human", json.dumps(payload, ensure_ascii=False))],
        payload=payload, aliases=llm_guard.Aliases(), fallback=fallback,
        key_parts={"v": PROMPT_VERSION_D, "input": payload},
        extra_check=lambda o: sorted(it.get("slot") for it in o.get("slots", [])) == [1, 2, 3, 4, 5],
        usable=lambda o: len(o.get("slots", [])) == 5,
        max_chars=60, post=ordered,
    )
    out = llm_guard.run(db, call, user_id=user.id)
    slots = out.output["slots"]
    return RoleSuggestion(
        roles=[s["role"] for s in slots], reasons=[s["reason"] for s in slots],
        source="RULE" if out.fallback else "AI", fallback=out.fallback, cached=out.cached, fail_reason=out.fail_reason,
    )


# ---------------------------------------------------------------------------
# 전술 댓글
# ---------------------------------------------------------------------------


def _require_play(db: Session, team_id: int, key: str) -> str:
    play = find_play(db, team_id, key)
    if play is None:
        raise errors.NotFound("없는 전술이에요.")
    return play_key(play)


def _comment_view(c: TacticComment, me: Player) -> TacticCommentView:
    mine = me.id is not None and c.author_player_id == me.id
    return TacticCommentView(
        id=c.id, body=c.body, author_player_id=c.author_player_id, author_name=c.author.display_name,
        created_at=c.created_at, mine=mine, can_delete=mine or _is_manager(me),
    )


def comments(db: Session, team_id: int, key: str, me: Player) -> TacticCommentList:
    k = _require_play(db, team_id, key)
    rows = db.scalars(
        select(TacticComment).options(selectinload(TacticComment.author))
        .where(TacticComment.team_id == team_id, TacticComment.play_key == k)
        .order_by(TacticComment.created_at, TacticComment.id)
    ).all()
    return TacticCommentList(items=[_comment_view(c, me) for c in rows])


def add_comment(db: Session, team_id: int, key: str, text: str, me: Player) -> TacticCommentView:
    if me.id is None:  # 팀원이 아닌 ADMIN
        raise errors.NotAMember("팀원만 댓글을 쓸 수 있어요.")
    body = text.strip()
    if not body:
        raise errors.ValidationError("댓글 내용을 적어 주세요.")
    k = _require_play(db, team_id, key)
    ratelimit.check(f"tactic-comment:{me.id}", COMMENTS_PER_MINUTE, 60)
    c = TacticComment(team_id=team_id, play_key=k, author_player_id=me.id, body=body)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _comment_view(c, me)


def delete_comment(db: Session, team_id: int, comment_id: int, me: Player) -> None:
    c = db.get(TacticComment, comment_id)
    if c is None or c.team_id != team_id:
        raise errors.NotFound("없는 댓글이에요.")
    if c.author_player_id != me.id and not _is_manager(me):
        raise errors.ForbiddenRole("내가 쓴 댓글만 지울 수 있어요.")
    db.delete(c)
    db.commit()
