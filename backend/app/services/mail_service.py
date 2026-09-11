"""메일 발송 — 비밀번호 재설정 링크 등. Resend HTTP API 를 쓰고, 키가 없으면(로컬·테스트) 서버 로그에만 남긴다.

설정: RESEND_API_KEY (없으면 로그 모드), MAIL_FROM (예: "HOOPLY <noreply@example.com>"; Resend 는 인증된 도메인 또는
onboarding@resend.dev 만 허용). 실패해도 예외를 밖으로 내지 않는다 — 비밀번호 찾기 응답은 항상 202 여야 하기 때문 (7.4절).
"""

from __future__ import annotations

import httpx

from app.core.config import get_settings

RESEND_URL = "https://api.resend.com/emails"


def send(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """메일 1통. 반환값은 발송 성공 여부 (로그 모드는 True). 테스트는 이 함수를 monkeypatch 한다."""
    s = get_settings()
    if not s.resend_api_key:
        print(f"[mail:dev] to={to} subject={subject}\n{text}")
        return True
    try:
        r = httpx.post(
            RESEND_URL, timeout=10,
            headers={"Authorization": f"Bearer {s.resend_api_key}"},
            json={"from": s.mail_from, "to": [to], "subject": subject, "text": text, "html": html or f"<pre>{text}</pre>"},
        )
        if r.status_code >= 300:
            print(f"[mail] 발송 실패 {r.status_code}: {r.text[:200]}")
            return False
        return True
    except httpx.HTTPError as e:  # 네트워크 오류도 삼킨다
        print(f"[mail] 발송 오류: {e}")
        return False


def send_password_reset(to: str, link: str) -> bool:
    text = (
        "HOOPLY 비밀번호 재설정 링크예요. 30분 안에 아래 링크를 열어 새 비밀번호를 정해 주세요.\n\n"
        f"{link}\n\n"
        "본인이 요청하지 않았다면 이 메일은 무시해도 돼요. 비밀번호는 바뀌지 않아요."
    )
    html = (
        "<p>HOOPLY 비밀번호 재설정 링크예요. <b>30분 안에</b> 아래 버튼을 눌러 새 비밀번호를 정해 주세요.</p>"
        f'<p><a href="{link}" style="display:inline-block;padding:12px 20px;background:#f26b1d;color:#fff;border-radius:10px;text-decoration:none;font-weight:700">비밀번호 재설정</a></p>'
        f'<p style="color:#666;font-size:12px">버튼이 안 눌리면 이 주소를 여세요: {link}<br>본인이 요청하지 않았다면 무시해도 돼요.</p>'
    )
    return send(to, "[HOOPLY] 비밀번호 재설정", text, html)
