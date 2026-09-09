"""일정·참석 서비스 (설계서 F4 · FR-08/09/15/34 · guest-feature-spec 5절 회차별 게스트).

흐름 B (5.3절): 일정 등록 → RSVP → 참석 현황(+게스트) → 배정. 이 모듈은 배정 전까지를 담당한다.

참석 행(event_attendances)은 회원이 응답하거나 매니저/등록자가 대신 만들 때 생긴다. 일정 등록 시
활성 회원 전원에 PENDING 행을 미리 만들지만, **그 뒤에 가입한 회원은 행이 없을 수 있으므로**
현황 조회는 행이 없는 회원을 PENDING 으로 합성해 보여준다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core import errors
from app.models import (
    AssignmentCandidate,
    AssignmentRun,
    AssignmentSlot,
    AssignmentSquad,
    Event,
    EventAttendance,
    GuestInvitePreset,
    Player,
    Quarter,
    Team,
    User,
)
from app.models.enums import (
    AttendanceStatus,
    EventStatus,
    PlayerKind,
    PlayerStatus,
    Position,
    TeamRole,
    TeamStatus,
)
from app.schemas.event import (
    AttendanceList,
    AttendanceSummary,
    AttendanceView,
    EventCreate,
    EventGuestCreate,
    EventGuestUpdate,
    EventUpdate,
    EventView,
    LockSuggestion,
)
from app.services import guest_service
from app.services.player_service import to_card

TEAM_COUNT_DEFAULT = 2  # 현재 운영은 2팀 고정 (13.1절 Q4)


# ---------------------------------------------------------------------------
# 일정
# ---------------------------------------------------------------------------


def _active_members(db: Session, team_id: int) -> list[Player]:
    return list(
        db.scalars(
            select(Player).where(
                Player.team_id == team_id, Player.kind == PlayerKind.MEMBER, Player.status == PlayerStatus.ACTIVE
            )
        ).all()
    )


def create_event(db: Session, team: Team, by: User, body: EventCreate) -> Event:
    if team.status != TeamStatus.ACTIVE:
        from app.models.enums import ApprovalStatus

        if team.approval_status != ApprovalStatus.APPROVED:
            raise errors.TeamNotActive("관리자 승인이 끝나면 일정을 만들 수 있어요.")
        raise errors.TeamNotActive()
    if body.start_time and body.end_time and body.end_time <= body.start_time:
        raise errors.ValidationError("종료 시각은 시작 시각보다 뒤여야 합니다.")
    event = Event(team_id=team.id, created_by=by.id, **body.model_dump())
    db.add(event)
    db.flush()
    for m in _active_members(db, team.id):
        db.add(EventAttendance(event_id=event.id, player_id=m.id, status=AttendanceStatus.PENDING))
    db.commit()
    return event


def close_rsvp(db: Session, event: Event) -> Event:
    """응답 마감 시각 전에 매니저가 응답을 닫는다 (status OPEN → CLOSED). 이후 본인 응답은 422 RSVP_CLOSED, 매니저 대리 응답은 계속 가능."""
    if event.status != EventStatus.OPEN:
        raise errors.ValidationError("응답을 받고 있는 일정만 마감할 수 있어요.")
    event.status = EventStatus.CLOSED
    db.commit()
    return event


def update_event(db: Session, event: Event, body: EventUpdate) -> Event:
    old_date = event.event_date
    for k, v in body.model_dump(exclude_unset=True).items():
        if k == "event_date" and v is None:
            continue  # 날짜는 비울 수 없다 (None = 변경 없음)
        setattr(event, k, v)
    if event.start_time and event.end_time and event.end_time <= event.start_time:
        raise errors.ValidationError("종료 시각은 시작 시각보다 뒤여야 합니다.")
    if event.event_date != old_date:
        # 쿼터 재생 순서(첫 2회 게이트 포함)가 날짜에 따라 달라지므로 다시 계산
        from app.services import rating_service

        db.flush()
        rating_service.recompute_team(db, event.team_id)
    db.commit()
    return event


def cancel_event(db: Session, event: Event) -> None:
    if event.status == EventStatus.DONE:
        raise errors.ValidationError("이미 종료된 일정은 취소할 수 없습니다.")
    event.status = EventStatus.CANCELED
    from app.services import rating_service

    db.flush()
    rating_service.recompute_team(db, event.team_id)
    db.commit()


def rsvp_open(event: Event) -> bool:
    if event.status != EventStatus.OPEN:
        return False
    return event.rsvp_deadline is None or event.rsvp_deadline > datetime.now(UTC)


def _attend_count(db: Session, event_id: int) -> int:
    return db.scalar(
        select(func.count()).select_from(EventAttendance).where(
            EventAttendance.event_id == event_id, EventAttendance.status == AttendanceStatus.ATTEND
        )
    ) or 0


def _bulk_stats(db: Session, event_ids: list[int], me: Player | None) -> dict[int, dict]:
    """여러 일정의 집계 필드를 일정 수와 무관하게 고정된 쿼리 수로 모은다 (목록 화면 N+1 방지).

    반환: event_id → {attend_count, my_status, adopted_candidate_id, my_squad_name, my_position, run_count,
    quarter_count, survey_total, survey_responded, my_survey_submitted}
    """
    from app.models import PostGameSurvey

    if not event_ids:
        return {}
    out: dict[int, dict] = {eid: {
        "attend_count": 0, "my_status": None, "adopted_candidate_id": None, "my_squad_name": None, "my_position": None,
        "run_count": 0, "quarter_count": 0, "survey_total": 0, "survey_responded": 0, "my_survey_submitted": False,
    } for eid in event_ids}
    for eid, n in db.execute(
        select(EventAttendance.event_id, func.count()).where(EventAttendance.event_id.in_(event_ids), EventAttendance.status == AttendanceStatus.ATTEND)
        .group_by(EventAttendance.event_id)
    ).all():
        out[eid]["attend_count"] = n
    for eid, n in db.execute(
        select(EventAttendance.event_id, func.count()).join(Player, Player.id == EventAttendance.player_id)
        .where(EventAttendance.event_id.in_(event_ids), EventAttendance.status == AttendanceStatus.ATTEND, Player.kind == PlayerKind.MEMBER)
        .group_by(EventAttendance.event_id)
    ).all():
        out[eid]["survey_total"] = n
    for eid, n in db.execute(
        select(PostGameSurvey.event_id, func.count()).where(PostGameSurvey.event_id.in_(event_ids)).group_by(PostGameSurvey.event_id)
    ).all():
        out[eid]["survey_responded"] = n
    for eid, cid in db.execute(
        select(AssignmentRun.event_id, AssignmentCandidate.id).join(AssignmentRun, AssignmentRun.id == AssignmentCandidate.run_id)
        .where(AssignmentRun.event_id.in_(event_ids), AssignmentCandidate.is_adopted.is_(True))
    ).all():
        out[eid]["adopted_candidate_id"] = cid
    for eid, n in db.execute(
        select(AssignmentRun.event_id, func.count()).where(AssignmentRun.event_id.in_(event_ids)).group_by(AssignmentRun.event_id)
    ).all():
        out[eid]["run_count"] = n
    for eid, n in db.execute(
        select(Quarter.event_id, func.count()).where(Quarter.event_id.in_(event_ids)).group_by(Quarter.event_id)
    ).all():
        out[eid]["quarter_count"] = n
    if me is not None and me.id:
        for eid in event_ids:
            out[eid]["my_status"] = AttendanceStatus.PENDING
        for eid, st in db.execute(
            select(EventAttendance.event_id, EventAttendance.status).where(EventAttendance.event_id.in_(event_ids), EventAttendance.player_id == me.id)
        ).all():
            out[eid]["my_status"] = st
        # 확정된 배정이 있으면 내 팀·포지션을 카드에 바로 보여준다 (팀 상세 일정 탭, 홈)
        for eid, name, pos in db.execute(
            select(AssignmentRun.event_id, AssignmentSquad.squad_name, AssignmentSlot.assigned_position)
            .join(AssignmentSlot, AssignmentSlot.squad_id == AssignmentSquad.id)
            .join(AssignmentCandidate, AssignmentCandidate.id == AssignmentSquad.candidate_id)
            .join(AssignmentRun, AssignmentRun.id == AssignmentCandidate.run_id)
            .where(AssignmentRun.event_id.in_(event_ids), AssignmentCandidate.is_adopted.is_(True), AssignmentSlot.player_id == me.id)
        ).all():
            out[eid]["my_squad_name"], out[eid]["my_position"] = name, pos
        for (eid,) in db.execute(
            select(PostGameSurvey.event_id).where(PostGameSurvey.event_id.in_(event_ids), PostGameSurvey.respondent_player_id == me.id)
        ).all():
            out[eid]["my_survey_submitted"] = True
    return out


def event_view(db: Session, event: Event, me: Player | None, *, stats: dict | None = None) -> EventView:
    """일정 카드/상세 응답. 목록에서는 `_bulk_stats` 로 미리 모은 `stats` 를 넘겨 쿼리를 줄인다."""
    from app.services import peer_service

    st = stats if stats is not None else _bulk_stats(db, [event.id], me)[event.id]
    return EventView(
        id=event.id, team_id=event.team_id, title=event.title, event_date=event.event_date,
        start_time=event.start_time, end_time=event.end_time, venue=event.venue, rsvp_deadline=event.rsvp_deadline,
        status=event.status, memo=event.memo, attend_count=st["attend_count"], my_attendance=st["my_status"],
        rsvp_open=rsvp_open(event), my_role=me.role if me else None,
        adopted_candidate_id=st["adopted_candidate_id"], run_count=st["run_count"],
        my_squad_name=st["my_squad_name"], my_assigned_position=st["my_position"].value if st["my_position"] else None,
        quarter_count=st["quarter_count"],
        survey_open=peer_service.is_open(event), my_survey_submitted=st["my_survey_submitted"],
        survey_responded=st["survey_responded"], survey_total=st["survey_total"],
    )


def list_events(db: Session, team: Team, me: Player, *, date_from, date_to, status, page: int, size: int):
    stmt = select(Event).where(Event.team_id == team.id)
    if date_from:
        stmt = stmt.where(Event.event_date >= date_from)
    if date_to:
        stmt = stmt.where(Event.event_date <= date_to)
    if status:
        stmt = stmt.where(Event.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Event.event_date.desc(), Event.id.desc()).offset((page - 1) * size).limit(size)).all()
    stats = _bulk_stats(db, [e.id for e in rows], me)
    return [event_view(db, e, me, stats=stats[e.id]) for e in rows], total


# ---------------------------------------------------------------------------
# 참석
# ---------------------------------------------------------------------------


def _get_row(db: Session, event_id: int, player_id: int) -> EventAttendance | None:
    return db.scalar(
        select(EventAttendance).where(EventAttendance.event_id == event_id, EventAttendance.player_id == player_id)
    )


def respond(db: Session, event: Event, me: Player, status: AttendanceStatus, note: str | None) -> EventAttendance:
    if me.id is None:
        raise errors.NotAMember("비소속 관리자는 본인 응답을 남길 수 없어요. 참가자 대리 응답을 쓰세요.")
    if not rsvp_open(event):
        raise errors.RsvpClosed()
    row = _get_row(db, event.id, me.id) or EventAttendance(event_id=event.id, player_id=me.id)
    row.status = status
    row.note = note
    row.responded_at = datetime.now(UTC)
    row.registered_by = None
    db.add(row)
    db.commit()
    return row


def set_attendance(
    db: Session, event: Event, player: Player, status: AttendanceStatus, note: str | None, by: User,
    lock_request_player_id: int | None = None, keep_lock: bool = True,
) -> EventAttendance:
    """매니저/등록자 대리 등록. RSVP 마감과 무관. flush 까지 (commit 은 호출자)."""
    if player.team_id != event.team_id or player.status != PlayerStatus.ACTIVE:
        raise errors.NotFound("이 팀의 참가자가 아닙니다.")
    row = _get_row(db, event.id, player.id) or EventAttendance(event_id=event.id, player_id=player.id)
    row.status = status
    if note is not None:
        row.note = note
    row.responded_at = datetime.now(UTC)
    row.registered_by = by.id
    if not keep_lock or lock_request_player_id is not None:
        row.team_lock_request_player_id = lock_request_player_id
    db.add(row)
    db.flush()
    return row


def attendance_view(db: Session, row: EventAttendance | None, player: Player, viewer: User, viewer_is_manager: bool) -> AttendanceView:
    reg_name = None
    lock_name = None
    if row is not None and row.registered_by:
        reg_name = db.scalar(select(User.name).where(User.id == row.registered_by))
    if row is not None and row.team_lock_request_player_id:
        lock_name = db.scalar(select(Player.display_name).where(Player.id == row.team_lock_request_player_id))
    can_edit = player.kind == PlayerKind.GUEST and (viewer_is_manager or player.created_by == viewer.id)
    return AttendanceView(
        player=to_card(player, include_grade=viewer_is_manager),
        status=row.status if row else AttendanceStatus.PENDING,
        note=row.note if row else None,
        responded_at=row.responded_at if row else None,
        registered_by=row.registered_by if row else None,
        registered_by_name=reg_name,
        team_lock_request_player_id=row.team_lock_request_player_id if row else None,
        team_lock_request_player_name=lock_name,
        can_edit=can_edit,
    )


def attendance_list(db: Session, event: Event, me: Player, viewer: User, status_filter: AttendanceStatus | None) -> AttendanceList:
    rows = db.scalars(
        select(EventAttendance).where(EventAttendance.event_id == event.id)
    ).all()
    by_player = {r.player_id: r for r in rows}
    players = db.scalars(
        select(Player)
        .where(Player.team_id == event.team_id, Player.status == PlayerStatus.ACTIVE)
        .options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user))
    ).all()
    # 회원은 행이 없어도 PENDING 으로, 게스트는 행이 있을 때만
    entries: list[tuple[EventAttendance | None, Player]] = []
    for p in players:
        row = by_player.get(p.id)
        if p.kind == PlayerKind.GUEST and row is None:
            continue
        entries.append((row, p))
    viewer_is_manager = me.role == TeamRole.MANAGER
    views = [attendance_view(db, row, p, viewer, viewer_is_manager) for row, p in entries]

    attend = [(row, p) for row, p in entries if row and row.status == AttendanceStatus.ATTEND]
    # 포지션 분포는 사람당 하나 — 가장 선호하는 포지션(preference_rank 1)만 센다 (중복 집계 방지)
    counts = {pos: 0 for pos in Position}
    for _, p in attend:
        card = to_card(p)
        if card.primary_position:
            counts[card.primary_position] += 1
    # 희소 자원 경고는 '가능' 기준 (선호가 아니어도 맡을 수 있으면 자원)
    handler = sum(1 for _, p in attend if any(pp.can_play and pp.position == Position.PG for pp in p.positions))
    bigman = sum(1 for _, p in attend if any(pp.can_play and pp.position in (Position.PF, Position.C) for pp in p.positions))
    warnings = []
    if len(attend) < TEAM_COUNT_DEFAULT * 5:
        warnings.append(f"{TEAM_COUNT_DEFAULT}팀을 만들려면 최소 {TEAM_COUNT_DEFAULT * 5}명이 필요해요 (현재 {len(attend)}명)")
    if attend and handler < TEAM_COUNT_DEFAULT:
        warnings.append(f"1번(핸들러) 가능 인원이 {handler}명이라 팀당 1명을 채우기 어려워요")
    if attend and bigman < TEAM_COUNT_DEFAULT:
        warnings.append(f"빅맨(4·5번) 가능 인원이 {bigman}명이라 팀당 1명을 채우기 어려워요")
    summary = AttendanceSummary(
        attend=len(attend),
        absent=sum(1 for row, _ in entries if row and row.status == AttendanceStatus.ABSENT),
        pending=sum(1 for row, _ in entries if row is None or row.status == AttendanceStatus.PENDING),
        guest_count=sum(1 for _, p in attend if p.kind == PlayerKind.GUEST),
        position_counts=counts, handler_count=handler, bigman_count=bigman, warnings=warnings,
    )
    if status_filter:
        views = [v for v in views if v.status == status_filter]
    order = {AttendanceStatus.ATTEND: 0, AttendanceStatus.PENDING: 1, AttendanceStatus.ABSENT: 2}
    views.sort(key=lambda v: (order[v.status], v.player.kind == "GUEST", v.player.display_name))
    return AttendanceList(items=views, summary=summary, my_player_id=me.id or None)


# ---------------------------------------------------------------------------
# 회차별 게스트 (guest-feature-spec 5절)
# ---------------------------------------------------------------------------


def register_guest(db: Session, event: Event, me: Player, by: User, body: EventGuestCreate):
    """게스트를 이 회차 참석자에 추가. 반환: (AttendanceView, None) 또는 (None, similar[]) 확인 요청."""
    if event.status == EventStatus.CANCELED:
        raise errors.ValidationError("취소된 일정에는 게스트를 등록할 수 없어요.")
    if body.preferred_position and body.preferred_position not in body.playable_positions:
        body = body.model_copy(update={"playable_positions": [body.preferred_position, *body.playable_positions]})  # 선호 포지션은 가능 포지션에 자동 포함
    team = db.get(Team, event.team_id)
    if body.existing_player_id is not None:
        guest = guest_service.require_guest(db, body.existing_player_id)
        if guest.team_id != event.team_id or guest.merged_into_player_id is not None:
            raise errors.NotFound("이 팀의 게스트가 아닙니다.")
        # 재방문: 등록자가 새 정보를 주면 덮어쓴다 (등급은 지정했을 때만)
        guest_service.update_guest(
            db, guest, by, display_name=None, skill_grade=body.skill_grade,
            preferred_position=body.preferred_position, playable_positions=body.playable_positions or None,
            grade_given=body.skill_grade is not None, height_cm=body.height_cm,
        )
    else:
        similar = guest_service.find_similar(db, event.team_id, body.display_name)
        if similar and not body.force_new:
            return None, similar
        guest = guest_service.create_guest(
            db, team, by, display_name=body.display_name, skill_grade=body.skill_grade,
            preferred_position=body.preferred_position, playable_positions=body.playable_positions, height_cm=body.height_cm,
        )
    lock_target = me.id if body.team_lock_request else None
    row = set_attendance(db, event, guest, AttendanceStatus.ATTEND, None, by, lock_request_player_id=lock_target, keep_lock=False)
    _upsert_preset(db, event.team_id, by, guest, body)
    db.commit()
    db.refresh(guest)
    return attendance_view(db, row, guest, by, me.role == TeamRole.MANAGER), None


def _upsert_preset(db: Session, team_id: int, by: User, guest: Player, body: EventGuestCreate) -> None:
    """(팀, 등록자, 이름) 단위로 초대 이력을 갱신한다. 다음 일정에서 '이전 초대 목록 불러오기' 에 쓰인다."""
    name = guest.display_name
    preset = db.scalar(
        select(GuestInvitePreset).where(
            GuestInvitePreset.team_id == team_id, GuestInvitePreset.created_by == by.id, GuestInvitePreset.display_name == name
        )
    )
    playable = [p.value for p in (body.playable_positions or [])] or [pp.position.value for pp in guest.positions if pp.can_play]
    preferred = body.preferred_position.value if body.preferred_position else next((pp.position.value for pp in guest.positions if pp.preference_rank == 1), None)
    grade = body.skill_grade if body.skill_grade is not None else (preset.skill_grade if preset else None)
    if preset is None:
        preset = GuestInvitePreset(team_id=team_id, created_by=by.id, display_name=name, use_count=0, last_used_at=datetime.now(UTC))
        db.add(preset)
    preset.skill_grade = grade
    preset.height_cm = body.height_cm if body.height_cm is not None else (guest.height_cm or preset.height_cm)
    preset.preferred_position = preferred
    preset.playable_positions = playable
    preset.team_lock_request = body.team_lock_request
    preset.last_player_id = guest.id
    preset.use_count += 1
    preset.last_used_at = datetime.now(UTC)
    db.flush()


def my_presets(db: Session, team_id: int, by: User) -> list[GuestInvitePreset]:
    """내가 이 팀에서 초대했던 게스트 목록 (최근 사용순)."""
    return list(
        db.scalars(
            select(GuestInvitePreset).where(GuestInvitePreset.team_id == team_id, GuestInvitePreset.created_by == by.id)
            .order_by(GuestInvitePreset.last_used_at.desc())
        ).all()
    )


def update_event_guest(db: Session, event: Event, me: Player, by: User, guest: Player, body: EventGuestUpdate) -> AttendanceView:
    if not guest_service.can_manage_guest(db, by, guest):
        raise errors.ForbiddenNotOwner()
    row = _get_row(db, event.id, guest.id)
    if row is None:
        raise errors.NotFound("이 회차에 등록되지 않은 게스트입니다.")
    fields = body.model_dump(exclude_unset=True)
    guest_service.update_guest(
        db, guest, by, display_name=body.display_name, skill_grade=body.skill_grade,
        preferred_position=body.preferred_position, playable_positions=body.playable_positions,
        grade_given="skill_grade" in fields, height_cm=body.height_cm,
    )
    if body.team_lock_request is not None:
        # 요청 대상은 "현재 수정하는 사람" 이 아니라 원래 등록자 — 매니저가 대신 켜 줄 때도 등록자 기준
        owner_player = db.scalar(
            select(Player).where(Player.team_id == event.team_id, Player.user_id == guest.created_by, Player.status == PlayerStatus.ACTIVE)
        )
        row.team_lock_request_player_id = (owner_player.id if owner_player else me.id) if body.team_lock_request else None
    if body.status is not None:
        row.status = body.status
        row.responded_at = datetime.now(UTC)
        row.registered_by = by.id
    db.commit()
    db.refresh(guest)
    return attendance_view(db, row, guest, by, me.role == TeamRole.MANAGER)


def remove_event_guest(db: Session, event: Event, by: User, guest: Player) -> None:
    """참석 행만 지운다 (불참 처리). players 원본은 남겨 다음 방문 때 재사용 (FR-12)."""
    if not guest_service.can_manage_guest(db, by, guest):
        raise errors.ForbiddenNotOwner()
    row = _get_row(db, event.id, guest.id)
    if row is None:
        raise errors.NotFound("이 회차에 등록되지 않은 게스트입니다.")
    db.delete(row)
    db.commit()


def lock_suggestions(db: Session, event: Event) -> list[LockSuggestion]:
    """묶기 제안: 요청이 있고, 게스트와 대상 모두 이 회차 ATTEND 인 것만 (스펙 7절: 대상이 불참이면 자동 무효)."""
    rows = db.execute(
        select(EventAttendance, Player)
        .join(Player, Player.id == EventAttendance.player_id)
        .where(
            EventAttendance.event_id == event.id, EventAttendance.status == AttendanceStatus.ATTEND,
            EventAttendance.team_lock_request_player_id.is_not(None), Player.kind == PlayerKind.GUEST,
        )
        .options(selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user))
    ).all()
    out = []
    for row, guest in rows:
        target_row = _get_row(db, event.id, row.team_lock_request_player_id)
        if target_row is None or target_row.status != AttendanceStatus.ATTEND:
            continue
        target = db.get(Player, row.team_lock_request_player_id, options=[selectinload(Player.profile), selectinload(Player.positions), selectinload(Player.user)])
        out.append(LockSuggestion(guest=to_card(guest, include_grade=True), target=to_card(target, include_grade=True), requested_by_user_id=row.registered_by))
    return out
