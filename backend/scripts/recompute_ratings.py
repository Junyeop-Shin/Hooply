"""팀 실력 지표를 다시 계산한다 — 쿼터별 기여도(quarter_lineups.residual) 백필용.

쿼터를 저장할 때마다 자동으로 도는 계산이지만, 계산식이나 저장 항목이 바뀐 뒤에는 한 번 돌려
기존 기록에도 반영해야 한다. 값이 바뀐 행만 쓰므로 여러 번 돌려도 안전하다.

    DATABASE_URL=postgresql+psycopg://... python -m scripts.recompute_ratings
    python -m scripts.recompute_ratings --team 4      특정 팀만
"""

from __future__ import annotations

import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Team
from app.services import rating_service


def main() -> None:
    only = None
    if "--team" in sys.argv:
        only = int(sys.argv[sys.argv.index("--team") + 1])
    with SessionLocal() as db:
        stmt = select(Team.id, Team.name).order_by(Team.id)
        if only is not None:
            stmt = stmt.where(Team.id == only)
        teams = db.execute(stmt).all()
        if not teams:
            print("대상 팀이 없어요.")
            return
        for tid, name in teams:
            result = rating_service.recompute_team(db, tid)
            db.commit()
            print(f"팀 {tid} {name} · 쿼터 {result['quarters']}개 (지표 반영 {result['rated']}개)")
    print("완료")


if __name__ == "__main__":
    main()
