# Repository Guidelines

## Project Structure & Module Organization
`main.py` is the interactive entrypoint for the full scraper pipeline. Core logic lives in `modules/`: `extraer_bandas.py` pulls DeathGrind.club data, `filtrar_youtube.py` removes mainstream releases, `extraer_links.py` resolves download links, and `descargar_y_organizar.py` handles downloads. Shared helpers are in `modules/utils.py` and `modules/logger.py`. Generated artifacts and runtime state live in `data/`; treat them as outputs, not source files. Use `scripts/` for maintenance checks such as `scripts/api_smoke_test.py`. The `old/` directory is archival and should not receive new work.

## Build, Test, and Development Commands
Run commands from the repository root:

```bash
python -m venv env
source env/bin/activate
pip install -r requirements.txt
playwright install chromium
python main.py
python scripts/api_smoke_test.py
```

`python main.py` runs the full interactive pipeline and may update files under `data/`. `python scripts/api_smoke_test.py` verifies login plus the main API endpoints without downloading content.

## Coding Style & Naming Conventions
Follow existing Python style: 4-space indentation, snake_case for functions and variables, and UPPER_CASE for module constants. Keep new code in Spanish when naming domain concepts, logs, prompts, and comments, because the current codebase is consistently Spanish-first. Prefer small helpers over long inline blocks, and keep side effects explicit around file writes and network retries. No formatter or linter is configured in-repo, so match current PEP 8-like style closely.

## Testing Guidelines
There is no formal `tests/` suite yet. For behavior changes, run `python scripts/api_smoke_test.py` first, then exercise the affected pipeline path through `python main.py` when practical. If your change alters generated outputs, mention which `data/` files were regenerated. Name new validation scripts descriptively, for example `scripts/test_descargas.py` or `scripts/smoke_links.py`.

## Commit & Pull Request Guidelines
Recent commits use short Spanish summaries, often focused on the change outcome, for example `Base de datos v3` or `Se agrega un nuevo filtro de descargas fallidas`. Keep commit messages brief, specific, and in the same style. PRs should describe the user-visible pipeline impact, list required `.env` or dependency changes, and note any intentional updates to tracked files in `data/`. Include sample console output when a change affects prompts, retries, or download behavior.

## Security & Configuration Tips
Do not commit real credentials in `.env`. Use `.env.example` as the template for `DEATHGRIND_EMAIL`, `DEATHGRIND_PASSWORD`, and `DESTINO_BASE`, and sanitize any logs or screenshots that expose account data or download paths.
