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


def generate_team_pdf(team: models.Team, tournament: models.Tournament, matches: list, base_url: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1*cm, bottomMargin=1.5*cm,
                            leftMargin=1.5*cm, rightMargin=1.5*cm)
    title_style, heading_style, body_style, pin_style = _get_styles()
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
    story.append(Spacer(1, 0.5*cm))

    # Team info
    from datetime import datetime
    date_str = tournament.date.strftime("%d.%m.%Y") if tournament.date else ""
    story.append(Paragraph(f"Datum: {date_str}", body_style))
    story.append(Paragraph(f"<b>Team:</b> {team.name}", heading_style))
    story.append(Paragraph(f"Gruppe: Feld {team.field_group}", body_style))
    story.append(Spacer(1, 0.3*cm))

    story.append(Paragraph("Ihr PIN:", body_style))
    story.append(Paragraph(team.pin, pin_style))
    story.append(Spacer(1, 0.3*cm))

    # QR Code
    url = f"{base_url}/turnier/{tournament.slug}/team/{team.id}?pin={team.pin}"
    qr_buf = _make_qr(url)
    qr_img = Image(qr_buf, width=4*cm, height=4*cm)
    qr_table = Table([[qr_img, Paragraph(
        f"Scannen Sie den QR-Code, um Ihren<br/>Spielplan einzusehen und Ihren<br/>Teamnamen zu ändern.<br/><br/>"
        f"<font size='8'>{url}</font>",
        body_style
    )]], colWidths=[4.5*cm, 13.5*cm])
    qr_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(qr_table)
    story.append(Spacer(1, 0.5*cm))

    # Schedule
    story.append(Paragraph("Euer Spielplan", heading_style))

    if matches:
        table_data = [["Zeit", "Feld", "Gegner"]]
        for m in matches:
            time_str = m.scheduled_time.strftime("%H:%M") if m.scheduled_time else "-"
            if m.team_a_id == team.id:
                opponent = m.team_b.name if m.team_b else (m.team_b_placeholder or "?")
            else:
                opponent = m.team_a.name if m.team_a else (m.team_a_placeholder or "?")
            table_data.append([time_str, str(m.field_number), opponent])

        t = Table(table_data, colWidths=[3*cm, 3*cm, 12*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FW_RED),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FW_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("Noch kein Spielplan generiert.", body_style))

    doc.build(story)
    buf.seek(0)
    return buf.read()


RANK_LABELS = {1: "1. Platz", 2: "2. Platz", 3: "3. Platz"}
RANK_COLORS = {
    1: colors.HexColor("#FFD700"),
    2: colors.HexColor("#C0C0C0"),
    3: colors.HexColor("#CD7F32"),
}


def generate_urkunde_pdf(rankings: list, tournament: models.Tournament) -> bytes:
    """rankings: list of (rank, team, players) tuples sorted by rank."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(A4),
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        leftMargin=2*cm, rightMargin=2*cm
    )
    styles = getSampleStyleSheet()
    story = []

    cert_title_style = ParagraphStyle(
        "CertTitle", fontName="Helvetica-Bold", fontSize=13,
        textColor=colors.white, alignment=TA_CENTER, spaceAfter=0, spaceBefore=0, leading=18,
    )
    rank_style = ParagraphStyle(
        "CertRank", fontName="Helvetica-Bold", fontSize=52,
        textColor=FW_RED, alignment=TA_CENTER, leading=60,
    )
    rank_label_style = ParagraphStyle(
        "CertRankLabel", fontName="Helvetica-Bold", fontSize=18,
        textColor=FW_DARK, alignment=TA_CENTER, leading=24,
    )
    team_style = ParagraphStyle(
        "CertTeam", fontName="Helvetica-Bold", fontSize=28,
        textColor=FW_RED, alignment=TA_CENTER, leading=34, spaceAfter=6,
    )
    players_label_style = ParagraphStyle(
        "CertPlayersLabel", fontName="Helvetica-Bold", fontSize=10,
        textColor=colors.HexColor("#888888"), alignment=TA_CENTER, leading=14,
    )
    player_style = ParagraphStyle(
        "CertPlayer", fontName="Helvetica", fontSize=11,
        textColor=FW_DARK, alignment=TA_CENTER, leading=15,
    )
    footer_style = ParagraphStyle(
        "CertFooter", fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#888888"), alignment=TA_CENTER,
    )
    date_str = tournament.date.strftime("%d.%m.%Y") if tournament.date else ""

    for i, (rank, team, players) in enumerate(rankings):
        if i > 0:
            story.append(PageBreak())

        accent = RANK_COLORS.get(rank, FW_DARK)

        header_data = [[Paragraph(
            f"<b>{tournament.name}</b> &nbsp;·&nbsp; {date_str} &nbsp;·&nbsp; Feuerwehr Wolfurt",
            cert_title_style
        )]]
        header_table = Table(header_data, colWidths=[25.7*cm])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), FW_RED),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.8*cm))

        story.append(Paragraph("URKUNDE", ParagraphStyle(
            "UK", fontName="Helvetica-Bold", fontSize=16,
            textColor=colors.HexColor("#888888"), alignment=TA_CENTER, spaceAfter=4, leading=20,
        )))
        story.append(Paragraph("Blaulicht Völkerball Turnier", ParagraphStyle(
            "UK2", fontName="Helvetica", fontSize=12,
            textColor=FW_DARK, alignment=TA_CENTER, leading=16,
        )))
        story.append(Spacer(1, 0.5*cm))
        story.append(HRFlowable(width="100%", thickness=2, color=accent, spaceAfter=0.5*cm))

        rank_label = RANK_LABELS.get(rank, f"{rank}. Platz")
        rank_cell = [[Paragraph(str(rank), rank_style)], [Paragraph(rank_label, rank_label_style)]]
        team_cell = [[Spacer(1, 0.4*cm)], [Paragraph(team.name, team_style)]]

        layout_table = Table([[rank_cell, team_cell]], colWidths=[5*cm, 20.7*cm])
        layout_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ]))
        story.append(layout_table)
        story.append(HRFlowable(
            width="100%", thickness=1, color=colors.HexColor("#eeeeee"),
            spaceBefore=0.4*cm, spaceAfter=0.4*cm
        ))

        if players:
            story.append(Paragraph("Spieler", players_label_style))
            story.append(Spacer(1, 0.2*cm))
            player_cols = 3
            rows = []
            row = []
            for p in players:
                nr = f"#{p.jersey_number} " if p.jersey_number is not None else ""
                row.append(Paragraph(f"{nr}{p.name}", player_style))
                if len(row) == player_cols:
                    rows.append(row)
                    row = []
            if row:
                while len(row) < player_cols:
                    row.append(Paragraph("", player_style))
                rows.append(row)
            if rows:
                col_w = 25.7 / player_cols
                player_table = Table(rows, colWidths=[col_w*cm] * player_cols)
                player_table.setStyle(TableStyle([
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]))
                story.append(player_table)

        story.append(Spacer(1, 0.6*cm))
        story.append(HRFlowable(width="100%", thickness=2, color=accent, spaceAfter=0.3*cm))

        sig_data = [[
            Paragraph("_________________________\nDatum / Unterschrift", footer_style),
            Paragraph("_________________________\nTurnierleiterin", footer_style),
        ]]
        sig_table = Table(sig_data, colWidths=[12.85*cm, 12.85*cm])
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
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1*cm, bottomMargin=1.5*cm,
                            leftMargin=1.5*cm, rightMargin=1.5*cm)
    title_style, heading_style, body_style, pin_style = _get_styles()
    story = []

    for i, team in enumerate(teams):
        if i > 0:
            from reportlab.platypus import PageBreak
            story.append(PageBreak())

        matches = matches_by_team.get(team.id, [])

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
        story.append(Spacer(1, 0.5*cm))

        date_str = tournament.date.strftime("%d.%m.%Y") if tournament.date else ""
        story.append(Paragraph(f"Datum: {date_str}", body_style))
        story.append(Paragraph(f"<b>Team:</b> {team.name}", heading_style))
        story.append(Paragraph(f"Gruppe: Feld {team.field_group}", body_style))
        story.append(Spacer(1, 0.3*cm))

        story.append(Paragraph("Ihr PIN:", body_style))
        story.append(Paragraph(team.pin, pin_style))
        story.append(Spacer(1, 0.3*cm))

        url = f"{base_url}/turnier/{tournament.slug}/team/{team.id}?pin={team.pin}"
        qr_buf = _make_qr(url)
        qr_img = Image(qr_buf, width=4*cm, height=4*cm)
        qr_table = Table([[qr_img, Paragraph(
            f"Scannen Sie den QR-Code für Ihren Spielplan.<br/><br/>"
            f"<font size='8'>{url}</font>",
            body_style
        )]], colWidths=[4.5*cm, 13.5*cm])
        qr_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(qr_table)
        story.append(Spacer(1, 0.5*cm))

        story.append(Paragraph("Euer Spielplan", heading_style))
        if matches:
            table_data = [["Zeit", "Feld", "Gegner"]]
            for m in matches:
                time_str = m.scheduled_time.strftime("%H:%M") if m.scheduled_time else "-"
                if m.team_a_id == team.id:
                    opponent = m.team_b.name if m.team_b else (m.team_b_placeholder or "?")
                else:
                    opponent = m.team_a.name if m.team_a else (m.team_a_placeholder or "?")
                table_data.append([time_str, str(m.field_number), opponent])
            t = Table(table_data, colWidths=[3*cm, 3*cm, 12*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), FW_RED),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, FW_LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(t)
        else:
            story.append(Paragraph("Noch kein Spielplan generiert.", body_style))

    doc.build(story)
    buf.seek(0)
    return buf.read()
