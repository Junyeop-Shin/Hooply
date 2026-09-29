"""7.3절 엔드포인트를 명세 순서대로 묶는다."""

from fastapi import APIRouter

from app.api.v1 import (
    admin,
    ai,
    assignments,
    auth,
    events,
    guests,
    peer,
    quarters,
    rankings,
    surveys,
    tactics,
    team_plays,
    teams,
    tutorial,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(surveys.router)
api_router.include_router(teams.router)
api_router.include_router(guests.router)
api_router.include_router(rankings.router)
api_router.include_router(events.router)
api_router.include_router(assignments.router)
api_router.include_router(quarters.router)
api_router.include_router(peer.router)
api_router.include_router(tutorial.router)
api_router.include_router(tactics.router)
api_router.include_router(team_plays.router)
api_router.include_router(ai.router)
api_router.include_router(admin.router)
