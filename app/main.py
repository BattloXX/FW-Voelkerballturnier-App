import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from app.database import engine, Base
from app import models
from app.routers import public, team, referee, admin
from app.auth import hash_password
from dotenv import load_dotenv

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _seed_superadmin()
    os.makedirs(os.getenv("UPLOAD_DIR", "static/uploads"), exist_ok=True)
    yield


def _seed_superadmin():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        existing = db.query(models.User).filter(models.User.role == models.UserRole.superadmin).first()
        if not existing:
            admin_user = models.User(
                username="admin",
                password_hash=hash_password("admin123"),
                role=models.UserRole.superadmin,
            )
            db.add(admin_user)
            db.commit()
            print("Superadmin erstellt: admin / admin123 — bitte Passwort sofort ändern!")
    finally:
        db.close()


app = FastAPI(title="Völkerball Turnier-Manager", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(public.router)
app.include_router(team.router)
app.include_router(referee.router)
app.include_router(admin.router)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
