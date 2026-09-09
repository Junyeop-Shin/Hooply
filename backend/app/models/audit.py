"""운영: audit_logs — 관리자 보정 등 민감 조작 이력 (설계서 6.1절 "운영" 그룹, 7.3절 관리자 API).

누가(actor) 무엇을(target) 어떻게(before → after) 왜(reason) 바꿨는지를 append-only 로 남긴다.
`GET /admin/audit-logs` 가 이 테이블을 읽는다. 기록 대상의 예:
  - 관리자 실력 지표 수동 보정 (`PATCH /admin/players/{id}/rating`) — skill_rating_history 와 함께 기록
  - 팀 강제 비활성화, 계정 정지
  - 게스트→회원 병합 / 병합 되돌리기
일반적인 CRUD 는 기록하지 않는다. "되돌릴 필요가 생길 수 있는 사람의 판단" 만 남기는 것이 목적이다.

skill_rating_history 와의 차이: 그쪽은 실력값 한 컬럼의 변동만 담는 도메인 이력이고, 여기는 어떤
테이블이든 대상이 될 수 있는 범용 감사 로그다.
"""

from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPK, CreatedAtMixin


class AuditLog(CreatedAtMixin, Base):
    """감사 로그 한 줄. 대상은 (target_type, target_id) 다형 참조이며 FK 를 걸지 않는다.

    FK 가 없는 이유: 대상 행이 나중에 삭제되어도 "삭제됐다는 사실" 을 포함한 이력은 남아야 하기 때문.
    before/after 는 변경 전후 값의 JSON 스냅샷이라 원본이 사라져도 내용을 복원할 수 있다.
    """

    __tablename__ = "audit_logs"
    # "이 선수/팀에 무슨 조작이 있었나" 조회용
    __table_args__ = (Index("ix_audit_logs_target", "target_type", "target_id"),)

    id: Mapped[BigPK]
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # 조작한 사람. 배치/시스템이면 NULL
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # 예: ADMIN_RATING_ADJUST
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)  # 대상 테이블명. 예: player / team / user
    target_id: Mapped[int | None]  # 대상 행의 id. 대상이 특정 행이 아닌 조작이면 NULL
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # 변경 전 필드 스냅샷. 생성 조작이면 NULL
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # 변경 후 필드 스냅샷. 삭제 조작이면 NULL
    reason: Mapped[str | None] = mapped_column(Text)  # 조작 사유 (관리자 폼에서 입력)
