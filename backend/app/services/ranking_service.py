"""매니저 실력 정렬 (F14 · 설계서 8.5절).

매니저가 팀원 카드를 실력 순으로 늘어놓은 결과를 **버전**으로 쌓는다 (덮어쓰지 않는다 — 6.2절
manager_rankings 설명). 새 버전을 저장하면 이전 버전은 is_active=false 가 되고, 활성 버전의 순위가
z-score 로 바뀌어 사전 실력값의 절반을 차지한다 (`prior_final_z = 0.5·설문 + 0.5·정렬`).
순위 → z 변환과 prior 갱신은 survey_service.recompute_team_priors 가 담당한다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import errors
from app.core.errors import ErrorDetail
from app.db.session import lock_team_stats
from app.models import ManagerRanking, ManagerRankingEntry, Player, Team, User
from app.models.enums import PlayerStatus
from app.schemas.team import RankingEntryView, RankingView
from app.services import survey_service
from app.services.player_service import to_card


def _players(db: Session, ids: set[int]) -> dict[int, Player]:
    return {
        p.id: p
        for p in db.scalars(
            select(Player).where(Player.id.in_(ids)).options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user))
        ).all()
    }


def _load(db: Session, ranking: ManagerRanking, players: dict[int, Player] | None = None) -> RankingView:
    if players is None:
        players = _players(db, {e.player_id for e in ranking.entries})
    return RankingView(
        id=ranking.id, ranked_at=ranking.created_at, ranked_by=ranking.ranked_by, is_active=ranking.is_active,
        entries=[RankingEntryView(rank_no=e.rank_no, player=to_card(players[e.player_id])) for e in sorted(ranking.entries, key=lambda x: x.rank_no) if e.player_id in players],
    )


def latest(db: Session, team: Team) -> RankingView:
    r = db.scalar(
        select(ManagerRanking).where(ManagerRanking.team_id == team.id, ManagerRanking.is_active.is_(True))
        .options(selectinload(ManagerRanking.entries)).order_by(ManagerRanking.created_at.desc())
    )
    if r is None:
        raise errors.NoRanking()
    return _load(db, r)


def history(db: Session, team: Team) -> list[RankingView]:
    rows = db.scalars(
        select(ManagerRanking).where(ManagerRanking.team_id == team.id)
        .options(selectinload(ManagerRanking.entries)).order_by(ManagerRanking.created_at.desc())
    ).all()
    players = _players(db, {e.player_id for r in rows for e in r.entries})  # 버전마다 따로 읽지 않고 한 번에
    return [_load(db, r, players) for r in rows]


def create(db: Session, team: Team, by: User, player_ids: list[int]) -> RankingView:
    """새 정렬 버전 저장. 중복 id 나 이 팀의 활성 참가자가 아닌 id 가 있으면 422 PLAYER_NOT_IN_TEAM."""
    if len(set(player_ids)) != len(player_ids):
        raise errors.ValidationError("같은 사람이 두 번 들어 있어요.")
    valid = set(
        db.scalars(
            select(Player.id).where(Player.team_id == team.id, Player.status == PlayerStatus.ACTIVE, Player.id.in_(player_ids))
        ).all()
    )
    bad = [pid for pid in player_ids if pid not in valid]
    if bad:
        raise errors.PlayerNotInTeam(details=[ErrorDetail(field="player_ids", reason=f"이 팀에 없는 사람이 {len(bad)}명 있어요.")])
    lock_team_stats(db, team.id)  # 정렬을 쓰기 전에 — 뒤따르는 사전값 · 지표 재계산과 잠금 순서를 맞춘다
    for old in db.scalars(select(ManagerRanking).where(ManagerRanking.team_id == team.id, ManagerRanking.is_active.is_(True))).all():
        old.is_active = False
    db.flush()  # 팀당 활성 버전은 하나 (uq_manager_rankings_active) — 새 버전을 넣기 전에 이전 것을 먼저 끈다
    ranking = ManagerRanking(team_id=team.id, ranked_by=by.id, is_active=True)
    ranking.entries = [ManagerRankingEntry(player_id=pid, rank_no=i + 1) for i, pid in enumerate(player_ids)]
    db.add(ranking)
    db.flush()
    survey_service.recompute_team_priors(db, team.id)
    db.commit()
    db.refresh(ranking)
    return _load(db, ranking)
