import sys
import os
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / "backend" / ".env")

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="Production Inventory Dashboard API")

SESSION_SECRET = os.getenv("SESSION_SECRET_KEY", "change-me-to-a-real-secret")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

ALLOWED_DOMAIN = "@bluerobotics.com"
PUBLIC_PATHS = {"/login", "/auth", "/logout"}

ACCESS_DENIED_HTML = """<!DOCTYPE html>
<html><head><title>Access Denied</title>
<style>
  body { font-family: system-ui, sans-serif; display: flex; align-items: center;
         justify-content: center; min-height: 100vh; background: #f0f4f8; margin: 0; }
  .card { background: #fff; padding: 2.5rem; border-radius: 1rem;
          box-shadow: 0 4px 24px rgba(0,0,0,0.1); text-align: center; max-width: 420px; }
  h1 { color: #b91c1c; font-size: 1.4rem; margin-bottom: 0.75rem; }
  p  { color: #334155; margin-bottom: 1.25rem; }
  a  { display: inline-block; padding: 0.5rem 1.5rem; background: #006994;
       color: #fff; border-radius: 0.5rem; text-decoration: none; }
</style></head>
<body><div class="card">
  <h1>Access Restricted</h1>
  <p>Only Blue Robotics employees (<b>@bluerobotics.com</b>) may access this dashboard.</p>
  <a href="/logout">Sign out &amp; try again</a>
</div></body></html>"""


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if path in PUBLIC_PATHS or path.startswith("/login") or path.startswith("/auth"):
        return await call_next(request)
    user = request.session.get("user")
    if not user:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)
        return RedirectResponse(url="/login")
    return await call_next(request)


@app.get("/login")
async def login(request: Request):
    redirect_uri = str(request.url_for("auth"))
    if os.getenv("VERCEL"):
        redirect_uri = redirect_uri.replace("http://", "https://")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth")
async def auth(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        return HTMLResponse(f"<p>Authentication error: {e}</p><p><a href='/login'>Try again</a></p>", status_code=400)

    user_info = token.get("userinfo")
    if not user_info:
        return HTMLResponse("<p>Could not retrieve user info.</p><p><a href='/login'>Try again</a></p>", status_code=400)

    email = user_info.get("email", "")
    if not email.endswith(ALLOWED_DOMAIN):
        return HTMLResponse(ACCESS_DENIED_HTML, status_code=403)

    request.session["user"] = {"email": email, "name": user_info.get("name", "")}
    return RedirectResponse(url="/")


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")


@app.get("/api/me")
async def me(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


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
