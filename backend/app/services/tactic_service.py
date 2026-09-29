"""전술 추천 · 전술판 (docs/07 FR-43~FR-47).

추천은 그날 **확정 배정**이 있으면 자동으로 만든다. 팀마다 전술 8개의 적합도를 계산해 기준(`FIT_MIN`) 이상인 것 중
상위 3개를 보여 준다. 매니저가 고르지 않아도 된다. 자리 배치도 자동이고, 매니저가 전술판에서 자리를 바꿔 저장하면
그 전술은 저장한 배치로 보인다(최종 결정은 사람이 — 설계서 1.4절). 빈 목록을 저장하면 추천 배치로 돌아간다.

역할 점수의 기준(키 백분위 · 게스트 평균 채우기)은 그 일정 참석자 전원(블랙+화이트)이고, 자리 배치는 팀마다 따로 한다.
계산은 app/tactics 가 하고 여기서는 DB 에서 재료를 모은다.

권한 (docs/07 3절)
  추천 · 전술판 보기          그 일정 참석자(확정 배정에 들었거나 참석 응답) · 매니저 · ADMIN
  자리별 점수 · 속성 · 교체 후보  매니저 · ADMIN 만 — 설문에서 나온 개인 특성이라서
  자리 바꿔 저장              매니저 · ADMIN
"""

from dataclasses import dataclass
from statistics import mean

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core import errors
from app.models import (
    AssignmentCandidate,
    Event,
    EventAttendance,
    EventPlayAssignment,
    Player,
    User,
)
from app.models.enums import AttendanceStatus, PlayerKind, TeamRole
from app.schemas.tactic import (
    EventPlayView,
    PlayLineup,
    PresetList,
    SlotLineup,
    SlotPlayer,
    SlotsIn,
    SquadBoard,
    SquadMember,
    SquadRecommendation,
    TacticRecommendation,
)
from app.services import survey_service
from app.services.assignment_service import _players_of, adopted_candidate
from app.tactics.matching import SLOTS, allowed_defenses, fit_play
from app.tactics.play import Play
from app.tactics.presets import PRESET_LIST, PRESETS_VERSION, get_play, play_key
from app.tactics.roles import PlayerRoles, compute_role_scores, role_input_from_features

TOP_N = 3
# 추천 기준 적합도. 다섯 자리 역할 점수 평균이 0.75 이상 — 자리마다 그 역할의 핵심 항목을 대부분 갖췄다는 뜻.
# 데모 팀 확정 배정 20건(팀별)에서 대인 수비용 7개 중 기준을 넘는 전술이 3~7개, 모두 같은 설문의 평범한 팀은 0개(최고 60)였다.
# 기준을 넘는 전술이 없으면 추천하지 않는다. 실제 배정이 쌓이면 조정한다 (명세 O4)
FIT_MIN = 75.0
BACKUP_MIN = 0.6  # 예비로 보여 줄 역할 점수 하한
BACKUP_MAX = 2


def presets() -> PresetList:
    return PresetList(presets_version=PRESETS_VERSION, items=PRESET_LIST)


def _is_manager(me: Player) -> bool:
    return me.role == TeamRole.MANAGER


@dataclass
class _Ctx:
    """한 일정의 확정 배정과 역할 점수 — 요청마다 한 번만 만든다."""

    cand: AssignmentCandidate
    by_squad: dict[int, list[int]]  # squad_no → player_id (회원 먼저·이름순)
    names: dict[int, str]  # squad_no → 블랙/화이트
    players: dict[int, Player]
    scores: dict[int, PlayerRoles]
    saved: dict[tuple[int, str], list[int | None]]  # (squad_no, play_key) → 슬롯 1~5 player_id

    def squad_of(self, pid: int | None) -> int | None:
        return next((no for no, ids in self.by_squad.items() if pid in ids), None)


def _order(players: dict[int, Player], ids: list[int]) -> list[int]:
    """회원 먼저, 이름순. 동점일 때 DP 가 명단 앞사람을 남기므로 순서를 고정해 결과가 매번 같게 한다."""
    return sorted((i for i in ids if i in players), key=lambda i: (players[i].kind == PlayerKind.GUEST, players[i].display_name, i))


def role_scores_for(db: Session, event: Event, players: dict[int, Player]) -> dict[int, PlayerRoles]:
    """확정 배정에 든 사람 전원의 역할 점수. 설문은 회원만, 키·포지션은 게스트도 자기 값."""
    features = {p.id: f for p, f in survey_service._members_with_features(db, event.team_id)}
    inputs = [
        role_input_from_features(
            pid, features.get(pid),
            height_cm=p.height_cm if p.user is None else p.user.height_cm,
            positions=[pp.position.value for pp in p.positions if pp.can_play],
            is_guest=p.kind == PlayerKind.GUEST,
        )
        for pid, p in players.items()
    ]
    return compute_role_scores(inputs)


def _context(db: Session, event: Event) -> _Ctx | None:
    cand = adopted_candidate(db, event)
    if cand is None:
        return None
    raw = {sq.squad_no: [s.player_id for s in sq.slots] for sq in cand.squads}
    players = _players_of(db, [pid for ids in raw.values() for pid in ids])
    saved: dict[tuple[int, str], list[int | None]] = {}
    for r in db.scalars(select(EventPlayAssignment).where(EventPlayAssignment.event_id == event.id)).all():
        saved.setdefault((r.squad_no, r.play_key), [None] * SLOTS)[r.slot - 1] = r.player_id
    return _Ctx(
        cand=cand,
        by_squad={no: _order(players, ids) for no, ids in raw.items()},
        names={sq.squad_no: sq.squad_name for sq in cand.squads},
        players=players,
        scores=role_scores_for(db, event, players),
        saved=saved,
    )


def _require_attendee(db: Session, event: Event, me: Player, ctx: _Ctx | None) -> None:
    if _is_manager(me):
        return
    if ctx is not None and ctx.squad_of(me.id) is not None:
        return
    attended = db.scalar(
        select(EventAttendance.id).where(
            EventAttendance.event_id == event.id, EventAttendance.player_id == me.id,
            EventAttendance.status == AttendanceStatus.ATTEND,
        )
    )
    if attended is None:
        raise errors.NotAttendee()


def _lineup(ctx: _Ctx, squad_no: int, play: Play, *, manager: bool) -> tuple[PlayLineup, float] | None:
    """(보여 줄 배치, 추천 배치의 적합도). 순위·기준은 추천 배치 적합도로 매기고, 매니저가 바꿔 저장했으면 그 배치를 보여 준다."""
    ids = ctx.by_squad[squad_no]
    roster = [ctx.scores[pid] for pid in ids]
    if len(roster) < SLOTS:
        return None
    auto = fit_play(play, roster)
    saved = ctx.saved.get((squad_no, play_key(play)))
    manual = saved is not None and all(pid in ids for pid in saved) and len(set(saved)) == SLOTS
    seat: list[int] = list(saved) if manual else [s.player_id for s in auto.slots]  # type: ignore[arg-type]
    bench = [p for p in roster if p.player_id not in seat]
    name = lambda pid: ctx.players[pid].display_name
    slots = []
    for k, pid in enumerate(seat):
        role = play.roles[k]
        pr = ctx.scores[pid]
        backups = sorted(
            (o for o in seat if o != pid and ctx.scores[o].scores[role] >= BACKUP_MIN),
            key=lambda o: -ctx.scores[o].scores[role],
        )[:BACKUP_MAX]
        slot = SlotLineup(
            slot=k + 1, role=role, player_id=pid, display_name=name(pid),
            backups=[SlotPlayer(player_id=o, display_name=name(o)) for o in backups],
        )
        if manager:
            alt = max(bench, key=lambda p: p.scores[role], default=None)
            slot.score = round(pr.scores[role] * 100)
            slot.matched_attrs = pr.matched_attrs(role)
            slot.missing_attrs = pr.missing_attrs(role)
            slot.alt_player_id = alt.player_id if alt else None
            slot.alt_display_name = name(alt.player_id) if alt else None
        slots.append(slot)
    fit = round(mean(ctx.scores[pid].scores[play.roles[k]] for k, pid in enumerate(seat)) * 100, 1)
    lineup = PlayLineup(
        play_key=play_key(play), name=play.name, summary=play.summary, defense=play.defense,
        fit=fit, manual=manual, slots=slots,
    )
    return lineup, auto.fit


def recommend(db: Session, event: Event, me: Player, *, squad_no: int | None, zone: bool) -> TacticRecommendation:
    ctx = _context(db, event)
    _require_attendee(db, event, me, ctx)
    if ctx is None:
        raise errors.NotAdoptedYet()
    manager = _is_manager(me)
    ok = allowed_defenses(zone)
    out = []
    for no in sorted(ctx.by_squad):
        if squad_no is not None and no != squad_no:
            continue
        ranked = []
        for i, play in enumerate(PRESET_LIST):
            if play.defense not in ok:
                continue
            got = _lineup(ctx, no, play, manager=manager)
            if got is not None and got[1] >= FIT_MIN:
                ranked.append((-got[1], i, got[0]))
        ranked.sort(key=lambda t: (t[0], t[1]))  # 적합도 높은 순, 같으면 목록 순서
        out.append(SquadRecommendation(
            squad_no=no, squad_name=ctx.names[no], member_count=len(ctx.by_squad[no]),
            items=[lu for _, _, lu in ranked[:TOP_N]],
        ))
    return TacticRecommendation(
        event_id=event.id, zone=zone, fit_min=FIT_MIN, presets_version=PRESETS_VERSION,
        can_edit=manager, my_squad_no=ctx.squad_of(me.id), squads=out,
    )


def play_view(db: Session, event: Event, key: str, me: Player) -> EventPlayView:
    play = get_play(key)
    if play is None:
        raise errors.NotFound("없는 전술이에요.")
    ctx = _context(db, event)
    _require_attendee(db, event, me, ctx)
    manager = _is_manager(me)
    squads: list[SquadBoard] = []
    if ctx is not None:
        for no in sorted(ctx.by_squad):
            got = _lineup(ctx, no, play, manager=manager)
            squads.append(SquadBoard(
                squad_no=no, squad_name=ctx.names[no],
                members=[
                    SquadMember(player_id=pid, display_name=ctx.players[pid].display_name, is_guest=ctx.players[pid].kind == PlayerKind.GUEST)
                    for pid in ctx.by_squad[no]
                ],
                lineup=got[0] if got else None,
            ))
    return EventPlayView(
        play_key=play_key(play), play=play, can_edit=manager,
        my_squad_no=ctx.squad_of(me.id) if ctx else None, squads=squads,
    )


def save_slots(db: Session, event: Event, key: str, body: SlotsIn, by: User, me: Player) -> EventPlayView:
    """매니저가 자리를 바꿔 저장. 다섯 자리를 모두 보내야 하고, 빈 목록이면 저장한 배치를 지워 추천 배치로 돌아간다."""
    play = get_play(key)
    if play is None:
        raise errors.NotFound("없는 전술이에요.")
    cand = adopted_candidate(db, event)
    if cand is None:
        raise errors.NotAdoptedYet()
    by_squad = {sq.squad_no: {s.player_id for s in sq.slots} for sq in cand.squads}
    if body.squad_no not in by_squad:
        raise errors.NotFound("그날 배정에 없는 팀이에요.")
    if body.slots and len(body.slots) != SLOTS:
        raise errors.ValidationError("다섯 자리를 모두 채워 주세요.")
    if len({s.slot for s in body.slots}) != len(body.slots):
        raise errors.ValidationError("같은 자리에 두 명을 앉힐 수 없어요.")
    if len({s.player_id for s in body.slots}) != len(body.slots):
        raise errors.ValidationError("한 사람을 두 자리에 앉힐 수 없어요.")
    outside = [s.player_id for s in body.slots if s.player_id not in by_squad[body.squad_no]]
    if outside:
        raise errors.PlayerNotInSquad(details=[errors.ErrorDetail(field="slots", reason="그날 이 팀에 배정되지 않은 선수예요.", context={"player_ids": outside})])
    key_ = play_key(play)
    db.execute(delete(EventPlayAssignment).where(
        EventPlayAssignment.event_id == event.id, EventPlayAssignment.squad_no == body.squad_no,
        EventPlayAssignment.play_key == key_,
    ))
    for s in body.slots:
        db.add(EventPlayAssignment(
            event_id=event.id, squad_no=body.squad_no, play_key=key_, slot=s.slot, player_id=s.player_id, assigned_by=by.id,
        ))
    db.commit()
    return play_view(db, event, key_, me)
