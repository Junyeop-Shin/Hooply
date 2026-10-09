"""게스트 서비스 — 등록·검색·수정·권한·병합 (설계서 F13 · 게스트 기능 설계).

게스트는 `players(kind=GUEST, user_id=NULL)` 행이다. 계정이 없으므로 로그인·설문·투표는 못 하지만
배정·쿼터 기록·투표의 **대상**은 된다 (3.1절). 이 모듈은 그 행의 생애주기를 다룬다.

권한 (스펙 3절): 등록은 팀원 누구나. 수정·삭제는 **등록자 본인(`created_by`) 또는 팀 매니저**.
아니면 403 FORBIDDEN_NOT_OWNER.

실력 (9.5절): 등록자가 등급(1~5)을 주면 클럽 내 분위수로 환산해 prior_overall, confidence 0.25.
미지정이면 클럽 평균(0), confidence 0 — 배정 화면에 `?` 배지가 붙는다.

병합 (6.2절, 13.2절 3항): 게스트가 정식 가입하면 매니저가 게스트 행의 `merged_into_player_id` 에 회원 행을
적고 status=LEFT. 행을 합치지 않으므로 `unmerge` 로 되돌릴 수 있다. `merge_candidates()` 는 "이름이 같은
게스트–회원 쌍" 을 힌트로 찾아 주지만 자동 병합하지는 않는다 (동명이인 위험).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import errors
from app.db.session import lock_team_stats
from app.models import Player, PlayerPosition, PlayerProfile, SkillRatingHistory, Team, User
from app.models.enums import (
    GlobalRole,
    PlayerKind,
    PlayerStatus,
    Position,
    PriorSource,
    RatingSource,
    TeamRole,
)
from app.services.player_service import PLAYER_LOAD

GUEST_GRADE_CONFIDENCE = Decimal("0.25")
GUEST_DEFAULT_CONFIDENCE = Decimal(0)


# ---------------------------------------------------------------------------
# 권한
# ---------------------------------------------------------------------------


def caller_player(db: Session, user: User, team_id: int) -> Player | None:
    """호출자의 이 팀 players 행 (ACTIVE). 없으면 None."""
    return db.scalar(
        select(Player).where(Player.team_id == team_id, Player.user_id == user.id, Player.status == PlayerStatus.ACTIVE)
    )


def is_manager(db: Session, user: User, team_id: int) -> bool:
    if user.global_role == GlobalRole.ADMIN:
        return True
    me = caller_player(db, user, team_id)
    return me is not None and me.role == TeamRole.MANAGER


def can_manage_guest(db: Session, user: User, guest: Player) -> bool:
    """스펙 3절: (등록자 본인) OR (팀 매니저) OR ADMIN."""
    return guest.created_by == user.id or is_manager(db, user, guest.team_id)


def require_guest(db: Session, player_id: int) -> Player:
    p = db.get(Player, player_id, options=PLAYER_LOAD)
    if p is None:
        raise errors.NotFound("이 사람을 찾을 수 없어요.")
    if p.kind != PlayerKind.GUEST:
        raise errors.ValidationError("게스트만 이렇게 고칠 수 있어요.")
    return p


# ---------------------------------------------------------------------------
# 실력 등급 → prior
# ---------------------------------------------------------------------------


def _member_priors(db: Session, team_id: int) -> list[Decimal]:
    return sorted(
        db.scalars(
            select(PlayerProfile.prior_overall)
            .join(Player, Player.id == PlayerProfile.player_id)
            .where(
                Player.team_id == team_id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE,
                PlayerProfile.prior_overall.is_not(None),
            )
        ).all()
    )


def grade_to_prior(db: Session, team_id: int, grade: int) -> Decimal:
    """등급 1~5 → prior_overall. 회원 prior 가 5개 이상이면 그 분포의 분위수, 아니면 선형(등급 3 = 0점)."""
    priors = _member_priors(db, team_id)
    if len(priors) >= 5:
        q = (grade - 0.5) / 5.0
        idx = min(int(q * len(priors)), len(priors) - 1)
        return Decimal(priors[idx]).quantize(Decimal("0.1"))
    return Decimal(str((grade - 3) * 1.0)).quantize(Decimal("0.1"))


def apply_guest_grade(db: Session, guest: Player, grade: int | None, by_user_id: int | None) -> None:
    """게스트 등급(1~5, None = 팀 평균)을 사전값으로 바꾼다. 쿼터가 있으면 팀 전체를 다시 재생한다.

    첫 줄에서 팀 잠금을 건다 — 프로필을 먼저 쓰고 재계산에서 잠그면 교착이 났다 (quarter_service 모듈 docstring).
    """
    lock_team_stats(db, guest.team_id)
    prof = guest.profile or PlayerProfile(player_id=guest.id)
    if guest.profile is None:
        guest.profile = prof
    before = prof.prior_overall
    if grade is None:
        priors = _member_priors(db, guest.team_id)
        after = (sum(priors) / len(priors)).quantize(Decimal("0.1")) if priors else Decimal("0.0")
        prof.prior_source = PriorSource.DEFAULT
        prof.skill_confidence = GUEST_DEFAULT_CONFIDENCE
    else:
        after = grade_to_prior(db, guest.team_id, grade)
        prof.prior_source = PriorSource.MANAGER
        prof.skill_confidence = max(prof.skill_confidence, GUEST_GRADE_CONFIDENCE)
    prof.prior_overall = after
    if prof.quarters_played == 0:
        prof.skill_overall = after + (prof.admin_adjust or Decimal(0))  # 쿼터가 있으면 아래 rating 재계산이 덮어쓴다
    if before != after:
        db.add(
            SkillRatingHistory(
                player_id=guest.id, source=RatingSource.MANAGER_ADJUST, before_value=before, after_value=after,
                delta=after - (before or Decimal(0)), ref_type="users", ref_id=by_user_id,
                reason=f"게스트 실력 {'미지정(팀 평균으로 계산)' if grade is None else f'{grade}단계'}",
            )
        )
    if prof.quarters_played:
        from app.services import rating_service

        db.flush()
        rating_service.recompute_team(db, guest.team_id)


def apply_guest_positions(db: Session, guest: Player, playable: list[Position] | None, preferred: Position | None) -> None:
    """None 이면 변경 없음. playable=[] 이면 전부 해제."""
    if playable is None and preferred is None:
        return
    current = {pp.position: pp for pp in guest.positions}
    if playable is not None:
        for pos, row in list(current.items()):
            if pos not in playable and (preferred is None or pos != preferred):
                db.delete(row)
                current.pop(pos)
        for pos in playable:
            current.setdefault(pos, PlayerPosition(player_id=guest.id, position=pos, can_play=True)).can_play = True
    if preferred is not None:
        for row in current.values():
            row.preference_rank = None
        row = current.setdefault(preferred, PlayerPosition(player_id=guest.id, position=preferred, can_play=True))
        row.can_play = True
        row.preference_rank = 1
    guest.positions = list(current.values())


# ---------------------------------------------------------------------------
# 등록 · 검색 · 수정
# ---------------------------------------------------------------------------


def find_similar(db: Session, team_id: int, display_name: str) -> list[Player]:
    """같은 팀에서 이름이 같은(대소문자·공백 무시) 미병합 게스트."""
    name = display_name.strip()
    return list(
        db.scalars(
            select(Player)
            .where(
                Player.team_id == team_id, Player.kind == PlayerKind.GUEST, Player.status == PlayerStatus.ACTIVE,
                Player.merged_into_player_id.is_(None), func.lower(Player.display_name) == name.lower(),
            )
            .options(*PLAYER_LOAD)
            .order_by(Player.joined_at.desc())
        ).all()
    )


def search_guests(db: Session, team_id: int, q: str | None) -> list[Player]:
    stmt = (
        select(Player)
        .where(Player.team_id == team_id, Player.kind == PlayerKind.GUEST, Player.status == PlayerStatus.ACTIVE)
        .options(*PLAYER_LOAD)
        .order_by(Player.display_name)
    )
    if q:
        stmt = stmt.where(Player.display_name.ilike(f"%{q.strip()}%"))
    return list(db.scalars(stmt).all())


def create_guest(
    db: Session, team: Team, creator: User, *, display_name: str, skill_grade: int | None,
    preferred_position: Position | None, playable_positions: list[Position], height_cm: int | None = None,
) -> Player:
    """새 게스트 행 + 프로필 + 포지션. flush 까지, commit 은 호출자."""
    guest = Player(
        team_id=team.id, user_id=None, kind=PlayerKind.GUEST, display_name=display_name.strip(),
        role=TeamRole.PLAYER, status=PlayerStatus.ACTIVE, created_by=creator.id, joined_at=datetime.now(UTC), height_cm=height_cm,
    )
    guest.profile = PlayerProfile()
    db.add(guest)
    db.flush()
    apply_guest_grade(db, guest, skill_grade, creator.id)
    apply_guest_positions(db, guest, playable_positions, preferred_position)
    db.flush()
    return guest


def update_guest(
    db: Session, guest: Player, by: User, *, display_name: str | None = None, skill_grade: int | None = None,
    preferred_position: Position | None = None, playable_positions: list[Position] | None = None,
    grade_given: bool = False, height_cm: int | None = None, height_given: bool = False,
) -> Player:
    """보낸 필드만 바꾼다. `grade_given` 이 True 면 skill_grade=None 도 '미지정으로 되돌리기' 로 해석한다.
    `height_given` 도 같다 — 요청에 `height_cm: null` 을 명시하면 키를 지우고, 필드를 빼면 그대로 둔다."""
    if display_name is not None:
        guest.display_name = display_name.strip()
    if height_given or height_cm is not None:
        guest.height_cm = height_cm
    if grade_given:
        apply_guest_grade(db, guest, skill_grade, by.id)
    apply_guest_positions(db, guest, playable_positions, preferred_position)
    db.flush()
    return guest


# ---------------------------------------------------------------------------
# 병합
# ---------------------------------------------------------------------------


def merge(db: Session, guest: Player, into_player_id: int) -> Player:
    if guest.merged_into_player_id is not None:
        raise errors.AlreadyMerged()
    target = db.get(Player, into_player_id)
    if target is None or target.team_id != guest.team_id or target.kind != PlayerKind.MEMBER:
        raise errors.MergeKindMismatch()
    lock_team_stats(db, guest.team_id)  # 쓰기 전에 (잠금 순서)
    guest.merged_into_player_id = target.id
    guest.status = PlayerStatus.LEFT
    db.add(
        SkillRatingHistory(
            player_id=target.id, source=RatingSource.MERGE, ref_type="players", ref_id=guest.id,
            reason=f"게스트 '{guest.display_name}'(#{guest.id}) 기록 승계",
        )
    )
    db.flush()
    from app.services import (
        rating_service,  # 병합 즉시 게스트의 쿼터가 회원 기록으로 합산되도록 재계산
    )

    rating_service.recompute_team(db, guest.team_id)
    db.commit()
    return target


def unmerge(db: Session, guest: Player) -> Player:
    if guest.merged_into_player_id is None:
        raise errors.NotFound("기록을 이어 준 적이 없는 게스트예요.")
    lock_team_stats(db, guest.team_id)  # 쓰기 전에 (잠금 순서)
    guest.merged_into_player_id = None
    guest.status = PlayerStatus.ACTIVE
    db.flush()
    from app.services import rating_service

    rating_service.recompute_team(db, guest.team_id)
    db.commit()
    return guest


def merge_candidates(db: Session, team_id: int) -> list[tuple[Player, Player]]:
    """이름이 같은 (게스트, 회원) 쌍. 게스트가 회원가입 후 팀에 들어온 경우를 찾는 힌트."""
    guests = search_guests(db, team_id, None)
    if not guests:
        return []
    members = db.scalars(
        select(Player)
        .where(Player.team_id == team_id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE)
        .options(*PLAYER_LOAD)
    ).all()
    # 회원 본인 확인(pending_claims)과 같은 정규화를 쓴다 — "게스트 허웅" 으로 등록된 게스트도 "허웅" 회원과 짝지어진다
    by_name: dict[str, list[Player]] = {}
    for m in members:
        for key in {_norm_name(m.display_name), _norm_name(m.user.name if m.user else None), _norm_name(m.user.nickname if m.user else None)} - {""}:
            by_name.setdefault(key, []).append(m)
    pairs = []
    for g in guests:
        for m in by_name.get(_norm_name(g.display_name), []):
            pairs.append((g, m))
    return pairs


# ---------------------------------------------------------------------------
# 본인 확인 병합 (사용자 요청 기능) — 가입한 회원이 같은 이름의 게스트 기록을 직접 가져간다
# ---------------------------------------------------------------------------


def _norm_name(name: str | None) -> str:
    """이름 비교용 정규화: 공백 제거, 소문자, 앞의 '게스트' 접두어 제거 ("게스트 허웅" ≒ "허웅")."""
    if not name:
        return ""
    n = "".join(name.split()).lower()
    return n.removeprefix("게스트")


def pending_claims(db: Session, user: User) -> list[tuple[Player, Player, dict]]:
    """이 사용자가 속한 팀마다, 이름이 같은 미병합 게스트 중 아직 확인/거절하지 않은 것. 반환 (게스트, 내 player, 요약)."""
    from app.models import Event, EventAttendance, GuestClaim, QuarterLineup
    from app.models.enums import AttendanceStatus, EventStatus

    my_names = {_norm_name(user.name), _norm_name(user.nickname)} - {""}
    if not my_names:
        return []
    mine = db.scalars(
        select(Player).where(Player.user_id == user.id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE)
    ).all()
    decided = {gid for (gid,) in db.execute(select(GuestClaim.guest_player_id).where(GuestClaim.user_id == user.id)).all()}
    out = []
    for me in mine:
        guests = db.scalars(
            select(Player).where(
                Player.team_id == me.team_id, Player.kind == PlayerKind.GUEST, Player.status == PlayerStatus.ACTIVE,
                Player.merged_into_player_id.is_(None),
            ).options(*PLAYER_LOAD)
        ).all()
        for g in guests:
            if g.id in decided or _norm_name(g.display_name) not in my_names:
                continue
            rows = db.execute(
                select(Event.event_date).join(EventAttendance, EventAttendance.event_id == Event.id)
                .where(EventAttendance.player_id == g.id, EventAttendance.status == AttendanceStatus.ATTEND, Event.status != EventStatus.CANCELED)
                .order_by(Event.event_date.desc())
            ).all()
            quarters = db.scalar(select(func.count()).select_from(QuarterLineup).where(QuarterLineup.player_id == g.id)) or 0
            out.append((g, me, {"events_attended": len(rows), "quarters_played": quarters, "last_event_date": rows[0][0] if rows else None}))
    return out


def claim(db: Session, user: User, guest: Player, accept: bool) -> Player | None:
    """확인이면 내 player 로 병합(매니저 병합과 동일), 거절이면 기록만 남겨 다시 묻지 않는다. 반환: 병합된 내 player 또는 None."""
    from app.models import GuestClaim
    from app.models.enums import ClaimStatus

    if guest.kind != PlayerKind.GUEST or guest.merged_into_player_id is not None:
        raise errors.AlreadyMerged()
    me = db.scalar(
        select(Player).where(Player.user_id == user.id, Player.team_id == guest.team_id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE)
    )
    if me is None:
        raise errors.NotAMember("이 팀에 속해 있어야 기록을 가져올 수 있어요.")
    if _norm_name(guest.display_name) not in {_norm_name(user.name), _norm_name(user.nickname)}:
        raise errors.ForbiddenRole("이름이 같은 게스트 기록만 가져올 수 있어요. 다른 이름이면 매니저에게 기록을 이어 달라고 말해 주세요.")
    existing = db.scalar(select(GuestClaim).where(GuestClaim.guest_player_id == guest.id, GuestClaim.user_id == user.id))
    if existing is None:
        existing = GuestClaim(guest_player_id=guest.id, user_id=user.id, status=ClaimStatus.DECLINED)
        db.add(existing)
    existing.status = ClaimStatus.CONFIRMED if accept else ClaimStatus.DECLINED
    if accept:
        merge(db, guest, me.id)  # 병합 · 실력 재계산 · commit 까지 한다 — 여기서 다시 돌리지 않는다
        db.refresh(me)
        return me
    db.commit()
    return None
