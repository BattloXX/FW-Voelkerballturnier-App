from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app import models
from app.services.standings import calculate_standings
from app.templates_config import templates

router = APIRouter()

MAX_PLAYERS = 10


@router.get("/turnier/{slug}/team/{team_id}", response_class=HTMLResponse)
def team_self_service(slug: str, team_id: int, pin: str, request: Request, db: Session = Depends(get_db)):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404, detail="Turnier nicht gefunden")

    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.tournament_id == t.id
    ).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team nicht gefunden")

    pin_valid = team.pin == pin

    matches = db.query(models.Match).filter(
        models.Match.tournament_id == t.id,
        or_(models.Match.team_a_id == team_id, models.Match.team_b_id == team_id)
    ).order_by(models.Match.scheduled_time).all()

    standings = calculate_standings(t, team.field_group, models.RoundType.prelim, db)
    my_rank = next((s for s in standings if s.team_id == team_id), None)

    saved = request.query_params.get("saved")
    saved_org = request.query_params.get("saved_org")
    saved_contact = request.query_params.get("saved_contact")
    error = request.query_params.get("error")

    return templates.TemplateResponse("team/self_service.html", {
        "request": request,
        "tournament": t,
        "team": team,
        "pin": pin,
        "pin_valid": pin_valid,
        "matches": matches,
        "my_rank": my_rank,
        "standings": standings,
        "max_players": MAX_PLAYERS,
        "saved": saved,
        "saved_org": saved_org,
        "saved_contact": saved_contact,
        "error": error,
    })


@router.post("/turnier/{slug}/team/{team_id}/spieler", response_class=HTMLResponse)
async def save_players(
    slug: str,
    team_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404)

    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.tournament_id == t.id
    ).first()
    if not team:
        raise HTTPException(status_code=404)

    form = await request.form()
    pin = form.get("pin", "")

    if team.pin != pin:
        return RedirectResponse(
            url=f"/turnier/{slug}/team/{team_id}?pin={pin}&error=pin",
            status_code=303
        )

    if team.players_locked and team.players:
        return RedirectResponse(
            url=f"/turnier/{slug}/team/{team_id}?pin={pin}&error=locked",
            status_code=303
        )

    # Alle bisherigen Spieler löschen und neu einlesen
    db.query(models.Player).filter(models.Player.team_id == team_id).delete()

    count = 0
    for i in range(1, MAX_PLAYERS + 1):
        name = form.get(f"spieler_name_{i}", "").strip()
        nummer_raw = form.get(f"spieler_nummer_{i}", "").strip()
        if not name:
            continue
        jersey = int(nummer_raw) if nummer_raw.isdigit() else None
        db.add(models.Player(
            team_id=team_id,
            name=name,
            jersey_number=jersey,
        ))
        count += 1

    if count > 0:
        team.players_locked = True
    db.commit()
    return RedirectResponse(
        url=f"/turnier/{slug}/team/{team_id}?pin={pin}&saved={count}",
        status_code=303
    )


@router.post("/turnier/{slug}/team/{team_id}/kontakt", response_class=HTMLResponse)
async def save_contact(
    slug: str,
    team_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404)
    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.tournament_id == t.id
    ).first()
    if not team:
        raise HTTPException(status_code=404)
    form = await request.form()
    pin = form.get("pin", "")
    if team.pin != pin:
        return RedirectResponse(
            url=f"/turnier/{slug}/team/{team_id}?pin={pin}&error=pin",
            status_code=303
        )
    team.contact_person = form.get("contact_person", "").strip() or None
    team.contact_phone = form.get("contact_phone", "").strip() or None
    db.commit()
    return RedirectResponse(
        url=f"/turnier/{slug}/team/{team_id}?pin={pin}&saved_contact=1",
        status_code=303
    )


@router.post("/turnier/{slug}/team/{team_id}/organisation", response_class=HTMLResponse)
async def save_organisation(
    slug: str,
    team_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    t = db.query(models.Tournament).filter(models.Tournament.slug == slug).first()
    if not t:
        raise HTTPException(status_code=404)
    team = db.query(models.Team).filter(
        models.Team.id == team_id,
        models.Team.tournament_id == t.id
    ).first()
    if not team:
        raise HTTPException(status_code=404)
    form = await request.form()
    pin = form.get("pin", "")
    if team.pin != pin:
        return RedirectResponse(
            url=f"/turnier/{slug}/team/{team_id}?pin={pin}&error=pin",
            status_code=303
        )
    org = form.get("organization", "").strip()
    team.organization = org or None
    db.commit()
    return RedirectResponse(
        url=f"/turnier/{slug}/team/{team_id}?pin={pin}&saved_org=1",
        status_code=303
    )
