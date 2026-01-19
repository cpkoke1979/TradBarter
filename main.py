from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

# ==========================
# Project paths
# ==========================
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ==========================
# App setup
# ==========================
app = FastAPI(title="TradBarter")

# Use an env var in real deployments.
# (Keeping a safe fallback so the app still runs locally.)
SECRET_KEY = os.getenv("TRADBARTER_SECRET_KEY", "dev-change-me")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Templates
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Static mounts (single clean convention: /static/img/...)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# User uploads
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


# ==========================
# Helpers
# ==========================

def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("user"))


def render_page(request: Request, template_name: str, context: dict | None = None):
    ctx = dict(context or {})
    ctx.update(
        {
            "request": request,
            "logged_in": is_logged_in(request),
            "user": request.session.get("user"),
        }
    )
    return templates.TemplateResponse(template_name, ctx)


def template_exists(name: str) -> bool:
    return (TEMPLATES_DIR / name).exists()


# ==========================
# Core marketing routes
# ==========================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return render_page(request, "index.html")


@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return render_page(request, "about.html")


@app.get("/browse", response_class=HTMLResponse)
async def browse(request: Request):
    return render_page(request, "browse.html")


@app.get("/contact", response_class=HTMLResponse)
async def contact(request: Request):
    return render_page(request, "contact.html")


@app.get("/account", response_class=HTMLResponse)
async def account(request: Request):
    # (Auth wiring comes later. For now this simply renders the UI.)
    return render_page(request, "account.html", {"logged_in": False})


# Nice-to-have redirects (keeps old links from breaking)
@app.get("/about-us")
async def about_us_redirect():
    return RedirectResponse(url="/about", status_code=302)


@app.get("/signup")
async def signup_redirect():
    return RedirectResponse(url="/account?mode=signup", status_code=302)


@app.get("/login")
async def login_redirect():
    return RedirectResponse(url="/account?mode=login", status_code=302)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# ==========================
# Optional: auto-render any other template pages
# (If a template exists, you can visit /<name> and it will render name.html)
# ==========================

@app.get("/{page}", response_class=HTMLResponse)
async def render_other_pages(request: Request, page: str):
    # Prevent accidental capture of common static-like paths
    if page in {"static", "uploads", "favicon.ico"}:
        return HTMLResponse("Not Found", status_code=404)

    # Map /how-it-works -> how-it-works.html etc.
    candidate = f"{page}.html"
    if template_exists(candidate):
        return render_page(request, candidate)

    return HTMLResponse("<h2>Page not found</h2>", status_code=404)
