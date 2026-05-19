from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
import httpx

from app.core.runtime_observability import record_bridge_hit


router = APIRouter()


@router.api_route("/api/{full_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def legacy_proxy(full_path: str, request: Request) -> Response:
    if full_path.startswith("v2/"):
        raise HTTPException(status_code=404, detail="not_found")
    upstream = getattr(request.app.state, "legacy_bridge_url", None)
    if not upstream:
        raise HTTPException(status_code=503, detail="legacy_bridge_unavailable")

    url = f"{upstream}/api/{full_path}"
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length"}
    }
    body = await request.body()
    # Some legacy endpoints legitimately stream large responses after doing
    # heavy PDF work, especially TikTok label enrichment. The previous 60s
    # client timeout caused the dashboard proxy to give up even though the
    # upstream runtime completed successfully, which surfaced as a 500 to the
    # browser and a BrokenPipeError in the legacy server.
    proxy_timeout = httpx.Timeout(connect=10.0, read=300.0, write=300.0, pool=10.0)
    async with httpx.AsyncClient(follow_redirects=False, timeout=proxy_timeout) as client:
        upstream_response = await client.request(
            request.method,
            url,
            params=request.query_params,
            content=body,
            headers=headers,
        )
    try:
        record_bridge_hit(request.url.path, request.method, upstream_response.status_code)
    except Exception:
        pass
    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in {"content-length", "transfer-encoding", "connection", "date", "server"}
    }
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )
