"""Serve the API and compiled React SPA from one slim offline container.

The product deployment keeps frontend and backend as separate services.  The
competition package deliberately combines only their runtime delivery layer so
that an offline archive does not have to carry Node.js, npm, or nginx.  API
routes and business logic are still provided by :mod:`backend.main` unchanged.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse

from backend.main import app


STATIC_ROOT = Path(os.getenv("CARBONLAB_STATIC_DIR", "/app/frontend-dist")).resolve()
INDEX_FILE = STATIC_ROOT / "index.html"


@app.get("/{requested_path:path}", include_in_schema=False)
async def offline_spa(requested_path: str, request: Request):
    """Return a static asset or the SPA shell without shadowing ``/api``."""

    if requested_path == "api" or requested_path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if not INDEX_FILE.is_file():
        return JSONResponse(
            status_code=503,
            content={"detail": "Offline frontend assets are unavailable"},
        )

    candidate = (STATIC_ROOT / requested_path).resolve()
    try:
        candidate.relative_to(STATIC_ROOT)
    except ValueError:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    if requested_path and candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(INDEX_FILE)
