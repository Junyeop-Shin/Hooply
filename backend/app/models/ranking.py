"""매니저 실력 정렬 (F14): manager_rankings / manager_ranking_entries. 덮어쓰지 않고 버전으로 쌓는다.

설계서 6.2절 · 8.5절. 매니저가 S-19 화면에서 팀원 카드를 드래그해 실력 순서를 매기면 그 결과를 저장한다.
사람은 절대 점수보다 순서 판단에 강하므로, 이 2분짜리 작업이 초기 6개월 배정 품질을 좌우한다
(설문 ρ 0.5 → 0.8 이면 팀 균형 36% 개선).

저장 방식: `POST /teams/{id}/rankings` 가 호출될 때마다 새 `manager_rankings` 행(버전)을 만들고, 그 아래에
선수별 `manager_ranking_entries` 를 넣는다. 이전 버전은 지우지 않는다 — 매니저가 바뀌거나 정렬이
이상해졌을 때 되돌릴 수 있어야 하고, 정렬 자체가 사전값 품질을 추적하는 자료가 되기 때문이다.

사전값 결합 (8.5절): prior_final_z = 0.5 × 설문 z + 0.5 × 정렬 순위 z. 정렬에 없는 신규 가입자는
설문값만 쓰다가 다음 정렬 때 편입된다.
"""

from sqlalchemy import Boolean, ForeignKey, SmallInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigPK, CreatedAtMixin


class ManagerRanking(CreatedAtMixin, Base):
    """정렬 한 버전(스냅샷). teams 1:N. `created_at` 이 곧 정렬 시각(ranked_at)이다.

    `GET /teams/{id}/rankings/latest` 는 is_active 인 것 중 가장 최근 버전을 돌려준다.
    """

    __tablename__ = "manager_rankings"

    id: Mapped[BigPK]
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    ranked_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)  # 정렬을 수행한 매니저
    # false 면 무효화된 버전 (되돌리기). DB 는 활성 버전 수를 제한하지 않으며, 최신 활성본을 쓴다
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)

    # rank_no 오름차순(상위 → 하위)으로 정렬되어 로드된다
    entries: Mapped[list["ManagerRankingEntry"]] = relationship(
        back_populates="ranking", cascade="all, delete-orphan", order_by="ManagerRankingEntry.rank_no"
    )


class ManagerRankingEntry(Base):
    """정렬 버전 안의 선수 한 명의 순위. (ranking_id, player_id) 와 (ranking_id, rank_no) 가 모두 유일하다.

    API 요청 `{player_ids: [상위→하위]}` 의 배열 인덱스+1 이 rank_no 가 된다.
    player_id 는 팀 소속이어야 하며(422 PLAYER_NOT_IN_TEAM), 게스트도 포함할 수 있다.
    """

    __tablename__ = "manager_ranking_entries"
    __table_args__ = (
        # 한 버전 안에서 같은 선수가 두 번 나오지 않도록
        UniqueConstraint("ranking_id", "player_id", name="uq_ranking_entries_player"),
        # 한 버전 안에서 같은 순위가 두 명에게 붙지 않도록 (동점 없음, 완전 서열)
        UniqueConstraint("ranking_id", "rank_no", name="uq_ranking_entries_rank_no"),
    )

    id: Mapped[BigPK]
    ranking_id: Mapped[int] = mapped_column(
        ForeignKey("manager_rankings.id", ondelete="CASCADE"), nullable=False
    )
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False)
    rank_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)  # 1 = 최상위

    ranking: Mapped[ManagerRanking] = relationship(back_populates="entries")
