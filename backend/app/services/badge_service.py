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


@dataclass(frozen=True)
class Badge:
    code: str
    group: Group
    title: str
    description: str
    metric: str  # counters() 의 키
    threshold: int


BADGES: tuple[Badge, ...] = (
    # 시작 — 앱을 쓰기 시작하면 바로 얻는 것들. 다음 할 일을 알려 주는 역할
    Badge("JOIN_TEAM", "START", "첫 팀", "팀 코드로 팀에 들어왔어요", "teams", 1),
    Badge("SURVEY_DONE", "START", "설문 완료", "실력·포지션 설문을 마쳤어요", "survey", 1),
    Badge("SELF_RANK_DONE", "START", "내 위치 응답", "이 동호회에서 내 실력 위치를 알려 줬어요", "self_rank", 1),
    Badge("FIRST_RSVP", "START", "첫 참석 응답", "일정에 참석/불참을 처음 답했어요", "rsvp", 1),
    # 활동 — 참석과 출전. 둘은 같은 행동이라 한 묶음
    Badge("FIRST_QUARTER", "ACTIVITY", "첫 출전", "쿼터 기록에 처음 이름이 올랐어요", "quarters", 1),
    Badge("QUARTERS_10", "ACTIVITY", "출전 10쿼터", "쿼터 10개를 뛰었어요", "quarters", 10),
    Badge("QUARTERS_50", "ACTIVITY", "출전 50쿼터", "쿼터 50개를 뛰었어요", "quarters", 50),
    Badge("QUARTERS_100", "ACTIVITY", "출전 100쿼터", "쿼터 100개를 뛰었어요", "quarters", 100),
    Badge("ATTEND_5", "ACTIVITY", "참석 5회", "일정에 5번 나왔어요", "attended", 5),
    Badge("ATTEND_10", "ACTIVITY", "참석 10회", "일정에 10번 나왔어요", "attended", 10),
    Badge("ATTEND_25", "ACTIVITY", "참석 25회", "일정에 25번 나왔어요", "attended", 25),
    Badge("STREAK_3", "ACTIVITY", "3회 연속 참석", "한 팀 일정에 3번 연속으로 나왔어요", "streak", 3),
    # 관계 — 투표하고, 지목받고, 사람을 데려오는 것
    Badge("FIRST_VOTE", "RELATION", "첫 투표", "경기 후 투표에 처음 응답했어요", "votes", 1),
    Badge("VOTES_5", "RELATION", "투표 5회", "경기 후 투표에 5번 응답했어요", "votes", 5),
    Badge("PLAY_AGAIN_1", "RELATION", "또 뛰고 싶은 사람", "'다음에 같이 뛰고 싶은 사람'으로 처음 지목받았어요", "play_again", 1),
    Badge("PLAY_AGAIN_5", "RELATION", "인기 동료", "'다음에 같이 뛰고 싶은 사람'으로 5번 지목받았어요", "play_again", 5),
    Badge("PLAY_AGAIN_10", "RELATION", "모두의 동료", "'다음에 같이 뛰고 싶은 사람'으로 10번 지목받았어요", "play_again", 10),
    Badge("MUTUAL_3", "RELATION", "서로 뽑은 사이 3명", "서로 지목한 사람이 3명이에요", "mutual", 3),
    Badge("GUEST_CONVERTED", "RELATION", "게스트를 팀원으로", "내가 부른 게스트가 가입해 기록을 이어받았어요", "guest_converted", 1),
)
BY_CODE = {b.code: b for b in BADGES}


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
    new = [UserBadge(user_id=user.id, code=b.code) for b in BADGES if b.code not in earned and c[b.metric] >= b.threshold]
    if new:
        db.add_all(new)
        db.commit()
        for row in new:
            earned[row.code] = row.earned_at
    return [
        BadgeView(code=b.code, group=b.group, title=b.title, description=b.description, threshold=b.threshold,
                  progress=min(c[b.metric], b.threshold) if b.code in earned else c[b.metric], earned_at=earned.get(b.code))
        for b in BADGES
    ]
