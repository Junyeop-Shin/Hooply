"""쿼터 기록 서비스 (설계서 F8 · FR-25 ~ FR-27 · S-15).

기록은 매니저가 **경기 후** 한 번에 입력한다 (2.5절). 쿼터마다 양 팀 출전 5명과 스코어만 받고,
서버가 출전 10명의 코트 마진을 계산해 저장한다. 저장·수정·삭제 뒤에는 rating_service 가 팀 전체를
다시 계산하므로 "삭제하면 마진이 롤백된다" 가 자동으로 성립한다 (13.2절 2항).

잠금 순서: 쓰기 경로(추가 · 일괄 저장 · 수정 · 삭제)는 **첫 쓰기 전에** 팀 잠금(lock_team_stats)을 건다.
쿼터 · 출전 행을 먼저 쓰고 나서 재계산에서 잠금을 걸면, 잠금을 먼저 잡고 같은 행을 다시 쓰려는 다른 요청과
서로를 기다려 교착(40P01 → 409)이 났다. 잠금은 재진입이라 안쪽 recompute_team 이 다시 걸어도 된다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import errors
from app.core.errors import ErrorDetail
from app.db.session import lock_team_stats
from app.models import (
    AssignmentCandidate,
    AssignmentRun,
    AssignmentSquad,
    Event,
    Player,
    Quarter,
    QuarterLineup,
    User,
)
from app.models.enums import DEFAULT_SQUAD_NAMES, EventStatus, PlayerStatus, Side
from app.schemas.game import (
    LineupIn,
    LineupView,
    PlayerQuarterCount,
    QuarterBulkResult,
    QuarterBulkSave,
    QuarterIn,
    QuarterListView,
    QuarterSummary,
    QuarterUpdate,
    QuarterView,
    SquadTally,
)
from app.services import rating_service

SIDE_LABEL = {Side.BLACK: DEFAULT_SQUAD_NAMES[0], Side.WHITE: DEFAULT_SQUAD_NAMES[1]}


def _squad_names(db: Session, event: Event) -> dict[int, str]:
    """확정 배정의 팀 번호 → 이름. 배정이 없으면 2팀(블랙 · 화이트)."""
    rows = db.execute(
        select(AssignmentSquad.squad_no, AssignmentSquad.squad_name)
        .join(AssignmentCandidate, AssignmentCandidate.id == AssignmentSquad.candidate_id)
        .join(AssignmentRun, AssignmentRun.id == AssignmentCandidate.run_id)
        .where(AssignmentRun.event_id == event.id, AssignmentCandidate.is_adopted.is_(True))
    ).all()
    return {no: name for no, name in rows} or {1: DEFAULT_SQUAD_NAMES[0], 2: DEFAULT_SQUAD_NAMES[1]}


def _validate_matchup(db: Session, event: Event, home: int, away: int, names: dict[int, str] | None = None) -> None:
    """3팀이면 쿼터마다 두 팀을 고른다. 같은 팀끼리, 그날 없는 팀은 안 된다."""
    names = names or _squad_names(db, event)
    if home == away:
        raise errors.ValidationError("한 쿼터에 같은 팀끼리 뛸 수 없어요. 두 팀을 골라 주세요.")
    bad = [no for no in (home, away) if no not in names]
    if bad:
        raise errors.ValidationError(f"그날 없는 팀이에요 (팀 {', '.join(map(str, bad))}).")


# ---------------------------------------------------------------------------
# 검증 · 계산
# ---------------------------------------------------------------------------


def _validate_lineups(db: Session, event: Event, lineups: list[LineupIn], kept: frozenset[int] = frozenset()) -> None:
    """사이드별 정확히 5명, 중복 없음, 새로 넣은 사람은 이 팀의 활동 중인 참가자. 위반은 400 / 422.

    `kept` = 이 쿼터에 이미 기록돼 있던 사람. 그 뒤 팀을 떠났거나 회원에게 이어 준 게스트여도 기록은 그대로 두어야
    하므로 다시 검사하지 않는다 — 검사하면 지난 경기의 점수 하나만 고쳐도 저장이 막힌다."""
    for side in (Side.BLACK, Side.WHITE):
        n = sum(1 for lineup in lineups if lineup.side == side)
        if n != 5:
            raise errors.InvalidLineupSize(f"{SIDE_LABEL[side]} 팀 {n}명이 선택되었어요. 팀당 5명이어야 해요.")
    ids = [lineup.player_id for lineup in lineups]
    if len(set(ids)) != len(ids):
        raise errors.ValidationError("같은 사람이 두 번 들어 있어요.")
    new_ids = [pid for pid in ids if pid not in kept]
    if not new_ids:
        return
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_(new_ids), Player.team_id == event.team_id, Player.status == PlayerStatus.ACTIVE)).all()}
    missing = [pid for pid in new_ids if pid not in players]
    if missing:
        raise errors.PlayerNotInTeam(details=[ErrorDetail(field="lineups", reason=f"이 팀에 없는 사람이 {len(missing)}명 있어요.")])
    # 회원 계정에 병합된 게스트 행은 쓸 수 없다 — 같은 사람이 두 번 세어진다. 회원 행(id)을 대신 넣어야 한다
    merged = [pid for pid, p in players.items() if p.merged_into_player_id is not None]
    if merged:
        raise errors.PlayerNotInTeam(
            "기록을 이미 팀원에게 이어 준 게스트예요. 팀원 이름으로 넣어 주세요.",
            details=[ErrorDetail(field="lineups", reason=f"이어 준 게스트 {len(merged)}명이 들어 있어요.")],
        )


def _apply(
    db: Session, q: Quarter, event: Event, *, black_score: int, white_score: int, duration_min: int, lineups: list[LineupIn] | None,
    home: int = 1, away: int = 2, names: dict[int, str] | None = None,
) -> None:
    _validate_matchup(db, event, home, away, names)
    q.black_score, q.white_score, q.duration_min = black_score, white_score, duration_min
    q.home_squad_no, q.away_squad_no = home, away
    if lineups is not None and {(x.player_id, x.side, x.position) for x in lineups} != {(x.player_id, x.side, x.position) for x in q.lineups}:
        # 라인업이 그대로면 검사 · 다시 넣기를 건너뛰고 마진만 다시 계산한다 (지난 쿼터 점수만 고치는 흔한 경우)
        _validate_lineups(db, event, lineups, kept=frozenset(x.player_id for x in q.lineups))
        for old in list(q.lineups):
            db.delete(old)
        db.flush()
        q.lineups = [
            QuarterLineup(
                player_id=lineup.player_id, side=lineup.side, position=lineup.position,
                raw_margin=0, normalized_margin=0,
            )
            for lineup in lineups
        ]
    # 마진은 스코어·길이가 바뀔 때마다 10명 전원 다시 계산 (6.2절 코트 마진 계산)
    for lineup in q.lineups:
        raw = (q.black_score - q.white_score) if lineup.side == Side.BLACK else (q.white_score - q.black_score)
        lineup.raw_margin = raw
        lineup.normalized_margin = rating_service.normalized_margin(raw, q.duration_min)
    db.flush()


def _sync_event_status(db: Session, event: Event) -> None:
    """쿼터가 있으면 DONE(경기 종료), 전부 지워지면 CLOSED 로 되돌린다."""
    count = db.scalar(select(Quarter.id).where(Quarter.event_id == event.id).limit(1))
    if count and event.status in (EventStatus.OPEN, EventStatus.CLOSED):
        event.status = EventStatus.DONE
    elif not count and event.status == EventStatus.DONE:
        event.status = EventStatus.CLOSED


def _finish(db: Session, event: Event) -> None:
    _sync_event_status(db, event)
    rating_service.recompute_team(db, event.team_id)
    db.commit()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def _guard(db: Session, event: Event) -> None:
    """쓰기 경로 공통 — 취소된 일정 거부, 그리고 첫 쓰기 전에 팀 잠금 (모듈 docstring 의 잠금 순서)."""
    if event.status == EventStatus.CANCELED:
        raise errors.ValidationError("취소된 일정에는 기록을 남길 수 없어요.")
    lock_team_stats(db, event.team_id)


def add_quarter(db: Session, event: Event, by: User, body: QuarterIn) -> Quarter:
    _guard(db, event)
    if db.scalar(select(Quarter.id).where(Quarter.event_id == event.id, Quarter.quarter_no == body.quarter_no)):
        raise errors.QuarterExists(f"{body.quarter_no}쿼터는 이미 기록했어요. 고치려면 기록 화면에서 저장해 주세요.")
    q = Quarter(event_id=event.id, quarter_no=body.quarter_no, black_score=0, white_score=0, duration_min=body.duration_min, recorded_by=by.id)
    db.add(q)
    db.flush()
    _apply(db, q, event, black_score=body.black_score, white_score=body.white_score, duration_min=body.duration_min, lineups=body.lineups,
           home=body.home_squad_no, away=body.away_squad_no)
    _finish(db, event)
    return _load(db, q.id)


def bulk_save(db: Session, event: Event, by: User, body: QuarterBulkSave) -> QuarterBulkResult:
    """목록이 그 회차 쿼터의 전체 상태가 된다: quarter_no 기준 있으면 수정, 없으면 생성, 빠지면 삭제."""
    _guard(db, event)
    nos = [q.quarter_no for q in body.quarters]
    if len(set(nos)) != len(nos):
        raise errors.ValidationError("같은 쿼터 번호가 두 번 들어 있어요.")
    existing = {q.quarter_no: q for q in db.scalars(select(Quarter).where(Quarter.event_id == event.id).options(selectinload(Quarter.lineups))).all()}
    created = updated = deleted = 0
    names = _squad_names(db, event)
    for item in body.quarters:
        q = existing.get(item.quarter_no)
        if q is None:
            q = Quarter(event_id=event.id, quarter_no=item.quarter_no, black_score=0, white_score=0, duration_min=item.duration_min, recorded_by=by.id)
            db.add(q)
            db.flush()
            created += 1
        else:
            q.recorded_by = by.id
            updated += 1
        _apply(db, q, event, black_score=item.black_score, white_score=item.white_score, duration_min=item.duration_min, lineups=item.lineups,
               home=item.home_squad_no, away=item.away_squad_no, names=names)
    for no, q in existing.items():
        if no not in set(nos):
            db.delete(q)
            deleted += 1
    db.flush()
    _finish(db, event)
    return QuarterBulkResult(created=created, updated=updated, deleted=deleted)


def update_quarter(db: Session, q: Quarter, body: QuarterUpdate) -> Quarter:
    event = db.get(Event, q.event_id)
    _guard(db, event)
    _apply(
        db, q, event,
        black_score=body.black_score if body.black_score is not None else q.black_score,
        white_score=body.white_score if body.white_score is not None else q.white_score,
        duration_min=body.duration_min if body.duration_min is not None else q.duration_min,
        lineups=body.lineups,
        home=body.home_squad_no if body.home_squad_no is not None else q.home_squad_no,
        away=body.away_squad_no if body.away_squad_no is not None else q.away_squad_no,
    )
    _finish(db, event)
    return _load(db, q.id)


def delete_quarter(db: Session, q: Quarter) -> None:
    event = db.get(Event, q.event_id)
    lock_team_stats(db, event.team_id)  # 지우기 전에 (취소된 일정의 기록도 지울 수는 있어야 하므로 _guard 는 쓰지 않는다)
    db.delete(q)
    db.flush()
    _finish(db, event)


# ---------------------------------------------------------------------------
# 조회
# ---------------------------------------------------------------------------


def _load(db: Session, quarter_id: int) -> Quarter:
    q = db.get(Quarter, quarter_id, options=[selectinload(Quarter.lineups)], populate_existing=True)
    if q is None:
        raise errors.NotFound("쿼터를 찾을 수 없어요.")
    return q


def get_quarter(db: Session, quarter_id: int) -> Quarter:
    return _load(db, quarter_id)


def quarter_view(db: Session, q: Quarter, names: dict[int, str] | None = None) -> QuarterView:
    if names is None:
        ids = [lineup.player_id for lineup in q.lineups]
        names = dict(db.execute(select(Player.id, Player.display_name).where(Player.id.in_(ids))).all())
    lineups = sorted(q.lineups, key=lambda lineup: (lineup.side != Side.BLACK, names.get(lineup.player_id, "")))
    return QuarterView(
        id=q.id, quarter_no=q.quarter_no, black_score=q.black_score, white_score=q.white_score, duration_min=q.duration_min,
        home_squad_no=q.home_squad_no, away_squad_no=q.away_squad_no,
        lineups=[
            LineupView(player_id=lineup.player_id, display_name=names.get(lineup.player_id, "?"), side=lineup.side, position=lineup.position, raw_margin=lineup.raw_margin, normalized_margin=lineup.normalized_margin)
            for lineup in lineups
        ],
    )


def list_quarters(db: Session, event: Event) -> QuarterListView:
    quarters = db.scalars(select(Quarter).where(Quarter.event_id == event.id).options(selectinload(Quarter.lineups)).order_by(Quarter.quarter_no)).all()
    ids = {lineup.player_id for q in quarters for lineup in q.lineups}
    names = dict(db.execute(select(Player.id, Player.display_name).where(Player.id.in_(ids))).all()) if ids else {}
    counts: dict[int, PlayerQuarterCount] = {}
    squad_names = _squad_names(db, event)
    tally = {no: SquadTally(squad_no=no, squad_name=nm, quarters=0, points_for=0, points_against=0, wins=0, losses=0) for no, nm in sorted(squad_names.items())}
    for q in quarters:
        for lineup in q.lineups:
            sq = q.home_squad_no if lineup.side == Side.BLACK else q.away_squad_no
            c = counts.setdefault(lineup.player_id, PlayerQuarterCount(player_id=lineup.player_id, display_name=names.get(lineup.player_id, "?"), side=lineup.side, squad_no=sq, quarters=0))
            c.quarters += 1
            c.side, c.squad_no = lineup.side, sq  # 마지막으로 뛴 팀
        for mine, score, other in ((q.home_squad_no, q.black_score, q.white_score), (q.away_squad_no, q.white_score, q.black_score)):
            t = tally.setdefault(mine, SquadTally(squad_no=mine, squad_name=DEFAULT_SQUAD_NAMES[(mine - 1) % len(DEFAULT_SQUAD_NAMES)], quarters=0, points_for=0, points_against=0, wins=0, losses=0))
            t.quarters += 1
            t.points_for += score
            t.points_against += other
            t.wins += score > other
            t.losses += score < other
    summary = QuarterSummary(
        quarter_count=len(quarters),
        black_total=sum(q.black_score for q in quarters),
        white_total=sum(q.white_score for q in quarters),
        black_wins=sum(1 for q in quarters if q.black_score > q.white_score),
        white_wins=sum(1 for q in quarters if q.white_score > q.black_score),
        per_player=sorted(counts.values(), key=lambda c: (c.squad_no, -c.quarters, c.display_name)),
        team_count=len(squad_names),
        squads=[tally[no] for no in sorted(tally)],
    )
    return QuarterListView(items=[quarter_view(db, q, names) for q in quarters], summary=summary)
