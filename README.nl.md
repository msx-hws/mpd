# MSX Pico DEVserver

[![Language: English](https://img.shields.io/badge/Language-English-blue.svg)](README.md)

*Lees deze documentatie in het Engels: [English](README.md).*

**MSX Pico DEVserver** (`mpd`) is een lichtgewicht lokale ontwikkel- & ROM/COM/DSK server om MSX ROM-, COM- en DSK-bestanden direct via Wi-Fi te serveren aan je **MSX Pico** (of compatibele flash cartridge), én te beheren via een moderne retro-webinterface en developer REST API.

![MSX ROM Server Interface](docs/images/msx_flask_ui.png)

---

## 💡 Wat is dit en hoe werkt het?

- **Voor je MSX Pico:** Je MSX Pico cartridge haalt spellen direct via het netwerk binnen. Je hoeft je SD-kaart dus niet steeds in je computer te steken om nieuwe games te proberen.
- **Wat is een API?** Een API (*Application Programming Interface*) is een digitale doorgeefluik waarmee apparaten en programma's met deze server kunnen praten. Zowel de MSX Pico als externe scripts gebruiken deze API om bestanden op te vragen, te downloaden of te uploaden.
- **Wat is Docker?** Docker zorgt ervoor dat de server in een kant-en-klaar geïsoleerd pakketje ("container") draait, inclusief alle benodigde programma's en Python-onderdelen. Je hoeft zelf niets ingewikkelds te installeren of te configureren; met één commando draait alles direct.

---

## ⚡ Belangrijkste Functies

- **Retro Cyberpunk Design:** Volledig responsive webinterface met donkere modus, CRT scanline overlay en Share Tech Mono terminal-look.
- **Automatische ROM Padding:** De MSX Pico vereist dat `.rom` bestanden minimaal `0x1000` (4096 bytes) groot zijn. De server vult kleinere bestanden tijdens het downloaden automatisch aan met null-bytes. De originele bestanden op de server blijven onaangetast!
- **Web Bestandsbeheer:** Upload, hernoem, download en verwijder spellen eenvoudig via je browser via de `/manage` pagina.
- **Interactieve API Documentatie (Swagger):** Bekijk en test alle API-functies direct via de ingebouwde Swagger UI op `/docs` of `/swagger`.

---

## 🕹️ Stap-voor-stap: MSX Pico instellen met `URL.TXT`

Om je MSX Pico verbinding te laten maken met deze server, moet de cartridge weten naar welk adres hij moet zoeken. Dit stel je in via een tekstbestandje genaamd `URL.TXT` op de micro-SD-kaart van je Pico.

Volg deze stappen exact:

### Stap 1: Sluit de SD-kaart aan op je computer
Plaats de micro-SD-kaart van je MSX Pico in je computer of kaartlezer.

### Stap 2: Open of maak de map `FH_FILES`
Open de SD-kaart in je Verkenner (Windows) of Finder (Mac).
- Kijk in de hoofdmap (root) van de SD-kaart.
- Zorg dat er een map staat met de naam:
  ```text
  FH_FILES
  ```
  *(Als deze map nog niet bestaat, maak deze dan nieuw aan met hoofdletters).*

### Stap 3: Maak het bestand `URL.TXT`
1. Open de map `FH_FILES`.
2. Maak hierin een nieuw tekstbestand aan met de naam **`URL.TXT`** (let op de `.txt` extensie en hoofdletters).
3. Open dit bestand met Kladblok (Notepad), TextEdit of een willekeurige code-editor.
4. Typ **uitsluitend** het HTTP-adres van je server, inclusief `http://` en een afsluitende schuine streep (`/`).

   **Voorbeeld:**
   ```text
   http://192.168.1.150/
   ```
   *(Vervang `192.168.1.150` door het IP-adres van de computer/server waarop deze software draait).*

> [!IMPORTANT]
> **Belangrijke regels voor `URL.TXT`:**
> - **Verplicht Poort 80 (HTTP):** De MSX Pico firmware verwacht standaard poort **80** (`http://`). De Pico kan **geen aangepaste poortnummers** (zoals `:8080`) aan in de URL. Als je de poort van de server aanpast naar iets anders dan 80, kan de MSX Pico er **niet** meer bij!
> - **Geen HTTPS:** Gebruik altijd `http://` en **nooit** `https://` (MSX hardware ondersteunt geen moderne encryptie).
> - **Afsluitende slash:** Sluit het adres altijd af met een slash (`/`), dus `http://192.168.1.150/`.
> - **Geen spaties of extra regels:** Plaats geen spaties voor of na de link en druk niet op Enter voor lege regels.
> - **Pas op voor dubbele extensies:** Let op in Windows dat het bestand niet stiekem `URL.TXT.txt` heet.

### Stap 4: Plaats de SD-kaart terug in je MSX Pico
Ontkoppel de SD-kaart veilig, steek hem in de MSX Pico cartridge en zet je MSX aan. Als de Pico en je computer met hetzelfde Wi-Fi-netwerk zijn verbonden, verschijnt je spellenlijst direct op het scherm!

---

## 🚀 Server Opstarten met Docker

Docker is de snelste en makkelijkste manier om de server te draaien.

### Wat heb je nodig?
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (geïnstalleerd en geopend op je pc of Mac).

### Installatie in 3 stappen:
1. **Download of kloon deze repository:**
   ```bash
   git clone https://github.com/msx-hws/mpd.git
   cd mpd
   ```
2. **Kopieer het configuratiebestand:**
   ```bash
   cp .env.example .env
   ```
   *(Standaard staat `HOST_PORT=80` ingesteld. **Laat dit op poort 80 staan**, want de MSX Pico kan alleen verbinding maken via poort 80 en ondersteunt geen aangepaste poorten!).*

   Bij Docker Desktop moet je ook `HOST_IP` in `.env` invullen met het LAN-IPv4-adres van je pc of Mac. Docker Desktop kan dit adres niet betrouwbaar vanuit de container detecteren.
3. **Start de server:**
   ```bash
   docker compose up -d
   ```
   *(De Tailwind CSS wordt tijdens de image-build gecompileerd; geen extra stap nodig. Na wijzigingen aan templates of CSS: `docker compose up -d --build`.)*

Klaar! Open nu in je browser:
- Webinterface: `http://localhost/` (of het lokale IP van je server)
- Bestandsbeheer: `http://localhost/manage`
- **Swagger API Documentatie:** `http://localhost/docs` (of `http://localhost/swagger`)

---

## 📖 API & Swagger Documentatie

De server beschikt over een complete REST API voor het automatiseren en beheren van bestanden:
- **`GET /api/files`** — Overzicht van alle bestanden en mappen (JSON).
- **`POST /api/upload`** — Nieuw bestand uploaden (multipart form-data).
- **`GET /api/download/<pad>`** — Bestand downloaden.
- **`DELETE /api/delete`** — Bestand of map verwijderen.
- **`GET /index2.php`** — De legacy MSX directory-listing en download interface.

👉 **Interactief testen:** Ga in je browser naar [`/docs`](http://localhost:5001/docs) of [`/swagger`](http://localhost:5001/swagger) om de ingebouwde **Swagger UI** te openen. Hier kun je live requests versturen en zien hoe de API reageert. De OpenAPI 3.0 specificatie vind je ook als bestand in [`docs/openapi.yaml`](docs/openapi.yaml).

---

## 🔧 Problemen Oplossen (Troubleshooting)

Lukt het verbinden niet, geeft Docker een foutmelding of start een spel niet? 
Bekijk dan onze uitgebreide storingsgids:

👉 **[docs/TROUBLESHOOTING.nl.md](docs/TROUBLESHOOTING.nl.md)** *(Engelse versie: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md))*

Hierin vind je oplossingen voor:
- MSX Pico die geen verbinding krijgt met het Wi-Fi-netwerk of server.
- Verkeerde poort- of firewall-instellingen op Windows en Mac.
- Docker foutmeldingen zoals poortconflicten (`address already in use`).
- Bestandsrechten bij het uploaden.
