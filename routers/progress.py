"""SSE-based pipeline progress streaming.

Provides an in-memory phase store and an SSE endpoint so the frontend can
render a real-time stepper while the pipeline is running.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict

from fastapi import APIRouter
from starlette.responses import StreamingResponse

logger = logging.getLogger("docxtract.progress")
router = APIRouter()

# ---------------------------------------------------------------------------
# Phase store  (in-memory — perfectly fine for a single-worker setup)
# ---------------------------------------------------------------------------

# { doc_id: { "phase": str, "status": str, "detail": str, "ts": float } }
_progress: Dict[int, Dict[str, Any]] = {}
# Monotonically incremented so SSE consumers know when something changed.
_version: Dict[int, int] = {}


PHASES = [
    "upload",
    "ingestion",
    "preprocessing",
    "extraction",
    "mapping",
    "validation",
    "done",
]


def set_phase(
    doc_id: int,
    phase: str,
    *,
    status: str = "active",
    detail: str = "",
) -> None:
    """Called by the pipeline / upload handler to broadcast phase changes."""
    _progress[doc_id] = {
        "phase": phase,
        "status": status,
        "detail": detail,
        "ts": time.time(),
    }
    _version[doc_id] = _version.get(doc_id, 0) + 1
    logger.debug("Progress doc=%d  phase=%s  status=%s", doc_id, phase, status)


def clear(doc_id: int) -> None:
    """Clean up after a document finishes processing."""
    _progress.pop(doc_id, None)
    _version.pop(doc_id, None)


# ---------------------------------------------------------------------------
# SSE endpoint
# ---------------------------------------------------------------------------

@router.get("/documents/{doc_id}/progress")
async def stream_progress(doc_id: int):
    """Server-Sent Events stream for pipeline progress on *doc_id*."""

    async def _event_generator():
        last_version = 0
        idle_ticks = 0
        max_idle = 120  # stop after 2 min of no activity

        while True:
            current = _version.get(doc_id, 0)

            if current > last_version:
                last_version = current
                idle_ticks = 0
                data = _progress.get(doc_id, {})
                yield f"data: {json.dumps(data)}\n\n"

                # If the pipeline is done or failed, send a final event and stop
                if data.get("phase") in ("done",) or data.get("status") == "failed":
                    await asyncio.sleep(0.3)
                    break
            else:
                idle_ticks += 1
                if idle_ticks >= max_idle:
                    yield f"data: {json.dumps({'phase': 'timeout', 'status': 'failed', 'detail': 'Progress stream timed out.'})}\n\n"
                    break

            await asyncio.sleep(0.25)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
