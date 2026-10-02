"""배지 — 서비스 사용을 유도하는 행동 성취 (기록 탭). 실력은 겨루지 않는다.

정본은 아래 BADGES 목록이다. DB(`user_badges`)는 "언제 얻었나" 만 기억하므로 기준을 낮춰도 이미 얻은 배지는 남고,
기준을 올려도 회수하지 않는다. 판정은 기록 탭을 열 때(`GET /me/badges`) 한 번에 한다 — 쿼터 저장처럼 남이 내
기록을 만드는 순간마다 10명씩 검사하지 않아도 되고, 자랑·알림 기능이 없으므로 그때 얻어도 늦지 않다.
집계는 사용자 단위: 내 모든 `players` 행(여러 팀)과 나로 병합된 게스트 행까지 합쳐 센다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    ChemistryScore,
    Event,
    EventAttendance,
    Player,
    PlayerProfile,
    PostGameSurvey,
    PostGameVote,
    QuarterLineup,
    User,
    UserBadge,
)
from app.models.enums import AttendanceStatus, EventStatus, PlayerKind, PlayerStatus, VoteType
from app.schemas.peer import BadgeView

Group = Literal["START", "ACTIVITY", "RELATION"]
Tier = Literal["BRONZE", "SILVER", "GOLD"]


@dataclass(frozen=True)
class Badge:
    code: str
    group: Group
    title: str
    description: str
    metric: str  # counters() 의 키
    threshold: int
    # 같은 행동을 쌓는 배지는 한 묶음(series)으로 동·은·금이 된다. 화면은 묶음 하나를 칸 하나로 보여 준다.
    # 아이콘 그림은 docs/badges/badge_art.py 의 SERIES / SINGLES 가 이 키·코드로 고른다
    series: str | None = None
    tier: Tier | None = None


BADGES: tuple[Badge, ...] = (
    # 시작 — 앱을 쓰기 시작하면 바로 얻는 것들. 다음 할 일을 알려 주는 역할
    Badge("JOIN_TEAM", "START", "첫 팀", "팀 코드로 팀에 들어왔어요", "teams", 1),
    Badge("SURVEY_DONE", "START", "설문 완료", "실력·포지션 설문을 마쳤어요", "survey", 1),
    Badge("SELF_RANK_DONE", "START", "내 위치 응답", "이 동호회에서 내 실력 위치를 알려 줬어요", "self_rank", 1),
    Badge("FIRST_RSVP", "START", "첫 참석 응답", "일정에 참석/불참을 처음 답했어요", "rsvp", 1),
    # 활동 — 참석과 출전. 둘은 같은 행동이라 한 묶음
    Badge("FIRST_QUARTER", "ACTIVITY", "첫 출전", "쿼터 기록에 처음 이름이 올랐어요", "quarters", 1),
    Badge("QUARTERS_10", "ACTIVITY", "출전 10쿼터", "쿼터 10개를 뛰었어요", "quarters", 10, "QUARTERS", "BRONZE"),
    Badge("QUARTERS_50", "ACTIVITY", "출전 50쿼터", "쿼터 50개를 뛰었어요", "quarters", 50, "QUARTERS", "SILVER"),
    Badge("QUARTERS_100", "ACTIVITY", "출전 100쿼터", "쿼터 100개를 뛰었어요", "quarters", 100, "QUARTERS", "GOLD"),
    Badge("ATTEND_5", "ACTIVITY", "참석 5회", "일정에 5번 나왔어요", "attended", 5, "ATTEND", "BRONZE"),
    Badge("ATTEND_10", "ACTIVITY", "참석 10회", "일정에 10번 나왔어요", "attended", 10, "ATTEND", "SILVER"),
    Badge("ATTEND_25", "ACTIVITY", "참석 25회", "일정에 25번 나왔어요", "attended", 25, "ATTEND", "GOLD"),
    Badge("STREAK_3", "ACTIVITY", "연속 참석", "한 팀 일정에 3번 연속으로 나왔어요", "streak", 3),
    # 관계 — 투표하고, 지목받고, 사람을 데려오는 것
    Badge("FIRST_VOTE", "RELATION", "투표 1회", "경기 후 투표에 처음 응답했어요", "votes", 1, "VOTES", "BRONZE"),
    Badge("VOTES_5", "RELATION", "투표 5회", "경기 후 투표에 5번 응답했어요", "votes", 5, "VOTES", "SILVER"),
    Badge("VOTES_10", "RELATION", "투표 10회", "경기 후 투표에 10번 응답했어요", "votes", 10, "VOTES", "GOLD"),
    Badge("PLAY_AGAIN_1", "RELATION", "지목 1회", "'다음에 같이 뛰고 싶은 사람'으로 처음 지목받았어요", "play_again", 1, "PLAY_AGAIN", "BRONZE"),
    Badge("PLAY_AGAIN_5", "RELATION", "지목 5회", "'다음에 같이 뛰고 싶은 사람'으로 5번 지목받았어요", "play_again", 5, "PLAY_AGAIN", "SILVER"),
    Badge("PLAY_AGAIN_10", "RELATION", "지목 10회", "'다음에 같이 뛰고 싶은 사람'으로 10번 지목받았어요", "play_again", 10, "PLAY_AGAIN", "GOLD"),
    Badge("MUTUAL_3", "RELATION", "서로 뽑은 사이", "서로 지목한 사람이 3명이 됐어요", "mutual", 3),
    Badge("GUEST_CONVERTED", "RELATION", "게스트 영입", "내가 부른 게스트가 가입해 기록을 이어받았어요", "guest_converted", 1),
)


def _my_player_ids(db: Session, user: User) -> list[int]:
    """내 players 행(모든 팀, 상태 무관) + 나로 병합된 게스트 행. 기록은 이 id 들에 걸려 있다."""
    mine = list(db.scalars(select(Player.id).where(Player.user_id == user.id)).all())
    if not mine:
        return []
    merged = list(db.scalars(select(Player.id).where(Player.merged_into_player_id.in_(mine))).all())
    return mine + merged


def counters(db: Session, user: User) -> dict[str, int]:
    """배지 판정에 쓰는 행동 지표. 모든 팀을 합쳐 센다."""
    ids = _my_player_ids(db, user)
    today = datetime.now(ZoneInfo(get_settings().timezone)).date()
    c: dict[str, int] = {
        "teams": 0, "survey": int(bool(user.onboarding_completed)), "self_rank": 0, "rsvp": 0, "quarters": 0,
        "attended": 0, "streak": 0, "votes": 0, "play_again": 0, "mutual": 0, "guest_converted": 0,
    }
    c["guest_converted"] = db.scalar(
        select(func.count()).select_from(Player).where(Player.created_by == user.id, Player.kind == PlayerKind.GUEST, Player.merged_into_player_id.is_not(None))
    ) or 0
    if not ids:
        return c
    c["teams"] = db.scalar(
        select(func.count()).select_from(Player).where(Player.user_id == user.id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE)
    ) or 0
    c["self_rank"] = db.scalar(
        select(func.count()).select_from(PlayerProfile).where(PlayerProfile.player_id.in_(ids), PlayerProfile.self_rank_level.is_not(None))
    ) or 0
    c["rsvp"] = db.scalar(
        select(func.count()).select_from(EventAttendance).where(EventAttendance.player_id.in_(ids), EventAttendance.responded_at.is_not(None))
    ) or 0
    c["quarters"] = db.scalar(select(func.count()).select_from(QuarterLineup).where(QuarterLineup.player_id.in_(ids))) or 0
    # 참석 회차와 연속 참석: 팀별로 지난 일정을 날짜순으로 놓고 내 응답 행을 본다 (행이 없는 회차 = 가입 전, 연속을 끊지 않는다)
    rows = db.execute(
        select(Event.team_id, Event.event_date, Event.id, EventAttendance.status)
        .join(EventAttendance, EventAttendance.event_id == Event.id)
        .where(EventAttendance.player_id.in_(ids), Event.status != EventStatus.CANCELED, Event.event_date <= today)
        .order_by(Event.team_id, Event.event_date, Event.id)
    ).all()
    streak = best = 0
    prev_team = None
    for team_id, _d, _eid, st in rows:
        if team_id != prev_team:
            streak, prev_team = 0, team_id
        attended = st == AttendanceStatus.ATTEND
        c["attended"] += int(attended)
        streak = streak + 1 if attended else 0
        best = max(best, streak)
    c["streak"] = best
    c["votes"] = db.scalar(select(func.count()).select_from(PostGameSurvey).where(PostGameSurvey.respondent_player_id.in_(ids))) or 0
    c["play_again"] = db.scalar(
        select(func.count()).select_from(PostGameVote).where(PostGameVote.target_player_id.in_(ids), PostGameVote.vote_type == VoteType.PLAY_AGAIN)
    ) or 0
    c["mutual"] = db.scalar(
        select(func.count()).select_from(ChemistryScore)
        .where(or_(ChemistryScore.player_a_id.in_(ids), ChemistryScore.player_b_id.in_(ids)), ChemistryScore.pref_mutual.is_(True))
    ) or 0
    return c


def sync(db: Session, user: User) -> list[BadgeView]:
    """지표를 다시 세어 새로 충족한 배지를 저장하고, 전체 목록(획득·미획득 + 진행도)을 돌려준다."""
    c = counters(db, user)
    earned = {b.code: b.earned_at for b in db.scalars(select(UserBadge).where(UserBadge.user_id == user.id)).all()}
    new = [b.code for b in BADGES if b.code not in earned and c[b.metric] >= b.threshold]
    if new:
        # 기록 탭을 두 기기(또는 두 탭)에서 동시에 열어도 유니크 위반이 나지 않게 — 이미 있는 배지는 건너뛴다
        db.execute(pg_insert(UserBadge).values([{"user_id": user.id, "code": code} for code in new]).on_conflict_do_nothing(constraint="uq_user_badges_code"))
        db.commit()
        earned.update(dict(db.execute(select(UserBadge.code, UserBadge.earned_at).where(UserBadge.user_id == user.id, UserBadge.code.in_(new))).all()))
    return [
        BadgeView(code=b.code, group=b.group, title=b.title, description=b.description, threshold=b.threshold, series=b.series, tier=b.tier,
                  progress=min(c[b.metric], b.threshold) if b.code in earned else c[b.metric], earned_at=earned.get(b.code))
        for b in BADGES
    ]
