import sys
from pathlib import Path

# Allow importing lib when running from backend/
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import os
import sqlite3
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lib.constants import WORK_AREAS, WORK_AREA_FIELD, WORK_AREA_MODEL
from lib.odoo_client import OdooClient
from lib.dashboard import build_dashboard_rows
from lib.comments_db import (
    _get_comment_conn,
    init_comments_table,
    get_comments_list,
    save_comment as db_save_comment,
)

odoo_client = OdooClient()

app = FastAPI(title="Production Inventory Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/work-areas")
def get_work_areas() -> List[str]:
    return WORK_AREAS


@app.get("/api/work-areas-from-odoo")
def get_work_areas_from_odoo():
    try:
        records = odoo_client.search_read(
            WORK_AREA_MODEL,
            [],
            fields=["id", "name"],
            limit=500,
        )
        return {"work_areas": [{"id": r["id"], "name": r["name"]} for r in records]}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/test-connection")
def test_odoo_connection():
    try:
        uid = odoo_client.uid
        return {
            "status": "success",
            "message": "Successfully connected to Odoo",
            "uid": uid,
            "url": odoo_client.url,
            "db": odoo_client.db,
            "username": odoo_client.username,
        }
    except Exception as e:
        import traceback
        print(f"Odoo connection error: {traceback.format_exc()}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to connect to Odoo: {str(e)}. Check your credentials.",
        )


@app.get("/api/debug-boms")
def debug_boms():
    try:
        boms = odoo_client.search_read(
            "mrp.bom",
            [],
            fields=["id", "product_id", "product_tmpl_id", "work_area"],
            limit=50,
        )
        return {"count": len(boms), "boms": boms}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/dashboard")
def get_dashboard(
    work_area: Optional[List[str]] = Query(None, description="Filter by one or more work area names")
):
    try:
        rows = build_dashboard_rows(odoo_client, work_area or WORK_AREAS)
        return rows
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=502, detail=str(e))


_comments_table_ready = False

def _ensure_comments_table():
    global _comments_table_ready
    if _comments_table_ready:
        return
    conn = _get_comment_conn()
    try:
        init_comments_table(conn)
        _comments_table_ready = True
    finally:
        conn.close()

@app.on_event("startup")
def _startup_init():
    _ensure_comments_table()


@app.get("/api/comments")
def get_comments(
    work_area: Optional[List[str]] = Query(None, description="Filter by work area(s)")
) -> List[dict]:
    _ensure_comments_table()
    return get_comments_list(work_area)


class CommentBody(BaseModel):
    internal_reference: str
    work_area: str
    comment: str


@app.post("/api/comments")
def save_comment(body: CommentBody) -> dict:
    _ensure_comments_table()
    db_save_comment(body.internal_reference, body.work_area, body.comment or "")
    return {"ok": True}


# Serve frontend locally (skip on Vercel where static files are served separately)
if not os.getenv("VERCEL"):
    FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
