"""OpenAPI responses 헬퍼 — 7.4절 에러 코드를 문서에 드러낸다."""

from typing import Any

from app.core.errors import ErrorResponse


def err(*codes: str, status: int) -> dict[int, dict[str, Any]]:
    return {status: {"model": ErrorResponse, "description": " / ".join(codes)}}


def errors(**by_status: tuple[str, ...] | str) -> dict[int, dict[str, Any]]:
    """예: errors(_401=("INVALID_CREDENTIALS",), _409="EMAIL_DUPLICATED")"""
    out: dict[int, dict[str, Any]] = {}
    for key, codes in by_status.items():
        status = int(key.lstrip("_"))
        codes = (codes,) if isinstance(codes, str) else codes
        out.update(err(*codes, status=status))
    return out

