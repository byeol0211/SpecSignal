# SpecSignal

A service for university students to explore certifications and activities and plan preparation around academic schedules.

## Current status (2026-11-10)

The previous frontend has been removed. The replacement will be based on [PLSAi](https://github.com/byeol0211/PLSAi), preserving the same product goals and feature requirements. PLSAi has not been imported yet.

- Preserved: FastAPI APIs, authentication, certification collection and normalization, Supabase integration and migrations.
- Removed: HTML, CSS, JavaScript, SVG assets, UI verification scripts and screenshots.
- Previous UI routes (`/`, `/catalog-live`) now return 404.
- Calendar, bookmarks, profiles and recommendation demos previously implemented in the browser must be rebuilt in the replacement frontend.

## Run the backend

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m src.web.server
```

`start-web.cmd` also starts the backend. Default address: `http://127.0.0.1:8000`. API schema: `/api/openapi.json`. See `.env.example` and the database document for configuration.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Documents

- [Project overview](docs/project-overview.md): product goals and feature reference; previous UI implementation status is historical.
- [Architecture decisions](docs/architecture-decisions.md): data strategy, architecture history and frontend replacement decision.
- [Design implementation](docs/design-implementation.md): historical record of the removed UI.
- [Supabase database](docs/supabase-database.md): database schema, collection, authentication and operations.
