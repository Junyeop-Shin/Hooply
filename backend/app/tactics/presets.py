"""프리셋 전술 22개 (docs/07 FR-42, 6절 — 1단계 8개 + O5 6개 + 지역 수비 6개 + 인바운드 2개). 이 파일이 정본이며 DB 에 두지 않는다.

좌표는 0~1 (court.py 기준: x 왼쪽→오른쪽, y 베이스라인→하프라인). 자주 쓰는 자리는 아래 상수로 모았다.
슬롯 번호는 전술 안의 자리 번호이지 포지션 번호가 아니다.

전술을 고치거나 추가하면 `PRESETS_VERSION` 을 올린다 — LLM 설명 캐시 키에 들어간다 (FR-49).
"""

from app.tactics.play import Play

PRESETS_VERSION = 5  # 5: 전술마다 막혔을 때의 대안(counter). 2: 스페인 픽앤롤 · 혼즈 플레어 · 스태거 · 해머 · 아이버슨 컷 · 오버로드 (명세 O5). 3: 지역 수비 4개. 4: 지역 2개 · 인바운드 2개

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


def _play(key: str, name: str, summary: str, defense: str, start: list, ball: int, roles: list, steps: list, situation: str = "half_court") -> Play:
    return Play.model_validate({
        "key": key, "name": name, "summary": summary, "defense": defense, "situation": situation,
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

# --- O5 에서 더한 6개 ---
PRESET_LIST += [
    _play(
        "spain_pnr", "스페인 픽앤롤", "픽앤롤에 슈터의 백스크린을 더해 롤하는 빅맨을 풀어 준다", "man",
        [TOP, R_CORNER, L_CORNER, L_WING, R_ELBOW], 1,
        ["ball_handler", "shooter", "spacer", "spacer", "screener_roll"],
        [
            ("5번이 탑으로 올라와 1번에게 스크린, 2번은 코너에서 페인트로 올라온다",
             [_screen(5, (0.57, 0.62), 1), _move(2, (0.56, 0.36))]),
            ("1번 오른쪽 돌파, 5번 롤, 2번이 롤하는 5번을 위해 백스크린",
             [_move(1, (0.74, 0.44), "dribble"), _move(5, RIM, "cut"), _screen(2, (0.55, 0.28), 5)]),
            ("2번은 탑 3점으로 팝, 1번이 롤한 5번에게 패스 (막히면 팝한 2번에게)",
             [_move(2, (0.42, 0.66)), _pass(1, 5)]),
            ("5번 골밑 마무리", [_shot(5)]),
        ],
    ),
    _play(
        "horns_flare", "혼즈 플레어", "혼즈에서 엘보로 공을 넣고, 반대편 슈터를 플레어 스크린으로 풀어 3점", "man",
        [TOP, R_CORNER, L_CORNER, L_ELBOW, R_ELBOW], 1,
        ["ball_handler", "shooter", "spacer", "post", "screener_pop"],
        [
            ("1번이 왼쪽 엘보 4번에게 패스", [_pass(1, 4)]),
            ("2번이 코너에서 올라오고, 5번이 2번에게 플레어 스크린",
             [_move(2, (0.8, 0.28)), _screen(5, (0.74, 0.36), 2)]),
            ("2번이 스크린 반대쪽 오른쪽 윙 3점으로 빠진다", [_move(2, (0.9, 0.44))]),
            ("4번이 2번에게 크로스코트 패스", [_pass(4, 2)]),
            ("2번 3점 슛", [_shot(2)]),
        ],
    ),
    _play(
        "stagger", "스태거", "빅맨 둘이 연달아 스크린, 슈터가 두 스크린을 타고 윙에서 캐치앤슛", "man",
        [TOP, (0.2, 0.07), R_WING, (0.4, 0.22), L_ELBOW], 1,
        ["ball_handler", "shooter", "spacer", "screener_pop", "screener_roll"],
        [
            ("4번이 베이스라인의 2번에게 첫 번째 스크린", [_screen(4, (0.29, 0.18), 2)]),
            ("5번이 두 번째 스크린, 2번은 두 스크린을 타고 왼쪽 윙으로",
             [_screen(5, (0.25, 0.33), 2), _move(2, (0.13, 0.5), "cut")]),
            ("1번이 2번에게 패스", [_pass(1, 2)]),
            ("2번 캐치앤슛 3점", [_shot(2)]),
        ],
    ),
    _play(
        "hammer", "해머", "베이스라인 돌파에 맞춰 반대편 슈터를 코너로 빼 주는 킥아웃 3점", "man",
        [R_WING, L_WING, R_CORNER, L_BLOCK, HIGH_POST], 1,
        ["ball_handler", "shooter", "spacer", "screener_pop", "post"],
        [
            ("1번이 오른쪽 윙에서 베이스라인 쪽으로 돌파", [_move(1, (0.75, 0.2), "dribble")]),
            ("4번이 2번에게 해머 스크린, 2번은 왼쪽 코너로",
             [_screen(4, (0.2, 0.22), 2), _move(2, L_CORNER)]),
            ("1번이 코너의 2번에게 킥아웃", [_pass(1, 2)]),
            ("2번 코너 3점", [_shot(2)]),
        ],
    ),
    _play(
        "iverson_cut", "아이버슨 컷", "득점원이 양쪽 엘보 스크린을 차례로 스치며 탑을 가로질러 공을 받는다", "man",
        [TOP, R_WING, L_CORNER, L_ELBOW, R_ELBOW], 1,
        ["ball_handler", "cutter", "spacer", "screener_pop", "screener_roll"],
        [
            ("1번이 왼쪽으로 드리블해 자리를 비운다", [_move(1, (0.3, 0.68), "dribble")]),
            ("5번·4번 엘보 스크린, 2번이 두 스크린을 스치며 왼쪽 윙으로",
             [_screen(5, (0.62, 0.48), 2), _screen(4, (0.4, 0.48), 2), _move(2, (0.16, 0.46), "cut")]),
            ("1번이 2번에게 패스", [_pass(1, 2)]),
            ("2번이 가운데로 돌파", [_move(2, (0.42, 0.3), "dribble")]),
            ("2번 돌파 마무리", [_shot(2)]),
        ],
    ),
    _play(
        "overload", "오버로드", "한쪽에 셋을 모아 지역 수비를 한쪽으로 끌고 짧은 코너에서 마무리", "zone",
        [TOP, R_WING, L_WING, HIGH_POST, R_BLOCK], 1,
        ["ball_handler", "shooter", "shooter", "post", "screener_pop"],
        [
            ("3번이 반대편 오른쪽 코너로 옮겨 가고, 5번은 짧은 코너로 내려간다",
             [_move(3, R_CORNER, "cut"), _move(5, (0.8, 0.18))]),
            ("1번이 오른쪽 윙 2번에게 패스", [_pass(1, 2)]),
            ("2번이 코너 3번에게 패스, 지역 수비가 코너로 끌려 나온다", [_pass(2, 3)]),
            ("3번이 짧은 코너 5번에게 패스", [_pass(3, 5)]),
            ("5번 베이스라인 점퍼 (막히면 하이포스트 4번에게)", [_shot(5)]),
        ],
    ),
]

# --- 지역 수비(2-3 · 3-2) 공략 4개 ---
PRESET_LIST += [
    _play(
        "baseline_runner", "베이스라인 러너", "슈터가 지역 수비 뒤 베이스라인을 따라 반대편 코너로 달려 3점", "zone",
        [TOP, L_CORNER, R_WING, HIGH_POST, R_BLOCK], 1,
        ["ball_handler", "shooter", "spacer", "post", "screener_roll"],
        [
            ("1번이 오른쪽 윙 3번에게 패스, 지역 수비가 오른쪽으로 움직인다", [_pass(1, 3)]),
            ("2번이 베이스라인을 따라 오른쪽 코너로 달리고, 5번이 뒷줄 수비를 막아 준다",
             [_move(2, R_CORNER, "cut"), _screen(5, (0.8, 0.12), 2)]),
            ("3번이 코너의 2번에게 패스", [_pass(3, 2)]),
            ("2번 코너 3점", [_shot(2)]),
        ],
    ),
    _play(
        "skip_reversal", "스킵 패스 전환", "한쪽으로 수비를 몰아 놓고 반대편 윙으로 한 번에 넘겨 3점", "zone",
        [TOP, R_WING, L_WING, L_BLOCK, R_BLOCK], 1,
        ["ball_handler", "ball_handler", "shooter", "post", "screener_pop"],
        [
            ("1번이 오른쪽 윙 2번에게 패스, 지역 수비가 오른쪽으로 쏠린다", [_pass(1, 2)]),
            ("5번이 짧은 코너로 내려가 수비를 더 끌고, 3번은 왼쪽 윙에서 넓게 선다",
             [_move(5, (0.8, 0.18)), _move(3, (0.12, 0.4))]),
            ("2번이 반대편 3번에게 스킵 패스", [_pass(2, 3)]),
            ("3번 3점 슛 (수비가 달려 나오면 골밑 4번에게)", [_shot(3)]),
        ],
    ),
    _play(
        "gap_attack", "갭 돌파 킥아웃", "앞줄 수비 두 명 사이로 파고들어 둘을 끌어들인 뒤 윙으로 빼 준다", "zone",
        [TOP, R_WING, L_WING, L_BLOCK, R_BLOCK], 1,
        ["ball_handler", "shooter", "spacer", "post", "screener_roll"],
        [
            ("1번이 앞줄 두 수비 사이(가운데)로 드리블 돌파", [_move(1, (0.5, 0.46), "dribble")]),
            ("두 수비가 몰리면 2번은 윙에서 넓게 서고, 5번은 골밑으로",
             [_move(2, (0.88, 0.42)), _move(5, (0.6, 0.12), "cut")]),
            ("1번이 오른쪽 윙 2번에게 킥아웃", [_pass(1, 2)]),
            ("2번 3점 슛 (막히면 골밑 5번에게)", [_shot(2)]),
        ],
    ),
    _play(
        "high_low", "하이-로우", "빅맨이 자유투 라인으로 올라와 받고, 골밑의 빅맨에게 내려 준다", "zone",
        [TOP, R_WING, L_WING, L_BLOCK, R_BLOCK], 1,
        ["ball_handler", "shooter", "shooter", "post", "post"],
        [
            ("4번이 골밑에서 자유투 라인으로 올라온다 (플래시)", [_move(4, HIGH_POST, "cut")]),
            ("1번이 자유투 라인 4번에게 패스, 5번은 골밑에서 수비를 등지고 자리 잡는다",
             [_pass(1, 4), _move(5, (0.58, 0.15))]),
            ("4번이 골밑 5번에게 내려 주는 패스", [_pass(4, 5)]),
            ("5번 골밑 슛", [_shot(5)]),
        ],
    ),
]

# --- 지역 수비 2개 더 (존 스크린 · 3-2 공략) ---
PRESET_LIST += [
    _play(
        "zone_screen_flare", "존 스크린 플레어", "빅맨 둘이 탑으로 올라오고, 한 명이 가드 쪽 수비를 막아 가드가 윙으로 빠져 3점", "zone",
        [TOP, R_CORNER, L_WING, L_BLOCK, R_BLOCK], 1,
        ["shooter", "spacer", "spacer", "post", "screener_pop"],
        [
            ("4번·5번이 골밑에서 탑 양쪽으로 올라온다", [_move(4, (0.4, 0.58)), _move(5, (0.6, 0.58))]),
            ("1번이 4번에게 패스", [_pass(1, 4)]),
            ("5번이 1번 쪽 수비를 막는 스크린, 1번은 오른쪽 윙으로 빠진다",
             [_screen(5, (0.6, 0.64), 1), _move(1, (0.86, 0.52))]),
            ("4번이 오른쪽 윙 1번에게 스킵 패스", [_pass(4, 1)]),
            ("1번 3점 슛", [_shot(1)]),
        ],
    ),
    _play(
        "corner_entry_212", "2-1-2 코너 엔트리", "3-2 지역 수비 공략 — 코너로 공을 넣고, 넣은 사람이 짧은 코너로 파고든다", "zone",
        [(0.34, 0.66), (0.66, 0.66), L_CORNER, R_CORNER, HIGH_POST], 1,
        ["cutter", "spacer", "shooter", "spacer", "post"],
        [
            ("1번이 왼쪽 코너 3번에게 패스", [_pass(1, 3)]),
            ("1번은 왼쪽 짧은 코너로 파고들고, 2번은 1번 자리로, 4번은 오른쪽 윙으로",
             [_move(1, (0.22, 0.16), "cut"), _move(2, (0.34, 0.66)), _move(4, (0.82, 0.46))]),
            ("3번이 짧은 코너의 1번에게 패스", [_pass(3, 1)]),
            ("1번 짧은 코너 슛 (막히면 골밑으로 내려오는 5번에게)", [_shot(1)]),
        ],
    ),
]

# --- 인바운드 (골밑 베이스라인에서 공을 넣을 때) — 오늘 추천에는 넣지 않고 목록에서 따로 보여 준다 ---
INBOUNDER = (0.62, -0.05)  # 베이스라인 뒤, 림 오른쪽
PRESET_LIST += [
    _play(
        "box_inbound", "박스 인바운드", "페인트 네 귀퉁이에서 시작 — 스크린을 걸어 준 사람에게 다시 스크린을 걸어 골밑 슛", "any",
        [INBOUNDER, L_ELBOW, R_ELBOW, L_BLOCK, R_BLOCK], 1,
        ["ball_handler", "shooter", "spacer", "cutter", "screener_roll"],
        [
            ("4번이 2번에게 다운스크린, 2번은 왼쪽 코너로 빠진다",
             [_screen(4, (0.34, 0.3), 2), _move(2, L_CORNER)]),
            ("5번이 스크린을 건 4번에게 다시 스크린, 4번은 골밑으로 컷, 3번은 탑으로 빠진다",
             [_screen(5, (0.44, 0.24), 4), _move(4, (0.5, 0.12), "cut"), _move(3, (0.62, 0.68))]),
            ("1번이 골밑 4번에게 패스 (막히면 코너 2번이나 탑 3번에게)", [_pass(1, 4)]),
            ("4번 골밑 마무리", [_shot(4)]),
        ],
        situation="inbound",
    ),
    _play(
        "stack_slip", "스택 슬립", "한 줄로 서 있다가 앞의 둘이 양쪽으로 갈라지면 셋째가 빈자리로 들어가 레이업", "any",
        [INBOUNDER, (0.5, 0.26), (0.5, 0.36), (0.5, 0.46), (0.5, 0.56)], 1,
        ["ball_handler", "shooter", "shooter", "cutter", "spacer"],
        [
            ("앞의 2번·3번이 양쪽 코너로 갈라지고, 5번은 탑으로 올라간다",
             [_move(2, (0.08, 0.12)), _move(3, (0.92, 0.12)), _move(5, (0.5, 0.7))]),
            ("4번이 빈자리로 미끄러져 골밑으로", [_move(4, (0.5, 0.12), "cut")]),
            ("1번이 4번에게 패스 (막히면 코너 2번·3번에게)", [_pass(1, 4)]),
            ("4번 레이업", [_shot(4)]),
        ],
        situation="inbound",
    ),
]

# 막혔을 때의 대안 — 자리는 {n}. 첫 선택지가 막히면 다음 선택지, 그래도 안 되면 다시 시작할 곳까지
COUNTERS: dict[str, str] = {
    "high_pnr": "{5}의 롤이 막히면 오른쪽 코너 {2}에게 킥아웃, 그것도 막히면 {4}에게 돌려 다시 시작해요",
    "horns": "{4}의 팝이 막히면 롤하는 {5}나 코너 {2}에게, 둘 다 막히면 {1}이 직접 돌파해요",
    "weave": "핸드오프 때 수비가 앞을 막으면 {3}이 바로 골밑으로 컷하고, {1}은 윙에서 받을 준비를 해요",
    "pistol": "{5}의 롤이 막히면 코너 {1}에게, 스크린이 늦으면 {2}가 그대로 돌파해요",
    "floppy": "{2}가 막히면 반대쪽 {4}의 스크린으로 방향을 바꾸고, 그래도 안 되면 팝한 {5}에게 줘요",
    "ucla": "{1}의 컷이 막히면 탑으로 팝한 {5}에게, {5}는 반대편 {3}에게 넘겨 다시 시작해요",
    "post_split": "{4}가 등을 지고 막히면 컷하는 {1}·{2}에게, 둘 다 막히면 반대편 {3}에게 빼 줘요",
    "zone_131": "{4}가 골밑에서 막히면 {5}가 양쪽 윙 {2}·{3}에게 킥아웃해요",
    "spain_pnr": "{5}의 롤이 막히면 탑으로 팝한 {2}에게, {2}도 막히면 왼쪽 {4}에게 돌려요",
    "horns_flare": "{2}가 막히면 {4}가 {5}에게 넘기거나 {1}에게 돌려 반대로 다시 시작해요",
    "stagger": "{2}가 첫 스크린에서 막히면 골밑으로 컷하고, {4}는 탑으로 올라와 받을 준비를 해요",
    "hammer": "코너 {2}가 막히면 골밑으로 들어오는 {5}에게, 둘 다 막히면 {1}이 직접 마무리해요",
    "iverson_cut": "{2}가 받기 어려우면 {5}가 {1}에게 픽앤롤을 걸고, 막히면 {3}에게 빼 줘요",
    "overload": "짧은 코너 {5}가 막히면 하이포스트 {4}에게, 수비가 다 쏠리면 반대편 {1}에게 넘겨요",
    "baseline_runner": "코너 {2}가 막히면 {5}가 골밑으로 들어가 받고, 아니면 {3}이 탑의 {1}에게 돌려요",
    "skip_reversal": "{3}에게 수비가 달려 나오면 골밑 {4}에게, 막히면 탑 {1}에게 돌려 반대로 다시 시작해요",
    "gap_attack": "윙 {2}가 막히면 골밑 {5}에게, 두 수비가 안 몰리면 {1}이 그대로 풀업을 쏴요",
    "high_low": "골밑 {5}가 막히면 {4}가 자유투 라인에서 직접 쏘거나 윙 {2}·{3}에게 빼 줘요",
    "zone_screen_flare": "{1}이 막히면 스크린을 건 {5}가 골밑으로 들어가고, {4}는 반대편 {3}에게 넘겨요",
    "corner_entry_212": "짧은 코너 {1}이 막히면 골밑으로 내려오는 {5}에게, 둘 다 막히면 {3}이 {2}에게 돌려요",
    "box_inbound": "{4}가 막히면 코너로 빠진 {2}에게, 그것도 막히면 탑으로 빠진 {3}에게 안전하게 넣어요",
    "stack_slip": "{4}가 막히면 양쪽 코너 {2}·{3}에게, 다 막히면 탑으로 올라간 {5}에게 안전하게 넣어요",
}
# 이 전술이 가정한 상대 수비의 스크린 대응 (전술판 수비 움직임이 이대로 고정된다, docs/07 D17).
# 기본은 스테이(스크린을 돌아 따라옴). 아래는 스위치를 깨려고 만든 전술이라 스위치를 가정한다
SWITCH_PLAYS = {
    "spain_pnr",  # 롤하는 빅맨의 수비에게 백스크린 — 스위치로 막으면 롤맨이 빈다
    "post_split",  # 포스트 투입 뒤 두 사람이 엇갈려 컷 — 스위치 혼선을 노린다
    "box_inbound",  # 스크린을 건 사람에게 다시 스크린(스크린 더 스크리너) — 스위치를 깬다
}
PRESET_LIST = [
    p.model_copy(update={"counter": COUNTERS.get(p.key, ""), "screen_call": "switch" if p.key in SWITCH_PLAYS else "stay"})
    for p in PRESET_LIST
]

PRESETS: dict[str, Play] = {p.key: p for p in PRESET_LIST}
PLAY_KEY_PREFIX = "preset:"
TEAM_KEY_PREFIX = "team:"  # 팀이 직접 만든 전술 — Play.key 는 "team_<id>", play_key 는 "team:<id>" (team_plays)


def play_key(play: Play) -> str:
    if play.key.startswith("team_"):
        return f"{TEAM_KEY_PREFIX}{play.key.removeprefix('team_')}"
    return f"{PLAY_KEY_PREFIX}{play.key}"


def team_play_id(key: str) -> int | None:
    """"team:12" → 12 (team_plays.id). 프리셋 키나 형식이 어긋나면 None — 댓글 · 별표 · 자리 배치의 team_play_id FK 값."""
    if not key.startswith(TEAM_KEY_PREFIX):
        return None
    raw = key.removeprefix(TEAM_KEY_PREFIX)
    return int(raw) if raw.isdigit() else None


def get_play(key: str) -> Play | None:
    """"preset:high_pnr" 또는 "high_pnr" → Play. 없으면 None."""
    return PRESETS.get(key.removeprefix(PLAY_KEY_PREFIX))
