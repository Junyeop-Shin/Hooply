"""전술 추천 · 이름표 (docs/07 FR-43~FR-47).

추천은 그날 **확정 배정**을 기준으로 한다. 역할 점수(키 백분위 · 게스트 평균 채우기)의 기준은 그 일정 참석자
전원(블랙+화이트)이고, 슬롯 배치는 팀마다 따로 한다. 계산은 app/tactics 가 하고 여기서는 DB 에서 재료를 모은다.

권한 (docs/07 3절)
  추천(적합도·충족/미충족 속성)  매니저·ADMIN 만 — 설문에서 나온 개인 특성이라서
  이름표 보기                    그 일정 참석자(확정 배정에 든 사람 또는 참석 응답자) + 매니저
  이름표 저장                    매니저·ADMIN
"""

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
    PlayRecommendation,
    PresetList,
    SavedPlay,
    SavedPlays,
    SlotRecommendation,
    SlotsIn,
    SlotTag,
    SquadMember,
    SquadRecommendation,
    SquadTags,
    TacticRecommendation,
)
from app.services import survey_service
from app.services.assignment_service import _players_of, adopted_candidate
from app.tactics.matching import SLOTS, rank_plays
from app.tactics.presets import PRESET_LIST, PRESETS_VERSION, get_play, play_key
from app.tactics.roles import PlayerRoles, compute_role_scores, role_input_from_features

TOP_N = 3


def presets() -> PresetList:
    return PresetList(presets_version=PRESETS_VERSION, items=PRESET_LIST)


def _adopted(db: Session, event: Event) -> AssignmentCandidate:
    cand = adopted_candidate(db, event)
    if cand is None:
        raise errors.NotAdoptedYet()
    return cand


def _squad_player_ids(cand: AssignmentCandidate) -> dict[int, list[int]]:
    return {sq.squad_no: [s.player_id for s in sq.slots] for sq in cand.squads}


def _order(players: dict[int, Player], ids: list[int]) -> list[int]:
    """회원 먼저, 이름순. 동점일 때 DP 가 명단 앞사람을 남기므로 순서를 고정해 결과가 매번 같게 한다."""
    return sorted((i for i in ids if i in players), key=lambda i: (players[i].kind == PlayerKind.GUEST, players[i].display_name, i))


def _is_manager(me: Player) -> bool:
    return me.role == TeamRole.MANAGER


def _require_attendee(db: Session, event: Event, me: Player, cand: AssignmentCandidate | None) -> None:
    if _is_manager(me):
        return
    if cand is not None and any(me.id in ids for ids in _squad_player_ids(cand).values()):
        return
    attended = db.scalar(
        select(EventAttendance.id).where(
            EventAttendance.event_id == event.id, EventAttendance.player_id == me.id,
            EventAttendance.status == AttendanceStatus.ATTEND,
        )
    )
    if attended is None:
        raise errors.NotAttendee()


def role_scores_for(db: Session, event: Event, players: dict[int, Player]) -> dict[int, PlayerRoles]:
    """확정 배정에 든 사람 전원의 역할 점수. 설문은 회원만, 키·포지션은 게스트도 자기 값."""
    features = {p.id: f for p, f in survey_service._members_with_features(db, event.team_id)}
    inputs = []
    for pid, p in players.items():
        is_guest = p.kind == PlayerKind.GUEST
        inputs.append(role_input_from_features(
            pid, features.get(pid),
            height_cm=p.height_cm if p.user is None else p.user.height_cm,
            positions=[pp.position.value for pp in p.positions if pp.can_play],
            is_guest=is_guest,
        ))
    return compute_role_scores(inputs)


def recommend(db: Session, event: Event, *, squad_no: int | None, zone: bool) -> TacticRecommendation:
    cand = _adopted(db, event)
    by_squad = _squad_player_ids(cand)
    players = _players_of(db, [pid for ids in by_squad.values() for pid in ids])
    scores = role_scores_for(db, event, players)
    name = lambda pid: players[pid].display_name
    out = []
    for sq in sorted(cand.squads, key=lambda s: s.squad_no):
        if squad_no is not None and sq.squad_no != squad_no:
            continue
        roster = [scores[pid] for pid in _order(players, by_squad[sq.squad_no])]
        items = []
        if len(roster) >= SLOTS:
            for fit in rank_plays(PRESET_LIST, roster, zone=zone, top=TOP_N):
                slots = []
                for pick in fit.slots:
                    pr = scores[pick.player_id]
                    slots.append(SlotRecommendation(
                        slot=pick.slot, role=pick.role, player_id=pick.player_id, display_name=name(pick.player_id),
                        score=round(pick.score * 100), matched_attrs=pr.matched_attrs(pick.role),
                        missing_attrs=pr.missing_attrs(pick.role), alt_player_id=pick.alt_player_id,
                        alt_display_name=name(pick.alt_player_id) if pick.alt_player_id else None,
                        alt_score=round(pick.alt_score * 100) if pick.alt_score is not None else None,
                    ))
                items.append(PlayRecommendation(
                    play_key=play_key(fit.play), name=fit.play.name, summary=fit.play.summary,
                    defense=fit.play.defense, fit=fit.fit, slots=slots,
                ))
        out.append(SquadRecommendation(squad_no=sq.squad_no, squad_name=sq.squad_name, member_count=len(roster), items=items))
    return TacticRecommendation(event_id=event.id, zone=zone, presets_version=PRESETS_VERSION, squads=out)


def _my_squad(cand: AssignmentCandidate | None, me: Player) -> int | None:
    if cand is None or me.id is None:
        return None
    return next((no for no, ids in _squad_player_ids(cand).items() if me.id in ids), None)


def play_view(db: Session, event: Event, key: str, me: Player) -> EventPlayView:
    play = get_play(key)
    if play is None:
        raise errors.NotFound("없는 전술이에요.")
    cand = adopted_candidate(db, event)
    _require_attendee(db, event, me, cand)
    squads: list[SquadTags] = []
    if cand is not None:
        by_squad = _squad_player_ids(cand)
        players = _players_of(db, [pid for ids in by_squad.values() for pid in ids])
        rows = db.scalars(
            select(EventPlayAssignment).where(
                EventPlayAssignment.event_id == event.id, EventPlayAssignment.play_key == play_key(play)
            )
        ).all()
        for sq in sorted(cand.squads, key=lambda s: s.squad_no):
            ids = set(by_squad[sq.squad_no])
            tags = sorted(
                (r for r in rows if r.squad_no == sq.squad_no and r.player_id in ids and r.player_id in players),
                key=lambda r: r.slot,
            )
            squads.append(SquadTags(
                squad_no=sq.squad_no, squad_name=sq.squad_name,
                members=[
                    SquadMember(player_id=pid, display_name=players[pid].display_name, is_guest=players[pid].kind == PlayerKind.GUEST)
                    for pid in _order(players, by_squad[sq.squad_no])
                ],
                slots=[SlotTag(slot=r.slot, player_id=r.player_id, display_name=players[r.player_id].display_name) for r in tags],
            ))
    return EventPlayView(
        play_key=play_key(play), play=play, can_edit=_is_manager(me), my_squad_no=_my_squad(cand, me), squads=squads,
    )


def save_slots(db: Session, event: Event, key: str, body: SlotsIn, by: User, me: Player) -> EventPlayView:
    play = get_play(key)
    if play is None:
        raise errors.NotFound("없는 전술이에요.")
    cand = _adopted(db, event)
    by_squad = _squad_player_ids(cand)
    if body.squad_no not in by_squad:
        raise errors.NotFound("그날 배정에 없는 팀이에요.")
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


def saved_plays(db: Session, event: Event, me: Player) -> SavedPlays:
    """그날 이름표가 저장된 전술 목록 (전술 탭에서 참석자에게 보여 준다). 지금 확정 배정의 팀 구성과 맞는 행만 센다."""
    cand = adopted_candidate(db, event)
    _require_attendee(db, event, me, cand)
    items: list[SavedPlay] = []
    if cand is not None:
        by_squad = {no: set(ids) for no, ids in _squad_player_ids(cand).items()}
        names = {sq.squad_no: sq.squad_name for sq in cand.squads}
        rows = db.scalars(select(EventPlayAssignment).where(EventPlayAssignment.event_id == event.id)).all()
        counts: dict[tuple[str, int], int] = {}
        for r in rows:
            if r.player_id in by_squad.get(r.squad_no, ()):
                counts[(r.play_key, r.squad_no)] = counts.get((r.play_key, r.squad_no), 0) + 1
        order = {play_key(p): i for i, p in enumerate(PRESET_LIST)}
        for (k, no), n in sorted(counts.items(), key=lambda kv: (kv[0][1], order.get(kv[0][0], 99))):
            play = get_play(k)
            if play is not None:
                items.append(SavedPlay(play_key=k, name=play.name, squad_no=no, squad_name=names[no], filled=n))
    return SavedPlays(event_id=event.id, can_edit=_is_manager(me), my_squad_no=_my_squad(cand, me), items=items)
