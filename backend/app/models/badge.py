"""배지: user_badges — 서비스 사용을 유도하는 작은 성취 표시 (기록 탭).

배지는 실력을 겨루지 않는다. "팀에 들어왔다 · 설문을 마쳤다 · 투표했다 · 꾸준히 나왔다" 처럼 **행동**만 센다.
사용자 단위로 둔다 — 두 팀을 다니는 사람의 참석 25회를 팀별로 따로 세면 억울하고, 설문·팀 가입 같은
시작 배지는 애초에 팀과 무관하다. 판정은 `badge_service.sync()` 가 기록 탭을 열 때 한다 (별도 알림 없음).
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigPK


class UserBadge(Base):
    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_badges_code"),)

    id: Mapped[BigPK]
    # user_id 조회는 uq_user_badges_code(user_id 가 맨 앞)가 맡는다 — 단독 인덱스는 0025 에서 지웠다
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)  # badge_service.BADGES 의 코드
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa_text("now()"))
