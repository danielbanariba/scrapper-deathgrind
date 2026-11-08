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
Unit tests live in `tests/` (stdlib `unittest`, fakes only: they never log in or ask for links, which depend on download credits). Run them with `PYTHONDONTWRITEBYTECODE=1 env/bin/python -m unittest discover -s tests -t .`. `python scripts/api_smoke_test.py` logs in for real and asks for one post's links, which may use a download credit; run it once, since several logins in a row lock the account for a while. Exercise the affected pipeline path through `python main.py` when practical. If your change alters generated outputs, mention which `data/` files were regenerated. Name new validation scripts descriptively, for example `scripts/test_descargas.py` or `scripts/smoke_links.py`.

## Commit & Pull Request Guidelines
Commits are in English, Gitmoji + Conventional Commits, following `templates/commit-template.en.git.txt` (for example `:bug: fix(login): read the csrf token from the sign-in page`). PR bodies follow `.github/pull_request_template.md` and should describe the user-visible pipeline impact, list required `.env` or dependency changes, and note any intentional updates to tracked files in `data/`. Include sample console output when a change affects prompts, retries, or download behavior.

## Security & Configuration Tips
Do not commit real credentials in `.env`. Use `.env.example` as the template for `DEATHGRIND_EMAIL`, `DEATHGRIND_PASSWORD`, and `DESTINO_BASE`, and sanitize any logs or screenshots that expose account data or download paths.
