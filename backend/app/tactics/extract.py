"""역할 자동 추출 — 직접 만든 전술의 자리마다 역할을 동작에서 읽어 낸다 (docs/07 FR-58).

매니저가 편집기에서 동작만 그리면, 자리마다 "무엇을 하는 자리인지" 를 규칙으로 정한다. AI 역할 태깅(체인 D)은
이 결과를 힌트로 받아 다듬고, AI 를 쓸 수 없으면 이 결과가 그대로 쓰인다. 매니저는 편집기에서 언제든 바꿀 수 있다.

규칙 (위에서부터 먼저 맞는 것)
  1. 스크린을 건다   → 공 가진 동료에게 걸고 골밑으로 가면(또는 컷) 롤, 3점 밖으로 빠지거나 공 없는 동료에게 걸고 남으면 팝
  2. 3점 슛으로 끝낸다 (처음 공을 가진 사람이 아니면) → 슈터
  3. 컷을 한다       → 커터
  4. 드리블 · 핸드오프를 한다, 또는 공을 들고 시작해 패스로 푼다 → 볼 핸들러
  5. 골밑에서, 또는 안쪽(엘보·하이포스트)에서 시작해 미드레인지에서 공을 받는다 → 포스트
  6. 안쪽에서 시작해 3점 밖으로 빠진다 → 팝
  7. 3점 밖에서 공을 받거나 코너에서 기다린다 → 슈터
  8. 엘보·하이포스트에 선다 → 포스트, 그 밖 → 스페이서 (외곽에서 자리만 지킨다)
볼 핸들러가 한 명도 없으면 스크리너·커터가 아닌 사람 중 패스를 가장 많이 한 사람(같으면 처음 공을 가진 사람)으로 한다.
프리셋 22개의 사람이 붙인 역할과 약 3분의 2가 같다 — 나머지는 "킥아웃을 기다리는 코너" 처럼 동작에 드러나지 않는 의도라서,
AI 태깅과 매니저 수정으로 채운다.
"""

from app.tactics.court import zone_of
from app.tactics.play import Play, Point, Role

ZONE_KO = {"three": "3점 밖", "mid": "미드레인지", "paint": "골밑"}


def positions(play: Play) -> list[list[Point]]:
    """단계마다 끝난 뒤 위치 (0번째 = 시작 위치). 프론트 stepStates 와 같은 계산."""
    out = [list(play.start)]
    for step in play.steps:
        pos = list(out[-1])
        for a in step.actions:
            if a.to is not None:
                pos[a.slot - 1] = a.to
        out.append(pos)
    return out


def _zone(p: Point) -> str:
    return zone_of(p.x, max(p.y, 0.0))


def extract_roles(play: Play) -> list[tuple[Role, str]]:
    """자리 1~5 의 (역할, 이유 한 줄)."""
    pos = positions(play)
    holder = play.ball
    hold_at: list[int | None] = []  # 단계를 시작할 때 공을 가진 자리
    screens: dict[int, list[int]] = {s: [] for s in range(1, 6)}  # 스크린을 건 단계
    handled: set[int] = set()  # 드리블 · 핸드오프
    passed: dict[int, int] = {}  # 패스 · 핸드오프 횟수
    cut: set[int] = set()
    received: dict[int, list[str]] = {s: [] for s in range(1, 6)}  # 공을 받은 자리의 구역
    shot: dict[int, str] = {}
    for k, step in enumerate(play.steps):
        hold_at.append(holder)
        nxt = holder
        for a in step.actions:
            if a.type == "screen":
                screens[a.slot].append(k)
            elif a.type in ("dribble", "handoff") and a.slot == holder:
                handled.add(a.slot)
            elif a.type == "cut":
                cut.add(a.slot)
            if a.slot == holder and a.type in ("pass", "handoff") and a.target:
                passed[a.slot] = passed.get(a.slot, 0) + 1
                received[a.target].append(_zone(pos[k + 1][a.target - 1]))
                nxt = a.target
            elif a.slot == holder and a.type == "shot":
                shot[a.slot] = _zone(pos[k][a.slot - 1])
                nxt = None
        holder = nxt

    out: list[tuple[Role, str]] = []
    for s in range(1, 6):
        st, end = play.start[s - 1], pos[-1][s - 1]
        start_zone, end_zone = _zone(st), _zone(end)
        inside_start = start_zone != "three" and st.y < 0.45  # 골밑 · 엘보 · 하이포스트에서 시작 (빅맨 자리)
        if screens[s]:
            k = screens[s][0]
            on_ball = any(a.slot == s and a.type == "screen" and a.target == hold_at[k] for a in play.steps[k].actions)
            later = [a for st_ in play.steps[k + 1:] for a in st_.actions if a.slot == s and a.to is not None]
            dest = _zone(later[0].to) if later else end_zone  # type: ignore[arg-type]
            dives = bool(later) and later[0].type == "cut" or dest == "paint" and on_ball
            if dest == "three" or (not dives and not on_ball):
                out.append(("screener_pop", "스크린을 건 뒤 밖에 남거나 3점 밖으로 빠져 공을 받아요"))
            else:
                out.append(("screener_roll", "공을 가진 동료에게 스크린을 건 뒤 골밑으로 들어가요"))
        elif shot.get(s) == "three" and s != play.ball:
            out.append(("shooter", "움직여서 3점 밖에서 공을 받아 슛해요"))
        elif s in cut:
            out.append(("cutter", "공 없이 빈 곳으로 컷해 들어가요"))
        elif s in handled or (s == play.ball and s in passed):
            out.append(("ball_handler", "공을 몰고 드리블·패스로 공격을 풀어요"))
        elif shot.get(s) == "three":
            out.append(("shooter", "3점 밖에서 슛으로 마무리해요"))
        elif "paint" in received[s] or ("mid" in received[s] and inside_start):
            out.append(("post", "안쪽에서 공을 받아 마무리하거나 내줘요"))
        elif inside_start and end_zone == "three":
            out.append(("screener_pop", "안쪽에서 3점 밖으로 빠져 공간을 만들어요 (팝)"))
        elif "three" in received[s] or (end_zone == "three" and end.y < 0.2):
            out.append(("shooter", "3점 밖(코너)에서 킥아웃을 기다려요"))
        elif inside_start and start_zone == "mid":
            out.append(("post", "하이포스트·엘보에서 공을 받을 자리를 잡아요"))
        else:
            out.append(("spacer", f"{ZONE_KO[end_zone]}에서 자리를 지켜 공간을 넓혀요"))
    if not any(r == "ball_handler" for r, _ in out):
        # 볼 핸들러가 없으면 스크리너·커터가 아닌 사람 중 패스를 가장 많이 한 사람 (같으면 처음 공을 가진 사람)
        free = [s for s in range(1, 6) if out[s - 1][0] not in ("screener_roll", "screener_pop", "cutter")]
        pick = max(free, key=lambda s: (passed.get(s, 0), s == play.ball), default=None)
        if pick is not None and (passed.get(pick, 0) or pick == play.ball):
            out[pick - 1] = ("ball_handler", "공을 돌리며 공격을 시작해요")
    return out
