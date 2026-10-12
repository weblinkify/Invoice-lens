# Contributing to InvoiceLens

Thanks for helping! This guide covers local setup, the quality bar, and how changes get merged.

## Setup

```bash
make setup     # backend + mock-erp (uv), frontend (npm), pre-commit hooks, .env
make dev       # API :8000 (SQLite, mock LLM) + Vite :5173
make dev-mock  # UI only, backed by MSW mocks
make up        # full stack in Docker (frontend :8080, API :8000, mock-erp :9000)
```

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, and Docker for E2E. Tesseract is optional locally (it's in the backend image).

## Workflow

1. Branch from `main`: `feat/…`, `fix/…`, `docs/…`.
2. Make the change **with tests**. Coverage gates: backend ≥ 85%, frontend ≥ 80%.
3. Changed an API route or schema? Run `make openapi` and commit `frontend/openapi.json` and `frontend/src/api/schema.d.ts`. CI fails if they're stale.
4. Run `make lint test` (and `make e2e` for UI or flow changes).
5. Use [Conventional Commits](https://www.conventionalcommits.org/): `feat(api): …`, `fix(frontend): …`, `test: …`, `docs: …`, `ci: …`, `chore: …`.
6. Open a PR. CI must be green (backend, frontend, e2e) before merge.

## Quality bar

- **Python**: fully typed, `mypy --strict`, `ruff check`, `ruff format`. Side effects (LLM, OCR, clock, HTTP, sleep) go through injectable dependencies.
- **TypeScript**: `strict`, no `any`, ESLint strict-type-checked, Prettier. API shapes come from the generated types only.
- **Errors**: return RFC 7807 problem+json (`AppError` in `backend/app/core/errors.py`).
- **No secrets** in code, tests or fixtures. Configuration goes in env vars and is documented in `.env.example` and the README table.
- Tests must not need network access or paid API keys (`LLM_PROVIDER=mock`).

## Regenerating fixtures

```bash
make generate-invoices   # deterministic: same seed → byte-identical PDFs
```

The MockProvider matches documents to ground truth by SHA-256, so regenerating changes which fields get noise. Update tests that rely on specific noisy fields (search for `invoice_02` and `invoice_03`).

## Repository settings (maintainers)

Protect `main` under **Settings → Branches → Add branch ruleset** (or *Branch protection rules*):

- Target: `main`
- ✅ Restrict deletions
- ✅ Block force pushes
- ✅ Require a pull request before merging (1 approval; dismiss stale approvals)
- ✅ Require status checks to pass, and require branches to be up to date:
  - `Backend (lint, types, tests)`
  - `Frontend (types in sync, lint, tests, build)`
  - `E2E (docker compose + Playwright)`
  - `E2E (static demo + Playwright)`
- ✅ Require linear history (optional)

With the GitHub CLI:

```bash
gh api -X PUT repos/weblinkify/Invoice-lens/branches/main/protection --input - <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "Backend (lint, types, tests)",
      "Frontend (types in sync, lint, tests, build)",
      "E2E (docker compose + Playwright)",
      "E2E (static demo + Playwright)"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": { "required_approving_review_count": 1, "dismiss_stale_reviews": true },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": true
}
JSON
```

Status-check names only become selectable after the CI workflow has run at least once on the repository.
