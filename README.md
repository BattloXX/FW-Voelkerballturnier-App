# Blaulicht Völkerball Turnier-Manager
### Feuerwehr Wolfurt

Vollständige Turnierverwaltungs-Webapp für das Blaulicht Völkerballturnier der Feuerwehr Wolfurt.  
Entwickelt mit FastAPI, MariaDB und Jinja2-Templates – optimiert für Tablets und Smartphones.

---

## Funktionsübersicht

| Bereich | Zugang | Beschreibung |
|---|---|---|
| **Startseite** | Öffentlich | Übersicht aller Turniere mit Status |
| **Spielplan** | Öffentlich | Live-Spielplan aller Runden mit automatischer Aktualisierung alle 30 Sekunden |
| **Rangliste** | Öffentlich | Endrangliste, Zwischenrunden- und Vorrunden-Tabellen pro Feld |
| **Spielregeln** | Öffentlich | Formatierte Spielregeln (Markdown) |
| **Team-Seite** | QR-Code + PIN | Teams sehen Spielplan, aktuelle Platzierung und tragen ihre Spielerliste ein (einmalig, danach gesperrt) |
| **Infoscreen** | Öffentlich | Vollbild-Anzeige für TV/Beamer mit Live-Rangliste, laufenden Spielen und Ergebnissen (30s Auto-Refresh) |
| **Schiedsrichter** | Login | Ergebniseingabe per Tablet, große Touch-freundliche Buttons |
| **Administration** | Login | Vollständige Turnierverwaltung inkl. Rangliste, editierbarem Spielplan und PDF-Export |

---

## Installation

### Voraussetzungen
- Python 3.11+
- MariaDB (läuft bereits auf dem Server)
- Nginx (läuft bereits, z.B. via CloudPanel)

### 1. Dateien hochladen

```bash
git clone https://github.com/BattloXX/FW-Voelkerballturnier-App.git .
```

### 2. Python-Umgebung einrichten

```bash
cd /home/fwwo-voelkerball/htdocs/voelkerball.fwwo.at

su - fwwo-voelkerball -s /bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
exit
```

### 3. Datenbank anlegen

```sql
CREATE DATABASE voelkerball_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'voelkerball'@'localhost' IDENTIFIED BY 'sicheres-passwort';
GRANT ALL PRIVILEGES ON voelkerball_db.* TO 'voelkerball'@'localhost';
```

### 4. Umgebungsvariablen konfigurieren

```bash
cp .env.example .env
nano .env
```

```env
DATABASE_URL=mysql+pymysql://voelkerball:sicheres-passwort@localhost/voelkerball_db
SECRET_KEY=langer-zufaelliger-schluessel
BASE_URL=https://voelkerball.fwwo.at
```

### 5. Systemd-Service installieren

```bash
cp voelkerball.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable voelkerball
systemctl start voelkerball
systemctl status voelkerball
```

### 6. Nginx konfigurieren (CloudPanel Vhost)

Im CloudPanel unter **Sites → voelkerball.fwwo.at → Vhost** den `location /`-Block auf Port `8091` umleiten und einen `/static/`-Block für direkte Dateiauslieferung hinzufügen.

---

## Erster Start

Beim ersten Start wird automatisch ein Superadmin-Account angelegt:

| Benutzername | Passwort |
|---|---|
| `admin` | `admin123` |

**Passwort sofort unter `/admin/benutzer` ändern!**

> Neue Datenbankspalten werden beim Start automatisch per `ALTER TABLE` ergänzt – kein manuelles Schema-Update nötig.

---

## URLs

### Öffentliche Seiten
| URL | Beschreibung |
|---|---|
| `/` | Startseite – alle Turniere |
| `/turnier/<slug>` | Turnier-Übersicht |
| `/turnier/<slug>/spielplan` | Spielplan aller Runden (Live-Updates) |
| `/turnier/<slug>/rangliste` | Rangliste – Endrangliste, Zwischenrunde, Vorrunde |
| `/turnier/<slug>/regeln` | Spielregeln |
| `/turnier/<slug>/team/<id>?pin=<pin>` | Team-Selbstverwaltung via QR-Code oder Header-Login |
| `/infoscreen` | Infoscreen (leitet zum ersten aktiven Turnier weiter) |
| `/infoscreen/<slug>` | Vollbild-Infoscreen für TV/Beamer |
| `/api/infoscreen/<slug>` | JSON-API für Infoscreen-Polling |

### Schiedsrichter
| URL | Beschreibung |
|---|---|
| `/schiri/login` | Schiedsrichter-Login |
| `/schiri/dashboard` | Turnier- und Feldauswahl |
| `/schiri/turnier/<slug>/feld/<n>` | Ergebniseingabe für Feld n |

### Administration
| URL | Beschreibung |
|---|---|
| `/admin/login` | Admin-Login |
| `/admin/dashboard` | Übersicht aller Turniere |
| `/admin/turnier/neu` | Neues Turnier erstellen |
| `/admin/turnier/<id>` | Turnier verwalten (Teams, Spielplan) |
| `/admin/turnier/<id>/spielplan` | Spielplan bearbeiten & Ergebnisse korrigieren |
| `/admin/turnier/<id>/spielplan/pdf` | Spielplan als PDF exportieren |
| `/admin/turnier/<id>/rangliste` | Rangliste aller Runden mit Korrekturmöglichkeit |
| `/admin/turnier/<id>/team/<team_id>/spieler` | Spielerliste eines Teams bearbeiten (Admin) |
| `/admin/turnier/<id>/pdf/alle` | Alle Team-PDFs als Sammel-PDF |
| `/admin/turnier/<id>/urkunden` | Urkunden-PDF für alle Teilnehmer |
| `/infoscreen/<slug>` | Vollbild-Infoscreen (auch direkt verknüpft im Admin) |
| `/admin/benutzer` | Benutzerverwaltung (nur Superadmin) |

---

## Turnierdurchführung – Ablauf

### Vorbereitung (vor dem Turnier)
1. **Admin-Login** → Neues Turnier erstellen (Startzeiten, Spielzeiten, Punkteregeln konfigurieren)
2. **Teams anlegen** → Name, Organisation (z.B. „FF Dornbirn") und Feld-Gruppe eingeben; PIN wird automatisch generiert
3. **Spielplan generieren** → Button „Spielplan generieren"
4. **Team-PDFs drucken** → Pro Team ein A4-Blatt mit QR-Code, PIN, Team-ID und Spielplan (`/admin/turnier/<id>/pdf/alle`)
5. Teams tragen ihre **Spielerliste** (bis zu 10 Spieler mit Name und Trikotnummer) einmalig über die Team-Seite ein. Nach dem Einreichen ist die Liste gesperrt; nur Admins können sie noch ändern.

### Während des Turniers
1. **Schiedsrichter** melden sich über den **„Schiedsrichter"**-Button im Footer an
2. Feld auswählen → Spiel starten → verbleibende Spieler am Ende eingeben
3. **Infoscreen** für TV/Beamer: `/infoscreen` – aktualisiert sich automatisch alle 30 Sekunden
4. Die **Rangliste** aktualisiert sich live – Aufstiegsplätze werden grün markiert

### Nach der Vorrunde
1. Admin-Bereich → **Spielplan** → Button **„⚡ Teams einsetzen"**
2. Zwischenrunden- und Platzierungsspiele werden automatisch mit den richtigen Teams aus der Vorrunden-Tabelle befüllt
3. Weiter wie gewohnt: Schiedsrichter geben Ergebnisse ein

### Nach dem Turnier
1. **Urkunden drucken** → `/admin/turnier/<id>/urkunden`
2. Jedes Team erhält eine Urkunde im Querformat mit Platzierung, Teamname, Organisation, Spielerliste, Glückwunsch-Text, Feuerwehr-Logo und Unterschriftszeilen

---

## Spielplan-Logik

### Vorrunde
- Jeder gegen jeden innerhalb der Feldgruppe (Round-Robin)
- Mehrere Felder spielen gleichzeitig in parallelen Zeitslots

### Zwischenrunde (Kreuzpaarungen)
- Gruppe Zw.1: Platz 1, 3, 5 von Feld 1 + Platz 2, 4, 6 von Feld 2
- Gruppe Zw.2: Platz 2, 4, 6 von Feld 1 + Platz 1, 3, 5 von Feld 2
- Wieder Round-Robin innerhalb der Zwischenrunden-Gruppe
- Nur bei mehr als einem aktiven Feld

### Platzierungsspiele
- 1. Zw.1 vs 1. Zw.2 → Finale (Platz 1/2)
- 2. Zw.1 vs 2. Zw.2 → Spiel um Platz 3/4
- usw.

### Startzeiten
- Können fix hinterlegt werden (Felder `Startzeit Zwischenrunde` / `Startzeit Platzierung` im Turnier-Formular)
- Alternativ: automatische Berechnung über konfigurierbare Pausenzeiten

### Wertung
- **3 Punkte** für Sieg (Team mit mehr Spielern am Feld bei Spielende)
- **1 Punkt** pro Team bei Unentschieden (gleich viele Spieler)
- **0 Punkte** für Niederlage
- Tiebreaker: Spieler-Differenz (mehr übrige Spieler = besser)
- Punktewerte sind pro Turnier konfigurierbar

---

## Team-Login im Header

Auf jeder öffentlichen Seite gibt es den **„👥 Team"**-Button im Header:

- Dropdown mit allen Teams des aktiven Turniers – kein Eintippen einer ID nötig
- PIN eingeben → direkt zur eigenen Team-Seite
- Alternativ: QR-Code vom Team-PDF scannen (öffnet die Seite direkt)

Die Team-ID ist zusätzlich auf dem PDF-Ausdruck vermerkt (für manuelle Eingabe, falls kein Dropdown verfügbar ist).

---

## Spielerliste (einmalige Eingabe)

- Teams tragen bis zu **10 Spieler** (Name + Trikotnummer) einmalig über ihre Team-Seite ein
- Vor dem Speichern muss per Checkbox bestätigt werden, dass die Liste vollständig ist
- Nach dem Einreichen ist die Liste **gesperrt** – das Team kann sie nicht mehr ändern
- **Admin kann Spieler jederzeit bearbeiten** und die Sperre aufheben oder neu setzen: `/admin/turnier/<id>/team/<team_id>/spieler`
- In der Admin-Übersicht zeigt ein Symbol den Status: 🔒 = gesperrt, 📋 = eingetragen (offen), — = noch keine Spieler

---

## Organisation / Verein

- Wird beim **Anlegen eines Teams** im Admin direkt mitgepflegt (z.B. „FF Lauterach")
- Kann jederzeit in der Team-Tabelle des Admins geändert werden (inline, Enter zum Speichern)
- Erscheint in der Team-Seite im Header, in Spielplan- und Ranglisten-Tabellen als kleiner Hinweis sowie auf der **Urkunde** unterhalb des Teamnamens

---

## Spielplan editieren (Admin)

Im Admin-Spielplan (`/admin/turnier/<id>/spielplan`) kann jedes Spiel über den ✏️-Button bearbeitet werden:

- **Uhrzeit** – geplante Anstoßzeit anpassen
- **Feld** – Spielfeld ändern
- **Runde** – zwischen Vorrunde, Zwischenrunde und Platzierungsspielen wechseln
- **Teams** – Team A oder Team B austauschen

Ergebnisse können direkt in der Spielplan-Zeile korrigiert werden: verbleibende Spieler beider Teams eingeben, Score wird automatisch berechnet.

---

## Rangliste (Admin)

Die Admin-Rangliste (`/admin/turnier/<id>/rangliste`) zeigt:

- Tabellen für alle Runden (Vorrunde pro Feld, Zwischenrunde, Platzierungsspiele)
- Aufstiegsmarkierung (grün = qualifiziert, rot = ausgeschieden)
- Vollständige Spielliste mit Inline-Korrektur-Modal pro Spiel

---

## Infoscreen (TV/Beamer)

Die Seite `/infoscreen/<slug>` ist als Vollbild-Großbildschirm-Anzeige ausgelegt:

- **Drei Spalten:** Rangliste (links) · Laufende Spiele + Nächste Spiele (Mitte) · Letzte Ergebnisse (rechts)
- **Live-Uhr** und LIVE-Indikator im roten Header
- **Automatische Aktualisierung** alle 30 Sekunden via AJAX
- Organisation wird unter dem Teamnamen angezeigt
- Kein Login nötig – `/infoscreen` leitet automatisch auf das aktive Turnier weiter
- Direktlink im Admin-Panel unter jedem Turnier (📺 Infoscreen)

---

## PDF-Ausgaben

### Spielplan-PDF
- Alle Runden auf einen Blick (Vorrunde, Zwischenrunde, Platzierungsspiele)
- A4, druckfertig mit Ergebnissen und Status

### Team-Ausdruck (vor dem Turnier)
- Ein A4-Blatt pro Team – sauberes 2-spaltiges Layout
- **Links:** Teamname (groß), Organisation, Datum, Feld, PIN (groß, rot)
- **Rechts:** QR-Code (5,5 cm), Team-ID zur manuellen Eingabe
- Darunter: eigener Spielplan als Tabelle
- Sammel-PDF aller Teams: `/admin/turnier/<id>/pdf/alle`

### Urkunden (nach dem Turnier)
- Querformat A4, eine Seite pro Team
- Enthält: Feuerwehr-Logo, Turniername, Datum, Platzierung (🥇🥈🥉), Teamname, Organisation, Spielerliste mit Trikotnummern, individueller Glückwunsch-Text, Unterschriftszeilen
- Alle teilnehmenden Teams erhalten eine Urkunde

---

## Logs & Fehlerbehebung

```bash
# Service-Status
systemctl status voelkerball

# Live-Logs
journalctl -u voelkerball -f

# Service neu starten
systemctl restart voelkerball
```

### Häufige Probleme

**Neue Datenbankspalten nach Update:**  
Neue Spalten werden beim App-Start automatisch per `ALTER TABLE` ergänzt (idempotent, schlägt bei bereits vorhandener Spalte lautlos fehl). Kein manuelles Eingreifen nötig.

**Punktesystem bei bestehenden Turnieren:**  
Bestehende Turniere können die alten Punktewerte haben. Unter `/admin/turnier/<id>/bearbeiten` auf 3 / 1 / 0 aktualisieren.

**bcrypt-Kompatibilität:**  
`bcrypt==4.0.1` ist in `requirements.txt` fixiert. Nicht auf neuere Versionen updaten, solange passlib 1.7.4 verwendet wird.

---

## Technischer Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.x
- **Datenbank:** MariaDB (mysql+pymysql)
- **Frontend:** Jinja2-Templates, Vanilla JavaScript (Live-Polling alle 30 s)
- **PDF:** ReportLab + qrcode
- **Auth:** JWT (PyJWT), bcrypt (passlib)
- **Server:** Uvicorn hinter Nginx (CloudPanel)
- **Fonts:** Oswald + Source Sans 3 (Google Fonts)
