import io
import os
import qrcode
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from sqlalchemy.orm import Session
from app import models

FW_RED = colors.HexColor("#CC0000")
FW_DARK = colors.HexColor("#2d2d2d")
FW_LIGHT = colors.HexColor("#f5f5f5")


def _make_qr(url: str) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _get_styles():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "FWTitle",
        parent=styles["Title"],
        textColor=colors.white,
        backColor=FW_RED,
        fontSize=22,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=0,
        spaceBefore=0,
        leading=28,
    )
    heading_style = ParagraphStyle(
        "FWHeading",
        parent=styles["Heading1"],
        textColor=FW_RED,
        fontSize=16,
        fontName="Helvetica-Bold",
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "FWBody",
        parent=styles["Normal"],
        fontSize=11,
        leading=16,
    )
    pin_style = ParagraphStyle(
        "FWPin",
        parent=styles["Normal"],
        textColor=FW_RED,
        fontSize=36,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    return title_style, heading_style, body_style, pin_style


def _team_page_story(team: models.Team, tournament: models.Tournament, matches: list, base_url: str) -> list:
    """Returns a list of Flowables for one team page (no PageBreak at start)."""
    content_w = 18 * cm
    date_str = tournament.date.strftime("%d.%m.%Y") if tournament.date else ""
    url = f"{base_url}/turnier/{tournament.slug}/team/{team.id}?pin={team.pin}"

    # ── Styles ──────────────────────────────────────────────────────────────
    hdr_s = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=18,
                           textColor=colors.white, alignment=TA_CENTER, leading=22)
    name_s = ParagraphStyle("TN", fontName="Helvetica-Bold", fontSize=24,
                            textColor=FW_RED, alignment=TA_LEFT, leading=28, spaceAfter=2)
    org_s = ParagraphStyle("TO", fontName="Helvetica", fontSize=12,
                           textColor=FW_DARK, alignment=TA_LEFT, leading=16, spaceAfter=0)
    meta_s = ParagraphStyle("TM", fontName="Helvetica", fontSize=10,
                            textColor=colors.HexColor("#666"), alignment=TA_LEFT, leading=14)
    pin_lbl_s = ParagraphStyle("PL", fontName="Helvetica", fontSize=8,
                               textColor=colors.HexColor("#aaa"), alignment=TA_LEFT,
                               leading=11, spaceBefore=8, spaceAfter=0,
                               letterSpacing=1)
    pin_val_s = ParagraphStyle("PV", fontName="Helvetica-Bold", fontSize=52,
                               textColor=FW_RED, alignment=TA_LEFT, leading=56)
    qr_id_s = ParagraphStyle("QI", fontName="Helvetica-Bold", fontSize=11,
                             textColor=FW_DARK, alignment=TA_CENTER, leading=14, spaceBefore=4)
    qr_hint_s = ParagraphStyle("QH", fontName="Helvetica", fontSize=8,
                               textColor=colors.HexColor("#888"), alignment=TA_CENTER, leading=11)
    sched_head_s = ParagraphStyle("SH", fontName="Helvetica-Bold", fontSize=13,
                                  textColor=FW_RED, leading=17, spaceBefore=2, spaceAfter=4)
    body_s = ParagraphStyle("BS", fontName="Helvetica", fontSize=10, leading=14)

    story = []

    # ── Header bar ──────────────────────────────────────────────────────────
    hdr_tbl = Table([[Paragraph(f"<b>{tournament.name}</b>", hdr_s)]], colWidths=[content_w])
    hdr_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FW_RED),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(hdr_tbl)
    story.append(Spacer(1, 0.5 * cm))

    # ── Left info + Right QR ─────────────────────────────────────────────────
    left = [Paragraph(team.name, name_s)]
    if getattr(team, "organization", None):
        left.append(Paragraph(team.organization, org_s))
    left += [
        Spacer(1, 0.2 * cm),
        Paragraph(f"Datum: {date_str}", meta_s),
        Paragraph(f"Gruppe: Feld {team.field_group}", meta_s),
        Spacer(1, 0.3 * cm),
        Paragraph("EUER PIN", pin_lbl_s),
        Paragraph(team.pin, pin_val_s),
    ]

    qr_buf = _make_qr(url)
    qr_img = Image(qr_buf, width=5.5 * cm, height=5.5 * cm)
    right = [
        qr_img,
        Paragraph(f"Team-ID: {team.id}", qr_id_s),
        Paragraph("QR-Code scannen für Spielplan", qr_hint_s),
    ]

    info_tbl = Table([[left, right]], colWidths=[11 * cm, 7 * cm])
    info_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 8),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=FW_RED, spaceAfter=0.4 * cm))

    # ── Schedule ─────────────────────────────────────────────────────────────
    story.append(Paragraph("Euer Spielplan", sched_head_s))
    if matches:
        tdata = [["Zeit", "Feld", "Gegner"]]
        for m in matches:
            time_str = m.scheduled_time.strftime("%H:%M") if m.scheduled_time else "–"
            opponent = (m.team_b.name if m.team_b else (m.team_b_placeholder or "?")) if m.team_a_id == team.id \
                else (m.team_a.name if m.team_a else (m.team_a_placeholder or "?"))
            tdata.append([time_str, str(m.field_number), opponent])
        sched_tbl = Table(tdata, colWidths=[3 * cm, 3 * cm, 12 * cm])
        sched_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FW_RED),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FW_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(sched_tbl)
    else:
        story.append(Paragraph("Noch kein Spielplan generiert.", body_s))

    return story


def generate_team_pdf(team: models.Team, tournament: models.Tournament, matches: list, base_url: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    doc.build(_team_page_story(team, tournament, matches, base_url))
    buf.seek(0)
    return buf.read()


RANK_LABELS = {1: "1. Platz", 2: "2. Platz", 3: "3. Platz"}
RANK_COLORS = {
    1: colors.HexColor("#FFD700"),
    2: colors.HexColor("#C0C0C0"),
    3: colors.HexColor("#CD7F32"),
}


LOGO_URL = "https://feuerwehr.wolfurt.at/wp-content/uploads/2015/02/cropped-logo-feuerwehr-aktiv-150x150.jpg"

CONGRATS = {
    1: "Herzlichen Glückwunsch zum 1. Platz! Eine herausragende Leistung – ihr seid die verdienten Sieger dieses Turniers!",
    2: "Herzlichen Glückwunsch zum 2. Platz! Eine fantastische Leistung und ein großartiges Turnier – ihr könnt sehr stolz auf euch sein!",
    3: "Herzlichen Glückwunsch zum 3. Platz! Ihr habt ein starkes Turnier gespielt und euch diesen Podiumsplatz redlich verdient!",
}
CONGRATS_DEFAULT = "Herzlichen Glückwunsch! Danke für eure Teilnahme und euren Sportsgeist bei diesem Turnier. Ihr habt eine tolle Leistung gezeigt!"


def _fetch_logo() -> io.BytesIO | None:
    try:
        import urllib.request
        data = urllib.request.urlopen(LOGO_URL, timeout=5).read()
        buf = io.BytesIO(data)
        buf.seek(0)
        return buf
    except Exception:
        return None


def generate_urkunde_pdf(rankings: list, tournament: models.Tournament) -> bytes:
    """rankings: list of (rank, team, players) tuples sorted by rank."""
    buf = io.BytesIO()
    page_w, page_h = landscape(A4)
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        leftMargin=2*cm, rightMargin=2*cm
    )
    content_w = page_w - 4*cm
    styles = getSampleStyleSheet()
    story = []

    cert_title_style = ParagraphStyle(
        "CertTitle", fontName="Helvetica-Bold", fontSize=12,
        textColor=colors.white, alignment=TA_CENTER, spaceAfter=0, spaceBefore=0, leading=17,
    )
    rank_style = ParagraphStyle(
        "CertRank", fontName="Helvetica-Bold", fontSize=56,
        textColor=FW_RED, alignment=TA_CENTER, leading=62,
    )
    rank_label_style = ParagraphStyle(
        "CertRankLabel", fontName="Helvetica-Bold", fontSize=16,
        textColor=FW_DARK, alignment=TA_CENTER, leading=22,
    )
    team_style = ParagraphStyle(
        "CertTeam", fontName="Helvetica-Bold", fontSize=30,
        textColor=FW_RED, alignment=TA_CENTER, leading=36, spaceAfter=4,
    )
    congrats_style = ParagraphStyle(
        "CertCongrats", fontName="Helvetica", fontSize=10,
        textColor=colors.HexColor("#555555"), alignment=TA_CENTER, leading=15,
    )
    players_label_style = ParagraphStyle(
        "CertPlayersLabel", fontName="Helvetica-Bold", fontSize=9,
        textColor=colors.HexColor("#999999"), alignment=TA_CENTER, leading=13,
        spaceBefore=4,
    )
    player_style = ParagraphStyle(
        "CertPlayer", fontName="Helvetica", fontSize=10,
        textColor=FW_DARK, alignment=TA_CENTER, leading=14,
    )
    footer_style = ParagraphStyle(
        "CertFooter", fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#888888"), alignment=TA_CENTER,
    )
    date_str = tournament.date.strftime("%d.%m.%Y") if tournament.date else ""

    logo_buf = _fetch_logo()

    for i, (rank, team, players) in enumerate(rankings):
        if i > 0:
            story.append(PageBreak())

        accent = RANK_COLORS.get(rank, FW_DARK)

        # Header: logo left, title center, date right
        logo_cell = ""
        if logo_buf:
            logo_buf.seek(0)
            logo_img = Image(logo_buf, width=1.2*cm, height=1.2*cm)
            logo_cell = logo_img
        else:
            logo_cell = Paragraph("", cert_title_style)

        header_inner = Table(
            [[logo_cell,
              Paragraph(f"<b>{tournament.name}</b><br/><font size='9'>Feuerwehr Wolfurt &nbsp;·&nbsp; {date_str}</font>", cert_title_style),
              Paragraph("", cert_title_style)]],
            colWidths=[1.6*cm, content_w - 3.2*cm, 1.6*cm]
        )
        header_inner.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ]))
        header_outer = Table([[header_inner]], colWidths=[content_w])
        header_outer.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), FW_RED),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(header_outer)
        story.append(Spacer(1, 0.6*cm))

        # "URKUNDE" title
        story.append(Paragraph("U R K U N D E", ParagraphStyle(
            "UK", fontName="Helvetica-Bold", fontSize=14,
            textColor=colors.HexColor("#aaaaaa"), alignment=TA_CENTER,
            spaceAfter=2, leading=18, characterSpacing=4,
        )))
        story.append(Paragraph("Blaulicht Völkerball Turnier", ParagraphStyle(
            "UK2", fontName="Helvetica", fontSize=11,
            textColor=FW_DARK, alignment=TA_CENTER, leading=15,
        )))
        story.append(Spacer(1, 0.4*cm))
        story.append(HRFlowable(width="100%", thickness=2, color=accent, spaceAfter=0.4*cm))

        # Rank + Team name
        org_style = ParagraphStyle(
            "CertOrg", fontName="Helvetica", fontSize=13,
            textColor=FW_DARK, alignment=TA_CENTER, leading=17, spaceAfter=2,
        )
        rank_label = RANK_LABELS.get(rank, f"{rank}. Platz")
        rank_block = [Paragraph(str(rank), rank_style), Paragraph(rank_label, rank_label_style)]
        team_block = [Spacer(1, 0.3*cm), Paragraph(team.name, team_style)]
        if getattr(team, "organization", None):
            team_block.append(Paragraph(team.organization, org_style))
        team_block += [
            Spacer(1, 0.2*cm),
            Paragraph(CONGRATS.get(rank, CONGRATS_DEFAULT), congrats_style),
        ]
        layout_table = Table([[rank_block, team_block]], colWidths=[5*cm, content_w - 5*cm])
        layout_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ]))
        story.append(layout_table)

        story.append(HRFlowable(
            width="100%", thickness=1, color=colors.HexColor("#eeeeee"),
            spaceBefore=0.3*cm, spaceAfter=0.3*cm
        ))

        if players:
            story.append(Paragraph("SPIELER", players_label_style))
            story.append(Spacer(1, 0.15*cm))
            player_cols = 3
            rows = []
            row = []
            for p in players:
                nr = f"#{p.jersey_number}  " if p.jersey_number is not None else ""
                row.append(Paragraph(f"{nr}{p.name}", player_style))
                if len(row) == player_cols:
                    rows.append(row)
                    row = []
            if row:
                while len(row) < player_cols:
                    row.append(Paragraph("", player_style))
                rows.append(row)
            if rows:
                col_w = content_w / player_cols
                player_table = Table(rows, colWidths=[col_w] * player_cols)
                player_table.setStyle(TableStyle([
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(player_table)
            story.append(Spacer(1, 0.4*cm))

        story.append(HRFlowable(width="100%", thickness=2, color=accent, spaceAfter=0.3*cm))

        sig_data = [[
            Paragraph("_________________________\nDatum / Unterschrift", footer_style),
            Paragraph("_________________________\nTurnierleiterin", footer_style),
        ]]
        sig_table = Table(sig_data, colWidths=[content_w / 2, content_w / 2])
        sig_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(sig_table)

    if not rankings:
        story.append(Paragraph("Keine Platzierungen vorhanden.", styles["Normal"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()


def generate_all_teams_pdf(teams: list, tournament: models.Tournament, matches_by_team: dict, base_url: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1 * cm, bottomMargin=1.5 * cm,
                            leftMargin=1.5 * cm, rightMargin=1.5 * cm)
    story = []
    for i, team in enumerate(teams):
        if i > 0:
            story.append(PageBreak())
        story.extend(_team_page_story(team, tournament, matches_by_team.get(team.id, []), base_url))
    doc.build(story)
    buf.seek(0)
    return buf.read()


def generate_schedule_pdf(tournament: models.Tournament, matches: list) -> bytes:
    """Generate a full schedule PDF with all matches grouped by round."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1*cm, bottomMargin=1.5*cm,
                            leftMargin=1.5*cm, rightMargin=1.5*cm)
    title_style, heading_style, body_style, _ = _get_styles()
    story = []

    # Header
    header_data = [[Paragraph(
        f"<b>{tournament.name}</b>",
        ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=20, textColor=colors.white, alignment=TA_CENTER)
    )]]
    header_table = Table(header_data, colWidths=[18*cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), FW_RED),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.3*cm))

    date_str = tournament.date.strftime("%d.%m.%Y") if tournament.date else ""
    story.append(Paragraph(f"Spielplan – {date_str}", body_style))
    story.append(Spacer(1, 0.4*cm))

    round_labels = {"prelim": "Vorrunde", "inter": "Zwischenrunde", "placement": "Platzierungsspiele"}
    round_order = ["prelim", "inter", "placement"]

    matches_by_round = {}
    for m in matches:
        key = m.round_type.value if hasattr(m.round_type, "value") else str(m.round_type)
        matches_by_round.setdefault(key, []).append(m)

    for rtype in round_order:
        rmatches = matches_by_round.get(rtype)
        if not rmatches:
            continue

        story.append(Paragraph(round_labels.get(rtype, rtype), heading_style))

        table_data = [["#", "Zeit", "Feld", "Team A", "Ergebnis", "Team B", "Status"]]
        for m in sorted(rmatches, key=lambda x: (x.scheduled_time or 0, x.sequence_number)):
            time_str = m.scheduled_time.strftime("%H:%M") if m.scheduled_time else "–"
            name_a = m.team_a.name if m.team_a else (m.team_a_placeholder or "?")
            name_b = m.team_b.name if m.team_b else (m.team_b_placeholder or "?")

            if m.score_a is not None and m.score_b is not None:
                if m.players_remaining_a is not None:
                    score_str = f"{m.players_remaining_a} : {m.players_remaining_b}\nSpieler"
                else:
                    score_str = f"{m.score_a} : {m.score_b}"
            else:
                score_str = "–"

            status_map = {"pending": "Ausstehend", "active": "Läuft", "finished": "Beendet"}
            status_str = status_map.get(m.status.value if hasattr(m.status, "value") else str(m.status), "–")

            table_data.append([
                str(m.sequence_number),
                time_str,
                str(m.field_number),
                name_a,
                score_str,
                name_b,
                status_str,
            ])

        col_widths = [1*cm, 1.6*cm, 1.2*cm, 4.2*cm, 2.4*cm, 4.2*cm, 2.4*cm]
        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FW_RED),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FW_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (0, 0), (2, -1), "CENTER"),
            ("ALIGN", (4, 0), (4, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.6*cm))

    if not matches:
        story.append(Paragraph("Noch kein Spielplan generiert.", body_style))

    doc.build(story)
    buf.seek(0)
    return buf.read()
