# Torobche 🌱

**An AI shopping agent for in-person shopping in Tehran.** Persian, RTL, mobile-first, with location-first onboarding and chat-based product discovery.

You describe a vague need → the agent asks up to 3 clarifying questions (quick-reply chips) → shows 3 product
cards (best / budget / premium) → you pick one → the agent lists the shops that sell it (list + map, open-now
badge, distance, in-person payment, transparency badge) → **with your explicit permission** it sends simulated
messages to the shops, parses the replies, re-ranks the shops → and finally builds a trip plan with a backup
shop and a nearby cafe.

The flow starts with **“Where are you?”**: use GPS, type a neighbourhood, or pick a point on a map. Search results stay in the chat; the shop map opens from a compact thumbnail.

## ✨ Highlights

- **Every product, shop and price comes from the real Torob dataset** (raw: 225,903 products · 331,506 offers ·
  6,476 shops; slim catalog: **40,120 products · 115,185 offers · 2,751 shops**). The LLM never invents an item,
  a shop or a price.
- **Specialty market card**: “🏬 The main market in Tehran for this category is X”, with in-data counts
  (e.g. 157 of 244 headphone shops are inside Jomhouri–Hafez). Opening hours are external facts and are
  labelled «اطلاعات عمومی».
- **Out-of-catalog fallback**: when the product is not in the dataset the agent says so honestly, offers real
  alternatives from the catalog and general shopping tips — never an invented shop or price.
- **Offline Tehran neighbourhood lookup**: around 60 neighbourhoods and aliases are bundled in
  `backend/app/data/tehran_neighbourhoods.json`. Neshan Search is merged in when configured; no API key is required.
- **Radius filters**: 2, 5 and 10 km, or all Tehran (the default), filter both shop results and the map. Empty radii offer a one-tap expansion.
- **Editable search summary**: product, budget, neighbourhood and radius stay visible; natural-language budget/location edits keep the current session.
- **Selective comparison**: select 2–4 product cards for a computed price range, median, seller count and visual “Agent analysis” verdict. The direct “X or Y?” path remains available.
- **Relevance-preserving search**: the core product noun remains required as secondary filters relax, including the one-shop rung. Aliases such as `ketooni/katani` and `Nike/Nayki` are expanded; accessory titles (covers, waxers, insoles, etc.) are excluded unless the user asked for that accessory.
- **Human in the loop**: no message is ever sent without a LangGraph `interrupt` approval; the user sees and
  can edit the exact message first.
- **Transparent evidence instead of fake reviews**: a 0–5 “information completeness” meter with the signals
  listed (declared hours, in-person payment, warranty, price freshness, number of sellers) — explicitly *not*
  a seller rating.
- **Deterministic demo**: `DEMO_MODE=1` + `DEMO_NOW` freeze the clock and the seller script, so the demo
  video is reproducible.
- Works fully with **`LLM_MODE=off`** (rule based fallbacks).

## 🧱 Stack

React 18 · Vite · TypeScript · TailwindCSS · react-leaflet (OSM) · framer-motion · Vazirmatn ·
FastAPI · LangGraph (+ SQLite checkpointer) · OpenAI SDK → BoxAPI · SQLite (read-only catalog)

## UX smoke screenshots

Desktop (1440×900) and mobile (390×844) captures for onboarding, location, result map, radius, summary, OOC suggestions and selected comparison are in [docs/ux](docs/ux/).

## 🚀 Quick start (from scratch)

Works with **no API keys at all** (`LLM_MODE=off`, rule-based):

```bash
# 0) fetch the real catalog from Git LFS (required on a fresh clone)
git lfs install && git lfs pull

# 1) venv + deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 2) build/update markets
python backend/scripts/build_markets.py --catalog data/catalog.db --out data/markets.json

# 3) build the SPA - vite writes directly to ../static, where FastAPI serves it
(cd frontend && npm ci && npm run build)

# 4) run rule-based + repeatable demo
PYTHONIOENCODING=utf-8 LLM_MODE=off DEMO_MODE=1 DEMO_NOW=2026-10-22T15:00:00+03:30 \
  uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

→ `http://127.0.0.1:8000/`

Windows: use `python -m venv .venv`, `.venv\Scripts\Activate.ps1`, then set
`$env:PYTHONIOENCODING="utf-8"; $env:LLM_MODE="off"; $env:DEMO_MODE="1"; $env:DEMO_NOW="2026-10-22T15:00:00+03:30"`
before the same uvicorn command.

Reproducibility notes:

- `vite.config.ts` sets `build.outDir` to `../static` with `emptyOutDir: true`, so a plain
  `npm run build` lands exactly where the backend serves it. `STATIC_DIR` falls back to
  `frontend/dist` only when `static/` is missing (older builds).
- Expected catalog counts after slimming: **40,120 products / 115,185 offers / 2,751 shops**
  (raw dataset: 225,903 / 331,506 / 6,476). The reduction is intentional: outlier prices and
  duplicate offers are dropped and the SQLite file must stay under 150 MB.
- `build_markets.py` **overwrites** the committed `data/markets.json`; edit the curated
  `MARKET_DEFINITIONS` / `EXTERNAL_MARKETS` in the script, not just the JSON file.
- The real `data/catalog.db` (about 126.6 MiB) is stored in Git LFS. Run `git lfs pull` after cloning.
  Startup validates the SQLite integrity/schema and non-empty products/offers/shops. If missing,
  zero-byte or invalid, it rebuilds to a temporary file when `TOROB_DATASET_DIR` points to a folder
  containing `shops.csv`, `products.csv`, and `offers.csv`; otherwise startup stops with an actionable error.
  Manual rebuild: `python backend/scripts/build_catalog.py --src /path/to/torob-dataset --out data/catalog.db`.

### GapGPT (default provider)

Set `BOXAPI_API_KEY` in `.env`; the default compatible endpoint is `https://api.gapgpt.app/v1`.
```dotenv
BOXAPI_BASE_URL=https://api.gapgpt.app/v1
LLM_MODE=on
LLM_MODEL=deepseek-v4.1-flash
LLM_MODEL_FALLBACK=gpt-4.1-mini
LLM_TIMEOUT=6
LLM_STRUCTURED=auto
LLM_COST_LOG=1
DECIDER_MODEL=typesafe/jev-1.14
DECIDER_TIMEOUT=4
MESSAGE_BUDGET_S=8
```
The example configuration uses `deepseek-v4.1-flash` with `gpt-4.1-mini` fallback and the
action-only `typesafe/jev-1.14` decider. Jev proposes an action; deterministic rules/catalog
guard category, brand, budget, neighbourhood and radius. Decisions are Pydantic-validated and
fall back to rules on timeout, 429 or invalid output. One message shares an 8-second budget
and makes at most two model requests.

Example GapGPT prices (USD per million input/output tokens): DeepSeek v4.1 Flash `$0.15/$0.60`,
GPT-4.1 Mini `$0.40/$1.60`, Jev `$0.042/$0`. Redacted `llm_call` records include usage and cost;
`GET /api/debug/llm-stats` is available only when `DEBUG=1`.
`LLM_STRUCTURED=auto` detects JSON schema/object support at runtime. `python backend/scripts/smoke_llm.py`
contacts only the configured `BOXAPI_BASE_URL`; add `--jev` to smoke `/systemone` separately. It never
sends credentials to alternate hosts. With no key or `LLM_MODE=off`, deterministic rules keep the app working.
Pricing/wallet details were checked on 2026-10-23; the published minimum top-up was 5,000 toman and the displayed USDT rate was about 273,564 toman.

Chat decisions use a typed eight-action union (`new_search`, `refine`, `change_radius`, `change_location`,
`compare`, `haggle`, `ooc`, `chitchat`); rules both provide fallback and guard category/brand/budget/location.
Regenerate the shared schemas and TypeScript types with `python backend/scripts/export_schemas.py` and
`cd frontend && npm run gen:types`. OOC uses a fixed honest sentence and only whitelisted Tehran-market routes.
A missing Neshan key silently falls back (approximate distance / local cafe list).

### Optional OpenRouter configuration

```dotenv
BOXAPI_BASE_URL=https://openrouter.ai/api/v1
LLM_MODEL=poolside/laguna-s-2.1:free
LLM_MODEL_FALLBACK=google/gemma-4-31b-it:free
```

Free models have daily quotas and may return HTTP 429. The client shares one `LLM_TIMEOUT`
deadline across at most two requests, tries the fallback model on failure, and then uses deterministic rules.

```bash
# 2) backend (with keys)
cp .env.example .env      # put your BOXAPI_API_KEY here
uvicorn backend.app.main:app --reload --port 8000

# 3) frontend (dev mode)
cd frontend && npm install && npm run dev
```

Health check: `curl http://localhost:8000/api/health`

## 🧪 Tests

```bash
pytest backend/tests -q
cd frontend && npm test     # pure helpers: prices, hours, icons, market filter, trip line
```

The backend suite covers the clarify loop (location/budget answers and «مهم نیست» skips),
laptop tokenization, out-of-catalog alternatives, seller-floor consistency and the full
approval → trip journey with `LLM_MODE=off`.

## ☁️ Deploy (Liara, Docker)

```bash
npm i -g @liara/cli && liara login
liara deploy
liara env set BOXAPI_API_KEY=... LLM_MODE=on
curl https://<app>.liara.run/api/health
```

## 🔒 Hard rules honoured by the code

1. Product / shop / price always come from the database.
2. No message is sent without a user approval interrupt.
3. Every seller reply is labelled «پاسخ شبیه‌سازی‌شده» (simulated).
4. The dataset phone numbers are fake and are never displayed or used.
5. Open status is `open | closed | unknown` in `Asia/Tehran`; missing hours are never “open”.
6. External (web) facts are labelled «اطلاعات عمومی»; Tehran only — Bazar-e Reza (Mashhad) is never used.
7. The whole flow works with `LLM_MODE=off`.

📄 MIT License — see [LICENSE](LICENSE). Persian docs: [README.md](README.md)
