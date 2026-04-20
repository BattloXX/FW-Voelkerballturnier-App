import markdown
import bleach
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.services.standings import calculate_standings, calculate_inter_standings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

ALLOWED_TAGS = ["p", "br", "b", "strong", "em", "i", "ul", "ol", "li", "h1", "h2", "h3", "h4", "blockquote"]


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    tournaments = db.query(models.Tournament).order_by(models.Tournament.date.desc()).all()
    return templates.TemplateResponse("index.html", {"request": request, "tournaments": tournaments})


@router.get("/turnier/{slug}", response_class=HTMLResponse)
def tournament_overview(slug: str, request: Request, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404, detail="Turnier nicht gefunden")
    return templates.TemplateResponse("tournament/overview.html", {"request": request, "tournament": t})


@router.get("/turnier/{slug}/spielplan", response_class=HTMLResponse)
def tournament_schedule(slug: str, request: Request, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404, detail="Turnier nicht gefunden")

    prelim_matches = db.query(models.Match).filter(
        models.Match.tournament_id == t.id,
        models.Match.round_type == models.RoundType.prelim
    ).order_by(models.Match.scheduled_time, models.Match.field_number).all()

    inter_matches = db.query(models.Match).filter(
        models.Match.tournament_id == t.id,
        models.Match.round_type == models.RoundType.inter
    ).order_by(models.Match.scheduled_time, models.Match.field_number).all()

    placement_matches = db.query(models.Match).filter(
        models.Match.tournament_id == t.id,
        models.Match.round_type == models.RoundType.placement
    ).order_by(models.Match.scheduled_time).all()

    # Nur Felder anzeigen, die tatsächlich Teams haben
    fields = _active_fields(t.id, db)
    prelim_by_field = {f: [m for m in prelim_matches if m.field_number == f] for f in fields}
    # Zwischenrunde nur anzeigen wenn >1 Feld mit Teams
    if len(fields) < 2:
        inter_matches = []
        placement_matches = []

    return templates.TemplateResponse("tournament/schedule.html", {
        "request": request,
        "tournament": t,
        "prelim_by_field": prelim_by_field,
        "inter_matches": inter_matches,
        "placement_matches": placement_matches,
        "fields": fields,
        "RoundType": models.RoundType,
        "MatchStatus": models.MatchStatus,
    })


@router.get("/turnier/{slug}/rangliste", response_class=HTMLResponse)
def tournament_standings(slug: str, request: Request, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404, detail="Turnier nicht gefunden")

    fields = _active_fields(t.id, db)
    standings_by_field = {}
    for f in fields:
        standings_by_field[f] = calculate_standings(t, f, models.RoundType.prelim, db)

    return templates.TemplateResponse("tournament/standings.html", {
        "request": request,
        "tournament": t,
        "standings_by_field": standings_by_field,
        "fields": fields,
    })


@router.get("/turnier/{slug}/regeln", response_class=HTMLResponse)
def tournament_rules(slug: str, request: Request, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404, detail="Turnier nicht gefunden")

    rules_html = ""
    if t.rules_text:
        raw_html = markdown.markdown(t.rules_text)
        rules_html = bleach.clean(raw_html, tags=ALLOWED_TAGS, strip=True)

    return templates.TemplateResponse("tournament/rules.html", {
        "request": request,
        "tournament": t,
        "rules_html": rules_html,
    })


@router.get("/api/turnier/{slug}/live")
def live_data(slug: str, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404)

    matches = db.query(models.Match).filter(
        models.Match.tournament_id == t.id
    ).order_by(models.Match.scheduled_time).all()

    fields = _active_fields(t.id, db)
    standings = {}
    for f in fields:
        s = calculate_standings(t, f, models.RoundType.prelim, db)
        standings[str(f)] = [e.model_dump() for e in s]

    match_data = []
    for m in matches:
        team_a_name = m.team_a.name if m.team_a else (m.team_a_placeholder or "?")
        team_b_name = m.team_b.name if m.team_b else (m.team_b_placeholder or "?")
        match_data.append({
            "id": m.id,
            "round_type": m.round_type.value,
            "field_number": m.field_number,
            "scheduled_time": m.scheduled_time.isoformat() if m.scheduled_time else None,
            "team_a": team_a_name,
            "team_b": team_b_name,
            "score_a": m.score_a,
            "score_b": m.score_b,
            "status": m.status.value,
        })

    return JSONResponse({"matches": match_data, "standings": standings})


def _active_fields(tournament_id: int, db: Session) -> list[int]:
    """Gibt nur Felder zurück, die tatsächlich Teams haben."""
    rows = db.query(models.Team.field_group).filter(
        models.Team.tournament_id == tournament_id
    ).distinct().order_by(models.Team.field_group).all()
    return [r[0] for r in rows]
