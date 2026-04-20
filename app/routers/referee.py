from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.auth import authenticate_user, create_access_token, require_referee, get_token_from_request, get_user_from_token
from app.templates_config import templates

router = APIRouter()


@router.get("/schiri/login", response_class=HTMLResponse)
def referee_login_page(request: Request):
    return templates.TemplateResponse("referee/login.html", {"request": request, "error": None})


@router.post("/schiri/login", response_class=HTMLResponse)
def referee_login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = authenticate_user(username, password, db)
    if not user or user.role not in (models.UserRole.referee, models.UserRole.admin, models.UserRole.superadmin):
        return templates.TemplateResponse("referee/login.html", {"request": request, "error": "Ungültige Zugangsdaten"})

    token = create_access_token({"sub": user.username})
    response = RedirectResponse(url="/schiri/dashboard", status_code=303)
    response.set_cookie("access_token", f"Bearer {token}", httponly=True, samesite="lax")
    return response


@router.get("/schiri/logout")
def referee_logout():
    response = RedirectResponse(url="/schiri/login", status_code=303)
    response.delete_cookie("access_token")
    return response


@router.get("/schiri/dashboard", response_class=HTMLResponse)
def referee_dashboard(request: Request, db: Session = Depends(get_db)):
    token = get_token_from_request(request)
    if not token:
        return RedirectResponse(url="/schiri/login", status_code=303)
    user = get_user_from_token(token, db)
    if not user or user.role not in (models.UserRole.referee, models.UserRole.admin, models.UserRole.superadmin):
        return RedirectResponse(url="/schiri/login", status_code=303)

    tournaments = db.query(models.Tournament).filter(
        models.Tournament.status == models.TournamentStatus.active
    ).all()

    if user.tournament_id:
        tournament = db.query(models.Tournament).filter(
            models.Tournament.id == user.tournament_id
        ).first()
        tournaments = [tournament] if tournament else []

    return templates.TemplateResponse("referee/dashboard.html", {
        "request": request,
        "user": user,
        "tournaments": tournaments,
    })


@router.get("/schiri/turnier/{slug}/feld/{field_number}", response_class=HTMLResponse)
def referee_field(slug: str, field_number: int, request: Request, db: Session = Depends(get_db)):
    token = get_token_from_request(request)
    if not token:
        return RedirectResponse(url="/schiri/login", status_code=303)
    user = get_user_from_token(token, db)
    if not user or user.role not in (models.UserRole.referee, models.UserRole.admin, models.UserRole.superadmin):
        return RedirectResponse(url="/schiri/login", status_code=303)

    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404)

    active_match = db.query(models.Match).filter(
        models.Match.tournament_id == t.id,
        models.Match.field_number == field_number,
        models.Match.status == models.MatchStatus.active
    ).first()

    next_match = db.query(models.Match).filter(
        models.Match.tournament_id == t.id,
        models.Match.field_number == field_number,
        models.Match.status == models.MatchStatus.pending
    ).order_by(models.Match.scheduled_time, models.Match.sequence_number).first()

    return templates.TemplateResponse("referee/field.html", {
        "request": request,
        "tournament": t,
        "field_number": field_number,
        "active_match": active_match,
        "next_match": next_match,
        "user": user,
    })


@router.post("/schiri/turnier/{slug}/match/{match_id}/start")
def start_match(slug: str, match_id: int, request: Request, db: Session = Depends(get_db)):
    token = get_token_from_request(request)
    user = get_user_from_token(token, db) if token else None
    if not user or user.role not in (models.UserRole.referee, models.UserRole.admin, models.UserRole.superadmin):
        raise HTTPException(status_code=401)

    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)

    match.status = models.MatchStatus.active
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/schiri/turnier/{slug}/match/{match_id}/result")
async def submit_result(slug: str, match_id: int, request: Request, db: Session = Depends(get_db)):
    token = get_token_from_request(request)
    user = get_user_from_token(token, db) if token else None
    if not user or user.role not in (models.UserRole.referee, models.UserRole.admin, models.UserRole.superadmin):
        raise HTTPException(status_code=401)

    data = await request.json()
    players_a = int(data.get("players_remaining_a", 0))
    players_b = int(data.get("players_remaining_b", 0))

    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404)

    match.players_remaining_a = players_a
    match.players_remaining_b = players_b
    match.score_a = 1 if players_a > players_b else (0 if players_a < players_b else 0)
    match.score_b = 1 if players_b > players_a else (0 if players_b < players_a else 0)
    # winner gets 1 point for the set; use players as tiebreaker
    if players_a > players_b:
        match.score_a = 1
        match.score_b = 0
    elif players_b > players_a:
        match.score_a = 0
        match.score_b = 1
    else:
        match.score_a = 0
        match.score_b = 0

    match.status = models.MatchStatus.finished
    match.entered_by = user.id
    match.entered_at = datetime.now(timezone.utc)
    db.commit()

    return JSONResponse({"ok": True})
