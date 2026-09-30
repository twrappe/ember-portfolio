# EMBER

EMBER connects to your Oura Ring and quietly tracks how your body is doing day to day — sleep, heart rate variability, resting heart rate, and temperature. It learns what's normal for *you* specifically, then surfaces when something starts to shift, before you necessarily feel it.

It's built for people who want to stay ahead of their own patterns. Each morning it runs automatically, compares yesterday's data to your personal 30-day baseline, and produces a plain-language summary you can read in under a minute.

## How it works

```
Oura Ring → pull_data.py → score_baseline.py → summarize.py
                                                       ↓
                              api.py ← data/   mood_server.py
                                ↓
                         React dashboard
```

1. **Collect** — pulls your daily readiness and sleep data from Oura
2. **Compare** — measures how today's readings sit against your recent personal baseline
3. **Summarise** — writes a short, plain-language daily summary using Claude AI
4. **Visualise** — live dashboard showing your trends, notices, and biometric charts
5. **Log** — optional morning and evening check-ins to capture how you're feeling

## Stack

| Layer | Technology |
|---|---|
| Data pipeline | Python, pandas, Oura API v2 |
| Auth | OAuth 2.0 + PKCE (S256) |
| AI summaries | Anthropic Claude |
| REST API | FastAPI + uvicorn |
| Dashboard | React, Vite, Recharts |
| E2E tests | Playwright |

## Setup

### 1. Prerequisites

- Python 3.10+
- Node.js 18+
- An [Oura Ring](https://ouraring.com) and developer account
- An Oura OAuth app with redirect URI set to `http://localhost:8080/callback`
- An [Anthropic API key](https://console.anthropic.com/) for daily summaries

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```
OURA_CLIENT_ID=your_client_id
OURA_CLIENT_SECRET=your_client_secret
OURA_REDIRECT_URI=http://localhost:8080/callback
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### 4. Authenticate with Oura

Run once to complete the OAuth flow and store your tokens:

```bash
python auth.py
```

This opens a browser, completes authorisation, and saves your tokens to `.env` automatically.

### 5. Run the pipeline

```bash
python run_ember.py
```

This pulls your latest data, scores it against your baseline, and writes a summary. Run this daily — or set it on a schedule. Logs go to `logs/ember.log`, data to `data/`.

### 6. Start the dashboard

**Terminal 1 — API:**
```bash
uvicorn api:app --reload --port 8000
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### 7. Daily check-ins (optional)

Short morning and evening forms to record how you're feeling. Adds personal context to the biometric data.

```bash
uvicorn mood_server:app --host 0.0.0.0 --port 8001
```

- Morning: `http://localhost:8001/morning`
- Evening: `http://localhost:8001/evening`
- Accessible from your phone on the same Wi-Fi network

## Project structure

```
auth.py              # OAuth 2.0 + PKCE authentication
token_manager.py     # Token validation and auto-refresh
pull_data.py         # Incremental Oura data collection
score_baseline.py    # Personal baseline scoring
summarize.py         # AI-generated daily summaries (Claude)
run_ember.py         # Pipeline orchestrator
api.py               # FastAPI REST API for the dashboard
mood_server.py       # Morning/evening check-in server
frontend/            # React + Vite dashboard
data/                # Your data, stored locally (gitignored)
logs/                # Run logs (gitignored)
.env                 # Your credentials (gitignored — never commit)
.env.example         # Credential template
```

## Notes

- Tokens refresh automatically — you only need to re-run `auth.py` if access is revoked.
- All your data stays on your machine. Nothing is sent anywhere except the Oura and Anthropic APIs.
- See [privacy.md](privacy.md) for full details.

## How it works

```
Oura Ring → pull_data.py → score_baseline.py → summarize.py
                                                       ↓
                              api.py ← data/   mood_server.py
                                ↓
                         React dashboard
```

1. **Collect** — pulls your daily readiness and sleep data from Oura
2. **Compare** — measures how today's readings sit against your recent personal baseline
3. **Summarise** — writes a short, plain-language daily summary using Claude AI
4. **Visualise** — live dashboard showing your trends, notices, and biometric charts
5. **Log** — optional morning and evening check-ins to capture how you're feeling

## Stack

| Layer | Technology |
|---|---|
| Data pipeline | Python, pandas, Oura API v2 |
| Auth | OAuth 2.0 + PKCE (S256) |
| AI summaries | Anthropic Claude |
| REST API | FastAPI + uvicorn |
| Dashboard | React, Vite, Recharts |
| E2E tests | Playwright |

## Setup

### 1. Prerequisites

- Python 3.10+
- Node.js 18+
- An [Oura Ring](https://ouraring.com) and developer account
- An Oura OAuth app with redirect URI set to `http://localhost:8080/callback`
- An [Anthropic API key](https://console.anthropic.com/) for AI summaries

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```
OURA_CLIENT_ID=your_client_id
OURA_CLIENT_SECRET=your_client_secret
OURA_REDIRECT_URI=http://localhost:8080/callback
ANTHROPIC_API_KEY=your_anthropic_api_key
```

### 4. Authenticate with Oura

Run once to complete the OAuth 2.0 + PKCE flow and store tokens:

```bash
python auth.py
```

This opens a browser, completes authorisation, and saves `OURA_ACCESS_TOKEN` and `OURA_REFRESH_TOKEN` to `.env` automatically.

### 5. Run the pipeline

Pulls data, scores deviations, and generates an AI summary:

```bash
python run_ember.py
```

Logs are written to `logs/ember.log`. Output CSVs and summaries are saved to `data/`.

### 6. Start the dashboard

**Terminal 1 — REST API:**
```bash
uvicorn api:app --reload --port 8000
```

**Terminal 2 — React frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

### 7. Mood logging (optional)

**Terminal 3 — Mood server:**
```bash
uvicorn mood_server:app --host 0.0.0.0 --port 8001
```

Morning form: `http://localhost:8001/morning`
Evening form: `http://localhost:8001/evening`

## Project structure

```
auth.py              # OAuth 2.0 + PKCE authentication
token_manager.py     # Token validation and auto-refresh
pull_data.py         # Incremental Oura data collection
score_baseline.py    # Rolling z-score deviation scoring
summarize.py         # AI-generated clinical summaries (Claude)
run_ember.py         # Pipeline orchestrator
api.py               # FastAPI REST API for the dashboard
mood_server.py       # Morning/evening mood logging server
frontend/            # React + Vite dashboard
data/                # Local data storage (gitignored)
logs/                # Pipeline run logs (gitignored)
.env                 # Credentials (gitignored — never commit)
.env.example         # Environment variable template
```

## Notes

- Tokens refresh automatically — re-authentication is only needed if the refresh token expires.
- All biometric data is stored locally and never transmitted beyond the Oura and Anthropic APIs.
- See [privacy.md](privacy.md) for full data handling details.
