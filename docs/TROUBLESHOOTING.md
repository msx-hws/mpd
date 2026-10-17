# Troubleshooting Guide

This guide helps you identify and resolve common issues with the **MSX-Pico-Station**, **Docker**, and network connectivity with your **MSX Pico / Flash cartridge**.

*Lees dit document in het Nederlands: [docs/TROUBLESHOOTING.nl.md](TROUBLESHOOTING.nl.md).*

---

## Table of Contents
1. [MSX Pico Cannot Connect or File List is Empty](#1-msx-pico-cannot-connect-or-file-list-is-empty)
2. [Docker Won't Start or Exits Immediately](#2-docker-wont-start-or-exits-immediately)
3. [Web Page Won't Load in Browser](#3-web-page-wont-load-in-browser)
4. [File Upload Fails](#4-file-upload-fails)
5. [Game Gives a Black Screen on MSX](#5-game-gives-a-black-screen-on-msx)
6. [Checking Logs & Status](#6-checking-logs--status)

---

## 1. MSX Pico Cannot Connect or File List is Empty

### Symptoms:
- The MSX Pico shows a connection error, times out, or remains stuck on "Connecting...".
- The file listing on screen is empty.

### Causes and Solutions:

#### A. Check `URL.TXT` on the Micro-SD Card
The file `URL.TXT` must strictly follow these requirements:
1. **Location:** inside the `FH_FILES/` folder in the root of your SD card (`SD_CARD:\FH_FILES\URL.TXT`).
2. **Content:** exact IP address with protocol and a trailing slash (`/`), for example:
   ```text
   http://192.168.1.150/
   ```
3. **No spaces or empty lines:** ensure there are no leading/trailing spaces or extra line breaks.
4. **No HTTPS:** MSX hardware does not support SSL/TLS encryption (`https://`). Always use `http://`.
5. **Exact filename:** make sure Windows didn't save it as `URL.TXT.txt` (turn on "File name extensions" in Windows Explorer).

#### B. Wi-Fi and Same Subnet
- Your MSX Pico and the machine running this application **must be on the same local Wi-Fi / LAN network**.
- Check if your router has **AP Isolation** or **Guest Wi-Fi** enabled. Devices on a guest network cannot communicate with local servers. Connect both devices to your standard home Wi-Fi.

#### C. Firewall Settings
- If running on Windows, macOS, or Linux, the local firewall might block incoming traffic on port `80` (or `5001`).
- **Test:** open a browser on another phone or laptop on the same network and navigate to `http://<server-ip>/`. If it doesn't load, the firewall is likely blocking incoming connections.

---

## 2. Docker Won't Start or Exits Immediately

### Symptoms:
- `docker compose up -d` outputs an error.
- `docker ps` does not show the container, or shows status `Exited`.

### Causes and Solutions:

#### A. Docker Desktop is not running
- Make sure **Docker Desktop** is running and the status icon is green ("Engine running").

#### B. Port 80 is already in use
- Error message: `bind: address already in use` or `port is already allocated`.
- Cause: Another application (e.g. Apache, Nginx, Skype, IIS, or another web service) is already listening on port 80.
- **Important Note for MSX Pico:** The MSX Pico cartridge firmware strictly expects port **80** and cannot connect to custom ports (like `:8080`). The best solution is to stop or reconfigure the other service using port 80 so that `msx-pico-station` can use it.
- *(Only if you are using the server purely via browser/API without an MSX Pico)*: You can change the port in `.env` (e.g. `HOST_PORT=8080`). Remember that doing so breaks compatibility with the MSX Pico hardware!

---

## 3. Web Page Won't Load in Browser

1. **Is the container running?**
   Run in your terminal:
   ```bash
   docker compose ps
   ```
   Verify that the status is `Up` or `healthy`.
2. **Check container logs:**
   ```bash
   docker compose logs -f
   ```
   Any Python or permission exceptions will be visible here.
3. **Test localhost:**
   If testing directly on the host machine, try `http://localhost/` in your browser.

---

## 4. File Upload Fails

1. **File permissions:**
   The Docker container runs as an unprivileged user (`app`). If the host directory `files/` does not grant write permissions, uploads will fail.
   - On Linux/macOS:
     ```bash
     chmod -R 777 files/
     ```
2. **Filenames with invalid characters:**
   Use standard alphanumeric characters, hyphens (`-`), and underscores (`_`). Spaces and special characters are automatically sanitized to maintain MSX-DOS and Pico compatibility.

---

## 5. Game Gives a Black Screen on MSX

1. **File size (.ROM padding):**
   The MSX Pico requires `.rom` files to be at least 4096 or 8192 bytes. This server automatically pads undersized ROMs with null bytes during download.
2. **Mapper compatibility:**
   Some games require specific ROM mappers (such as Konami SCC, ASCII 8K, ASCII 16K). Consult your MSX Pico cartridge documentation regarding supported mappers.
3. **Converted .COM files:**
   If you have a `.com` executable and wish to launch it via the Pico ROM loader, rename its extension to `.rom` before serving.

---

## 6. Checking Logs & Status

The server logs all requests, downloads, uploads, and MSX clients.

- **Real-time Docker logs:**
  ```bash
  docker compose logs -f
  ```
- **Log file on disk:**
  Logs are saved in `logs/app.log`.
- **Health check endpoint:**
  From the host, you can verify health status via:
  ```bash
  curl http://localhost:5001/health/getstatus
  ```
