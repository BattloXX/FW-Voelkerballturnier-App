from fastapi.templating import Jinja2Templates
from app.database import SessionLocal
from app import models

templates = Jinja2Templates(directory="app/templates")


def _get_nav_tournaments():
    db = SessionLocal()
    try:
        return db.query(models.Tournament).filter(
            models.Tournament.status.in_([
                models.TournamentStatus.active,
                models.TournamentStatus.registration,
            ])
        ).order_by(models.Tournament.date).all()
    except Exception:
        return []
    finally:
        db.close()


def _get_all_tournaments():
    db = SessionLocal()
    try:
        return db.query(models.Tournament).order_by(models.Tournament.date.desc()).all()
    except Exception:
        return []
    finally:
        db.close()


templates.env.globals["get_nav_tournaments"] = _get_nav_tournaments
templates.env.globals["get_all_tournaments"] = _get_all_tournaments
