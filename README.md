# Newton — Current Events

The agency's current-events service. Scans Reddit, X, LinkedIn, YouTube, RSS,
and the open web for news that affects the business — prospect announcements,
client moves, industry shifts — and serves them as a hyper-current feed scored
for buying-signal value, on a per-account-owner basis.

Built standalone today. Folds into ALF as the "Current Events" tab at v1.0.

## Quickstart (local)

```bash
./run_newton.sh
```

Then open <http://localhost:8080>.

That script creates a venv, installs deps, and runs `uvicorn` on port 8080.
If you'd rather do it yourself:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
uvicorn newton.main:app --host 0.0.0.0 --port 8080 --reload
```


## Deploy on the web

Newton is a web app — running it from a terminal was just dev mode. To put it on
the internet so ALF (or you, from a browser) can talk to it, pick a host:

### Railway (easiest)
1. Push this folder to a GitHub repo.
2. Go to <https://railway.app> → New Project → Deploy from GitHub.
3. Railway reads `railway.json` and `Dockerfile` automatically. Click deploy.
4. Add env var `ANTHROPIC_API_KEY` in the Railway dashboard. (Optional but recommended.)
5. Add a **second service** in the same project: same repo, override start command to `python -m workers.streamer`. That's the continuous news streamer.

You get a `https://newton-xxxx.up.railway.app` URL in ~2 minutes.

### Fly.io
```bash
brew install flyctl
fly auth login
fly launch --no-deploy           # reads fly.toml
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly deploy
```

### Render
Push to GitHub, connect at <https://render.com>. `render.yaml` defines both
the web service and the streamer worker. Set `ANTHROPIC_API_KEY` in the Render dashboard.

### Continuous streaming

The `worker` process (`python -m workers.streamer`) runs the ingestion loop
every `NEWTON_STREAM_INTERVAL_SEC` seconds (default 15 min). Each cycle:
fetches Google News RSS for every prospect's query bundle, scores + classifies
+ freshness-gates each item, and writes the result to disk (`seed_hits.json`)
so the web service picks them up on the next dashboard refresh.

**Source plan (free-tier first):**
- **Google News RSS** — primary source. No key, unlimited. Aggregates from every
  major news outlet, so this alone covers a lot of ground.
- **Industry RSS feeds** — FreightWaves, JOC, Supply Chain Dive, Logistics
  Management. Free. Easy to add to the streamer when you want them.
- **Reddit RSS / PRAW** — free. PRAW key recommended for higher rate limits.
- **YouTube Data API v3** — free tier (10k units/day, ~100 searches/day) covers
  trade-show keynotes, investor-day Q&A, plant-tour videos.
- **X / LinkedIn** — paid only; not used. Stubs remain in code but require keys
  to do anything.

## Embed in ALF

Two paths once Newton is live at a URL:

1. **Quick path — iframe**:
   In ALF, add a tab that renders `<iframe src="https://newton-yourdomain.com" />`.
   CORS is already permissive. Zero work on Newton's side.
2. **Clean path — API**:
   ALF calls Newton's API directly and renders the data in ALF's own UI.
   `GET /current-events/{owner_id}` returns everything the dashboard needs in
   one payload. `POST /alf/notes` is already there to accept ALF's writes back.

The iframe is what you turn on first; the API integration is v1.0.

## Turn on the LLM

Copy `.env.example` to `.env` and set:

```
ANTHROPIC_API_KEY=sk-ant-...
```

With the key in place, the LLM pass runs on every event (classification +
relevance scoring), and the **Draft outreach** button generates real first-touch
messages in your voice. Without the key, everything still works — Newton falls
back to rules-based scoring and produces clearly-marked stub drafts.

## Bring your own prospects

The stub source ships with three demo owners (Dan / Kim / Marco). Replace it
by dropping a `newton/data/prospects.json` file:

```json
{
  "owners": [
    {"id": "o_me", "name": "Your Name", "email": "you@example.com"}
  ],
  "prospects": [
    {
      "id": "p_001", "owner_id": "o_me",
      "name": "Acme Logistics", "priority": true,
      "added_at": "2025-11-01T00:00:00",
      "industry": "3PL",
      "domains": ["acmelogistics.com"],
      "facility_cities": ["Houston"],
      "known_execs": ["Karen Liu"],
      "archive_url_hashes": []
    }
  ]
}
```

Restart the service. Or point at a file elsewhere with
`NEWTON_PROSPECTS_FILE=/path/to/file.json`.

## Run the monitor against real news

```bash
python -m workers.run_monitor --prospect "Tyson Foods" --prospect "General Mills"
```

Fetches Google News RSS for each, scores + classifies + freshness-gates, writes
`newton_run.json`. Add `--no-llm` to skip the LLM pass.

## What's in the UI

- **Owner picker** (top bar) — switches the feed to that owner's prospects.
- **Stats** — count of prospects, priority, cold-start, hits.
- **Watchlists** (left) — Expos, Client news, Prospect news, Industry news,
  Event news, Economic, Transport.
- **Prospect feed** (center) — priority accounts first, then cold-start, then
  active. Each hit shows the buying-signal category badge (color-coded), the
  freshness status, source, and the score.
- **Recommendations** (right) — manufacturers in the news with buying signals
  that aren't on anyone's list yet. Surfaces extra prominently when the owner
  is otherwise quiet.
- **Draft outreach** — opens a modal, generates a first-touch message in the
  owner's voice (LinkedIn / Email / Phone). Save to ideas or send to ALF notes.

## Layout

```
newton/
├── newton/
│   ├── api/              REST + WebSocket handlers
│   │   ├── dashboard.py  /current-events/{owner_id} ← UI talks to this
│   │   ├── prospects.py  /prospects, /prospects/{id}/draft-outreach
│   │   ├── voice.py      /voice/profiles
│   │   ├── alf_actions.py /alf/notes
│   │   ├── ideas.py · recommendations.py · watchlists.py · automation.py · feed.py · ticker.py
│   ├── prospects/        prospect monitor (source, signals, freshness, monitor)
│   ├── recommendations/  recommendation engine
│   ├── ingestion/        per-source workers (reddit, x, linkedin, youtube, rss, web)
│   ├── scoring/          rules.py + llm.py
│   ├── voice/            per-owner-per-channel voice profiles
│   ├── ideas/            ideas vault + LLM outreach drafting
│   ├── integrations/     ALF stub client (queue today, real API at v1.0)
│   ├── store/            in-memory hit cache
│   ├── watchlists/       seeded with the v0.3 watchlist set
│   ├── automation/       per-workflow tier registry
│   ├── data/             seed_hits.json, optional prospects.json override
│   ├── web/              index.html — the live UI
│   ├── events.py         shared event envelope
│   ├── models.py · db.py · config.py · main.py
├── workers/
│   └── run_monitor.py    local CLI runner
├── tests/                75 tests, all green
├── docker-compose.yml    api + worker + postgres + redis (optional)
├── pyproject.toml
├── run_newton.sh         single-command quickstart
└── .env.example
```

## Roadmap

- ✅ **v0.3** — scope cleanup (news/events only; financials live in Milburn)
- ✅ **v0.4** — local runner; real prospect pipeline on Google News RSS
- ✅ **v0.5** — LLM classifier + relevance scorer
- ✅ **v0.6** — outreach drafting + voice profiles + ALF stub queue + **live UI**
- ⏭ **v0.7** — "Mark not relevant" feedback loop (trainable per-prospect)
- ⏭ **v1.0** — ALF integration. Newton becomes ALF's Current Events tab; the
  ALF stub queue gets drained to real ALF API calls.

