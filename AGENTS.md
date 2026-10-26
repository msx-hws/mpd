# Instructions for AI Agents & Developers

## MSX Pico Hardware Protocol (`/index2.php`)
- **Strict Protocol:** The MSX Pico cartridge firmware (ESP8266/RP2040) parses `/index2.php` line by line (`<filename>\t<size>\n`).
- **NO Artificial Headers or Banners:** NEVER inject artificial items, server announcements, or dummy banner lines (e.g. `mpd [IP]\t0`) into the index listing. The MSX Pico firmware expects every entry to represent a downloadable file with a valid size > 0; unexpected/zero-byte entries corrupt the parser and result in **"No Entries"** on the MSX.
- **Filename Filtering & Display:** The firmware filters files alphabetically by requesting `?type=ROM&char=<letter>`. The display name must match the actual title of the game. Never let automatic timestamps or technical prefixes (such as `YYYYMMDD_HHMMSS_`) break the starting character of the game's title.
- **Padding:** ROM and COM downloads must be padded to multiples of 4096 bytes (0x1000) or 8192 bytes as expected by the cartridge loader.
- **Port Requirement:** The MSX Pico firmware only connects via HTTP over port 80.
