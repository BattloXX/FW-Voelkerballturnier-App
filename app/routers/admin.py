import os
import random
import string
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app import models
from app.auth import authenticate_user, create_access_token, require_admin, require_superadmin, get_token_from_request, get_user_from_token, hash_password
from app.services.schedule import generate_schedule, resolve_teams
from app.services.pdf import generate_team_pdf, generate_all_teams_pdf, generate_urkunde_pdf, generate_schedule_pdf
from app.services.standings import calculate_standings, calculate_inter_standings, calculate_group_standings
from app.templates_config import templates
import markdown
import bleach

router = APIRouter(prefix="/admin")

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "static/uploads")
BASE_URL = os.getenv("BASE_URL", "http://localhost:8001")

ALLOWED_TAGS = ["p", "br", "b", "strong", "em", "i", "ul", "ol", "li", "h1", "h2", "h3", "h4", "blockquote"]


def _generate_pin() -> str:
    return "".join(random.choices(string.digits, k=4))


def _get_admin_user(request: Request, db: Session):
    token = get_token_from_request(request)
    if not token:
        return None
    user = get_user_from_token(token, db)
    if not user or user.role not in (models.UserRole.admin, models.UserRole.superadmin):
        return None
    return user


# Auth
@router.get("/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def admin_login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(username, password, db)
    if not user or user.role not in (models.UserRole.admin, models.UserRole.superadmin):
        return templates.TemplateResponse("admin/login.html", {"request": request, "error": "Ungültige Zugangsdaten"})

    token = create_access_token({"sub": user.username})
    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie("access_token", f"Bearer {token}", httponly=True, samesite="lax")
    return response


@router.get("/logout")
def admin_logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("access_token")
    return response


# Dashboard
@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    tournaments = db.query(models.Tournament).order_by(models.Tournament.date.desc()).all()
    return templates.TemplateResponse("admin/dashboard.html", {"request": request, "user": user, "tournaments": tournaments})


# Tournament CRUD
@router.get("/turnier/neu", response_class=HTMLResponse)
def new_tournament_form(request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    return templates.TemplateResponse("admin/tournament_form.html", {"request": request, "user": user, "tournament": None, "error": None})


@router.post("/turnier/neu", response_class=HTMLResponse)
async def create_tournament(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    date: str = Form(...),
    status: str = Form("registration"),
    rules_text: str = Form(""),
    game_duration_prelim: int = Form(5),
    game_duration_inter: int = Form(10),
    game_duration_placement: int = Form(10),
    break_between_games: int = Form(2),
    break_prelim_to_inter: int = Form(15),
    start_time: str = Form(""),
    inter_start_time: str = Form(""),
    placement_start_time: str = Form(""),
    points_win: int = Form(3),
    points_draw: int = Form(1),
    points_loss: int = Form(0),
    num_fields: int = Form(2),
    promotions_per_field: int = Form(6),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)

    existing = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if existing:
        return templates.TemplateResponse("admin/tournament_form.html", {
            "request": request, "user": user, "tournament": None,
            "error": f"Slug '{slug}' bereits vergeben."
        })

    logo_path = None
    if logo and logo.filename:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        ext = os.path.splitext(logo.filename)[1]
        fname = f"{slug}_logo{ext}"
        fpath = os.path.join(UPLOAD_DIR, fname)
        content = await logo.read()
        with open(fpath, "wb") as f:
            f.write(content)
        logo_path = f"/static/uploads/{fname}"

    t = models.Tournament(
        slug=slug.strip().lower(),
        name=name.strip(),
        description=description.strip() or None,
        date=datetime.fromisoformat(date),
        status=models.TournamentStatus(status),
        rules_text=rules_text.strip() or None,
        game_duration_prelim=game_duration_prelim,
        game_duration_inter=game_duration_inter,
        game_duration_placement=game_duration_placement,
        break_between_games=break_between_games,
        break_prelim_to_inter=break_prelim_to_inter,
        start_time=datetime.fromisoformat(start_time) if start_time else None,
        inter_start_time=datetime.fromisoformat(inter_start_time) if inter_start_time else None,
        placement_start_time=datetime.fromisoformat(placement_start_time) if placement_start_time else None,
        points_win=points_win,
        points_draw=points_draw,
        points_loss=points_loss,
        num_fields=num_fields,
        promotions_per_field=promotions_per_field,
        logo_path=logo_path,
    )
    db.add(t)
    db.commit()
    return RedirectResponse(url=f"/admin/turnier/{t.id}", status_code=303)


@router.get("/turnier/{tournament_id}", response_class=HTMLResponse)
def tournament_admin(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)
    teams = db.query(models.Team).filter(models.Team.tournament_id == tournament_id).order_by(models.Team.field_group, models.Team.name).all()
    match_count = db.query(models.Match).filter(models.Match.tournament_id == tournament_id).count()
    finished_count = db.query(models.Match).filter(
        models.Match.tournament_id == tournament_id,
        models.Match.status == models.MatchStatus.finished
    ).count()
    return templates.TemplateResponse("admin/tournament_detail.html", {
        "request": request, "user": user, "tournament": t,
        "teams": teams, "match_count": match_count, "finished_count": finished_count,
    })


@router.get("/turnier/{tournament_id}/bearbeiten", response_class=HTMLResponse)
def edit_tournament_form(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/tournament_form.html", {"request": request, "user": user, "tournament": t, "error": None})


@router.post("/turnier/{tournament_id}/bearbeiten", response_class=HTMLResponse)
async def update_tournament(
    tournament_id: int,
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    date: str = Form(...),
    status: str = Form("registration"),
    rules_text: str = Form(""),
    game_duration_prelim: int = Form(5),
    game_duration_inter: int = Form(10),
    game_duration_placement: int = Form(10),
    break_between_games: int = Form(2),
    break_prelim_to_inter: int = Form(15),
    start_time: str = Form(""),
    inter_start_time: str = Form(""),
    placement_start_time: str = Form(""),
    points_win: int = Form(3),
    points_draw: int = Form(1),
    points_loss: int = Form(0),
    num_fields: int = Form(2),
    promotions_per_field: int = Form(6),
    logo: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)

    if logo and logo.filename:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        ext = os.path.splitext(logo.filename)[1]
        fname = f"{slug}_logo{ext}"
        fpath = os.path.join(UPLOAD_DIR, fname)
        content = await logo.read()
        with open(fpath, "wb") as f:
            f.write(content)
        t.logo_path = f"/static/uploads/{fname}"

    t.name = name.strip()
    t.slug = slug.strip().lower()
    t.description = description.strip() or None
    t.date = datetime.fromisoformat(date)
    t.status = models.TournamentStatus(status)
    t.rules_text = rules_text.strip() or None
    t.game_duration_prelim = game_duration_prelim
    t.game_duration_inter = game_duration_inter
    t.game_duration_placement = game_duration_placement
    t.break_between_games = break_between_games
    t.break_prelim_to_inter = break_prelim_to_inter
    t.start_time = datetime.fromisoformat(start_time) if start_time else None
    t.inter_start_time = datetime.fromisoformat(inter_start_time) if inter_start_time else None
    t.placement_start_time = datetime.fromisoformat(placement_start_time) if placement_start_time else None
    t.points_win = points_win
    t.points_draw = points_draw
    t.points_loss = points_loss
    t.num_fields = num_fields
    t.promotions_per_field = promotions_per_field
    db.commit()
    return RedirectResponse(url=f"/admin/turnier/{tournament_id}", status_code=303)


# Teams
@router.post("/turnier/{tournament_id}/team/neu")
def add_team(
    tournament_id: int,
    request: Request,
    name: str = Form(...),
    organization: str = Form(""),
    field_group: int = Form(...),
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)

    team = models.Team(
        tournament_id=tournament_id,
        name=name.strip(),
        organization=organization.strip() or None,
        field_group=field_group,
        pin=_generate_pin(),
    )
    db.add(team)
    db.commit()
    return RedirectResponse(url=f"/admin/turnier/{tournament_id}", status_code=303)


@router.post("/turnier/{tournament_id}/team/{team_id}/loeschen")
def delete_team(tournament_id: int, team_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if team:
        db.delete(team)
        db.commit()
    return RedirectResponse(url=f"/admin/turnier/{tournament_id}", status_code=303)


@router.post("/turnier/{tournament_id}/team/{team_id}/umbenennen")
def rename_team_admin(
    tournament_id: int,
    team_id: int,
    request: Request,
    name: str = Form(...),
    organization: str = Form(""),
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if team:
        team.name = name.strip()
        team.organization = organization.strip() or None
        db.commit()
    return RedirectResponse(url=f"/admin/turnier/{tournament_id}", status_code=303)


@router.get("/turnier/{tournament_id}/team/{team_id}/spieler", response_class=HTMLResponse)
def admin_team_players_get(tournament_id: int, team_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    team = db.query(models.Team).filter(
        models.Team.id == team_id, models.Team.tournament_id == tournament_id
    ).first()
    if not t or not team:
        raise HTTPException(status_code=404)
    saved = request.query_params.get("saved")
    return templates.TemplateResponse("admin/team_players.html", {
        "request": request, "user": user, "tournament": t, "team": team,
        "max_players": 6, "saved": saved,
    })


@router.post("/turnier/{tournament_id}/team/{team_id}/spieler")
async def admin_team_players_post(
    tournament_id: int, team_id: int, request: Request,
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    team = db.query(models.Team).filter(
        models.Team.id == team_id, models.Team.tournament_id == tournament_id
    ).first()
    if not t or not team:
        raise HTTPException(status_code=404)
    form = await request.form()

    db.query(models.Player).filter(models.Player.team_id == team_id).delete()
    count = 0
    for i in range(1, 7):
        name = form.get(f"spieler_name_{i}", "").strip()
        nummer_raw = form.get(f"spieler_nummer_{i}", "").strip()
        if not name:
            continue
        jersey = int(nummer_raw) if nummer_raw.isdigit() else None
        db.add(models.Player(team_id=team_id, name=name, jersey_number=jersey))
        count += 1

    team.players_locked = form.get("players_locked", "") == "1"
    db.commit()
    return RedirectResponse(
        url=f"/admin/turnier/{tournament_id}/team/{team_id}/spieler?saved={count}",
        status_code=303
    )


# Schedule
@router.post("/turnier/{tournament_id}/spielplan/generieren")
def generate_tournament_schedule(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)
    try:
        generate_schedule(t, db)
    except ValueError as e:
        teams = db.query(models.Team).filter(models.Team.tournament_id == tournament_id).all()
        return templates.TemplateResponse("admin/tournament_detail.html", {
            "request": request, "user": user, "tournament": t, "teams": teams,
            "error": str(e), "match_count": 0, "finished_count": 0,
        })
    return RedirectResponse(url=f"/admin/turnier/{tournament_id}/spielplan", status_code=303)


@router.post("/turnier/{tournament_id}/spielplan/loeschen")
def delete_schedule(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    db.query(models.Match).filter(models.Match.tournament_id == tournament_id).delete()
    db.commit()
    return RedirectResponse(url=f"/admin/turnier/{tournament_id}", status_code=303)


@router.post("/turnier/{tournament_id}/teams-einsetzen")
def teams_einsetzen(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)
    stats = resolve_teams(t, db)
    return RedirectResponse(
        url=f"/admin/turnier/{tournament_id}/spielplan?eingesetzt=1&inter={stats['inter_resolved']}&placement={stats['placement_resolved']}&fehler={len(stats['errors'])}",
        status_code=303
    )


@router.get("/turnier/{tournament_id}/spielplan", response_class=HTMLResponse)
def schedule_admin(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)
    matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament_id
    ).order_by(models.Match.round_type, models.Match.sequence_number).all()
    teams = db.query(models.Team).filter(
        models.Team.tournament_id == tournament_id
    ).order_by(models.Team.field_group, models.Team.name).all()
    return templates.TemplateResponse("admin/schedule.html", {
        "request": request, "user": user, "tournament": t, "matches": matches,
        "teams": teams,
        "RoundType": models.RoundType, "MatchStatus": models.MatchStatus,
    })


@router.post("/turnier/{tournament_id}/match/{match_id}/ergebnis")
async def admin_set_result(tournament_id: int, match_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    data = await request.json()
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)

    p_a = data.get("players_remaining_a")
    p_b = data.get("players_remaining_b")
    match.players_remaining_a = p_a
    match.players_remaining_b = p_b

    # Derive score from players (team with more players wins)
    if p_a is not None and p_b is not None:
        if p_a > p_b:
            match.score_a, match.score_b = 1, 0
        elif p_b > p_a:
            match.score_a, match.score_b = 0, 1
        else:
            match.score_a, match.score_b = 0, 0
    else:
        match.score_a = data.get("score_a")
        match.score_b = data.get("score_b")

    match.status = models.MatchStatus.finished
    match.entered_by = user.id
    match.entered_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@router.post("/turnier/{tournament_id}/match/{match_id}/reset")
def admin_reset_match(tournament_id: int, match_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)
    match.score_a = None
    match.score_b = None
    match.players_remaining_a = None
    match.players_remaining_b = None
    match.status = models.MatchStatus.pending
    db.commit()
    return {"ok": True}


@router.post("/turnier/{tournament_id}/match/{match_id}/bearbeiten")
async def admin_edit_match(tournament_id: int, match_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        raise HTTPException(status_code=401)
    data = await request.json()
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)

    if "scheduled_time" in data and data["scheduled_time"]:
        try:
            match.scheduled_time = datetime.fromisoformat(data["scheduled_time"])
        except ValueError:
            pass

    if "field_number" in data and data["field_number"] is not None:
        match.field_number = int(data["field_number"])

    if "round_type" in data and data["round_type"]:
        try:
            match.round_type = models.RoundType(data["round_type"])
        except ValueError:
            pass

    team_a_id = data.get("team_a_id")
    team_b_id = data.get("team_b_id")
    if team_a_id is not None:
        match.team_a_id = int(team_a_id) if team_a_id else None
    if team_b_id is not None:
        match.team_b_id = int(team_b_id) if team_b_id else None

    db.commit()
    return {"ok": True}


# Rangliste Admin
@router.get("/turnier/{tournament_id}/rangliste", response_class=HTMLResponse)
def admin_standings(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)

    fields = sorted(set(
        team.field_group for team in db.query(models.Team).filter(models.Team.tournament_id == tournament_id).all()
    ))
    standings_by_field = {f: calculate_standings(t, f, models.RoundType.prelim, db) for f in fields}

    inter_groups = sorted(set(
        m.field_number for m in db.query(models.Match).filter(
            models.Match.tournament_id == tournament_id,
            models.Match.round_type == models.RoundType.inter,
        ).all()
    ))
    inter_standings = {g: calculate_inter_standings(t, g, db) for g in inter_groups}

    placement_groups = sorted(set(
        m.field_number for m in db.query(models.Match).filter(
            models.Match.tournament_id == tournament_id,
            models.Match.round_type == models.RoundType.placement,
        ).all()
    ))
    placement_standings = {g: calculate_group_standings(t, g, models.RoundType.placement, db) for g in placement_groups}

    matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament_id
    ).order_by(models.Match.round_type, models.Match.sequence_number).all()

    return templates.TemplateResponse("admin/standings_admin.html", {
        "request": request, "user": user, "tournament": t,
        "fields": fields, "standings_by_field": standings_by_field,
        "inter_groups": inter_groups, "inter_standings": inter_standings,
        "placement_groups": placement_groups, "placement_standings": placement_standings,
        "matches": matches,
        "RoundType": models.RoundType, "MatchStatus": models.MatchStatus,
    })


# PDF
@router.get("/turnier/{tournament_id}/spielplan/pdf")
def schedule_pdf_export(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)
    matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament_id
    ).order_by(models.Match.round_type, models.Match.scheduled_time, models.Match.sequence_number).all()
    pdf_bytes = generate_schedule_pdf(t, matches)
    fname = f"spielplan_{t.slug}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


# PDF (Teams)
@router.get("/turnier/{tournament_id}/team/{team_id}/pdf")
def team_pdf(tournament_id: int, team_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not t or not team:
        raise HTTPException(status_code=404)
    matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament_id,
        or_(models.Match.team_a_id == team_id, models.Match.team_b_id == team_id)
    ).order_by(models.Match.scheduled_time).all()
    pdf_bytes = generate_team_pdf(team, t, matches, BASE_URL)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="team_{team_id}.pdf"'})


@router.get("/turnier/{tournament_id}/pdf/alle")
def all_teams_pdf(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)
    teams = db.query(models.Team).filter(models.Team.tournament_id == tournament_id).order_by(models.Team.field_group, models.Team.name).all()
    matches_by_team = {}
    for team in teams:
        matches_by_team[team.id] = db.query(models.Match).filter(
            models.Match.tournament_id == tournament_id,
            or_(models.Match.team_a_id == team.id, models.Match.team_b_id == team.id)
        ).order_by(models.Match.scheduled_time).all()
    pdf_bytes = generate_all_teams_pdf(teams, t, matches_by_team, BASE_URL)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="alle_teams.pdf"'})


@router.get("/turnier/{tournament_id}/urkunden")
def urkunden_pdf(tournament_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    t = db.query(models.Tournament).filter(models.Tournament.id == tournament_id).first()
    if not t:
        raise HTTPException(status_code=404)

    rankings = _get_final_rankings(t, db)
    pdf_bytes = generate_urkunde_pdf(rankings, t)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="urkunden_{t.slug}.pdf"'})


def _get_final_rankings(tournament: models.Tournament, db: Session) -> list:
    """Returns list of (rank, team, players) for ALL teams, sorted by final placement."""
    all_teams = db.query(models.Team).filter(
        models.Team.tournament_id == tournament.id
    ).order_by(models.Team.field_group, models.Team.name).all()

    def _players(team_id):
        return db.query(models.Player).filter(
            models.Player.team_id == team_id
        ).order_by(models.Player.jersey_number).all()

    placement_matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament.id,
        models.Match.round_type == models.RoundType.placement,
    ).all()

    if placement_matches:
        finished = [m for m in placement_matches if m.status == models.MatchStatus.finished]
        rank_groups = sorted(set(m.field_number for m in placement_matches))
        result = []
        placed_team_ids = set()
        current_rank = 1

        for group in rank_groups:
            group_all = [m for m in placement_matches if m.field_number == group]
            group_finished = [m for m in finished if m.field_number == group]
            team_ids = set()
            for m in group_all:
                if m.team_a_id:
                    team_ids.add(m.team_a_id)
                if m.team_b_id:
                    team_ids.add(m.team_b_id)
            if not team_ids:
                continue

            stats = {tid: {"points": 0, "diff": 0} for tid in team_ids}
            for m in group_finished:
                if not m.team_a_id or not m.team_b_id:
                    continue
                if m.score_a is None or m.score_b is None:
                    continue
                diff = (m.players_remaining_a or 0) - (m.players_remaining_b or 0)
                if m.score_a > m.score_b:
                    stats[m.team_a_id]["points"] += tournament.points_win
                    stats[m.team_a_id]["diff"] += diff
                    stats[m.team_b_id]["points"] += tournament.points_loss
                    stats[m.team_b_id]["diff"] -= diff
                elif m.score_b > m.score_a:
                    stats[m.team_b_id]["points"] += tournament.points_win
                    stats[m.team_b_id]["diff"] -= diff
                    stats[m.team_a_id]["points"] += tournament.points_loss
                    stats[m.team_a_id]["diff"] += diff
                else:
                    stats[m.team_a_id]["points"] += 1
                    stats[m.team_b_id]["points"] += 1

            sorted_ids = sorted(
                team_ids, key=lambda tid: (-stats[tid]["points"], -stats[tid]["diff"])
            )
            for r, tid in enumerate(sorted_ids):
                team = db.query(models.Team).filter(models.Team.id == tid).first()
                if team:
                    result.append((current_rank + r, team, _players(tid)))
                    placed_team_ids.add(tid)
            current_rank += len(sorted_ids)

        # Add any teams not covered by placement matches (fallback via prelim rank)
        remaining = [t for t in all_teams if t.id not in placed_team_ids]
        if remaining:
            remaining_entries = []
            for t in remaining:
                entries = calculate_standings(tournament, t.field_group, models.RoundType.prelim, db)
                entry = next((e for e in entries if e.team_id == t.id), None)
                pts = entry.points if entry else 0
                diff = entry.diff if entry else 0
                remaining_entries.append((pts, diff, t))
            remaining_entries.sort(key=lambda x: (-x[0], -x[1], x[2].name))
            for r, (_, _, team) in enumerate(remaining_entries):
                result.append((current_rank + r, team, _players(team.id)))

        return result

    # No placement matches: use prelim standings per field sorted by rank
    fields = sorted(set(t.field_group for t in all_teams))
    all_entries = []
    for f in fields:
        entries = calculate_standings(tournament, f, models.RoundType.prelim, db)
        all_entries.extend(entries)

    all_entries.sort(key=lambda e: (-e.points, -e.diff, e.team_name))
    result = []
    for i, entry in enumerate(all_entries):
        team = db.query(models.Team).filter(models.Team.id == entry.team_id).first()
        if team:
            result.append((i + 1, team, _players(team.id)))

    # Add teams with no matches at all
    ranked_ids = {team.id for _, team, _ in result}
    for r, team in enumerate(t for t in all_teams if t.id not in ranked_ids):
        result.append((len(result) + 1, team, _players(team.id)))

    return result


# Users
@router.get("/benutzer", response_class=HTMLResponse)
def users_list(request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user or user.role != models.UserRole.superadmin:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    users = db.query(models.User).order_by(models.User.role, models.User.username).all()
    tournaments = db.query(models.Tournament).all()
    return templates.TemplateResponse("admin/users.html", {
        "request": request, "user": user, "users": users, "tournaments": tournaments,
        "UserRole": models.UserRole,
    })


@router.post("/benutzer/neu")
def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    tournament_id: str = Form(""),
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user or user.role != models.UserRole.superadmin:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    new_user = models.User(
        username=username.strip(),
        password_hash=hash_password(password),
        role=models.UserRole(role),
        tournament_id=int(tournament_id) if tournament_id else None,
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/admin/benutzer", status_code=303)


@router.post("/benutzer/{user_id}/loeschen")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = _get_admin_user(request, db)
    if not user or user.role != models.UserRole.superadmin:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if u and u.id != user.id:
        db.delete(u)
        db.commit()
    return RedirectResponse(url="/admin/benutzer", status_code=303)


@router.post("/benutzer/{user_id}/passwort")
def change_password(
    user_id: int,
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user or user.role != models.UserRole.superadmin:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    u = db.query(models.User).filter(models.User.id == user_id).first()
    if u:
        u.password_hash = hash_password(password)
        db.commit()
    return RedirectResponse(url="/admin/benutzer", status_code=303)
