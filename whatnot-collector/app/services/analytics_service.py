from server.reconciler import materialize_recent_stream_facts


def refresh_recent_stream_facts(stream_id: int):
    materialize_recent_stream_facts(stream_id)
    return {"ok": True, "stream_id": stream_id}

