from typing import List, Tuple, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app import models


# ---------------------------------------------------------------------------
# Round-Robin Hilfsfunktion
# ---------------------------------------------------------------------------

def round_robin_pairs(n: int) -> List[Tuple[int, int]]:
    """Standard Round-Robin für n Teams (0-basiert). Gibt alle Paarungen zurück."""
    teams = list(range(n))
    if n % 2 == 1:
        teams.append(None)  # Freilos bei ungerader Anzahl

    pairs = []
    num_rounds = len(teams) - 1
    mid = len(teams) // 2

    for _ in range(num_rounds):
        for i in range(mid):
            a, b = teams[i], teams[len(teams) - 1 - i]
            if a is not None and b is not None:
                pairs.append((a, b))
        teams = [teams[0]] + [teams[-1]] + teams[1:-1]

    return pairs


# ---------------------------------------------------------------------------
# Spielplan generieren
# ---------------------------------------------------------------------------

def generate_schedule(tournament: models.Tournament, db: Session) -> None:
    """
    Vollständigen Spielplan generieren.
    Vorrunde mit echten Teams, Zwischenrunde + Platzierung mit Platzhaltern.
    Schlägt fehl wenn bereits Ergebnisse eingetragen sind.
    """
    if db.query(models.Match).filter(
        models.Match.tournament_id == tournament.id,
        models.Match.status == models.MatchStatus.finished
    ).count() > 0:
        raise ValueError(
            "Spielplan kann nicht neu generiert werden: Es sind bereits Ergebnisse eingetragen."
        )

    db.query(models.Match).filter(models.Match.tournament_id == tournament.id).delete()
    db.commit()

    teams_by_field = {
        field: db.query(models.Team).filter(
            models.Team.tournament_id == tournament.id,
            models.Team.field_group == field
        ).order_by(models.Team.id).all()
        for field in range(1, tournament.num_fields + 1)
    }

    start = tournament.start_time or tournament.date
    seq = 1

    # ── Vorrunde ────────────────────────────────────────────────────────────
    pairs_by_field = {f: round_robin_pairs(len(t)) for f, t in teams_by_field.items()}
    field_idx = {f: 0 for f in range(1, tournament.num_fields + 1)}
    current_time = start
    prelim_end_time = start  # wird nach jedem Slot aktualisiert

    while True:
        slot = []
        for field in range(1, tournament.num_fields + 1):
            idx = field_idx[field]
            if idx < len(pairs_by_field[field]):
                ai, bi = pairs_by_field[field][idx]
                slot.append((field, teams_by_field[field][ai], teams_by_field[field][bi]))
                field_idx[field] += 1
        if not slot:
            break

        for field, team_a, team_b in slot:
            db.add(models.Match(
                tournament_id=tournament.id,
                round_type=models.RoundType.prelim,
                field_number=field,
                sequence_number=seq,
                scheduled_time=current_time,
                team_a_id=team_a.id,
                team_b_id=team_b.id,
                status=models.MatchStatus.pending,
            ))
            seq += 1

        prelim_end_time = current_time + timedelta(minutes=tournament.game_duration_prelim)
        current_time = prelim_end_time + timedelta(minutes=tournament.break_between_games)

    # ── Zwischenrunde ───────────────────────────────────────────────────────
    if tournament.num_fields >= 2:
        # Startzeit: fix hinterlegt oder pause-basiert
        if tournament.inter_start_time:
            inter_time = tournament.inter_start_time
        else:
            inter_time = prelim_end_time + timedelta(minutes=tournament.break_prelim_to_inter)

        inter_groups = _build_inter_groups(tournament.num_fields, tournament.promotions_per_field)
        inter_end_time = inter_time

        for group_num, placeholders in enumerate(inter_groups, 1):
            t = inter_time
            for ai, bi in round_robin_pairs(len(placeholders)):
                db.add(models.Match(
                    tournament_id=tournament.id,
                    round_type=models.RoundType.inter,
                    field_number=group_num,
                    sequence_number=seq,
                    scheduled_time=t,
                    team_a_placeholder=placeholders[ai],
                    team_b_placeholder=placeholders[bi],
                    status=models.MatchStatus.pending,
                ))
                seq += 1
                end_of_match = t + timedelta(minutes=tournament.game_duration_inter)
                if end_of_match > inter_end_time:
                    inter_end_time = end_of_match
                t += timedelta(minutes=tournament.game_duration_inter + tournament.break_between_games)
    else:
        inter_end_time = prelim_end_time + timedelta(minutes=tournament.break_prelim_to_inter)

    # ── Platzierungsspiele ──────────────────────────────────────────────────
    if tournament.placement_start_time:
        placement_time = tournament.placement_start_time
    else:
        placement_time = inter_end_time + timedelta(minutes=tournament.break_prelim_to_inter)

    num_groups = tournament.num_fields if tournament.num_fields >= 2 else 1
    placement_groups = _build_placement_groups(num_groups, tournament.promotions_per_field)

    t = placement_time
    for rank_group in placement_groups:
        # rank_group = Liste von Platzhaltern, die gegeneinander spielen
        for ai, bi in round_robin_pairs(len(rank_group)):
            db.add(models.Match(
                tournament_id=tournament.id,
                round_type=models.RoundType.placement,
                field_number=1,
                sequence_number=seq,
                scheduled_time=t,
                team_a_placeholder=rank_group[ai],
                team_b_placeholder=rank_group[bi],
                status=models.MatchStatus.pending,
            ))
            seq += 1
            t += timedelta(minutes=tournament.game_duration_placement + tournament.break_between_games)

    db.commit()


# ---------------------------------------------------------------------------
# Gruppen-Berechnung: Zwischenrunde
# ---------------------------------------------------------------------------

def _build_inter_groups(num_fields: int, num_promoted: int) -> List[List[str]]:
    """
    Baut Zwischenrunden-Gruppen durch Rotation.

    Formel: Gruppe G (1-basiert) bekommt Rang R (1-basiert) von
            Feld f = ((G + R - 2) % num_fields) + 1

    Garantiert maximale Durchmischung: kein Feld dominiert eine Gruppe.

    Beispiel 2 Felder, 6 Aufsteiger:
      Gruppe 1: 1.F1, 2.F2, 3.F1, 4.F2, 5.F1, 6.F2
      Gruppe 2: 1.F2, 2.F1, 3.F2, 4.F1, 5.F2, 6.F1

    Beispiel 3 Felder, 4 Aufsteiger:
      Gruppe 1: 1.F1, 2.F2, 3.F3, 4.F1
      Gruppe 2: 1.F2, 2.F3, 3.F1, 4.F2
      Gruppe 3: 1.F3, 2.F1, 3.F2, 4.F3
    """
    groups = []
    for g in range(1, num_fields + 1):
        group = []
        for r in range(1, num_promoted + 1):
            field = ((g + r - 2) % num_fields) + 1
            group.append(f"{r}.Feld{field}")
        groups.append(group)
    return groups


# ---------------------------------------------------------------------------
# Gruppen-Berechnung: Platzierungsspiele
# ---------------------------------------------------------------------------

def _build_placement_groups(num_groups: int, num_promoted: int) -> List[List[str]]:
    """
    Baut Platzierungsspiel-Gruppen: Teams gleichen Rangs spielen gegeneinander.

    Für num_groups == 2: je ein Spiel pro Rang (Finale, 3./4.-Platz, ...)
    Für num_groups >= 3: Round-Robin unter allen Teams desselben Rangs

    Reihenfolge: Platz 1 zuerst (Finale zuerst im Spielplan).

    Beispiel 2 Gruppen, 6 Plätze:
      [1.Zw1, 1.Zw2]  → Finale
      [2.Zw1, 2.Zw2]  → 3./4. Platz
      ...

    Beispiel 3 Gruppen, 4 Plätze:
      [1.Zw1, 1.Zw2, 1.Zw3]  → Spiel um Platz 1-3
      [2.Zw1, 2.Zw2, 2.Zw3]  → Spiel um Platz 4-6
      ...
    """
    result = []
    for rank in range(1, num_promoted + 1):
        group = [f"{rank}.Zw{g}" for g in range(1, num_groups + 1)]
        result.append(group)
    return result


# ---------------------------------------------------------------------------
# Teams einsetzen (nach Vorrunde / Zwischenrunde)
# ---------------------------------------------------------------------------

def resolve_teams(tournament: models.Tournament, db: Session) -> dict:
    """
    Löst Platzhalter in Zwischenrunde und Platzierungsspielen auf.
    Kann mehrfach aufgerufen werden (idempotent).
    """
    from app.services.standings import calculate_standings, calculate_inter_standings

    stats = {"inter_resolved": 0, "placement_resolved": 0, "errors": []}

    # Vorrunden-Tabelle pro Feld
    field_standings = {}
    for field in range(1, tournament.num_fields + 1):
        s = calculate_standings(tournament, field, models.RoundType.prelim, db)
        field_standings[field] = {e.rank: e.team_id for e in s}

    # Zwischenrunde befüllen
    for match in db.query(models.Match).filter(
        models.Match.tournament_id == tournament.id,
        models.Match.round_type == models.RoundType.inter,
    ).all():
        changed = False
        if match.team_a_placeholder and not match.team_a_id:
            tid = _resolve_prelim_ph(match.team_a_placeholder, field_standings)
            if tid:
                match.team_a_id = tid
                changed = True
            else:
                stats["errors"].append(f"'{match.team_a_placeholder}' nicht auflösbar")
        if match.team_b_placeholder and not match.team_b_id:
            tid = _resolve_prelim_ph(match.team_b_placeholder, field_standings)
            if tid:
                match.team_b_id = tid
                changed = True
            else:
                stats["errors"].append(f"'{match.team_b_placeholder}' nicht auflösbar")
        if match.team_a_id and match.team_b_id:
            stats["inter_resolved"] += 1

    db.commit()

    # Zwischenrunden-Tabelle pro Gruppe
    inter_standings = {}
    for g in range(1, tournament.num_fields + 1):
        s = calculate_inter_standings(tournament, g, db)
        inter_standings[g] = {e.rank: e.team_id for e in s}

    # Platzierungsspiele befüllen
    for match in db.query(models.Match).filter(
        models.Match.tournament_id == tournament.id,
        models.Match.round_type == models.RoundType.placement,
    ).all():
        if match.team_a_placeholder and not match.team_a_id:
            tid = _resolve_inter_ph(match.team_a_placeholder, inter_standings)
            if tid:
                match.team_a_id = tid
            else:
                stats["errors"].append(f"'{match.team_a_placeholder}' nicht auflösbar")
        if match.team_b_placeholder and not match.team_b_id:
            tid = _resolve_inter_ph(match.team_b_placeholder, inter_standings)
            if tid:
                match.team_b_id = tid
            else:
                stats["errors"].append(f"'{match.team_b_placeholder}' nicht auflösbar")
        if match.team_a_id and match.team_b_id:
            stats["placement_resolved"] += 1

    db.commit()
    return stats


def _resolve_prelim_ph(placeholder: str, field_standings: dict) -> Optional[int]:
    """'2.Feld1' → Team-ID aus Vorrunden-Tabelle."""
    try:
        rank_str, field_str = placeholder.split(".")
        rank = int(rank_str)
        field = int(field_str.replace("Feld", ""))
        return field_standings.get(field, {}).get(rank)
    except Exception:
        return None


def _resolve_inter_ph(placeholder: str, inter_standings: dict) -> Optional[int]:
    """'2.Zw1' → Team-ID aus Zwischenrunden-Tabelle."""
    try:
        # Format: "{rank}.Zw{group}"
        dot_idx = placeholder.index(".")
        rank = int(placeholder[:dot_idx])
        group = int(placeholder[dot_idx + 1:].replace("Zw", ""))
        return inter_standings.get(group, {}).get(rank)
    except Exception:
        return None


# Rückwärtskompatibilität
def resolve_inter_placeholders(tournament: models.Tournament, db: Session) -> None:
    resolve_teams(tournament, db)
