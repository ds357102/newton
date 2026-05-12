# Deploying Newton — step by step

Goal: take the code in this folder and turn it into a URL you can open in a browser. ~10 minutes the first time.

We'll deploy to **Railway** because it's the cleanest UI and the cheapest way to run a small web service with a worker baked in (~$5/month). Fly.io and Render walkthroughs are at the bottom — they work but have rougher edges.

## 0. What you need

- A GitHub account.
- A Railway account (free signup — they'll ask for a credit card eventually but the trial credit covers Newton's first month).
- An Anthropic API key from <https://console.anthropic.com> (optional but recommended — without it the LLM bits no-op gracefully).

## 1. Put the code on GitHub

Open Terminal. Go to the newton folder:

```bash
cd "/Users/dscherrer/Library/Application Support/Claude/local-agent-mode-sessions/.../outputs/newton"
```

Initialize git and commit:

```bash
git init
git add .
git commit -m "Newton v0.6 — initial deploy"
```

Make a GitHub repo:
1. Go to <https://github.com/new>.
2. Name: `newton`. Visibility: **Private** (recommended — keeps the AI prompts and prospect data out of public view).
3. Do NOT check "Add a README" or any other initialize options — we already have all that.
4. Click Create.

GitHub shows you a "push existing repository" snippet. Copy-paste it in Terminal. It looks like:

```bash
git remote add origin https://github.com/YOUR-USERNAME/newton.git
git branch -M main
git push -u origin main
```

GitHub may ask you to log in. Done with this step when `git push` says `Branch 'main' set up to track 'origin/main'`.

## 2. Deploy on Railway

1. Go to <https://railway.app> and sign in with GitHub.
2. Click **+ New Project** (top-right).
3. Pick **Deploy from GitHub repo**.
4. Authorize Railway to access your repos if prompted, then pick the `newton` repo.
5. Railway reads `railway.json` and the `Dockerfile` automatically. It starts building. Wait ~3 minutes — you'll see logs scrolling.
6. When the build finishes, you'll see a green "Active" status.

**Get a public URL:**
1. Click the Newton service tile.
2. Settings tab → Networking → **Generate Domain**.
3. Railway gives you something like `newton-production-a1b2.up.railway.app`.
4. Open it in a new tab. The Newton UI should load.

## 3. Add your Anthropic key

In the Railway service:
1. Variables tab → **+ New Variable**.
2. Name: `ANTHROPIC_API_KEY`. Value: `sk-ant-...` (paste your key).
3. Click Add. Railway redeploys automatically (~30s).

Refresh the Newton UI. Top-right should now show **LLM ON** instead of LLM OFF.

That's it. You're live.

## 4. Bring your real prospects (optional)

Edit `newton/data/prospects.json` locally:

```json
{
  "owners": [
    {"id": "o_dan", "name": "Dan Scherrer", "email": "dan@example.com"}
  ],
  "prospects": [
    {
      "id": "p_real_001",
      "owner_id": "o_dan",
      "name": "Tyson Foods",
      "priority": true,
      "added_at": "2025-11-01T00:00:00",
      "industry": "food manufacturing",
      "domains": ["tysonfoods.com"],
      "facility_cities": ["Springdale", "Memphis"],
      "known_execs": [],
      "archive_url_hashes": []
    }
  ]
}
```

Commit and push:

```bash
git add newton/data/prospects.json
git commit -m "Add real prospects"
git push
```

Railway auto-redeploys in ~1 minute. Refresh the UI — your prospects show up in the owner picker.

## 5. What's running in there

One Railway service runs both:
- The **web UI + API** (what you visit in the browser).
- The **streamer**, as a background task inside the same process. Every 15 minutes it fetches Google News RSS + 37 industry feeds + 20 Reddit feeds, attributes hits to your prospects, and writes them to disk.

You'll see the first cycle's results within ~15 minutes of the service coming up.

## Verify it's actually streaming

In Railway, click the service → **Deployments** → click the active deployment → **View Logs**.

You should see (every 15 min):

```
newton.streamer: cycle starting: 3 prospects, 37 industry feeds, 20 reddit feeds
newton.streamer:   industry: fetched 412; 8 attributed
newton.streamer:   reddit: fetched 195; 2 attributed
newton.streamer: cycle done: 27 hits surfaced (from 487 unique URLs)
```

If you see those lines, the streamer is alive and feeding the UI.

## When things break

**Build fails** → Open the deployment logs. Send me the last 30 lines and I'll diagnose.

**UI loads but no prospects show up** → Open `https://YOUR-URL/healthz`. If `llm_configured: false` and you set the key, the variable name might be wrong (`ANTHROPIC_API_KEY`, exactly). If `cached_hits: 0`, the streamer hasn't run yet — wait 15 min, or restart the deployment.

**Streamer logs show lots of failed fetches** → Some RSS feeds change URLs. Send me the failure list and I'll prune.

**Costs surprise you** → bump `NEWTON_STREAM_INTERVAL_SEC` to `1800` (30 min) or `3600` (1 hr) in Variables. Halves or quarters the cost.

---

## Alternate hosts (skip if Railway works)

### Fly.io (free tier)

```bash
brew install flyctl
fly auth login
cd <newton folder>
fly launch --no-deploy        # reads fly.toml, names the app
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
fly deploy
fly open
```

### Render

Push to GitHub, then at <https://render.com>:
1. + New → Blueprint → connect the repo. Render reads `render.yaml`.
2. Set `ANTHROPIC_API_KEY` in the Render dashboard.
3. Render's free tier sleeps web services after 15 min of inactivity — paid tier ($7/mo) keeps them warm.

---

## Connecting this to ALF (later)

Once Newton has a URL (say `https://newton.yourdomain.com`), there are two ways ALF can pull it in:

1. **Iframe** — fastest. In ALF, add a "Current Events" tab whose content is `<iframe src="https://newton.yourdomain.com" />`. CORS is already permissive. Zero work on Newton's side.
2. **API** — cleaner long-term. ALF calls `GET /current-events/{owner_id}` on Newton's domain and renders the data in ALF's own UI. `POST /alf/notes` is there to accept writes from Newton back into ALF.

Iframe is what you turn on first.
