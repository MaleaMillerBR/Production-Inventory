import sys
import os
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Production Inventory Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from lib.constants import WORK_AREAS
    from lib.odoo_client import OdooClient
    from lib.dashboard import build_dashboard_rows
    from lib.comments_db import (
        _get_comment_conn,
        init_comments_table,
        get_comments_list,
        save_comment as db_save_comment,
    )
    _imports_ok = True
except Exception as _import_err:
    _imports_ok = False

if _imports_ok:
    odoo_client = OdooClient()

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

    @app.get("/api/work-areas")
    def get_work_areas() -> List[str]:
        return WORK_AREAS

    @app.get("/api/dashboard")
    def get_dashboard(
        work_area: Optional[List[str]] = Query(None),
    ):
        try:
            return build_dashboard_rows(odoo_client, work_area or WORK_AREAS)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            raise HTTPException(status_code=502, detail=str(e))

    @app.get("/api/comments")
    def get_comments(
        work_area: Optional[List[str]] = Query(None),
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
