import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import sqlalchemy as sa
from app.database import engine, Base, SessionLocal
from app import models
from app.routers import public, team, referee, admin
from app.auth import hash_password
from app.templates_config import templates
from dotenv import load_dotenv

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _seed_superadmin()
    os.makedirs(os.getenv("UPLOAD_DIR", "static/uploads"), exist_ok=True)
    yield


def _migrate_schema():
    """Add missing columns to existing tables without a full migration tool."""
    with engine.connect() as conn:
        pending = [
            "ALTER TABLE tournaments ADD COLUMN points_draw INT NOT NULL DEFAULT 1",
            "ALTER TABLE teams ADD COLUMN players_locked TINYINT(1) NOT NULL DEFAULT 0",
            "ALTER TABLE teams ADD COLUMN organization VARCHAR(200) NULL",
        ]
        for sql in pending:
            try:
                conn.execute(sa.text(sql))
                conn.commit()
            except Exception:
                pass  # column already exists


def _seed_superadmin():
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
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
