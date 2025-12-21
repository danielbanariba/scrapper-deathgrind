# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Web scraping automation for DeathGrind.club music database. Extracts band/album data via API, filters by record labels, validates against YouTube for underground material discovery, extracts download links, and downloads/organizes files automatically.

## Tech Stack

- Python 3.13
- Playwright + playwright-stealth (browser automation with anti-detection)
- Selenium (YouTube validation)
- Requests (HTTP/API calls)
- python-dotenv (credential management)

## Installation

```bash
# Create and activate virtual environment
python -m venv env
source env/bin/activate

# Install Python dependencies
pip install playwright requests python-dotenv selenium playwright-stealth

# Install Playwright browsers
playwright install chromium

# Install system dependencies (for download/extraction)
# Arch Linux
sudo pacman -S unrar p7zip
yay -S megatools

# Debian/Ubuntu
sudo apt install unrar p7zip-full megatools
```

## Primary Command

```bash
python main.py
```

## Pipeline (5 pasos)

```
1. Extraer bandas + repertorio (API) - filtra por sellos
2. Filtrar por YouTube (solo underground)
3. Extraer links de descarga (API)
4. Filtrar por ya descargados (omite duplicados)
5. Descargar, extraer y organizar archivos
```

## Modules

| Module | Purpose |
|--------|---------|
| `modules/extraer_bandas.py` | Extract bands + repertoire from API, filter by blacklisted labels |
| `modules/filtrar_youtube.py` | Filter out releases available on YouTube |
| `modules/extraer_links.py` | Extract download links via API |
| `modules/descargar_y_organizar.py` | Download, extract, rename and organize files |

## DeathGrind.club API

```
Base URL: https://deathgrind.club/api
Endpoints:
  POST /auth/login           - Authentication (returns CSRF token)
  GET  /posts/filter         - List posts by genre
       ?genres={id}&offset={page}
  GET  /posts/{id}/links     - Get download links for a post
  GET  /bands/{id}/discography - Get band's discography

Auth headers required:
  x-csrf-token: {token}
  x-uuid: {uuid}
  Cookie: authToken, csrfToken
```

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Credentials: `DEATHGRIND_EMAIL`, `DEATHGRIND_PASSWORD` |
| `lista_sello.txt` | Blacklist of record labels to filter out |
| `generos_activos.txt` | TSV with genre IDs, article counts, and names |
| `keywords_album.txt` | YouTube keywords for album detection |
| `keywords_ep.txt` | YouTube keywords for EP detection |
| `data/descargados.txt` | List of already downloaded releases (persists) |

## Disc Type IDs

```python
TIPOS_DISCO = {
    1: "Album",
    2: "EP",
    3: "Demo",
    4: "Single",
    5: "Split",
    6: "Compilation",
    7: "Live"
}
```

## Data Flow

```
API → posts[]
    → FILTRO 1 (sello blacklist) → posts_filtrados[]
    → FILTRO 2 (tipo disco) → repertorio.json
    → FILTRO 3 (YouTube) → repertorio_filtrado.json
    → FILTRO 4 (links disponibles) → repertorio_con_links.json
    → FILTRO 5 (ya descargados) → omite duplicados
    → DESCARGA → /destino/Banda - Album (Year)/
```

## Output Files

| File | Purpose |
|------|---------|
| `data/bandas.json` | Unique bands extracted |
| `data/repertorio.json` | All releases (filtered by label) |
| `data/repertorio_filtrado.json` | Releases after YouTube filter |
| `data/repertorio_con_links.json` | Releases with download links |
| `data/links_descarga.txt` | Plain list of download URLs |
| `data/descargados.txt` | Already downloaded (persists between runs) |

## Download Destination

```
/run/media/banar/Entretenimiento/01_edicion_automatizada/01_limpieza_de_impurezas/
```

## Supported Download Services

- Mega.nz (via megadl)
- Mediafire
- Direct HTTP links (.zip, .rar, .7z)

## Rate Limiting

The scraper uses conservative delays to avoid being blocked:
- 1 second between API pages
- 3 seconds between genres
- 30+ seconds on HTTP 429 (rate limit), never gives up
