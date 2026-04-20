from typing import List, Dict
from sqlalchemy.orm import Session
from app import models
from app.schemas import StandingEntry


def calculate_standings(tournament: models.Tournament, field_group: int, round_type: models.RoundType, db: Session) -> List[StandingEntry]:
    teams = db.query(models.Team).filter(
        models.Team.tournament_id == tournament.id,
        models.Team.field_group == field_group
    ).all()

    if round_type == models.RoundType.prelim:
        matches = db.query(models.Match).filter(
            models.Match.tournament_id == tournament.id,
            models.Match.round_type == models.RoundType.prelim,
            models.Match.field_number == field_group,
            models.Match.status == models.MatchStatus.finished
        ).all()
    else:
        matches = db.query(models.Match).filter(
            models.Match.tournament_id == tournament.id,
            models.Match.round_type == round_type,
            models.Match.field_number == field_group,
            models.Match.status == models.MatchStatus.finished
        ).all()

    stats: Dict[int, dict] = {
        t.id: {"team": t, "played": 0, "wins": 0, "losses": 0, "points": 0, "diff": 0}
        for t in teams
    }

    for match in matches:
        if match.team_a_id not in stats or match.team_b_id not in stats:
            continue
        if match.score_a is None or match.score_b is None:
            continue

        stats[match.team_a_id]["played"] += 1
        stats[match.team_b_id]["played"] += 1

        diff_a = (match.players_remaining_a or 0) - (match.players_remaining_b or 0)
        stats[match.team_a_id]["diff"] += diff_a
        stats[match.team_b_id]["diff"] -= diff_a

        if match.score_a > match.score_b:
            stats[match.team_a_id]["wins"] += 1
            stats[match.team_a_id]["points"] += tournament.points_win
            stats[match.team_b_id]["losses"] += 1
            stats[match.team_b_id]["points"] += tournament.points_loss
        elif match.score_b > match.score_a:
            stats[match.team_b_id]["wins"] += 1
            stats[match.team_b_id]["points"] += tournament.points_win
            stats[match.team_a_id]["losses"] += 1
            stats[match.team_a_id]["points"] += tournament.points_loss
        else:
            stats[match.team_a_id]["points"] += 1
            stats[match.team_b_id]["points"] += 1

    sorted_teams = sorted(
        stats.values(),
        key=lambda x: (-x["points"], -x["diff"], x["team"].name)
    )

    result = []
    for i, s in enumerate(sorted_teams):
        result.append(StandingEntry(
            rank=i + 1,
            team_id=s["team"].id,
            team_name=s["team"].name,
            played=s["played"],
            wins=s["wins"],
            losses=s["losses"],
            points=s["points"],
            diff=s["diff"],
            promotes=(i + 1) <= tournament.promotions_per_field
        ))
    return result


def calculate_inter_standings(tournament: models.Tournament, inter_group: int, db: Session) -> List[StandingEntry]:
    matches = db.query(models.Match).filter(
        models.Match.tournament_id == tournament.id,
        models.Match.round_type == models.RoundType.inter,
        models.Match.field_number == inter_group,
        models.Match.status == models.MatchStatus.finished
    ).all()

    team_ids = set()
    for m in matches:
        if m.team_a_id:
            team_ids.add(m.team_a_id)
        if m.team_b_id:
            team_ids.add(m.team_b_id)

    teams = db.query(models.Team).filter(models.Team.id.in_(team_ids)).all()

    stats: Dict[int, dict] = {
        t.id: {"team": t, "played": 0, "wins": 0, "losses": 0, "points": 0, "diff": 0}
        for t in teams
    }

    for match in matches:
        if not match.team_a_id or not match.team_b_id:
            continue
        if match.score_a is None or match.score_b is None:
            continue

        stats[match.team_a_id]["played"] += 1
        stats[match.team_b_id]["played"] += 1

        diff_a = (match.players_remaining_a or 0) - (match.players_remaining_b or 0)
        stats[match.team_a_id]["diff"] += diff_a
        stats[match.team_b_id]["diff"] -= diff_a

        if match.score_a > match.score_b:
            stats[match.team_a_id]["wins"] += 1
            stats[match.team_a_id]["points"] += tournament.points_win
            stats[match.team_b_id]["losses"] += 1
            stats[match.team_b_id]["points"] += tournament.points_loss
        elif match.score_b > match.score_a:
            stats[match.team_b_id]["wins"] += 1
            stats[match.team_b_id]["points"] += tournament.points_win
            stats[match.team_a_id]["losses"] += 1
            stats[match.team_a_id]["points"] += tournament.points_loss
        else:
            stats[match.team_a_id]["points"] += 1
            stats[match.team_b_id]["points"] += 1

    sorted_teams = sorted(
        stats.values(),
        key=lambda x: (-x["points"], -x["diff"], x["team"].name)
    )

    result = []
    for i, s in enumerate(sorted_teams):
        result.append(StandingEntry(
            rank=i + 1,
            team_id=s["team"].id,
            team_name=s["team"].name,
            played=s["played"],
            wins=s["wins"],
            losses=s["losses"],
            points=s["points"],
            diff=s["diff"],
            promotes=True
        ))
    return result
