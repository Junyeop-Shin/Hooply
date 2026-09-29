"""프리셋 전술 8개 (docs/07 FR-42, 6절). 이 파일이 정본이며 DB 에 두지 않는다.

좌표는 0~1 (court.py 기준: x 왼쪽→오른쪽, y 베이스라인→하프라인). 자주 쓰는 자리는 아래 상수로 모았다.
슬롯 번호는 전술 안의 자리 번호이지 포지션 번호가 아니다.

전술을 고치거나 추가하면 `PRESETS_VERSION` 을 올린다 — LLM 설명 캐시 키에 들어간다 (FR-49).
"""

from app.tactics.play import Play

PRESETS_VERSION = 1

# 자주 쓰는 자리 (x, y)
TOP = (0.5, 0.66)  # 탑 3점 밖
R_WING, L_WING = (0.85, 0.48), (0.15, 0.48)  # 45도 윙 3점 밖
R_CORNER, L_CORNER = (0.95, 0.05), (0.05, 0.05)  # 코너 3점
R_ELBOW, L_ELBOW = (0.66, 0.42), (0.34, 0.42)  # 자유투 라인 양 끝
R_BLOCK, L_BLOCK = (0.66, 0.16), (0.34, 0.16)  # 로우포스트
HIGH_POST = (0.5, 0.42)  # 자유투 라인 가운데
RIM = (0.52, 0.13)  # 골밑 마무리 자리 (림 바로 앞)


def _p(xy: tuple[float, float]) -> dict:
    return {"x": xy[0], "y": xy[1]}


def _play(key: str, name: str, summary: str, defense: str, start: list, ball: int, roles: list, steps: list) -> Play:
    return Play.model_validate({
        "key": key, "name": name, "summary": summary, "defense": defense,
        "start": [_p(s) for s in start], "ball": ball, "roles": roles,
        "steps": [{"caption": c, "actions": a} for c, a in steps],
    })


def _move(slot: int, to, kind: str = "move") -> dict:
    return {"type": kind, "slot": slot, "to": _p(to)}


def _screen(slot: int, to, target: int) -> dict:
    return {"type": "screen", "slot": slot, "to": _p(to), "target": target}


def _pass(slot: int, target: int, kind: str = "pass") -> dict:
    return {"type": kind, "slot": slot, "target": target}


def _shot(slot: int) -> dict:
    return {"type": "shot", "slot": slot}


PRESET_LIST: list[Play] = [
    _play(
        "high_pnr", "하이 픽앤롤", "빅맨이 탑에서 스크린, 핸들러가 돌파한 뒤 롤하는 빅맨에게", "man",
        [TOP, R_CORNER, L_CORNER, L_WING, R_ELBOW], 1,
        ["ball_handler", "shooter", "shooter", "spacer", "screener_roll"],
        [
            ("5번이 탑으로 올라와 1번에게 스크린", [_screen(5, (0.57, 0.63), 1)]),
            ("1번이 스크린을 타고 오른쪽으로 돌파, 5번은 림으로 롤",
             [_move(1, (0.72, 0.4), "dribble"), _move(5, RIM, "cut"), _move(4, (0.26, 0.62))]),
            ("1번이 롤하는 5번에게 패스 (막히면 오른쪽 코너 2번에게)", [_pass(1, 5)]),
            ("5번 골밑 마무리", [_shot(5)]),
        ],
    ),
    _play(
        "horns", "혼즈", "양쪽 엘보에 빅맨 둘, 한 명은 롤하고 한 명은 3점으로 팝", "man",
        [TOP, R_CORNER, L_CORNER, L_ELBOW, R_ELBOW], 1,
        ["ball_handler", "shooter", "shooter", "screener_pop", "screener_roll"],
        [
            ("5번이 엘보에서 올라와 1번에게 스크린", [_screen(5, (0.58, 0.62), 1)]),
            ("1번 오른쪽으로 돌파, 5번 롤, 4번은 탑 3점으로 팝",
             [_move(1, (0.72, 0.42), "dribble"), _move(5, RIM, "cut"), _move(4, (0.42, 0.66))]),
            ("1번이 팝한 4번에게 패스 (롤한 5번·코너도 선택지)", [_pass(1, 4)]),
            ("4번 3점 슛", [_shot(4)]),
        ],
    ),
    _play(
        "weave", "핸드오프 위브", "가드·윙이 핸드오프로 공을 이어받으며 수비를 흔든다", "man",
        [TOP, R_WING, L_WING, L_BLOCK, R_BLOCK], 1,
        ["ball_handler", "ball_handler", "shooter", "spacer", "spacer"],
        [
            ("1번이 오른쪽으로 드리블, 2번이 받으러 올라온다",
             [_move(1, (0.7, 0.6), "dribble"), _move(2, (0.76, 0.57))]),
            ("1번이 2번에게 핸드오프", [_pass(1, 2, "handoff")]),
            ("2번이 가운데로 드리블, 1번은 오른쪽 윙으로, 3번이 받으러 온다",
             [_move(2, (0.42, 0.62), "dribble"), _move(1, R_WING), _move(3, (0.34, 0.58))]),
            ("2번이 3번에게 핸드오프", [_pass(2, 3, "handoff")]),
            ("3번이 왼쪽으로 돌파, 2번은 탑으로 빠진다",
             [_move(3, (0.3, 0.3), "dribble"), _move(2, TOP)]),
            ("수비가 몰리면 3번이 오른쪽 윙 1번에게 킥아웃 → 3점", [_pass(3, 1)]),
        ],
    ),
    _play(
        "pistol", "피스톨(21)", "속공 뒤 바로 이어지는 윙 핸드오프와 픽앤롤", "man",
        [(0.72, 0.85), R_CORNER, L_CORNER, L_WING, (0.5, 0.8)], 1,
        ["shooter", "ball_handler", "spacer", "spacer", "screener_roll"],
        [
            ("1번이 오른쪽 윙으로 드리블, 2번이 코너에서 올라온다",
             [_move(1, (0.8, 0.6), "dribble"), _move(2, (0.84, 0.52)), _move(5, (0.55, 0.7))]),
            ("1번이 2번에게 핸드오프", [_pass(1, 2, "handoff")]),
            ("5번이 2번에게 스크린, 1번은 오른쪽 코너로",
             [_screen(5, (0.72, 0.56), 2), _move(1, R_CORNER)]),
            ("2번 가운데로 돌파, 5번 롤", [_move(2, (0.6, 0.38), "dribble"), _move(5, (0.46, 0.14), "cut")]),
            ("2번이 롤하는 5번에게 패스 (막히면 코너 1번에게)", [_pass(2, 5)]),
            ("5번 골밑 마무리", [_shot(5)]),
        ],
    ),
    _play(
        "floppy", "플로피", "슈터가 골밑에서 빅맨 스크린을 돌아 나와 캐치앤슛", "man",
        [TOP, (0.5, 0.08), L_WING, L_BLOCK, R_BLOCK], 1,
        ["ball_handler", "shooter", "spacer", "screener_pop", "screener_pop"],
        [
            ("4번·5번이 양쪽 블록에서 대기, 5번이 2번에게 스크린", [_screen(5, (0.63, 0.19), 2)]),
            ("2번이 스크린을 돌아 오른쪽 윙으로, 5번은 미드레인지로 팝",
             [_move(2, (0.85, 0.45), "cut"), _move(5, (0.7, 0.32))]),
            ("1번이 2번에게 패스", [_pass(1, 2)]),
            ("2번 캐치앤슛 3점", [_shot(2)]),
        ],
    ),
    _play(
        "ucla", "UCLA 컷", "패스한 가드가 하이포스트 스크린을 스쳐 림으로 컷", "man",
        [TOP, R_WING, L_WING, L_CORNER, HIGH_POST], 1,
        ["cutter", "ball_handler", "spacer", "spacer", "screener_pop"],
        [
            ("1번이 오른쪽 윙 2번에게 패스", [_pass(1, 2)]),
            ("5번이 하이포스트에서 1번에게 스크린", [_screen(5, (0.55, 0.52), 1)]),
            ("1번이 스크린을 스쳐 림으로 컷, 5번은 탑으로 팝",
             [_move(1, RIM, "cut"), _move(5, TOP)]),
            ("2번이 컷하는 1번에게 패스 (막히면 탑의 5번에게)", [_pass(2, 1)]),
            ("1번 골밑 레이업", [_shot(1)]),
        ],
    ),
    _play(
        "post_split", "포스트 엔트리 + 스플릿", "포스트에 공을 넣고, 넣은 두 사람이 엇갈려 컷", "any",
        [TOP, R_WING, L_WING, R_BLOCK, L_CORNER], 1,
        ["cutter", "cutter", "spacer", "post", "spacer"],
        [
            ("1번이 오른쪽 윙 2번에게 패스", [_pass(1, 2)]),
            ("2번이 로우포스트 4번에게 투입", [_pass(2, 4)]),
            ("2번이 올라가 1번에게 스크린", [_screen(2, (0.64, 0.6), 1)]),
            ("1번은 스크린을 타고 오른쪽 윙으로, 2번은 림으로 컷 (스플릿)",
             [_move(1, R_WING), _move(2, RIM, "cut")]),
            ("4번이 컷하는 2번에게 패스 (막히면 포스트업 슛)", [_pass(4, 2)]),
            ("2번 골밑 마무리", [_shot(2)]),
        ],
    ),
    _play(
        "zone_131", "1-3-1 지역 공격", "자유투 라인에 공을 넣어 지역 수비 가운데를 가른다", "zone",
        [TOP, R_WING, L_WING, (0.64, 0.04), HIGH_POST], 1,
        ["ball_handler", "shooter", "shooter", "cutter", "post"],
        [
            ("1번이 자유투 라인 5번에게 패스", [_pass(1, 5)]),
            ("4번이 베이스라인을 따라 반대편 골밑으로", [_move(4, (0.4, 0.12), "cut")]),
            ("5번이 골밑 4번에게 패스 (막히면 양쪽 윙으로 킥아웃)", [_pass(5, 4)]),
            ("4번 골밑 슛", [_shot(4)]),
        ],
    ),
]

PRESETS: dict[str, Play] = {p.key: p for p in PRESET_LIST}
PLAY_KEY_PREFIX = "preset:"


def play_key(play: Play) -> str:
    return f"{PLAY_KEY_PREFIX}{play.key}"


def get_play(key: str) -> Play | None:
    """"preset:high_pnr" 또는 "high_pnr" → Play. 없으면 None."""
    return PRESETS.get(key.removeprefix(PLAY_KEY_PREFIX))
