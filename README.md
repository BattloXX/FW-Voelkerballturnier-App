# Blaulicht Völkerball Turnier-Manager
### Feuerwehr Wolfurt

Vollständige Turnierverwaltungs-Webapp für das Blaulicht Völkerballturnier der Feuerwehr Wolfurt.  
Entwickelt mit FastAPI, MariaDB und Jinja2-Templates – optimiert für Tablets und Smartphones.

---

## Funktionsübersicht

| Bereich | Zugang | Beschreibung |
|---|---|---|
| **Startseite** | Öffentlich | Übersicht aller Turniere mit Status |
| **Spielplan** | Öffentlich | Live-Spielplan mit automatischer Aktualisierung alle 30 Sekunden |
| **Rangliste** | Öffentlich | Tabellenstände mit Aufstiegs-/Abstiegsmarkierung |
| **Spielregeln** | Öffentlich | Formatierte Spielregeln (Markdown) |
| **Team-Seite** | QR-Code + PIN | Teams sehen ihren Spielplan, können Teamnamen ändern |
| **Schiedsrichter** | Login | Ergebniseingabe per Tablet, große Buttons |
| **Administration** | Login | Vollständige Turnierverwaltung |

---

## Installation

### Voraussetzungen
- Python 3.11+
- MariaDB (läuft bereits auf dem Server)
- Nginx (läuft bereits, z.B. via CloudPanel)

### 1. Dateien hochladen

```bash
# Dateien nach /home/fwwo-voelkerball/htdocs/voelkerball.fwwo.at/ hochladen
# z.B. via SFTP oder git clone
```

### 2. Python-Umgebung einrichten

```bash
cd /home/fwwo-voelkerball/htdocs/voelkerball.fwwo.at

# Als Site-User ausführen:
su - fwwo-voelkerball -s /bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
exit
```

### 3. Datenbank anlegen (in CloudPanel UI oder per CLI)

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

Folgende Werte anpassen:

```env
DATABASE_URL=mysql+pymysql://voelkerball:sicheres-passwort@localhost/voelkerball_db
SECRET_KEY=langer-zufaelliger-schluessel
BASE_URL=https://voelkerball.fwwo.at
```

### 5. Systemd-Service installieren

```bash
# Als root:
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

---

## URLs

### Öffentliche Seiten
| URL | Beschreibung |
|---|---|
| `/` | Startseite – alle Turniere |
| `/turnier/<slug>` | Turnier-Übersicht |
| `/turnier/<slug>/spielplan` | Spielplan (Live-Updates) |
| `/turnier/<slug>/rangliste` | Rangliste |
| `/turnier/<slug>/regeln` | Spielregeln |
| `/turnier/<slug>/team/<id>?pin=<pin>` | Team-Selbstverwaltung via QR-Code |

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
| `/admin/turnier/<id>/spielplan` | Spielplan-Verwaltung & Ergebniskorrektur |
| `/admin/benutzer` | Benutzerverwaltung (nur Superadmin) |

---

## Turnierdurchführung – Ablauf

### Vorbereitung (vor dem Turnier)
1. **Admin-Login** → Neues Turnier erstellen
2. **Teams anlegen** → Name + Feld-Gruppe zuweisen (PIN wird automatisch generiert)
3. **Spielplan generieren** → Button „Spielplan generieren"
4. **Team-PDFs drucken** → Pro Team ein A4-Blatt mit QR-Code, PIN und eigenem Spielplan

### Während des Turniers
1. **Schiedsrichter** melden sich unter `/schiri/login` an
2. Feld auswählen → nächstes Spiel starten → Ergebnis (verbleibende Spieler) eingeben
3. **Live-Anzeige** auf Beamer oder öffentlichem Bildschirm: `/turnier/<slug>/spielplan`

### Nach der Vorrunde
1. Admin-Bereich → **Spielplan** → Button **„⚡ Teams einsetzen"**
2. Die Zwischenrunden- und Platzierungsspiele werden automatisch mit den richtigen Teams aus der Vorrunden-Tabelle befüllt

---

## Spielplan-Logik

### Vorrunde
- Jeder gegen jeden innerhalb der Feldgruppe (Round-Robin)
- Mehrere Felder spielen gleichzeitig (parallele Zeitslots)

### Zwischenrunde (Kreuzpaarungen)
- Gruppe Zw.1: Platz 1, 3, 5 von Feld 1 + Platz 2, 4, 6 von Feld 2
- Gruppe Zw.2: Platz 2, 4, 6 von Feld 1 + Platz 1, 3, 5 von Feld 2
- Wieder Round-Robin innerhalb der Zwischenrunden-Gruppe

### Platzierungsspiele
- 1. Zw.1 vs 1. Zw.2 → Finale (Platz 1/2)
- 2. Zw.1 vs 2. Zw.2 → Spiel um Platz 3/4
- usw.

### Wertung
- **2 Punkte** für Sieg, **1 Punkt** für Niederlage (konfigurierbar)
- Tiebreaker: Spieler-Differenz (abgeschossene Spieler)

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

---

## Technischer Stack

- **Backend:** Python 3.11, FastAPI, SQLAlchemy 2.x
- **Datenbank:** MariaDB
- **Frontend:** Jinja2-Templates, Vanilla JavaScript
- **PDF:** ReportLab + qrcode
- **Auth:** JWT (PyJWT), bcrypt (passlib)
- **Server:** Uvicorn hinter Nginx (CloudPanel)
