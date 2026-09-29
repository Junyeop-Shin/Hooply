"""모든 모델을 한 곳에서 import해 Base.metadata에 등록한다 (Alembic autogenerate용).

SQLAlchemy 는 모델 클래스가 import 되어야 `Base.metadata` 에 테이블이 등록된다. 이 패키지를
import 하는 것만으로 설계서 6장 ERD 의 28개 테이블이 전부 등록되도록 여기에 모아 두었다.
  - alembic/env.py 는 `from app.models import Base` 한 줄로 전체 스키마를 인식한다.
  - 서비스·라우터 코드는 `from app.models import Player, Team` 처럼 이 패키지에서 가져오면 된다.

파일 ↔ 설계서 6.1절 엔터티 그룹 대응
  account.py    계정·인증   users / auth_identities / password_reset_tokens
  team.py       팀·참가자   teams / players
  profile.py    프로필      player_profiles / player_positions / skill_rating_history
  ranking.py    매니저 판단 manager_rankings / manager_ranking_entries
  survey.py     설문        survey_templates / questions / options / responses / answers
  event.py      일정        events / event_attendances
  assignment.py 배정        assignment_runs / constraints / candidates / squads / slots
  game.py       경기        quarters / quarter_lineups
  peer.py       피어 평가   post_game_surveys / post_game_votes / chemistry_scores
  audit.py      운영        audit_logs
  tactic.py     전술        event_play_assignments (전술 이름표)
  enums.py      위 테이블들이 쓰는 VARCHAR 열거값 정의

주의: import 순서는 relationship 문자열 참조("PlayerProfile" 등)가 해석될 때 모든 클래스가
이미 로드되어 있기만 하면 되므로 알파벳순으로 유지한다. 순환 import 를 피하기 위해 모델 모듈끼리는
필요한 경우에만 서로 import 한다 (예: profile.py → team.py).
"""

from app.db.base import Base
from app.models.account import AuthIdentity, PasswordResetToken, RevokedToken, User, UserAvatar
from app.models.assignment import (
    AssignmentCandidate,
    AssignmentConstraint,
    AssignmentRun,
    AssignmentSlot,
    AssignmentSquad,
)
from app.models.audit import AuditLog
from app.models.badge import UserBadge
from app.models.event import Event, EventAttendance
from app.models.game import Quarter, QuarterLineup
from app.models.peer import ChemistryScore, PostGameSurvey, PostGameVote
from app.models.profile import PlayerPosition, PlayerProfile, SkillRatingHistory
from app.models.ranking import ManagerRanking, ManagerRankingEntry
from app.models.survey import (
    SurveyAnswer,
    SurveyOption,
    SurveyQuestion,
    SurveyResponse,
    SurveyTemplate,
)
from app.models.tactic import EventPlayAssignment
from app.models.team import GuestClaim, GuestInvitePreset, Player, Team

# 외부에 공개하는 이름 목록. `from app.models import *` 와 정적 분석 도구가 참조한다.
__all__ = [
    "AssignmentCandidate",
    "AssignmentConstraint",
    "AssignmentRun",
    "AssignmentSlot",
    "AssignmentSquad",
    "AuditLog",
    "AuthIdentity",
    "Base",
    "ChemistryScore",
    "Event",
    "EventAttendance",
    "EventPlayAssignment",
    "GuestClaim",
    "GuestInvitePreset",
    "ManagerRanking",
    "ManagerRankingEntry",
    "PasswordResetToken",
    "Player",
    "PlayerPosition",
    "PlayerProfile",
    "PostGameSurvey",
    "PostGameVote",
    "Quarter",
    "QuarterLineup",
    "RevokedToken",
    "SkillRatingHistory",
    "SurveyAnswer",
    "SurveyOption",
    "SurveyQuestion",
    "SurveyResponse",
    "SurveyTemplate",
    "Team",
    "User",
    "UserAvatar",
    "UserBadge",
]
