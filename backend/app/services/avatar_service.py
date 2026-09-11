"""프로필 사진 — 업로드(데이터 URL 수신)·조회·삭제, users.profile_image_url 갱신.

사진은 `user_avatars` 에 바이트로 담고, 계정에는 `/api/v1/users/{id}/avatar?v={키}` 주소만 남긴다.
그래서 팀원 목록 같은 응답에는 짧은 문자열만 실리고, 실제 이미지는 브라우저가 한 번 받아 캐시한다.
"""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core import errors
from app.models import User, UserAvatar

ALLOWED = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_BYTES = 512 * 1024  # 프론트가 256px JPEG 로 줄여 보내면 보통 20~50KB


def _decode(data_url: str) -> tuple[str, bytes]:
    """`data:image/jpeg;base64,...` 를 (mime, 바이트) 로. 형식·종류·크기를 모두 여기서 검증한다."""
    if not data_url.startswith("data:"):
        raise errors.ValidationError("이미지 형식이 올바르지 않아요.")
    try:
        header, payload = data_url.split(",", 1)
        mime = header[5:].split(";")[0].strip().lower()
        raw = base64.b64decode(payload, validate=True)
    except Exception:  # noqa: BLE001 — 어떤 형식 오류든 같은 안내로 돌려준다
        raise errors.ValidationError("이미지를 읽지 못했어요. 다른 사진으로 시도해 주세요.") from None
    if mime not in ALLOWED:
        raise errors.ValidationError("JPG · PNG · WEBP 사진만 올릴 수 있어요.")
    if not raw:
        raise errors.ValidationError("이미지를 읽지 못했어요. 다른 사진으로 시도해 주세요.")
    if len(raw) > MAX_BYTES:
        raise errors.ValidationError(f"사진이 너무 커요. {MAX_BYTES // 1024}KB 이하로 올려 주세요.")
    return mime, raw


def avatar_url(user_id: int, cache_key: str) -> str:
    return f"/api/v1/users/{user_id}/avatar?v={cache_key}"


def set_avatar(db: Session, user: User, data_url: str) -> User:
    """사진을 저장(또는 교체)하고 계정의 이미지 주소를 갱신한다. commit 까지."""
    mime, raw = _decode(data_url)
    row = db.get(UserAvatar, user.id)
    key = secrets.token_urlsafe(9)[:12]
    if row is None:
        row = UserAvatar(user_id=user.id, content_type=mime, data=raw, cache_key=key)
        db.add(row)
    else:
        row.content_type, row.data, row.cache_key, row.updated_at = mime, raw, key, datetime.now(UTC)
    user.profile_image_url = avatar_url(user.id, key)
    db.commit()
    db.refresh(user)
    return user


def clear_avatar(db: Session, user: User) -> User:
    """사진을 지운다. 카카오에서 받아 온 외부 주소만 있는 경우에도 주소를 비운다."""
    row = db.get(UserAvatar, user.id)
    if row is not None:
        db.delete(row)
    user.profile_image_url = None
    db.commit()
    db.refresh(user)
    return user


def get_avatar(db: Session, user_id: int, cache_key: str | None) -> UserAvatar:
    """이미지 태그는 토큰을 실을 수 없으므로 주소의 키로 확인한다. 키가 없거나 다르면 404 로 존재도 알리지 않는다."""
    row = db.get(UserAvatar, user_id)
    if row is None or not cache_key or not secrets.compare_digest(cache_key, row.cache_key):
        raise errors.NotFound("사진을 찾을 수 없습니다.")
    return row
