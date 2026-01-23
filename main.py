from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from passlib.context import CryptContext


# =========================
# App + Paths
# =========================
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"

app = FastAPI(title="TradBarter MVP (Core Loop)")

# Session cookie (keep simple for MVP)
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-me")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,  # set True when you're 100% HTTPS everywhere
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# =========================
# DB helpers
# =========================
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              postcode TEXT,
              email TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              created_at TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trade_threads (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              listing_id TEXT NOT NULL,
              owner_user_id INTEGER NOT NULL,
              created_at TEXT DEFAULT (datetime('now')),
              UNIQUE(listing_id, owner_user_id),
              FOREIGN KEY(owner_user_id) REFERENCES users(id)
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              trade_id INTEGER NOT NULL,
              sender_user_id INTEGER NOT NULL,
              body TEXT NOT NULL,
              created_at TEXT DEFAULT (datetime('now')),
              FOREIGN KEY(trade_id) REFERENCES trade_threads(id),
              FOREIGN KEY(sender_user_id) REFERENCES users(id)
            );
            """
        )


init_db()


# =========================
# Auth helpers
# =========================
def get_current_user_id(request: Request) -> Optional[int]:
    uid = request.session.get("user_id")
    return int(uid) if uid else None


def require_login(request: Request, next_path: str) -> None:
    if not get_current_user_id(request):
        raise HTTPException(status_code=401, detail=f"Login required. Go to /account?mode=login&next={next_path}")


def safe_next_path(next_path: str, default: str = "/browse") -> str:
    """
    Prevent open redirects. Only allow relative internal paths.
    """
    if not next_path:
        return default
    if next_path.startswith("http://") or next_path.startswith("https://"):
        return default
    if not next_path.startswith("/"):
        return default
    return next_path


def set_login(request: Request, user_id: int) -> None:
    request.session["user_id"] = int(user_id)


def clear_login(request: Request) -> None:
    request.session.pop("user_id", None)


# =========================
# Page routes (6 pages)
# =========================
@app.get("/", response_class=HTMLResponse)
def page_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "logged_in": bool(get_current_user_id(request))})


@app.get("/browse", response_class=HTMLResponse)
def page_browse(request: Request):
    return templates.TemplateResponse("browse.html", {"request": request, "logged_in": bool(get_current_user_id(request))})


@app.get("/trade", response_class=HTMLResponse)
def page_trade(request: Request):
    # trade.html uses a template var for CTA swap in Step 2
    return templates.TemplateResponse("trade.html", {"request": request, "logged_in": bool(get_current_user_id(request))})


@app.get("/account", response_class=HTMLResponse)
def page_account(request: Request):
    return templates.TemplateResponse("account.html", {"request": request, "logged_in": bool(get_current_user_id(request))})


@app.get("/about", response_class=HTMLResponse)
def page_about(request: Request):
    return templates.TemplateResponse("about.html", {"request": request, "logged_in": bool(get_current_user_id(request))})


@app.get("/contact", response_class=HTMLResponse)
def page_contact(request: Request):
    return templates.TemplateResponse("contact.html", {"request": request, "logged_in": bool(get_current_user_id(request))})


# =========================
# Legacy/compat redirects (keep users from 404s)
# =========================
@app.get("/login")
def legacy_login(next: str = "/browse"):
    return RedirectResponse(url=f"/account?mode=login&next={safe_next_path(next)}", status_code=302)


@app.get("/signup")
def legacy_signup(next: str = "/browse"):
    return RedirectResponse(url=f"/account?mode=signup&next={safe_next_path(next)}", status_code=302)


@app.get("/dashboard")
def legacy_dashboard(request: Request):
    # Dashboard is scrapped. Keep people in the core loop.
    if get_current_user_id(request):
        return RedirectResponse(url="/browse", status_code=302)
    return RedirectResponse(url="/account?mode=login&next=/browse", status_code=302)


@app.get("/about-us")
def legacy_about():
    return RedirectResponse(url="/about", status_code=302)


@app.get("/how-it-works")
def legacy_how_it_works():
    # If you still have a page, map it here; otherwise keep it simple.
    return RedirectResponse(url="/", status_code=302)


# =========================
# Auth actions (POST)
# =========================
@app.post("/login")
def do_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form(""),
):
    next_path = safe_next_path(next, default="/browse")
    with db() as conn:
        row = conn.execute("SELECT id, password_hash FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
    if not row or not pwd_context.verify(password, row["password_hash"]):
        # keep it simple: bounce back to account with login mode
        return RedirectResponse(url=f"/account?mode=login&next={next_path}", status_code=303)

    set_login(request, int(row["id"]))
    return RedirectResponse(url=next_path, status_code=303)


@app.post("/signup")
def do_signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    postcode: str = Form(""),
    next: str = Form(""),
):
    next_path = safe_next_path(next, default="/browse")
    if password != password_confirm:
        return RedirectResponse(url=f"/account?mode=signup&next={next_path}", status_code=303)

    pw_hash = pwd_context.hash(password)
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO users(name, postcode, email, password_hash) VALUES(?,?,?,?)",
                (name, postcode, email.strip().lower(), pw_hash),
            )
            user_id = int(cur.lastrowid)
    except sqlite3.IntegrityError:
        # email already exists -> go to login
        return RedirectResponse(url=f"/account?mode=login&next={next_path}", status_code=303)

    set_login(request, user_id)
    return RedirectResponse(url=next_path, status_code=303)


@app.get("/logout")
def do_logout(request: Request, next: str = "/browse"):
    clear_login(request)
    return RedirectResponse(url=safe_next_path(next, default="/browse"), status_code=302)


# =========================
# Trade messaging (core loop)
# =========================
@app.get("/propose-trade/{listing_id}")
def propose_trade(request: Request, listing_id: str):
    uid = get_current_user_id(request)
    if not uid:
        # send to account with return to the exact trade
        return RedirectResponse(url=f"/account?mode=login&next=/trade?id={listing_id}", status_code=302)

    with db() as conn:
        row = conn.execute(
            "SELECT id FROM trade_threads WHERE listing_id=? AND owner_user_id=?",
            (listing_id, uid),
        ).fetchone()
        if row:
            trade_id = int(row["id"])
        else:
            cur = conn.execute(
                "INSERT INTO trade_threads(listing_id, owner_user_id) VALUES(?,?)",
                (listing_id, uid),
            )
            trade_id = int(cur.lastrowid)

    return RedirectResponse(url=f"/trade-chat/{trade_id}", status_code=302)


@app.get("/trade-chat/{trade_id}", response_class=HTMLResponse)
def trade_chat(request: Request, trade_id: int):
    uid = get_current_user_id(request)
    if not uid:
        return RedirectResponse(url=f"/account?mode=login&next=/trade-chat/{trade_id}", status_code=302)

    with db() as conn:
        thread = conn.execute("SELECT id, listing_id, owner_user_id, created_at FROM trade_threads WHERE id=?", (trade_id,)).fetchone()
        if not thread:
            return RedirectResponse(url="/browse", status_code=302)

        msgs = conn.execute(
            """
            SELECT m.id, m.body, m.created_at, m.sender_user_id
            FROM messages m
            WHERE m.trade_id=?
            ORDER BY m.id ASC
            """,
            (trade_id,),
        ).fetchall()

    # Minimal inline HTML (keeps you moving even if templates aren't ready).
    # You can replace this with a template later (trade-chat.html).
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'/>"
        "<title>TradBarter — Messages</title>"
        "<style>body{font-family:system-ui,Segoe UI,Arial;max-width:820px;margin:20px auto;padding:0 14px;}"
        ".top{display:flex;justify-content:space-between;gap:10px;align-items:center;}"
        "a{color:#0B2E59;font-weight:700;text-decoration:none;}"
        ".msg{border:1px solid rgba(0,0,0,0.08);border-radius:12px;padding:10px 12px;margin:10px 0;}"
        ".meta{opacity:0.7;font-size:12px;margin-bottom:6px;}"
        "textarea{width:100%;min-height:84px;border-radius:12px;border:1px solid rgba(0,0,0,0.14);padding:10px;}"
        "button{background:#F7941D;color:#fff;border:0;border-radius:12px;padding:10px 14px;font-weight:800;cursor:pointer;}"
        "</style></head><body>"
    ]
    parts.append("<div class='top'>")
    parts.append(f"<div><div style='font-size:18px;font-weight:900;'>Trade messages</div><div style='opacity:.75;'>Listing: {thread['listing_id']}</div></div>")
    parts.append("<div><a href='/browse'>Back to browse</a></div>")
    parts.append("</div>")

    if msgs:
        for m in msgs:
            who = "You" if int(m["sender_user_id"]) == uid else "Other"
            parts.append("<div class='msg'>")
            parts.append(f"<div class='meta'>{who} • {m['created_at']}</div>")
            parts.append(f"<div>{m['body']}</div>")
            parts.append("</div>")
    else:
        parts.append("<p style='opacity:.75;margin-top:14px;'>No messages yet. Start the trade by sending a clear first message.</p>")

    parts.append("<form method='post' action='/message-trade/%d' style='margin-top:14px;'>" % trade_id)
    parts.append("<textarea name='body' placeholder='Write your message…' required></textarea>")
    parts.append("<div style='margin-top:10px;display:flex;justify-content:flex-end;'><button type='submit'>Send</button></div>")
    parts.append("</form>")
    parts.append("</body></html>")
    return HTMLResponse("".join(parts))


@app.post("/message-trade/{trade_id}")
def message_trade(request: Request, trade_id: int, body: str = Form(...)):
    uid = get_current_user_id(request)
    if not uid:
        return RedirectResponse(url=f"/account?mode=login&next=/trade-chat/{trade_id}", status_code=303)

    text = (body or "").strip()
    if not text:
        return RedirectResponse(url=f"/trade-chat/{trade_id}", status_code=303)

    with db() as conn:
        conn.execute(
            "INSERT INTO messages(trade_id, sender_user_id, body) VALUES(?,?,?)",
            (trade_id, uid, text),
        )

    return RedirectResponse(url=f"/trade-chat/{trade_id}", status_code=303)
