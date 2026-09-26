"""Hooply 배지 아이콘 원본 — 틀 5종 + 그림 12종을 여기 한 곳에서 정의하고 세 가지를 만든다.

  python3 docs/badges/badge_art.py

  1) frontend/src/components/badge-art.ts   앱이 쓰는 SVG 조각 (BadgeIcon 컴포넌트가 조합)
  2) docs/badges/svg/*.svg                  배지마다 완성된 SVG 파일 (틀 + 그림, 단독으로 열림)
  3) docs/badges/preview.html               전체 목록 미리보기 (브라우저로 열기)

아이콘을 고칠 때는 이 파일만 고치고 다시 실행한다. 생성된 파일을 손으로 고치면 다음 실행에서 덮어써진다.
규칙은 docs/06-배지.md 참고.
"""

from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TS_OUT = ROOT / "frontend" / "src" / "components" / "badge-art.ts"
SVG_DIR = ROOT / "docs" / "badges" / "svg"
PREVIEW = ROOT / "docs" / "badges" / "preview.html"

# ---------------------------------------------------------------------------
# 색 — 앱 index.css 토큰과 같은 값. 금속 색은 테두리에만 쓴다
# ---------------------------------------------------------------------------
O, OL = "#f26b1d", "#ffa66b"          # 오렌지 / 밝은 오렌지 (포인트)
NV, NM, NS, NL = "#14213d", "#3d5480", "#e0e6f0", "#c2cde0"  # 네이비 / 중간 / 옅은 / 옅은2
Y, W = "#f5c542", "#ffffff"          # 노랑(불꽃 속·별) / 흰색

CX, CY = 32.0, 32.0  # 메달 중심 (viewBox 0 0 64 64)
PICT_SHIFT = 5       # 그림은 (32,27) 기준으로 그렸으므로 5 내려 메달 중심에 맞춘다


def f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# 틀 조각
# ---------------------------------------------------------------------------
def scallop(r_in: float, r_out: float, n: int) -> str:
    """톱니(물결) 테두리 — n 개의 볼록한 호."""
    d = ""
    for k in range(n):
        a0 = 2 * math.pi * k / n - math.pi / 2
        a1 = 2 * math.pi * (k + 1) / n - math.pi / 2
        am = (a0 + a1) / 2
        x0, y0 = CX + r_in * math.cos(a0), CY + r_in * math.sin(a0)
        x1, y1 = CX + r_in * math.cos(a1), CY + r_in * math.sin(a1)
        qx, qy = CX + r_out * math.cos(am), CY + r_out * math.sin(am)
        if k == 0:
            d += f"M{f(x0)} {f(y0)}"
        d += f"Q{f(qx)} {f(qy)} {f(x1)} {f(y1)}"
    return d + "Z"


def laurel(side: int) -> str:
    """월계수 가지 (side -1 왼쪽, 1 오른쪽): 줄기 호 + 잎 6장."""
    r_stem, r_leaf = 21.6, 23.0
    degs = [112, 128, 144, 160, 176, 192]
    a0, a1 = math.radians(degs[0] - 4), math.radians(degs[-1] + 6)
    if side > 0:
        a0, a1 = math.pi - a0, math.pi - a1
    x0, y0 = CX + r_stem * math.cos(a0), CY + r_stem * math.sin(a0)
    x1, y1 = CX + r_stem * math.cos(a1), CY + r_stem * math.sin(a1)
    out = [f'<path d="M{f(x0)} {f(y0)}A{r_stem} {r_stem} 0 0 {1 if side < 0 else 0} {f(x1)} {f(y1)}" fill="none" stroke="#b37a10" stroke-width=".9" stroke-linecap="round"/>']
    for i, deg in enumerate(degs):
        a = math.radians(deg if side < 0 else 180 - deg)
        x, y = CX + r_leaf * math.cos(a), CY + r_leaf * math.sin(a)
        tang = math.degrees(a) + (90 if side < 0 else -90) + (-35 if side < 0 else 35)
        sc = 1 - i * 0.05
        out.append(f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(3.4 * sc)}" ry="{f(1.5 * sc)}" transform="rotate({f(tang)} {f(x)} {f(y)})" fill="#d99a1e" stroke="#a8700c" stroke-width=".4"/>')
    return "".join(out)


def star(cx: float, cy: float, big: float, small: float) -> str:
    pts = []
    for k in range(10):
        r = big if k % 2 == 0 else small
        a = -math.pi / 2 + k * math.pi / 5
        pts.append(f"{f(cx + r * math.cos(a))},{f(cy + r * math.sin(a))}")
    return " ".join(pts)


def beads(r: float, n: int) -> str:
    return "".join(f'<circle cx="{f(CX + r * math.cos(2 * math.pi * k / n))}" cy="{f(CY + r * math.sin(2 * math.pi * k / n))}" r=".75" fill="#fff" opacity=".75"/>' for k in range(n))


def rays() -> str:
    out = []
    for k in range(12):
        a = 2 * math.pi * k / 12 - math.pi / 2
        pts = [(CX + 21 * math.cos(a - 0.07), CY + 21 * math.sin(a - 0.07)), (CX + 31 * math.cos(a), CY + 31 * math.sin(a)), (CX + 21 * math.cos(a + 0.07), CY + 21 * math.sin(a + 0.07))]
        out.append('<polygon points="' + " ".join(f"{f(x)},{f(y)}" for x, y in pts) + '" fill="#f7d472" opacity=".55"/>')
    return "".join(out)


# 그라데이션 — 앱에서는 BadgeDefs 가 한 번만 그리고, 단독 SVG 파일에는 필요한 것만 넣는다
GRADIENTS = {
    "hb-bronze": '<linearGradient id="hb-bronze" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e8b184"/><stop offset=".55" stop-color="#c47a45"/><stop offset="1" stop-color="#8f4f25"/></linearGradient>',
    "hb-brand": '<linearGradient id="hb-brand" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff9150"/><stop offset="1" stop-color="#d9560f"/></linearGradient>',
    "hb-silver": '<linearGradient id="hb-silver" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#f4f6fa"/><stop offset=".5" stop-color="#aeb8c8"/><stop offset="1" stop-color="#6f7d95"/></linearGradient>',
    "hb-silver-in": '<linearGradient id="hb-silver-in" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7c8aa2"/><stop offset="1" stop-color="#cfd6e1"/></linearGradient>',
    "hb-gold": '<linearGradient id="hb-gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fde9a8"/><stop offset=".5" stop-color="#e8a92c"/><stop offset="1" stop-color="#b37a10"/></linearGradient>',
    "hb-gold-in": '<linearGradient id="hb-gold-in" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c0860f"/><stop offset="1" stop-color="#f7d472"/></linearGradient>',
    "hb-ball": '<radialGradient id="hb-ball" cx=".38" cy=".32" r=".8"><stop offset="0" stop-color="#ffa66b"/><stop offset="1" stop-color="#e2600f"/></radialGradient>',
    "hb-flame": '<linearGradient id="hb-flame" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffb070"/><stop offset="1" stop-color="#f26b1d"/></linearGradient>',
}

DISC = f'<circle cx="32" cy="32" r="14.2" fill="{W}"/>'


def frames(locked_ring: str, locked_disc: str) -> dict[str, str]:
    """틀 5종. 잠김 색만 대상(앱 토큰 / 파일용 고정값)에 따라 다르다."""
    return {
        "locked": f'<circle cx="32" cy="32" r="19.6" {locked_ring}/><circle cx="32" cy="32" r="14.2" {locked_disc}/>',
        "single": '<circle cx="32" cy="32" r="19.6" fill="url(#hb-brand)"/><circle cx="32" cy="32" r="16.6" fill="none" stroke="#fff" stroke-width=".7" opacity=".55"/>' + DISC,
        "bronze": '<circle cx="32" cy="32" r="19.6" fill="url(#hb-bronze)" stroke="#7a4020" stroke-width=".6"/><circle cx="32" cy="32" r="16.6" fill="none" stroke="#f0c29c" stroke-width=".7" opacity=".8"/>' + DISC,
        "silver": f'<path d="{scallop(19.2, 22.2, 18)}" fill="url(#hb-silver)" stroke="#5c6981" stroke-width=".6"/><circle cx="32" cy="32" r="17.2" fill="url(#hb-silver-in)"/>{beads(15.6, 16)}' + DISC,
        "gold": (rays() + laurel(-1) + laurel(1)
                 + f'<path d="{scallop(19.2, 22.6, 20)}" fill="url(#hb-gold)" stroke="#9a6608" stroke-width=".6"/><circle cx="32" cy="32" r="17.2" fill="url(#hb-gold-in)"/>{beads(15.6, 20)}'
                 + f'<circle cx="32" cy="32" r="14.2" fill="#fffaf0"/><polygon points="{star(32, 6.2, 3.8, 1.6)}" fill="#f5c542" stroke="#b37a10" stroke-width=".6" stroke-linejoin="round"/>'
                 + '<path d="M51 11v4M49 13h4M12.5 48.5v3M11 50h3" fill="none" stroke="#e8a92c" stroke-width="1.3" stroke-linecap="round"/>'),
    }


FRAME_GRADIENTS = {"locked": [], "single": ["hb-brand"], "bronze": ["hb-bronze"], "silver": ["hb-silver", "hb-silver-in"], "gold": ["hb-gold", "hb-gold-in"]}

# ---------------------------------------------------------------------------
# 그림 12종 — (32,27) 중심, 지름 20 안. 네이비 외곽선 1.5 + 면 채움 + 오렌지 포인트 하나
# ---------------------------------------------------------------------------
N = f'stroke="{NV}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"'
PICTS: dict[str, str] = {
    "ball": f'<circle cx="32" cy="27" r="9.8" fill="url(#hb-ball)" {N}/><path d="M32 17.2V36.8M22.2 27H41.8M25.2 19.9Q29.6 27 25.2 34.1M38.8 19.9Q34.4 27 38.8 34.1" fill="none" stroke="{NV}" stroke-width="1.3" stroke-linecap="round"/><ellipse cx="28.2" cy="21.6" rx="2.6" ry="1.4" transform="rotate(-35 28.2 21.6)" fill="{W}" opacity=".45"/>',
    "sneaker": f'<path d="M21.8 31.4V24.6L26.4 23.2L28.8 18.6L32.6 20Q33.2 24 37.2 25.4L40.8 26.8Q42.4 27.4 42.2 31.4Z" fill="{O}" {N}/><path d="M28.8 18.6L32.6 20Q33 22.2 34.4 23.6L30.2 24.8Z" fill="{OL}"/><path d="M21.8 31.4H42.2V34Q42.2 35.6 40.6 35.6H23.4Q21.8 35.6 21.8 34Z" fill="{W}" {N}/><path d="M28 23.4L31 24.4M27 25.6L30 26.6M26 27.8L29 28.8" stroke="{W}" stroke-width="1.3" stroke-linecap="round"/><path d="M36.4 33.4H40" stroke="{NL}" stroke-width="1.2" stroke-linecap="round"/>',
    "calendar": f'<rect x="22.4" y="19.4" width="19.2" height="17" rx="2.8" fill="{W}" {N}/><path d="M22.4 22.2Q22.4 19.4 25.2 19.4H38.8Q41.6 19.4 41.6 22.2V24.6H22.4Z" fill="{NM}" {N}/><rect x="26.2" y="16.6" width="2.4" height="5" rx="1.2" fill="{NV}"/><rect x="35.4" y="16.6" width="2.4" height="5" rx="1.2" fill="{NV}"/><path d="M27.4 30.2L30.6 33.2L36.8 27.2" fill="none" stroke="{O}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>',
    "bubble": f'<path d="M22.4 21Q22.4 18.4 25 18.4H39Q41.6 18.4 41.6 21V28.8Q41.6 31.4 39 31.4H30.4L25.8 35.6V31.4H25Q22.4 31.4 22.4 28.8Z" fill="{NS}" {N}/><circle cx="37.6" cy="18.6" r="3.2" fill="{O}" stroke="{W}" stroke-width="1.2"/><path d="M27.2 24.8L30.4 27.8L35.8 22.4" fill="none" stroke="{NV}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
    "jersey": f'<path d="M27.4 17.8V19.8Q27.4 23.4 23.8 24.6V36.6H40.2V24.6Q36.6 23.4 36.6 19.8V17.8Q34.4 21.4 32 21.4Q29.6 21.4 27.4 17.8Z" fill="{O}" {N}/><path d="M27.4 18.8Q29.6 22.6 32 22.6Q34.4 22.6 36.6 18.8" fill="none" stroke="{W}" stroke-width="1.2"/><path d="M23.8 26H26.2M37.8 26H40.2" stroke="{W}" stroke-width="1.2"/><path d="M30.2 28.6L32.8 26.6V33.6M30.2 33.6H35" fill="none" stroke="{W}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "clipboard": f'<rect x="23.4" y="19" width="17.2" height="18" rx="2.4" fill="{NM}" {N}/><rect x="25.6" y="22" width="12.8" height="12.8" rx="1.2" fill="{W}"/><rect x="28.2" y="16.8" width="7.6" height="4.4" rx="1.4" fill="{NS}" {N}/><path d="M28 28.6L30.8 31.4L36 25.8" fill="none" stroke="{O}" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>',
    "rank": f'<path d="M21.8 36.2H42.2" stroke="{NV}" stroke-width="1.5" stroke-linecap="round"/><rect x="22.8" y="29.6" width="5" height="6.6" rx="1" fill="{NS}" {N}/><rect x="29.5" y="25.4" width="5" height="10.8" rx="1" fill="{O}" {N}/><rect x="36.2" y="21.4" width="5" height="14.8" rx="1" fill="{NL}" {N}/><path d="M32 23.2L29.6 19.9A2.8 2.8 0 1 1 34.4 19.9Z" fill="{NV}"/><circle cx="32" cy="18.3" r="1" fill="{W}"/>',
    "flame": f'<path d="M32 16.8C33.6 21.2 39.2 23.4 39.2 29.4A7.2 7.2 0 0 1 24.8 29.4C24.8 25.6 27.2 23.8 28.4 21.4C29.6 23.3 30 24.6 30 26.2C31.8 24.6 32.6 21.2 32 16.8Z" fill="url(#hb-flame)" stroke="#b3430c" stroke-width="1.4" stroke-linejoin="round"/><path d="M32 35.6A3 3 0 0 1 29 32.6C29 30.6 31 29.6 32 27.6C33 29.6 35 30.6 35 32.6A3 3 0 0 1 32 35.6Z" fill="{Y}"/><path d="M36.8 19.6l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z" fill="{Y}"/>',
    "ballot": f'<rect x="27.6" y="16.8" width="8.8" height="12" rx="1" fill="{W}" {N} transform="rotate(-8 32 22.8)"/><path d="M29.8 22.6L31.6 24.4L34.6 21" fill="none" stroke="{O}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" transform="rotate(-8 32 22.8)"/><path d="M22.4 27.2H41.6V35Q41.6 36.8 39.8 36.8H24.2Q22.4 36.8 22.4 35Z" fill="{NM}" {N}/><rect x="26.4" y="26" width="11.2" height="2.4" rx="1.2" fill="{NV}"/><path d="M25.4 32.2H38.6" stroke="{NL}" stroke-width="1.2" stroke-linecap="round"/>',
    "people": f'<path d="M20.8 36.4Q20.8 30.2 26.2 30.2Q31.6 30.2 31.6 36.4Z" fill="{NL}" {N}/><circle cx="26.2" cy="25.8" r="3.4" fill="{NL}" {N}/><path d="M32.4 36.4Q32.4 30.2 37.8 30.2Q43.2 30.2 43.2 36.4Z" fill="{NS}" {N}/><circle cx="37.8" cy="25.8" r="3.4" fill="{NS}" {N}/><path d="M32 23.2C28.4 20.8 28.6 17 31 17C31.7 17 32 17.6 32 18.2C32 17.6 32.3 17 33 17C35.4 17 35.6 20.8 32 23.2Z" fill="{O}" stroke="{W}" stroke-width="1"/>',
    "mutual": f'<circle cx="23.4" cy="25" r="2.8" fill="{NV}"/><path d="M19.6 33.4Q19.6 29.4 23.4 29.4Q27.2 29.4 27.2 33.4Z" fill="{NV}"/><circle cx="40.6" cy="25" r="2.8" fill="{O}"/><path d="M36.8 33.4Q36.8 29.4 40.6 29.4Q44.4 29.4 44.4 33.4Z" fill="{O}"/><path d="M27.2 21.8Q32 18 36.8 21.8M34.4 20.2L36.8 21.8L35.6 19" fill="none" stroke="{NV}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M36.8 36Q32 39.2 27.2 36M29.6 37.6L27.2 36L28.4 38.8" fill="none" stroke="{O}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
    "guest": f'<path d="M21.6 36.6Q21.6 29.6 28.4 29.6Q35.2 29.6 35.2 36.6Z" fill="{NS}" {N}/><circle cx="28.4" cy="23.8" r="4" fill="{NS}" {N}/><circle cx="38.4" cy="22.4" r="4.6" fill="{O}" stroke="{W}" stroke-width="1.2"/><path d="M38.4 20V24.8M36 22.4H40.8" stroke="{W}" stroke-width="1.7" stroke-linecap="round"/>',
}
PICT_GRADIENTS = {"ball": ["hb-ball"], "flame": ["hb-flame"]}

# ---------------------------------------------------------------------------
# 칸 목록 — 서버 배지 코드와의 대응 (backend/app/services/badge_service.py 의 series 와 같아야 한다)
# ---------------------------------------------------------------------------
SINGLES = [  # (배지 코드, 칸 이름, 그림)
    ("JOIN_TEAM", "첫 팀", "jersey"), ("SURVEY_DONE", "설문 완료", "clipboard"), ("SELF_RANK_DONE", "내 위치 응답", "rank"),
    ("FIRST_RSVP", "첫 참석 응답", "bubble"), ("FIRST_QUARTER", "첫 출전", "sneaker"), ("STREAK_3", "연속 참석", "flame"),
    ("MUTUAL_3", "서로 뽑은 사이", "mutual"), ("GUEST_CONVERTED", "게스트 영입", "guest"),
]
SERIES = [  # (묶음 키, 칸 이름, 그림, 시트 설명)
    ("QUARTERS", "출전", "ball", "기록된 쿼터에 뛴 만큼 올라가요."),
    ("ATTEND", "참석", "calendar", "지난 일정에 참석한 만큼 올라가요."),
    ("VOTES", "투표", "ballot", "경기 후 투표에 응답한 만큼 올라가요."),
    ("PLAY_AGAIN", "동료 지목", "people", "'다음에 같이 뛰고 싶은 사람'으로 지목받은 만큼 올라가요."),
]


def svg_file(frame: str, pict: str) -> str:
    """단독으로 열리는 완성 SVG (잠김 색은 밝은 화면 기준 고정값)."""
    fr = frames('fill="#e7e5e4"', 'fill="#f5f5f4"')[frame]
    grads = FRAME_GRADIENTS[frame] + PICT_GRADIENTS.get(pict, [])
    defs = "<defs>" + "".join(GRADIENTS[g] for g in grads) + "</defs>" if grads else ""
    pg = f'<g transform="translate(0 {PICT_SHIFT})"' + (' style="filter:grayscale(1);opacity:.42"' if frame == "locked" else "") + f">{PICTS[pict]}</g>"
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="128" height="128">{defs}{fr}{pg}</svg>\n'


def write_ts() -> None:
    # 앱: 잠김 색은 화면 토큰을 따라 다크 모드에서도 자연스럽게
    fr = frames('style="fill:var(--color-line)"', 'style="fill:var(--color-sunken)"')
    js = lambda s: s.replace("\\", "\\\\").replace("`", "\\`")  # noqa: E731
    lines = [
        "/**",
        " * 배지 아이콘 SVG 조각 — 자동 생성 파일. 직접 고치지 말고 docs/badges/badge_art.py 를 고친 뒤",
        " *   python3 docs/badges/badge_art.py",
        " * 를 실행한다. 조합은 components/badge-icon.tsx, 규칙은 docs/06-배지.md.",
        " */",
        "export type BadgeFrame = 'locked' | 'single' | 'bronze' | 'silver' | 'gold'",
        f"export type BadgePict = {' | '.join(repr(k) for k in PICTS)}",
        "",
        "/** 모든 배지가 공유하는 그라데이션. 화면에 BadgeDefs 를 한 번 그려 둔다 */",
        f"export const BADGE_DEFS = `{js(''.join(GRADIENTS.values()))}`",
        "",
        "export const FRAMES: Record<BadgeFrame, string> = {",
        *[f"  {k}: `{js(v)}`," for k, v in fr.items()],
        "}",
        "",
        "/** 그림은 (32,27) 기준이라 조합할 때 translate(0 5) 로 메달 중심에 맞춘다 */",
        f"export const PICT_SHIFT = {PICT_SHIFT}",
        "export const PICTS: Record<BadgePict, string> = {",
        *[f"  {k}: `{js(v)}`," for k, v in PICTS.items()],
        "}",
        "",
        "/** 배지 코드 → 그림 (단일 배지) · 묶음 키 → 칸 이름과 그림 (서버 badge_service.py 의 series 와 같다) */",
        "export const SINGLE_PICT: Record<string, BadgePict> = {",
        *[f"  {code}: '{p}',  // {name}" for code, name, p in SINGLES],
        "}",
        "export const SERIES_INFO: Record<string, { title: string; pict: BadgePict; desc: string }> = {",
        *[f"  {key}: {{ title: '{name}', pict: '{p}', desc: \"{d}\" }}," for key, name, p, d in SERIES],
        "}",
        "",
    ]
    TS_OUT.write_text("\n".join(lines))


def write_svgs() -> list[tuple[str, str, str]]:
    SVG_DIR.mkdir(parents=True, exist_ok=True)
    for old in SVG_DIR.glob("*.svg"):
        old.unlink()
    made = []
    for code, name, p in SINGLES:
        for fr in ("single", "locked"):
            fn = f"{code.lower()}-{fr}.svg"
            (SVG_DIR / fn).write_text(svg_file(fr, p))
            made.append((fn, name, fr))
    for key, name, p, _desc in SERIES:
        for fr in ("bronze", "silver", "gold", "locked"):
            fn = f"{key.lower()}-{fr}.svg"
            (SVG_DIR / fn).write_text(svg_file(fr, p))
            made.append((fn, name, fr))
    for fr in ("locked", "single", "bronze", "silver", "gold"):
        fn = f"_frame-{fr}.svg"
        (SVG_DIR / fn).write_text(svg_file(fr, "ball"))
        made.append((fn, f"틀 {fr}", fr))
    return made


def write_preview(made: list[tuple[str, str, str]]) -> None:
    ko = {"locked": "잠김", "single": "단일", "bronze": "동", "silver": "은", "gold": "금"}
    cells = "".join(f'<figure><img src="svg/{fn}" alt="{name} {ko[fr]}" width="72" height="72"><figcaption>{name}<br><small>{ko[fr]} · {fn}</small></figcaption></figure>' for fn, name, fr in made)
    PREVIEW.write_text(f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>Hooply 배지 아이콘</title>
<style>body{{margin:0;padding:24px 16px;font:14px/1.5 -apple-system,"Apple SD Gothic Neo",sans-serif;background:#f5f5f4;color:#0f1b2d}}
h1{{font-size:18px;margin:0 0 4px}}p{{margin:0 0 16px;color:#78716c}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px}}
figure{{margin:0;background:#fff;border:1px solid #e7e5e4;border-radius:12px;padding:10px;display:grid;justify-items:center;text-align:center}}
figcaption{{font-size:12px}}small{{color:#a8a29e;word-break:break-all}}</style></head><body>
<h1>Hooply 배지 아이콘</h1><p>docs/badges/badge_art.py 가 만든 파일 {len(made)}개. 규칙은 docs/06-배지.md.</p>
<div class="grid">{cells}</div></body></html>
""")


if __name__ == "__main__":
    write_ts()
    made = write_svgs()
    write_preview(made)
    print(f"badge-art.ts · svg {len(made)}개 · preview.html 생성")
