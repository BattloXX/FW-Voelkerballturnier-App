import os
import random
import string
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Form, File, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app import models
from app.auth import authenticate_user, create_access_token, require_admin, require_superadmin, get_token_from_request, get_user_from_token, hash_password
from app.services.schedule import generate_schedule, resolve_teams
from app.services.pdf import generate_team_pdf, generate_all_teams_pdf
import markdown
import bleach

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")

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
    points_win: int = Form(2),
    points_loss: int = Form(1),
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
    points_win: int = Form(2),
    points_loss: int = Form(1),
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
    field_group: int = Form(...),
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)

    team = models.Team(
        tournament_id=tournament_id,
        name=name.strip(),
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
    db: Session = Depends(get_db)
):
    user = _get_admin_user(request, db)
    if not user:
        return RedirectResponse(url="/admin/login", status_code=303)
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if team:
        team.name = name.strip()
        db.commit()
    return RedirectResponse(url=f"/admin/turnier/{tournament_id}", status_code=303)


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
    return templates.TemplateResponse("admin/schedule.html", {
        "request": request, "user": user, "tournament": t, "matches": matches,
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
    match.score_a = data.get("score_a")
    match.score_b = data.get("score_b")
    match.players_remaining_a = data.get("players_remaining_a")
    match.players_remaining_b = data.get("players_remaining_b")
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


# PDF
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
