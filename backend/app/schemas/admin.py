"""관리자 콘솔 스키마 — 7.3절 "관리자" 엔드포인트의 요청/응답 (F12, S-18). **ADMIN 전용**.

대상 엔드포인트: GET /admin/users, GET /admin/players/{id}/raw, PATCH /admin/players/{id}/rating,
GET /admin/audit-logs. 전역 권한 `users.global_role = ADMIN` 이 아니면 403 FORBIDDEN_ROLE.

일반 CRUD 화면은 SQLAdmin 이 대신하므로(11.4절), 여기에는 SQLAdmin 으로 표현하기 어려운
"선수 원시 데이터 한 화면에 모아 보기"와 "이력을 남기는 지표 보정"만 있다.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AdminUserRow(ORMModel):
    """사용자 테이블 한 줄 — `GET /admin/users?q=&page=&size=` 의 `Page.items` 원소.

    탈퇴(soft delete) 계정도 포함해서 보여준다. 비밀번호 해시는 절대 포함하지 않는다.
    """

    id: int
    email: str | None = Field(description="카카오 전용 계정이면 None")
    name: str
    nickname: str | None
    global_role: str = Field(description="ADMIN / USER")
    onboarding_completed: bool
    created_at: datetime
    deleted_at: datetime | None = Field(description="soft delete 시각. 살아 있는 계정은 None")


class PlayerRawData(BaseModel):
    """선수 원시 데이터 전체 — `GET /admin/players/{id}/raw` (3.2절 ADMIN "원시 데이터 전체 열람").

    이상치 보정·문의 대응용으로 관련 테이블을 그대로 덤프한다. 형태를 `dict` 로 둔 것은 열이
    바뀔 때마다 스키마를 고치지 않기 위해서다. 화면에 쓰는 정형 응답이 아니라 조사용이다.
    """

    player: dict[str, Any] = Field(description="players 행 (merged_into_player_id 포함)")
    profile: dict[str, Any] | None = Field(description="player_profiles 행. 프로필이 없으면 None")
    survey_answers: list[dict[str, Any]] = Field(description="온보딩 설문 응답 원본")
    lineups: list[dict[str, Any]] = Field(description="quarter_lineups 전체 (쿼터별 마진 이력)")
    votes_received: list[dict[str, Any]] = Field(description="post_game_votes 중 이 선수를 대상으로 한 것")
    rating_history: list[dict[str, Any]] = Field(description="skill_rating_history — 실력 지표 변동 이력 (source 별)")


class RatingAdjust(BaseModel):
    """실력 지표 수동 보정 — `PATCH /admin/players/{id}/rating`.

    `player_profiles.skill_overall` 을 덮어쓰고 `skill_rating_history` 에 source=ADMIN_ADJUST 로
    before/after/reason 을 남긴다. 그래서 사유는 필수다. `audit_logs` 에도 기록된다.
    """

    skill_overall: Decimal = Field(description="새 종합 실력 값 (점/쿼터 단위, 9.2절)")
    reason: str = Field(min_length=1, description="보정 사유. 이력에 그대로 남는다")


class AuditLogView(ORMModel):
    """감사 로그 한 줄 — `GET /admin/audit-logs` 의 `Page.items` 원소 (6.1절 `audit_logs`).

    지표 보정, 계정 정지, 팀 강제 비활성화 같은 민감 조작만 기록한다.
    """

    id: int
    actor_user_id: int | None = Field(description="조작한 사람의 users.id. 시스템 배치면 None")
    action: str = Field(description="조작 종류 (예: RATING_ADJUST)")
    target_type: str = Field(description="대상 테이블/엔터티 이름 (예: player)")
    target_id: int | None = Field(description="대상 행 id")
    before: dict[str, Any] | None = Field(description="변경 전 값 스냅샷")
    after: dict[str, Any] | None = Field(description="변경 후 값 스냅샷")
    reason: str | None
    created_at: datetime
