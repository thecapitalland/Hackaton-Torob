# 🌱 تربچه (Torobche)

**دستیار خرید حضوری در تهران** — از «امروز چی می‌خوام بخرم؟» تا «برنامهٔ رفتنم با کدوم مغازه شروع کنم».

تربچه یک اپلیکیشن وب فارسی و موبایل‌فرست (React + LangGraph + FastAPI) است که با داده‌های واقعی ترب
(دیتاست خام: ۲۲۵٬۹۰۳ کالا · ۳۳۱٬۵۰۶ آفر · ۶٬۴۷۶ فروشگاه؛ خروجی اسلیم: **۴۰٬۱۲۰ کالا · ۱۱۵٬۱۸۵ آفر · ۲٬۷۵۱ فروشگاه**)
کار می‌کند و فقط چیزی را نشان می‌دهد که **واقعاً در دیتابیس هست**.

---

## 🎬 جریان کار

```
پیام کاربر
   ↓  understand (LLM + قوانین)         ← بودجه، دسته، محله، قسطی، امروز؟
   ↓  clarify (interrupt + چیپ)         ← حداکثر ۳ سؤال، آخرین گزینه «مهم نیست»
   ↓  search (SQL روی catalog.db)
   ├─→ recommend        کارت‌های بهترین / اقتصادی / پریمیوم + کارت «بورس تخصصی»
   └─→ out_of_catalog   «در داده‌های ترب نبود» + گزینه‌های واقعی + نکته‌های عمومی
   ↓  select_product → find_stores       فروشگاه‌ها + نقشه + امتیاز شفافیت
   ↓  verify (interrupt تأیید کاربر)     پیام شبیه‌سازی‌شده → خواندن پاسخ → رتبه‌بندی دوباره
   ↓  trip                                برنامهٔ رفتن + پلن ب + کافهٔ نمونه + چک‌لیست
```

## ✨ قابلیت‌ها

- **چت فارسی RTL** با استخراج نیاز (بودجه «۴ میلیون» → ۴٬۰۰۰٬۰۰۰ تومان، محله، قسطی، امروز).
- **سه کارت پیشنهاد**: 🏆 بهترین · 💸 اقتصادی · 💎 پریمیوم — با «چرا این؟» و هشدار قیمت غیرعادی.
- **کارت بازار تخصصی**: «🏬 بورس این کالا در تهران: بورس جمهوری–حافظ» با آمار واقعی از داده‌ها
  (مثلاً هدفون: ۱۵۷ فروشگاه در بازار از ۲۴۴ فروشگاه شهر) و برچسب «اطلاعات عمومی» برای ساعت کاری.
- **انتخاب فروشگاه**: لیست + نقشه (react-leaflet/OSM)، نشان «باز است تا ۲۰:۳۰»، فاصلهٔ هوایی،
  پاساژ/طبقه، پرداخت حضوری، و **نشان شفافیت** (۵ نقطه) — به‌جای امتیاز جعلی فروشنده.
- **پیام‌رسانی با تأیید انسان (HITL)**: قبل از هر پیام یک `interrupt` لاگراف، پیش‌نویس پیام قابل ویرایش،
  سپس پاسخ‌های **شبیه‌سازی‌شده** (موجود / قیمت جدید / ناموجود / بی‌پاسخ) و رتبه‌بندی مجدد.
- **نقشه و مسیر (Update #1)**: ریسپانسیو کامل (موبایل تک‌ستون، تبلت پنل تاشو، ۱۲۸۰+ دوپنله ۴۰/۶۰)،
  فاصله و زمان پیاده روی کارت‌ها («فاصلهٔ تقریبی» در حالت fallback)، خط مسیر روی نقشه،
  جئوکدینگ معکوس («شما نزدیک … هستید») و دیپ‌لینک‌های «مسیریابی در نشان/بلد» —
  کلید `NESHAN_API_KEY` فقط سمت بک‌اند است و نبودش به fallback کامل برمی‌گردد.
- **برنامهٔ رفتن**: خط زمانی، پلن ب، کافه (نشان → OSM → لیست محلی + برچسب منبع)، چک‌لیست و لینک‌های «نشان» و «بلد».
- **Out-of-catalog**: اگر کالایی در داده‌ها نبود، صادقانه می‌گوید، گزینه‌های واقعی از داده‌ها نشان می‌دهد
  و نکته‌های عمومی را با برچسب «اطلاعات عمومی، نه از داده‌های ترب» می‌آورد — بدون ساختن مغازه یا قیمت.
- **کشوی «🧠 چطور به این نتیجه رسیدم؟»**: هر نود گراف با خلاصه و زمان پاسخ.
- با `LLM_MODE=off` **کاملاً کار می‌کند** (حالت قاعده‌محور).

## 🧱 پشته

| بخش | فناوری |
|---|---|
| فرانت‌اند | React 18 · Vite · TypeScript · TailwindCSS · react-leaflet (OSM) · framer-motion · Vazirmatn |
| بک‌اند | Python 3.11+ · FastAPI · LangGraph (SqliteSaver) · OpenAI SDK → BoxAPI · Pydantic |
| داده | SQLite خواندنی (`data/catalog.db`) — ساخته‌شده از CSV رسمی ترب |

---

## 🚀 اجرا

### ۰) از صفر (Run from scratch)

از کلون تمیز تا اجرا — بدون هیچ کلید API.

**ویندوز (PowerShell):**

```powershell
# 1) venv + نصب وابستگی‌ها
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt

# 2) ساخت دیتابیس از دیتاست خام ترب (به shops.csv / products.csv / offers.csv نیاز دارد)
python backend\scripts\build_catalog.py --src <مسیر دیتاست torob-dataset> --out data\catalog.db
python backend\scripts\build_markets.py --catalog data\catalog.db --out data\markets.json

# 3) بیلد فرانت‌اند — خروجی مستقیماً در static/ ساخته می‌شود (همان‌جا که بک‌اند سرو می‌کند)
cd frontend
npm install --cache ..\.npm-cache
npm run build
cd ..

# 4) اجرا بدون LLM و دموِ تکرارپذیر
$env:PYTHONIOENCODING="utf-8"
$env:LLM_MODE="off"; $env:DEMO_MODE="1"; $env:DEMO_NOW="2026-10-22T15:00:00+03:30"
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

**لینوکس / macOS:**

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r backend/requirements.txt
python backend/scripts/build_catalog.py --src /path/to/torob-dataset --out data/catalog.db
python backend/scripts/build_markets.py --catalog data/catalog.db --out data/markets.json
(cd frontend && npm ci && npm run build)
PYTHONIOENCODING=utf-8 LLM_MODE=off DEMO_MODE=1 DEMO_NOW=2026-10-22T15:00:00+03:30 uvicorn backend.app.main:app --port 8000
```

→ `http://127.0.0.1:8000/`

نکته‌های بازتولیدپذیری:

- `vite.config.ts` مقدار `build.outDir` را روی `../static` گذاشته است؛ بنابراین `npm run build` دقیقاً همان جایی
  می‌نویسد که FastAPI سرو می‌کند و کپی دستی لازم نیست. اگر فقط بیلد قدیمی `frontend/dist` موجود باشد،
  `STATIC_DIR` به‌طور خودکار به آن fallback می‌کند.
- ورودی `build_catalog.py` باید سه CSV رسمی `shops.csv`، `products.csv` و `offers.csv` را داشته باشد.
  شمارش مورد انتظار بعد از اسلیم: **۴۰٬۱۲۰ کالا / ۱۱۵٬۱۸۵ آفر / ۲٬۷۵۱ فروشگاه**
  (دیتاست خام: ۲۲۵٬۹۰۳ / ۳۳۱٬۵۰۶ / ۶٬۴۷۶ — کاهش عمدی برای زیر ۱۵۰ مگابایت شدن دیتابیس و حذف پرت‌هاست).
- `build_markets.py` فایل `data/markets.json` را **بازنویسی** می‌کند؛ تغییرات دستی در آن (بازارهای بیرونی،
  ساعت‌های کاری) باید در `MARKET_DEFINITIONS` / `EXTERNAL_MARKETS` داخل اسکریپت اعمال شود، نه فقط در JSON.

بعداً وقتی کلید BoxAPI و (اختیاری) کلید نشان (`NESHAN_API_KEY`) را در `.env` گذاشتی،
یک بار `python backend/scripts/smoke_llm.py` را بزن تا base_url/model درست پیدا شود،
`LLM_MODE=on` را در `.env` بگذار و همان دستور uvicorn را اجرا کن. نبودِ کلید نشان باعث
fallback کامل (فاصلهٔ تقریبی/کافهٔ محلی) می‌شود — اپ هرگز نمی‌شکند.

### ۱) دیتابیس را بساز

```bash
python -m venv .venv
.venv\Scripts\activate            # ویندوز
pip install -r backend/requirements.txt

python backend/scripts/build_catalog.py \
  --src /path/to/torob-dataset \
  --out data/catalog.db

python backend/scripts/build_markets.py \
  --catalog data/catalog.db --out data/markets.json
```

`build_catalog.py` چاپ می‌کند: قیمت‌های خارج از بازه حذف شدند، آفرهای پرت (مثل ۲۲٬۹۵۰٬۰۰۰ برای R50i)
حذف شدند، برای هر (کالا، فروشگاه) فقط ارزان‌ترین آفر ماند و در صورت لزوم دیتابیس تا زیر ۱۵۰ مگابایت
کوچک شد.

> فایل `data/catalog.db` داخل گیت نیست (حجمش زیاد است)؛ با همین دستور ساخته می‌شود.

### ۲) بک‌اند

```bash
cp .env.example .env      # کلید BOXAPI را داخلش بگذار
uvicorn backend.app.main:app --reload --port 8000
```

`GET http://localhost:8000/api/health` →
`{"ok":true,"catalog_rows":{...},"llm_mode":"on","tz":"Asia/Tehran"}`

### ۳) فرانت‌اند

```bash
cd frontend
npm install
npm run dev      # http://localhost:5173  (پروکسی /api به 8000)
```

### ۴) داکر (همان چیزی که روی Liara دیپلوی می‌شود)

```bash
docker build -t torobche .
docker run -p 8000:8000 --env-file .env torobche
```

## ☁️ دیپلوی روی Liara

```bash
npm i -g @liara/cli
liara login
liara deploy            # liara.json: platform=docker, port=8000
liara env set BOXAPI_API_KEY=... LLM_MODE=on
curl https://<app>.liara.run/api/health
```

قبل از دیپلوی حتماً `data/catalog.db` را ساخته باشید، چون ایمیج از همین پوشه ساخته می‌شود.

## 🧪 تست

```bash
pytest backend/tests -q
# تست‌های واحد فرانت‌اند (helpers خالص: قیمت، ساعت، آیکن، فیلتر بازار، خط سفر)
cd frontend && npm test
```

| فایل | چه چیزی را می‌سنجد |
|---|---|
| `test_search.py` | «هدفون بلوتوثی زیر ۴ میلیون» → R50i در ۳ تای اول، «گوشی سامسونگ» → A07/A17، «A55» → گوشی نه LCD، توکنایز «لپ تاپ» (بدون «تاپ»)، ۳ کارت لپ‌تاپ |
| `test_clarify.py` | پاسخ «جمهوری» به سؤال محله → `slots.location`، «مهم نیست» → skip و رسیدن به کارت‌ها، پاسخ بودجه قبل از understand |
| `test_hours.py` | مهریسا نوین پنجشنبه ۱۵:۰۰ → «باز است تا ۲۰:۳۰» با ارقام فارسی، جمعه → بسته، آوان آران → نامشخص، ترجمهٔ ساعت بازارها |
| `test_ooc.py` | زعفران/زعفرون → بازار سید اسماعیل، حذف گزینه‌های بی‌ربط (بدون پیجر/عطر)، سه‌تار → گیتار، حذف «تومان» از نکته‌ها |
| `test_seller.py` | «طبقه» پاسخ شبیه‌سازی‌شده با `floor` واقعی فروشگاه یکی است |
| `test_api.py` | کل مسیر: چت → سؤال → کارت → فروشگاه → تأیید پیام → برنامهٔ رفتن (با `LLM_MODE=off`) |
| `frontend/src/lib/pure.test.ts` | `formatPrice` (گروه‌بندی fa-IR)، `faHours`، آیکن دسته، نام بهترین فروشگاه تأییدشده، فیلتر شعاع بازار، خط dashed سفر |

## 🔐 قوانین سخت (که در کد رعایت شده‌اند)

1. هر کالا/فروشگاه/قیمت نمایش‌داده‌شده **از دیتابیس** می‌آید؛ LLM هیچ‌وقت چیزی نمی‌سازد.
2. هیچ پیامی بدون تأیید کاربر (`interrupt`) ارسال نمی‌شود.
3. همهٔ پاسخ‌های فروشنده با برچسب «پاسخ شبیه‌سازی‌شده» نمایش داده می‌شوند.
4. شماره‌های تلفن دیتاست (جعلی) هرگز نمایش یا استفاده نمی‌شوند.
5. وضعیت باز بودن فقط `open | closed | unknown` (منطقهٔ زمانی تهران)؛ نبودِ ساعت ⇒ «نامشخص».
6. داده‌های بیرون از ترب با برچسب «اطلاعات عمومی» مشخص می‌شوند (بازار رضا اصلاً استفاده نمی‌شود).
7. برنامه با `LLM_MODE=off` هم کامل کار می‌کند.

## 📁 ساختار پروژه

```
torobche/
├── backend/
│   ├── app/
│   │   ├── main.py        # FastAPI + اندپوینت‌ها
│   │   ├── graph.py       # گراف LangGraph
│   │   ├── state.py       # تعریف State
│   │   ├── llm.py         # کلاینت BoxAPI (+ fallback)
│   │   ├── prompts.py     # ۷ پرامپت
│   │   ├── rules.py       # fallback های قاعده‌محور
│   │   ├── normalize.py   # نرمال‌سازی فارسی
│   │   ├── data_static.py # بارگذاری داده‌های ثابت
│   │   └── tools/         # catalog, hours, geo, ranking, transparency,
│   │                      # seller_sim, markets, ooc, cafes
│   ├── scripts/           # build_catalog.py, build_markets.py, smoke_llm.py
│   └── tests/
├── frontend/src/
│   ├── App.tsx, api.ts, format.ts, copy.fa.ts, types.ts
│   └── components/        # Chat, ProductCards, MarketCard, Stores, MapView,
│                          # PermissionSheet, Inbox, TripPlan, TraceDrawer, …
├── data/                  # catalog.db (ساخته می‌شود), markets.json, mock_*.json
├── Dockerfile  liara.json  .env.example
```

## 🎥 سناریوی دمو

۱. «یه هدفون بلوتوثی خوب می‌خوام زیر ۴ میلیون، امروز حضوری نزدیک فردوسی»
۲. یک چیپ: «آره، قسطی»
۳. سه کارت (بهترین = R50i) + کارت «بورس جمهوری–حافظ، ۱۵۷ فروشگاه»
۴. فروشگاه‌ها: نقشه، نشان «باز»، برگهٔ شفافیت
۵. انتخاب دو فروشگاه → برگهٔ اجازه → تأیید → نخست‌های گفتگو با پاسخ (۳٫۱۵ میلیون / ۴٫۱ میلیون)
۶. بنر «۱ فروشگاه تأیید کرد» → برنامهٔ رفتن + کافه
۷. (اختیاری) «زعفران و ادویه» → کارت «در داده‌های ترب نبود»

با `DEMO_MODE=1` و `DEMO_NOW=2026-10-22T15:00:00+03:30` نتیجه‌ها کاملاً تکرارپذیرند.

## 📄 مجوز

MIT — [LICENSE](LICENSE)
