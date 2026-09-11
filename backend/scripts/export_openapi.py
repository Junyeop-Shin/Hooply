"""docs/04-API명세-openapi.yaml 재생성 — FastAPI 가 만든 OpenAPI 를 제출용으로 간결하게 정리한다.

  cd backend && python -m scripts.export_openapi
설명 문구·title·default 를 걷어내고, anyOf[X, null] 은 OAS 3.0 의 nullable 로 바꾼다. 경로의 /api/v1 은 servers 로 옮긴다.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.main import create_app

OUT = Path(__file__).resolve().parents[2] / "docs" / "04-API명세-openapi.yaml"


def _short(s: str | None, n: int = 70) -> str | None:
    if not s:
        return None
    s = s.strip().split("\n")[0].strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _slim(sc):
    if isinstance(sc, list):
        return [_slim(x) for x in sc]
    if not isinstance(sc, dict):
        return sc
    if "anyOf" in sc:
        opts = [x for x in sc["anyOf"] if x.get("type") != "null"]
        if len(opts) == 1 and len(opts) < len(sc["anyOf"]):
            base = _slim(opts[0])
            base["nullable"] = True
            if "enum" in sc:
                base["enum"] = sc["enum"]
            return base
    out = {}
    for k, v in sc.items():
        if k in ("description", "title", "examples", "example", "default"):
            continue
        out[k] = _slim(v) if isinstance(v, (dict, list)) else v
    return out


def main() -> None:
    spec = create_app().openapi()
    paths = {}
    for path, ops in spec["paths"].items():
        p = {}
        for method, op in ops.items():
            o = {"summary": op.get("summary"), "tags": op.get("tags", [])}
            params = []
            for prm in op.get("parameters", []):
                sc = _slim(prm.get("schema", {}))
                params.append({"name": prm["name"], "in": prm["in"], "required": prm.get("required", False), "schema": {k: sc[k] for k in ("type", "enum", "nullable") if k in sc}})
            if params:
                o["parameters"] = params
            rb = op.get("requestBody")
            if rb:
                o["requestBody"] = {"required": True, "content": {"application/json": {"schema": _slim(rb["content"]["application/json"]["schema"])}}}
            if "/auth/" in path and "refresh" not in path and "link" not in path:
                o["security"] = []
            res = {}
            for code, r in op.get("responses", {}).items():
                if code == "422" and "HTTPValidationError" in json.dumps(r):
                    continue
                rr = {"description": "성공" if str(code).startswith("2") else (_short(r.get("description")) or "응답")}
                c = r.get("content", {}).get("application/json", {})
                if c.get("schema"):
                    rr["content"] = {"application/json": {"schema": _slim(c["schema"])}}
                res[str(code)] = rr
            o["responses"] = res
            p[method] = o
        paths[path.replace("/api/v1", "", 1)] = p
    schemas = {k: _slim(v) for k, v in spec["components"]["schemas"].items() if k not in ("HTTPValidationError", "ValidationError")}
    out = {
        "openapi": "3.0.3",
        "info": {"title": "HOOPLY API", "version": "1.0.0", "description": "농구 동호회 팀 매칭 서비스. 인증은 Bearer JWT(access 30분/refresh 14일). 모든 4xx/5xx 본문은 ErrorResponse {code, message, details[]}."},
        "servers": [{"url": "https://hooply-backend.onrender.com/api/v1", "description": "운영"}, {"url": "http://localhost:8000/api/v1", "description": "로컬"}],
        "security": [{"bearerAuth": []}],
        "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}, "schemas": schemas},
    }
    OUT.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=160), encoding="utf-8")
    print(f"{OUT.name}: paths={len(paths)} schemas={len(schemas)}")


if __name__ == "__main__":
    main()
