# MSX-Flask Project Architectuur & Beveiliging

Dit document beschrijft het ontwerp (OpenSpec) voor het msx-flask project. Het bevat de uitwerking van het accountsysteem, IP-beveiliging en infrastructuur-richtlijnen volgens de principes DRY, KISS en Shift Left.

## 1. Project Principes
- **KISS (Keep It Simple, Stupid):** We vermijden complexe authenticatieprotocollen zoals OAuth voor de MSX-clients. Authenticatie voor de retro-clients (MSX) gebeurt op basis van het externe IP-adres. De webinterface gebruikt eenvoudige sessie-gebaseerde login.
- **DRY (Don't Repeat Yourself):** Code voor bestandstoegang, validatie (`safe_path`) en IP-checks wordt gecentraliseerd en hergebruikt. Geen dubbele logica voor de webinterface en MSX API.
- **Shift Left:** Beveiliging, testen en foutafhandeling worden zo vroeg mogelijk in de pipeline toegepast. Valideer bestandsnamen en paden *voordat* er schijfoperaties plaatsvinden (dit gebeurt al in `safe_path`).

## 2. Account Systeem & IP-Authenticatie
Omdat de MSX API verplicht HTTP gebruikt en moderne encryptie ontbreekt, gebruiken we IP-whitelisting per account:

1. **Registratie:** Gebruikers maken een account aan via de webinterface (gebruikersnaam/wachtwoord).
2. **Eigen Map:** Bij registratie wordt automatisch een geïsoleerde map aangemaakt: `files/<username>/`.
3. **IP Koppeling:** Gebruikers loggen in op de web portal (welke HTTPS gebruikt via een reverse proxy, zie sectie 3) en stellen daar hun huidige MSX IP-adres in. 
4. **MSX API Requests:** Wanneer `/index2.php` wordt aangeroepen, checkt de backend het `request.remote_addr`.
   - Staat dit IP in de database? Gekoppeld aan user X?
   - Zo ja: serveer alleen de inhoud van `files/X/`.
   - Zo nee: stuur een 401 Unauthorized of simpele lege lijst terug.

## 3. Beveiligingsontwerp (HTTP, Linux & UniFi)

Omdat MSX computers geen moderne HTTPS kunnen afhandelen, moet de communicatie naar de MSX helaas in platte tekst over HTTP. Om dit toch maximaal te beveiligen zonder de rest van je netwerk bloot te stellen, passen we de volgende infrastructuur toe:

### A. UniFi (Netwerk Laag)
- **VLAN Isolatie:** Plaats de Linux server die msx-flask draait in een afgeschermd DMZ/IoT VLAN. Deze server mag geen toegang hebben tot de rest van je thuisnetwerk (LAN).
- **GeoIP / Landen Blokkade:** Gebruik UniFi Threat Management of Firewall Rules om inkomend verkeer uit onverwachte landen (zoals Rusland, China) standaard te blokkeren voor poort 80/HTTP.
- **Port Forwarding:** Forward poort 80 (MSX) en 443 (Webinterface) alleen naar dit specifieke server IP.

### B. Linux Server Laag
- **Nginx Reverse Proxy:** Gebruik Nginx (of Caddy) vóór Flask. 
  - Nginx draait op poort 80 voor de specifieke MSX route (`/index2.php`). 
  - Voor de webinterface en accountbeheer forceert Nginx HTTPS (met Let's Encrypt / Certbot).
- **Fail2Ban:** Bescherm de HTTP-endpoints met Fail2Ban. Bij meerdere foutieve aanvragen op de MSX-poort (of foute paden) wordt het IP tijdelijk via `iptables`/`ufw` geblokkeerd.
- **Beperkte Rechten (Least Privilege):** 
  - Draai de Flask applicatie als een non-root user (bijv. `msx-app`).
  - Maak de applicatiecode read-only voor de `msx-app` user. Alleen de `files/` directory en SQLite database hebben schrijf-rechten nodig.
  - Gebruik AppArmor of SELinux om de Flask applicatie te beperken in wat het op de server kan zien (chroot-achtig gedrag).
- **Rate Limiting:** Configureer in Nginx limieten voor het aantal requests per IP per minuut om (D)DoS en scraping te voorkomen.

## 4. API Specificatie (OpenAPI)
Zie `openapi.yaml` in de root van het project voor de volledige endpoints, inclusief het beheer van het toegestane IP-adres en de gescheiden paden.
