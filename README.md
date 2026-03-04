# Ads Performance Reporting Dashboard

A local web dashboard that joins **Google Ads spend/click data** with **Archer Affiliates revenue data** on Amazon ASIN, refreshing every 4 hours automatically.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend API | FastAPI + Uvicorn |
| Scheduler | APScheduler (4-hour interval) |
| Database | SQLite (local cache) |
| Frontend | React + Vite + Tailwind CSS |
| Charts | Recharts |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Google Ads developer token + OAuth credentials (see below)
- Archer Affiliates API credentials

---

## 1 — Clone & configure

```bash
git clone <repo-url>
cd ads-dashboard
```

### Backend environment

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and fill in:

```bash
ARCHER_BASE_URL=https://api.archeraffiliates.com
ARCHER_USERNAME=EXPLORADS
ARCHER_PASSWORD=your_password_here
GOOGLE_ADS_CUSTOMER_ID=6133884014
```

---

## 2 — Google Ads OAuth setup

You need a developer token and OAuth 2.0 credentials. Do this **once**:

### 2a — Developer token
1. Log in to Google Ads → **Tools & Settings → API Center**
2. Apply for a developer token (basic access is sufficient for testing)

### 2b — OAuth credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable the **Google Ads API**
4. Go to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client IDs**
5. Application type: **Desktop app**
6. Download the JSON file and save it as `backend/client_secrets.json`

### 2c — Generate refresh token

```bash
cd backend
pip install google-auth-oauthlib
python generate_refresh_token.py
```

A browser window opens → log in with the Google account that has access to the Ads account → authorize → copy the printed refresh token.

### 2d — Create google-ads.yaml

```bash
cp backend/google-ads.yaml.example backend/google-ads.yaml
```

Edit `backend/google-ads.yaml`:

```yaml
developer_token: YOUR_DEVELOPER_TOKEN
client_id: YOUR_CLIENT_ID.apps.googleusercontent.com
client_secret: YOUR_CLIENT_SECRET
refresh_token: YOUR_REFRESH_TOKEN
# login_customer_id: YOUR_MCC_ID   # uncomment if using a Manager Account
```

---

## 3 — Backend setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize the database
python init_db.py

# Start the server
uvicorn app.main:app --reload --port 8000
```

The backend starts on **http://localhost:8000**.

On first run it automatically:
- Creates SQLite tables
- Triggers an initial data sync (Google Ads yesterday + Archer last 5 days)
- Schedules a sync every 4 hours

### Manual sync trigger

```bash
curl -X POST http://localhost:8000/api/sync/trigger
```

### Sync status

```bash
curl http://localhost:8000/api/sync/status
```

---

## 4 — Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The frontend starts on **http://localhost:5173** and proxies `/api` requests to the backend at port 8000.

---

## 5 — Using the dashboard

Open **http://localhost:5173** in your browser.

| Control | Description |
|---------|-------------|
| Yesterday / L7D / L14D / L30D / MTD | Preset date ranges |
| Custom date pickers | Pick any date range |
| Day / Week / Month toggle | Group drill-down rows by period |
| Filter campaign / ASIN | Filter the campaign table |
| Click column headers | Sort campaigns by any column (asc/desc) |
| Click campaign row `▸` | Expand to see per-period date breakdown |
| Refresh Now button | Trigger an immediate sync |
| ↓ Export CSV | Download aggregated or detailed CSV |

### Campaign Table

The table has **two levels**:
- **Level 1** — One row per campaign (totals across selected date range). Click any column header to sort. Click a row to expand.
- **Level 2** — Per-period rows appear below the campaign when expanded. Always shown in chronological order.

Columns on both levels: Spend, Revenue, ROAS, **RPC** (Revenue Per Click), ACOS, Orders, Clicks, CTR.

### CSV Export

Click **↓ Export CSV** above the table:
- **Aggregated** — one row per campaign, totals across selected dates
- **Detailed** — one row per campaign × date period (requires campaigns to be expanded, or all date data is fetched automatically)

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/dashboard/summary` | Totals for date range (spend, revenue, ROAS, RPC, orders) |
| GET | `/api/dashboard/campaigns` | Campaign-level aggregates (no date dimension), sortable |
| GET | `/api/dashboard/campaigns/{id}/dates` | Date drill-down for one campaign (chronological) |
| GET | `/api/dashboard/timeseries` | Time-series data for chart |
| GET | `/api/sync/status` | Last sync info + next scheduled run |
| POST | `/api/sync/trigger` | Trigger immediate sync |

**Campaigns query params:** `date_from`, `date_to`, `sort_by`, `sort_dir` (asc/desc), `asin` (filter), `campaign` (filter)

**Dates query params:** `date_from`, `date_to`, `groupby` (day/week/month)

Example:
```
GET /api/dashboard/campaigns?date_from=2026-02-01&date_to=2026-02-18&sort_by=rpc&sort_dir=desc
GET /api/dashboard/campaigns/12345678/dates?date_from=2026-02-01&date_to=2026-02-18&groupby=day
```

---

## ASIN Extraction

Campaign names must follow the pattern `"Brand Name - ASIN"`:

```
VALI Caffeine L-Theanine - B074G3SYTT  →  B074G3SYTT
L-Theanine Plus - B074G3SYTT           →  B074G3SYTT
```

The ASIN is extracted at sync time and stored in the database for fast joins.

---

## Archer API Auto-Discovery

Since Archer's API docs are behind login, the client automatically tries common endpoint paths and parameter names on first run. Once a working endpoint is found, check the backend logs for a line like:

```
Archer: discovered endpoint /reports/earnings with params start_date/end_date.
Set ARCHER_REPORTS_ENDPOINT=/reports/earnings in .env to skip discovery.
```

Add that to your `.env` to skip discovery on future restarts.

---

## Project Structure

```
ads-dashboard/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI app + lifespan
│   │   ├── config.py             # Settings from .env
│   │   ├── database.py           # SQLAlchemy engine
│   │   ├── models.py             # ORM tables
│   │   ├── schemas.py            # Pydantic schemas
│   │   ├── scheduler.py          # APScheduler 4-hour job
│   │   ├── api/
│   │   │   ├── routes_dashboard.py
│   │   │   ├── routes_sync.py
│   │   │   └── routes_health.py
│   │   ├── services/
│   │   │   ├── archer_client.py  # Auto-discovery HTTP client
│   │   │   ├── google_ads_client.py
│   │   │   ├── sync_service.py   # Orchestrates fetch + upsert
│   │   │   └── aggregation.py    # JOIN queries
│   │   └── utils/
│   │       ├── asin_extractor.py
│   │       └── date_utils.py
│   ├── generate_refresh_token.py
│   ├── init_db.py
│   ├── .env                      # secrets (gitignored)
│   ├── google-ads.yaml           # OAuth creds (gitignored)
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── App.tsx
    │   ├── api/client.ts
    │   ├── types/index.ts
    │   ├── hooks/
    │   │   ├── useDashboardData.ts
    │   │   ├── useCampaignDates.ts  # lazy fetch + cache per campaign
    │   │   └── useRefresh.ts
    │   ├── utils/
    │   │   ├── formatters.ts        # fmtUSD, fmtROAS, fmtRPC, fmtPct
    │   │   └── csvExport.ts         # aggregated / detailed CSV download
    │   └── components/
    │       ├── table/
    │       │   ├── CampaignTable.tsx    # two-level expandable + sort
    │       │   ├── DateDrillDown.tsx    # per-period rows (chronological)
    │       │   └── TableFilters.tsx
    │       └── export/
    │           └── ExportModal.tsx      # CSV export dialog
    ├── vite.config.ts
    └── package.json
```

---

## Security

- All credentials stored in `.env` and `google-ads.yaml` — both are gitignored
- No credentials are hardcoded anywhere in the source
- CORS is restricted to `localhost:5173` in development
