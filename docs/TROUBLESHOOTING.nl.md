# Problemen Oplossen (Troubleshooting)

Dit document helpt je bij het opsporen en oplossen van veelvoorkomende problemen met de **MSX ROM & DSK Server**, **Docker** en de verbinding met je **MSX Pico / Flash cartridge**.

---

## Inhoudsopgave
1. [MSX Pico vindt geen bestanden of maakt geen verbinding](#1-msx-pico-vindt-geen-bestanden-of-maakt-geen-verbinding)
2. [Docker start niet of container stopt direct](#2-docker-start-niet-of-container-stopt-direct)
3. [De webpagina laadt niet in de browser](#3-de-webpagina-laadt-niet-in-de-browser)
4. [Uploaden van bestanden lukt niet](#4-uploaden-van-bestanden-lukt-niet)
5. [Spel start niet of geeft een zwart scherm op de MSX](#5-spel-start-niet-of-geeft-een-zwart-scherm-op-de-msx)
6. [Logs en status controleren](#6-logs-en-status-controleren)

---

## 1. MSX Pico vindt geen bestanden of maakt geen verbinding

### Symptomen:
- De MSX Pico geeft een time-out, error of blijft hangen op "Connecting...".
- De bestandenlijst blijft helemaal leeg.

### Oorzaken en oplossingen:

#### A. Controleer `URL.TXT` op de SD-kaart
Het bestand `URL.TXT` moet exact aan de volgende eisen voldoen:
1. **Locatie:** in de map `FH_FILES/` direct in de root van je SD-kaart (`SD-kaart:\FH_FILES\URL.TXT`).
2. **Inhoud:** exact het IP-adres met protocol en afsluitende schuine streep (`/`), bijvoorbeeld:
   ```text
   http://192.168.1.150/
   ```
3. **Geen spaties of extra regels:** zorg dat er geen verborgen spaties voor of na het adres staan, en geen extra witregels.
4. **Geen HTTPS:** MSX-hardware ondersteunt geen SSL/TLS encryptie (`https://`). Gebruik altijd `http://`.
5. **Exacte bestandsnaam:** let op dat Windows het bestand niet per ongeluk `URL.TXT.txt` noemt (schakel "Bestandsnaamextensies weergeven" in via Windows Verkenner).

#### B. WiFi en hetzelfde netwerk
- Je MSX Pico én de computer/server waarop deze applicatie draait **moeten met hetzelfde netwerk (dezelfde router/WiFi)** verbonden zijn.
- Sommige routers hebben een functie genaamd **AP Isolation** of **Gastnetwerk (Guest Wi-Fi)** ingeschakeld. Als de MSX Pico op een gastnetwerk zit, kan hij de server niet bereiken. Sluit beide aan op het gewone thuisnetwerk.

#### C. Firewall op de computer
- Als de server draait op Windows, macOS of Linux, kan de ingebouwde firewall inkomend verkeer op poort `80` (of `5001`) blokkeren.
- **Test:** open vanaf een andere telefoon of laptop in hetzelfde netwerk de browser en ga naar `http://<IP-van-je-server>/`. Laadt de pagina niet? Dan blokkeert de firewall waarschijnlijk de verbinding.

---

## 2. Docker start niet of container stopt direct

### Symptomen:
- `docker compose up -d` geeft een foutmelding.
- `docker ps` toont de container niet of toont de status `Exited`.

### Oorzaken en oplossingen:

#### A. Docker Desktop draait niet
- Zorg ervoor dat het programma **Docker Desktop** daadwerkelijk is opgestart en het icoontje groen is ("Engine running").

#### B. Poort 80 is al in gebruik
- Foutmelding: `bind: address already in use` of `port is already allocated`.
- Oorzaak: Er draait al een ander programma (zoals Apache, Nginx, Skype, IIS of een andere webserver) op poort 80 van je computer.
- **Let op voor de MSX Pico:** De MSX Pico cartridge ondersteunt **geen** afwijkende poorten (zoals `:8080`) in de URL en vereist standaard poort `80`. De beste oplossing is daarom om het conflicterende programma op poort 80 te stoppen of te verplaatsen naar een andere poort, zodat `msx-pico-station` poort 80 kan gebruiken.
- *(Alleen als je de server puur via de browser/API gebruikt en géén MSX Pico)*: Dan kun je in `.env` de poort wijzigen (bijv. `HOST_PORT=8080`). Zodra je dit doet, kan de MSX Pico er echter **niet** meer bij!

---

## 3. De webpagina laadt niet in de browser

1. **Draait de container wel?**
   Voer in de terminal uit:
   ```bash
   docker compose ps
   ```
   Kijk of de status `Up` of `healthy` is.
2. **Kijk in de logs:**
   ```bash
   docker compose logs -f
   ```
   Hier zie je direct of er een Python- of permissiefout optreedt.
3. **Probeer localhost:**
   Als je op de server zelf zit, test dan in je browser `http://localhost/` (of `http://localhost:5001/` indien lokaal gestart zonder Docker).

---

## 4. Uploaden van bestanden lukt niet

1. **Map-rechten (File permissions):**
   De container draait onder een veilige, niet-root gebruiker (`app`). Als de map `files/` op je computer geen schrijfrechten heeft voor deze gebruiker, kan het uploaden mislukken.
   - Op Linux/macOS:
     ```bash
     chmod -R 777 files/
     ```
2. **Bestandsnaam bevat vreemde tekens:**
   Gebruik bij voorkeur standaard letters, cijfers, streepjes (`-`) en underscores (`_`). Spaties en speciale leestekens worden automatisch gefilterd om compatibiliteit met MSX-DOS en de Pico te waarborgen.

---

## 5. Spel start niet of geeft een zwart scherm op de MSX

1. **Bestandsgrootte (.ROM padding):**
   De MSX Pico vereist dat `.rom` bestanden minimaal 4096 of 8192 bytes zijn. Deze server vult kleine bestanden automatisch aan met null-bytes tijdens het downloaden.
2. **Onjuist ROM-type / mapper:**
   Sommige spellen vereisen een specifieke mapper (zoals Konami SCC, ASCII 8K, ASCII 16K). Raadpleeg de handleiding van je MSX Pico over welke mapper-types ondersteund worden.
3. **Geconverteerde .COM bestanden:**
   Als je een `.com` programma downloadt als `.rom`, zorg dan dat je de extensie in de `files/` map hernoemt naar `.rom` zodat de server deze als cartridge-ROM serveert.

---

## 6. Logs en status controleren

De server houdt uitgebreide logs bij van alle downloads, uploads en MSX-aanvragen.

- **Realtime Docker logs:**
  ```bash
  docker compose logs -f
  ```
- **Logbestand bekijken:**
  Het logbestand vind je in `logs/app.log`.
- **Health check status:**
  Vanaf de servermachine kun je de status controleren via:
  ```bash
  curl http://localhost:5001/health/getstatus
  ```
