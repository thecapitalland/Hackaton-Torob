# Torobche 🌱

**An AI shopping agent for in-person shopping in Tehran.** Persian, RTL, mobile-first.

You describe a vague need → the agent asks up to 3 clarifying questions (quick-reply chips) → shows 3 product
cards (best / budget / premium) → you pick one → the agent lists the shops that sell it (list + map, open-now
badge, distance, in-person payment, transparency badge) → **with your explicit permission** it sends simulated
messages to the shops, parses the replies, re-ranks the shops → and finally builds a trip plan with a backup
shop and a nearby cafe.

## ✨ Highlights

- **Every product, shop and price comes from the real Torob dataset** (raw: 225,903 products · 331,506 offers ·
  6,476 shops; slim catalog: **40,120 products · 115,185 offers · 2,751 shops**). The LLM never invents an item,
  a shop or a price.
- **Specialty market card**: “🏬 The main market in Tehran for this category is X”, with in-data counts
  (e.g. 157 of 244 headphone shops are inside Jomhouri–Hafez). Opening hours are external facts and are
  labelled «اطلاعات عمومی».
- **Out-of-catalog fallback**: when the product is not in the dataset the agent says so honestly, offers real
  alternatives from the catalog and general shopping tips — never an invented shop or price.
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

## 🚀 Quick start (from scratch)

Works with **no API keys at all** (`LLM_MODE=off`, rule-based):

```bash
# 1) venv + deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

# 2) build the slim catalog + markets data from the official CSVs
#    required inputs: shops.csv, products.csv, offers.csv
python backend/scripts/build_catalog.py --src /path/to/torob-dataset --out data/catalog.db
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

Later, add `BOXAPI_API_KEY` (+ optional `NESHAN_API_KEY`) to `.env`, run
`python backend/scripts/smoke_llm.py` once to pick a working base_url/model,
set `LLM_MODE=on` and restart. A missing Neshan key silently falls back
(approximate distance / local cafe list) — the app never breaks.

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
