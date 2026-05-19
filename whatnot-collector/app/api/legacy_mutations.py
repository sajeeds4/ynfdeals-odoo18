from __future__ import annotations

from fastapi import APIRouter, Body, Response

from app.services.legacy_mutation_service import (
    mutate_active_item_status,
    mutate_current_lot_clear,
    mutate_current_lot_drop,
    mutate_current_lot_remove_candidate,
    mutate_current_lot_reuse,
    mutate_current_lot_select_product,
    mutate_current_lot_set,
    mutate_current_lot_awaiting,
    mutate_ingest_winner,
    mutate_reassign,
    mutate_scan,
    mutate_spectator_start,
    mutate_spectator_stop,
    mutate_stream_start,
    mutate_stream_stop,
    mutate_winner_assignment_confirm,
    mutate_winner_assignment_delete,
    mutate_winner_assignment_item_delete,
    mutate_winner_assignment_lot,
    mutate_winner_assignment_scan,
    mutate_winner_assignment_status,
    mutate_winner_assignment_undo,
)


router = APIRouter()


def _respond(payload: dict, response: Response):
    status = payload.pop("_status", None)
    if status:
        response.status_code = status
    return payload


@router.post("/api/current_lot/set")
def legacy_current_lot_set(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_current_lot_set(session_id=payload.get("session_id"), lot_number=payload.get("lot_number") or ""),
        response,
    )


@router.post("/api/current_lot/select_product")
def legacy_current_lot_select_product(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_current_lot_select_product(item_id=payload.get("item_id")), response)


@router.post("/api/current_lot/remove_candidate")
def legacy_current_lot_remove_candidate(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_current_lot_remove_candidate(item_id=payload.get("item_id")), response)


@router.post("/api/current_lot/drop")
def legacy_current_lot_drop(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_current_lot_drop(), response)


@router.post("/api/current_lot/reuse")
def legacy_current_lot_reuse(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_current_lot_reuse(), response)


@router.post("/api/current_lot/clear")
def legacy_current_lot_clear(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_current_lot_clear(), response)


@router.post("/api/current_lot/awaiting")
def legacy_current_lot_awaiting(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_current_lot_awaiting(), response)


@router.post("/api/active_item_status")
def legacy_active_item_status(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_active_item_status(
            active_item_id=payload.get("active_item_id"),
            status=payload.get("status"),
        ),
        response,
    )


@router.post("/api/reassign")
def legacy_reassign(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_reassign(
            auction_result_id=payload.get("auction_result_id"),
            active_item_id=payload.get("active_item_id"),
        ),
        response,
    )


@router.post("/api/scan")
def legacy_scan(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_scan(barcode=payload.get("barcode") or ""), response)


@router.post("/api/winner_assignment/scan")
def legacy_winner_assignment_scan(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_winner_assignment_scan(
            barcode=payload.get("barcode") or "",
            assignment_id=payload.get("assignment_id"),
            session_id=payload.get("session_id"),
        ),
        response,
    )


@router.post("/api/winner_assignment/confirm")
def legacy_winner_assignment_confirm(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_winner_assignment_confirm(assignment_id=payload.get("assignment_id")), response)


@router.post("/api/winner_assignment/undo")
def legacy_winner_assignment_undo(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_winner_assignment_undo(assignment_id=payload.get("assignment_id")), response)


@router.post("/api/winner_assignment/item/delete")
def legacy_winner_assignment_item_delete(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_winner_assignment_item_delete(
            assignment_id=payload.get("assignment_id"),
            item_id=payload.get("item_id"),
        ),
        response,
    )


@router.post("/api/winner_assignment/status")
def legacy_winner_assignment_status(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_winner_assignment_status(
            assignment_id=payload.get("assignment_id"),
            status=payload.get("status"),
            notes=payload.get("notes"),
        ),
        response,
    )


@router.post("/api/winner_assignment/lot")
def legacy_winner_assignment_lot(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_winner_assignment_lot(
            assignment_id=payload.get("assignment_id"),
            lot_number=payload.get("lot_number") or "",
        ),
        response,
    )


@router.post("/api/winner_assignment/delete")
def legacy_winner_assignment_delete(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_winner_assignment_delete(assignment_id=payload.get("assignment_id")), response)


@router.post("/api/ingest_winner")
def legacy_ingest_winner(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_ingest_winner(
            winner_username=payload.get("winner_username") or "",
            lot_number=payload.get("lot_number") or "",
            event_id=payload.get("event_id"),
            sale_price=payload.get("sale_price"),
            sold_at=payload.get("sold_at"),
        ),
        response,
    )


@router.post("/api/stream_start")
def legacy_stream_start(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_stream_start(
            stream_url=payload.get("stream_url") or "",
            mode=payload.get("mode", "our_stream"),
        ),
        response,
    )


@router.post("/api/stream_stop")
def legacy_stream_stop(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_stream_stop(), response)


@router.post("/api/live_collector/start")
def legacy_live_collector_start(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_stream_start(
            stream_url=payload.get("stream_url") or "",
            mode=payload.get("mode", "our_stream"),
        ),
        response,
    )


@router.post("/api/live_collector/stop")
def legacy_live_collector_stop(response: Response, payload: dict | None = Body(default=None)):
    return _respond(mutate_stream_stop(), response)


@router.post("/api/spectator/start")
def legacy_spectator_start(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(
        mutate_spectator_start(
            stream_urls=payload.get("stream_urls") or [],
            stream_url=payload.get("stream_url"),
            replace_all=bool(payload.get("replace_all")),
        ),
        response,
    )


@router.post("/api/spectator/stop")
def legacy_spectator_stop(response: Response, payload: dict | None = Body(default=None)):
    payload = payload or {}
    return _respond(mutate_spectator_stop(stream_url=payload.get("stream_url")), response)
