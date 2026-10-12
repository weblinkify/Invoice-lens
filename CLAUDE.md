# CLAUDE.md — InvoiceLens

AI invoice-extraction portal. Monorepo: `backend/` (FastAPI), `frontend/` (React + Vite),
`mock-erp/` (fake ERP webhook receiver), `sample-data/` (demo invoices).

## Hard rules
- Everything (dev, tests, CI) must work with **no paid API keys**: `LLM_PROVIDER=mock` is the default.
- No secrets in the repo. All configuration comes from env vars (`backend/app/core/config.py`, `.env.example`).
- Python: every function fully typed, `mypy --strict` clean, `ruff check` + `ruff format` clean.
- TypeScript: `strict`, no `any`. API types are **generated** (`frontend/src/api/schema.d.ts`) — never hand-write them; run `make openapi` after changing backend routes/schemas.
- Dependency injection for side effects: LLM provider, OCR engine, clock, HTTP client, sleeper. Tests swap fakes in via `app.dependency_overrides` or constructor args.
- Errors leave the API as RFC 7807 `application/problem+json` (`app/core/errors.py`).
- Commit messages: Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`).

## Commands
| Task | Command |
| --- | --- |
| Install everything | `make setup` |
| Run locally (SQLite, hot reload) | `make dev` |
| Frontend without backend (MSW) | `make dev-mock` |
| Backend tests + coverage | `cd backend && uv run pytest --cov` |
| Frontend tests + coverage | `cd frontend && npm run test:coverage` |
| Lint / typecheck all | `make lint` |
| Regenerate API types | `make openapi` |
| Full stack in Docker | `make up` (frontend :8080, API :8000, mock-erp :9000; override with `FRONTEND_PORT`/`BACKEND_PORT`/`MOCK_ERP_PORT`) |
| README accuracy table | `make accuracy` |
| E2E | `make e2e` (resets the stack's documents; writes `docs/screenshots/`) |
| E2E against the static demo (MSW, what Vercel serves) | `make e2e-demo` (`DEMO_URL=https://…` to hit a deployment) |
| Deploy live demo | `cd frontend && npx vercel deploy --prod --scope field-iq1` (project `invoicelens`, config in `frontend/vercel.json`) |
| Seed demo data | `make demo` |
| Regenerate invoice fixtures | `make generate-invoices` |

## Backend layout (`backend/app`)
- `core/` settings, JSON logging, problem+json errors, API-key auth
- `domain/` pure logic: extraction schema, IBAN/VAT validators, business rules, confidence scoring, few-shot builder
- `ocr/` `OcrEngine` protocol; `pdfplumber` text layer with `pytesseract` fallback
- `llm/` `LLMProvider` protocol; `MockProvider` (default, deterministic), `AnthropicProvider`, `OpenAIProvider`
- `db/` SQLAlchemy 2.0 models + session; migrations in `backend/alembic`
- `services/` extraction pipeline, storage, exports, webhooks (HMAC + backoff), accuracy metrics
- `api/` routers under `/api/v1`, dependencies

Background work uses FastAPI `BackgroundTasks`. Tests run the pipeline synchronously against SQLite.

## Frontend layout (`frontend/src`)
- `api/` generated `schema.d.ts`, typed fetch client, TanStack Query hooks
- `components/ui/` shadcn-style primitives; `components/` feature components
- `pages/` Upload, Documents, Review, Settings
- `mocks/` MSW handlers + fixtures (used by Vitest and `npm run dev:mock`)
- `e2e/` Playwright specs (run against docker compose)

## Gotchas
- Mock invoices are matched to ground truth by SHA-256 of the file bytes, so regenerating fixtures changes which noise the MockProvider injects.
- Intel macOS: `cryptography>=49` has no wheels, constrained in `backend/pyproject.toml`.
- Bounding boxes are normalized `[x0, y0, x1, y1]` in 0..1 with a top-left origin.
- Run the API with the factory: `uvicorn --factory app.main:create_app` (there is no module-level `app`).
- Reviewer corrections are learned per vendor (few-shot), so re-uploading a fixture after correcting it returns the fixed value at 0.97. E2E clears documents first for that reason.
- openapi-fetch must late-bind `fetch` (see `src/api/client.ts`) or MSW can't intercept it in tests.
- nginx must serve `.mjs` as JavaScript or the pdf.js worker fails ("Could not load the PDF").
- `DocumentViewer` ignores width changes ≤ 24px and reserves the scrollbar gutter; without that, a scrollbar toggling resizes the page in a loop (flashing preview).
- Frontend pins: React 18 (spec), `react-pdf@10` (v11 needs React 19), TypeScript 5.9 (openapi-typescript peer).
