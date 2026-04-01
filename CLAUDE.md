# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Web scraping automation for DeathGrind.club music database. Extracts band/album data via API, filters by record labels, validates against YouTube for underground material discovery, extracts download links, and downloads/organizes files automatically.

The entire codebase (variable names, logs, comments, UI) is in Spanish.

## Tech Stack

- Python 3.13+
- Playwright + playwright-stealth (async browser automation with anti-detection for YouTube)
- Requests (HTTP/API calls, threaded with connection pooling)
- Custom `.env` parser in `modules/utils.py` (not the python-dotenv library)
- psutil (optional, for system resource detection)

## Installation

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
playwright install chromium

# System dependencies (download/extraction)
# Arch: sudo pacman -S unrar p7zip && yay -S megatools
```

## Primary Command

```bash
python main.py
```

Interactive prompts ask for: disc types, headless mode, resume vs clean start. No CLI flags.

## Architecture

### Pipeline (`main.py`)

```
ejecutar_pipeline() — 3 steps:
  Step 1: extraer_bandas.run()        → API scrape, filter by label/downloaded/failed → data/repertorio.json
  Step 2: filtrar_youtube.run()       → Playwright async, parallel YouTube search     → data/repertorio_filtrado.json
  Step 3: extraer_links.run()         → API scrape, parallel link extraction          → data/repertorio_con_links.json

ejecutar_descarga() — separate call after pipeline:
  Step 4: descargar_y_organizar.run() → Download, extract, rename, organize files
```

Resume mode only skips the initial extraction step when `data/repertorio.json` already exists; YouTube filtering and link extraction are recalculated each run.

### Module Architecture

| Module                             | Concurrency                            | Purpose                                                                                          |
| ---------------------------------- | -------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `modules/extraer_bandas.py`        | ThreadPoolExecutor (3 workers)         | Scrapes posts by genre, filters by label blacklist, already-downloaded, and failed posts         |
| `modules/filtrar_youtube.py`       | asyncio + Playwright (N browser pages) | Searches YouTube for "full album" streams; if found, marks release as mainstream and excludes it |
| `modules/extraer_links.py`         | ThreadPoolExecutor (N workers)         | Fetches download links per post via API with thread-local sessions                               |
| `modules/descargar_y_organizar.py` | Sequential                             | Downloads from multiple services, extracts archives, renames/organizes into destination          |
| `modules/utils.py`                 | —                                      | Shared constants, auth, rate limiting, resource detection                                        |
| `modules/logger.py`                | —                                      | Centralized logging with emoji formatter                                                         |

### Key Patterns

- **Rate limiting**: All API modules retry indefinitely on HTTP 429 with exponential backoff (base 30s, max 300s). `delay_con_jitter()` adds randomness to all delays.
- **Authentication**: `crear_sesion_autenticada()` in `utils.py` handles login, CSRF token extraction, and session setup. All API modules reuse this.
- **Thread-local sessions**: `extraer_bandas.py` and `extraer_links.py` use `threading.local()` to give each worker its own `requests.Session` with connection pooling.
- **YouTube filter**: Revalidates the full current repertory on every run; no YouTube cache is used.
- **Failed posts tracking**: `data/fallidos_bandas.txt` tracks posts with broken links, auto-expires after 30 days.
- **Mega cooldown**: When Mega rate-limits, cooldown timestamp is written to `data/mega_cooldown.txt` and pending downloads saved to `data/mega_pendientes.json`.

## DeathGrind.club API

```
Base URL: https://deathgrind.club/api
Endpoints:
  POST /auth/login             - Auth (returns CSRF token)
  GET  /posts/filter?genres={id}&offset={page} - List posts by genre
  GET  /posts/{id}/links       - Get download links for a post
  GET  /bands/{id}/discography - Get band's discography

Auth headers: x-csrf-token, x-uuid, Cookie (authToken, csrfToken)
```

## Configuration Files

| File                                     | Purpose                                                 |
| ---------------------------------------- | ------------------------------------------------------- |
| `.env`                                   | `DEATHGRIND_EMAIL`, `DEATHGRIND_PASSWORD`               |
| `generos_activos.txt`                    | TSV: genre ID, article count, name (header row skipped) |
| `lista_sello.txt`                        | Label blacklist (one per line)                          |
| `keywords_album.txt` / `keywords_ep.txt` | YouTube mainstream detection keywords                   |

## Data Files

| File                             | Persists | Purpose                                                      |
| -------------------------------- | -------- | ------------------------------------------------------------ |
| `data/descargados.txt`           | Yes      | Already downloaded releases (format: `post_id\|band\|album`) |
| `data/fallidos_bandas.txt`       | Yes      | Posts with broken links (auto-expires 30 days)               |
| `data/mega_pendientes.json`      | Yes      | Mega downloads deferred due to rate limiting                 |
| `data/mega_cooldown.txt`         | Yes      | Mega cooldown timestamp                                      |
| `data/repertorio.json`           | No       | Cleaned each run — intermediate pipeline data                |
| `data/repertorio_filtrado.json`  | No       | Cleaned each run                                             |
| `data/repertorio_con_links.json` | No       | Cleaned each run                                             |

## Disc Type IDs

```python
TIPOS_DISCO = {1: "Album", 2: "EP", 3: "Demo", 4: "Single", 5: "Split", 6: "Compilation", 7: "Live"}
```

## Supported Download Services

Mega.nz (via megadl), Mediafire, Google Drive, Yandex Disk, pCloud, Mail.ru Cloud, Workupload, direct HTTP links (.zip, .rar, .7z)

## Download Destination

```
/mnt/Entretenimiento/01_edicion_automatizada/01_limpieza_de_impurezas/
```

Overridable via `DESTINO_BASE` env var. Temp dir: `/tmp/deathgrind_downloads`.
