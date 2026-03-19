# TeaBuy Backend (M1)

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
uvicorn app.main:app --reload
```

## Migrate (Supabase)

Set `SUPABASE_DB_URL` or `DATABASE_URL` in `.env`.

```bash
cd backend
alembic upgrade head
```

## Seed dev data

```bash
python -m app.scripts.seed_dev
```

## Key endpoints

- `GET /api/v1/health`
- `GET /api/v1/health/db`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/home` (Bearer token)
- `POST /api/v1/orders` (`Idempotency-Key` required)
- `POST /api/v1/payments/mock/callback` (requires signature)
