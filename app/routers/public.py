import markdown
import bleach
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.services.standings import calculate_standings, calculate_inter_standings, calculate_group_standings
from app.templates_config import templates

router = APIRouter()

ALLOWED_TAGS = ["p", "br", "b", "strong", "em", "i", "ul", "ol", "li", "h1", "h2", "h3", "h4", "blockquote"]


@router.post("/team/login")
def team_login(
    team_id: int = Form(...),
    pin: str = Form(...),
    db: Session = Depends(get_db)
):
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    pin = pin.strip()
    if not team or team.pin != pin:
        return RedirectResponse(url="/?team_error=1", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == team.tournament_id).first()
    if not t:
        return RedirectResponse(url="/?team_error=1", status_code=303)
    return RedirectResponse(url=f"/turnier/{t.slug}/team/{team_id}?pin={pin}", status_code=303)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    tournaments = db.query(models.Tournament).order_by(models.Tournament.date.desc()).all()
    team_error = request.query_params.get("team_error")
    return templates.TemplateResponse("index.html", {"request": request, "tournaments": tournaments, "team_error": team_error})


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

    fields = _active_fields(t.id, db)
    prelim_by_field = {f: [m for m in prelim_matches if m.field_number == f] for f in fields}

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

    # Zwischenrunde
    inter_groups = sorted(set(
        m.field_number for m in db.query(models.Match).filter(
            models.Match.tournament_id == t.id,
            models.Match.round_type == models.RoundType.inter,
        ).all()
    ))
    inter_standings_by_group = {}
    for g in inter_groups:
        inter_standings_by_group[g] = calculate_inter_standings(t, g, db)

    # Platzierungsspiele / Gesamtranking
    placement_matches = db.query(models.Match).filter(
        models.Match.tournament_id == t.id,
        models.Match.round_type == models.RoundType.placement,
        models.Match.status == models.MatchStatus.finished,
    ).all()
    placement_groups = sorted(set(m.field_number for m in placement_matches))
    placement_standings_by_group = {}
    for g in placement_groups:
        placement_standings_by_group[g] = calculate_group_standings(t, g, models.RoundType.placement, db)

    return templates.TemplateResponse("tournament/standings.html", {
        "request": request,
        "tournament": t,
        "standings_by_field": standings_by_field,
        "fields": fields,
        "inter_standings_by_group": inter_standings_by_group,
        "inter_groups": inter_groups,
        "placement_standings_by_group": placement_standings_by_group,
        "placement_groups": placement_groups,
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


@router.get("/infoscreen", response_class=HTMLResponse)
def infoscreen_redirect(db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(
        models.Tournament.status.in_([
            models.TournamentStatus.active,
            models.TournamentStatus.registration,
        ])
    ).order_by(models.Tournament.date).first()
    if not t:
        t = db.query(models.Tournament).order_by(models.Tournament.date.desc()).first()
    if not t:
        raise HTTPException(status_code=404, detail="Kein Turnier gefunden")
    return RedirectResponse(url=f"/infoscreen/{t.slug}", status_code=302)


@router.get("/infoscreen/{slug}", response_class=HTMLResponse)
def infoscreen(slug: str, request: Request, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404, detail="Turnier nicht gefunden")

    fields = _active_fields(t.id, db)
    standings_by_field = {f: calculate_standings(t, f, models.RoundType.prelim, db) for f in fields}

    inter_groups = sorted(set(
        m.field_number for m in db.query(models.Match).filter(
            models.Match.tournament_id == t.id,
            models.Match.round_type == models.RoundType.inter,
        ).all()
    ))
    inter_standings_by_group = {g: calculate_inter_standings(t, g, db) for g in inter_groups}

    raw_matches = db.query(models.Match).filter(
        models.Match.tournament_id == t.id
    ).order_by(models.Match.scheduled_time, models.Match.field_number).all()

    matches = [_match_dict(m) for m in raw_matches]

    return templates.TemplateResponse("infoscreen.html", {
        "request": request,
        "tournament": t,
        "fields": fields,
        "standings_by_field": standings_by_field,
        "inter_groups": inter_groups,
        "inter_standings_by_group": inter_standings_by_group,
        "matches": matches,
    })


@router.get("/api/infoscreen/{slug}")
def api_infoscreen(slug: str, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404)

    fields = _active_fields(t.id, db)
    standings = {}
    for f in fields:
        entries = calculate_standings(t, f, models.RoundType.prelim, db)
        standings[str(f)] = [e.model_dump() for e in entries]

    inter_groups = sorted(set(
        m.field_number for m in db.query(models.Match).filter(
            models.Match.tournament_id == t.id,
            models.Match.round_type == models.RoundType.inter,
        ).all()
    ))
    inter_standings = {}
    for g in inter_groups:
        entries = calculate_inter_standings(t, g, db)
        inter_standings[str(g)] = [e.model_dump() for e in entries]

    raw_matches = db.query(models.Match).filter(
        models.Match.tournament_id == t.id
    ).order_by(models.Match.scheduled_time, models.Match.field_number).all()

    match_data = []
    for m in raw_matches:
        d = _match_dict(m)
        d["scheduled_time"] = m.scheduled_time.isoformat() if m.scheduled_time else None
        match_data.append(d)

    return JSONResponse({"matches": match_data, "standings": standings, "inter_standings": inter_standings})


def _match_dict(m: models.Match) -> dict:
    team_a = m.team_a.name if m.team_a else (m.team_a_placeholder or "?")
    team_b = m.team_b.name if m.team_b else (m.team_b_placeholder or "?")
    scheduled_time_str = m.scheduled_time.strftime("%H:%M") if m.scheduled_time else ""
    return {
        "id": m.id,
        "round_type": m.round_type.value if m.round_type else "",
        "field_number": m.field_number,
        "scheduled_time": scheduled_time_str,
        "team_a": team_a,
        "team_b": team_b,
        "team_a_name": team_a,
        "team_b_name": team_b,
        "team_a_org": m.team_a.organization if m.team_a else None,
        "team_b_org": m.team_b.organization if m.team_b else None,
        "score_a": m.score_a,
        "score_b": m.score_b,
        "players_remaining_a": m.players_remaining_a,
        "players_remaining_b": m.players_remaining_b,
        "status": m.status.value if m.status else "pending",
    }


def _active_fields(tournament_id: int, db: Session) -> list[int]:
    """Gibt nur Felder zurück, die tatsächlich Teams haben."""
    rows = db.query(models.Team.field_group).filter(
        models.Team.tournament_id == tournament_id
    ).distinct().order_by(models.Team.field_group).all()
    return [r[0] for r in rows]
