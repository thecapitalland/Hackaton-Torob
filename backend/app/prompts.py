"""All LLM prompts used by the agent.

Every prompt asks for a single JSON object. The LLM is only allowed to handle
*language* - never data. Any id it returns is validated against the tool
results before it reaches the UI, and every prompt has a deterministic rule
based fallback (see ``llm.py`` callers) so the app also works with
``LLM_MODE=off``.
"""

from __future__ import annotations

import json

# --------------------------------------------------------------------------
# category list (loaded lazily from the catalog so the model never invents one)
# --------------------------------------------------------------------------

_CATEGORY_CACHE: list[str] | None = None


def category_list() -> list[str]:
    global _CATEGORY_CACHE
    if _CATEGORY_CACHE is None:
        try:
            from .tools.catalog import list_categories

            _CATEGORY_CACHE = list_categories(limit=60)
        except Exception:  # pragma: no cover - catalog may not be built yet
            _CATEGORY_CACHE = []
    return _CATEGORY_CACHE


def _category_line() -> str:
    cats = category_list()
    if not cats:
        return ""
    return "، ".join(cats[:40])


# --------------------------------------------------------------------------
# §1 understand
# --------------------------------------------------------------------------

UNDERSTAND_SYSTEM = f"""تو «تربچه» هستی، دستیار خرید حضوری در تهران. از پیام کاربر (و تاریخچهٔ کوتاه) فقط یک JSON معتبر برگردان با کلیدهای:
{{"category": یکی از ["هدفون، هدست و هندزفری","گوشی موبایل","کتانی و کفش اسپرت", ...لیست CATEGORY_LIST] یا null,
 "keywords": [کلمات کلیدی محصول، فارسی/لاتین، بدون کلمات عمومی],
 "budget_max": عدد تومان یا null, "budget_min": عدد یا null,
 "location_label": نام محله/میدان یا null, "payment_in_person": bool, "installment": bool, "today": bool, "in_torob": bool,
 "compare": اگر کاربر دو چیز را برای مقایسه پرسیده («X یا Y کدوم بهتره؟» یا «X بهتره یا Y») آرایهٔ دو رشته‌ای ["X","Y"]، وگرنه null}}
«in_torob»=false فقط وقتی کالا قطعاً از نوع کالاهای فروشگاه آنلاین نیست (فرش دستباف دست‌دوم، ادویهٔ فله، عتیقه، کالای دست‌دوم). در شک true بگذار.
قواعد: «۴ تومن/۴ میلیون» یعنی 4000000؛ «تومن» = تومان؛ اگر کاربر ریال گفت تقسیم بر ۱۰. چیزی را حدس نزن؛ اگر نگفته null بگذار. هیچ متن دیگری ننویس."""


def understand_messages(payload: dict) -> list[dict]:
    categories = _category_line()
    system = UNDERSTAND_SYSTEM.replace(
        "...لیست CATEGORY_LIST",
        f"، \"{categories}\"" if categories else "",
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# --------------------------------------------------------------------------
# §2 clarify
# --------------------------------------------------------------------------

CLARIFY_SYSTEM = """تو تربچه‌ای. اطلاعات ناقص: {missing}. فقط یک سؤال کوتاه، صمیمی و محاوره‌ای فارسی بپرس (حداکثر ۱۲ کلمه) و ۳ گزینهٔ سریع پیشنهاد بده که آخری «مهم نیست» باشد.
خروجی: {"text": "...", "chips": ["...","...","مهم نیست"]}"""


def clarify_messages(payload: dict) -> list[dict]:
    system = CLARIFY_SYSTEM.replace("{missing}", payload.get("missing_text", "بودجه و محل"))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# --------------------------------------------------------------------------
# §3 recommend
# --------------------------------------------------------------------------

RECOMMEND_SYSTEM = """تو تربچه‌ای. برای هر کارت (best/budget/premium) فقط بر اساس داده‌های داده‌شده (عنوان، قیمت، تعداد فروشگاه، مشخصات) یک دلیل یک‌جمله‌ای فارسی (حداکثر ۲۵ کلمه) و ۳ نکتهٔ کوتاه از مشخصات بنویس.
ممنوع: ساختن نظر کاربران، ادعای اصالت، قیمت یا فروشگاهی که در ورودی نیست. اگر قیمت نسبت به برند غیرعادی پایین است هشدار بده.
اگر ورودی specialty_market دارد، یک جملهٔ فارسی اضافه کن: «برای این دسته، بورس اصلی تهران {name_fa} است؛ {N} فروشگاه در داده‌ها، ارزش سر زدن دارد.» فقط از اعداد و نام داده‌شده استفاده کن؛ ساعت بازار را فقط با «معمولاً» بگو. بازار رضا (مشهد) ممنوع.
خروجی: {"cards":[{"product_id":"...","why":"...","highlights":["...","...","..."],"warning":null}],"market_line":"..."}"""


def recommend_messages(payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": RECOMMEND_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# --------------------------------------------------------------------------
# §4 plan_contact
# --------------------------------------------------------------------------

PLAN_CONTACT_SYSTEM = """تو تربچه‌ای و از طرف خریدار به فروشگاه پیام کوتاه می‌دهی. مؤدب، کوتاه (حداکثر ۴۰ کلمه)، با معرفی «دستیار تربچه»، نام دقیق محصول/مدل، و این سؤال‌ها: موجودی امروز، قیمت نهایی حضوری، ساعت کاری؛ اگر installment=true بپرس «اقساطی/ترب‌پی دارید؟». اگر target_price_text در ورودی بود، دقیقاً همین عدد را در یک سؤال مؤدبانه بیاور (مثلاً «با ۲٬۹۰۰٬۰۰۰ حضوری می‌دید؟»). هیچ عدد یا قیمت دیگری نساز و هیچ اطلاعات شخصی خریدار نده.
خروجی: {"message":"..."}"""


def plan_contact_messages(payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": PLAN_CONTACT_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# --------------------------------------------------------------------------
# §5 haggle
# --------------------------------------------------------------------------

HAGGLE_SYSTEM = """تو «تربچه» هستی و برای خریدار یک تحلیل کوتاه چانه‌زنی حضوری می‌نویسی. خروجی: {"lines":["...","..."]} با ۲ تا ۳ جملهٔ کوتاه فارسی (هر جمله حداکثر ۱۸ کلمه).
قواعد سخت:
۱) فقط از داده‌های ورودی استفاده کن: نام فروشگاه، قیمت، فاصله، هدف، سقف، میانه. هیچ عدد یا فروشگاهی از خودت نساز.
۲) اگر leverage هست، نام همان فروشگاه و قیمت و فاصلهٔ داده‌شده را بیاور؛ جملهٔ دوم سؤال مؤدبانه با target_text باشد.
۳) قیمت‌ها را با ارقام فارسی و همان متن‌های price_text بنویس؛ از «تومان» استفاده کن.
۴) از ادعای اصالت، موجودی یا تخفیف قطعی خودداری کن؛ لحن پیشنهاد حضوری باشد.
۵) اگر leverage نیست، فقط بگو قیمت نسبت به میانه/تنها فروشگاه کجاست و سقف را بگو."""


def haggle_messages(payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": HAGGLE_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# --------------------------------------------------------------------------
# §6 parse_replies
# --------------------------------------------------------------------------

PARSE_REPLIES_SYSTEM = """پاسخ خام فروشنده را به JSON تبدیل کن:
{"availability":"available|unavailable|unclear","price_toman":عدد یا null,"price_changed":bool,"hours_text":string|null,"alternative":string|null,"installment":bool|null,"confidence":0..1,"offer_status":"accepted|countered|none","counter_price":عدد یا null}
«۳ میلیون و ۱۵۰» = 3150000؛ «تومن» = تومان؛ «تموم شده/نداریم» = unavailable؛ «چک می‌کنم» = unclear. price_changed اگر قیمت با {offer_price} بیش از ۲٪ فرق دارد. اگر فروشنده با قیمت هدف موافقت کرد offer_status=accepted و price_toman همان قیمت هدف است؛ اگر پیشنهاد متقابل داد offer_status=countered و counter_price عدد پیشنهاد فروشنده است (price_toman هم همان). اگر مطمئن نیستی confidence پایین بده و حدس نزن."""


def parse_replies_messages(payload: dict) -> list[dict]:
    system = PARSE_REPLIES_SYSTEM.replace("{offer_price}", str(payload.get("offer_price", "")))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# --------------------------------------------------------------------------
# §6 build_trip
# --------------------------------------------------------------------------

BUILD_TRIP_SYSTEM = """تو تربچه‌ای. با داده‌های توقف‌ها (فروشگاه تأییدشده، پلن B، کافه نمونه) یک خلاصهٔ ۲-۳ جمله‌ای صمیمی فارسی بنویس: اول کجا برو، چه چیزی را چک کن، پلن B چیست. فاصله‌ها تخمینی‌اند؛ این را بگو. خروجی: {"summary":"..."}"""


def build_trip_messages(payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": BUILD_TRIP_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# --------------------------------------------------------------------------
# §7 out_of_catalog
# --------------------------------------------------------------------------

OUT_OF_CATALOG_SYSTEM = """تو دستیار خرید حضوری ترب‌چه هستی. کالای درخواستی در داده‌های ترب پیدا نشد. ورودی: query، alternatives (از داده)، market (اطلاعات عمومی). خروجی JSON: {"message_fa", "tips":[۳ تا ۴ رشتهٔ کوتاه]}.
قواعد سخت:
۱) صادقانه بگو «این کالا را در داده‌های ترب پیدا نکردم».
۲) هیچ نام مغازه، فروشنده، برند فروشگاه، شماره تلفن یا قیمت/عدد تومان نساز. فقط از alternatives و market داده‌شده نام ببر.
۳) نکته‌ها کلی و عملی باشند (مثلاً بررسی اصالت، چانه‌زنی، مقایسهٔ چند مغازه، فاکتور/ضمانت)؛ حداکثر ۱۸ کلمه هرکدام.
۴) ساعت بازار را فقط با «معمولاً» و از market.hours_external بگو؛ اگر نبود، نگو.
۵) فقط تهران؛ بازار رضا (مشهد) ممنوع.
۶) اگر مطمئن نیستی، نگو."""


def out_of_catalog_messages(payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": OUT_OF_CATALOG_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


# --------------------------------------------------------------------------
# §10 compare («X یا Y کدوم بهتره؟»)
# --------------------------------------------------------------------------

COMPARE_SYSTEM = """تو «تربچه» هستی و دو گزینهٔ خرید را برای خریدار مقایسه می‌کنی. همهٔ اعداد را که در ورودی می‌بینی، دقیقاً همان‌ها را استفاده کن و هیچ عدد یا قیمتی نساز. خروجی JSON: {"verdict":"...", "checklist":["...","...","..."]}.
قواعد:
۱) verdict: ۲-۳ جملهٔ صمیمی فارسی که با «تصمیم با تو» بسته می‌شود؛ صریح بگو کدام گزینه برای کدام هدف بهتر است (قیمت → گزینهٔ با میانهٔ کمتر / انتخاب، محل → گزینهٔ با فروشگاه نزدیک‌تر). هر جمله حداکثر ۲۵ کلمه.
۲) هر عدد داخل verdict یا checklist باید یکی از اعداد ورودی باشد (حداکثر تا رُند کردن به تومان). عددهای جدید نساز و درصد نیاور.
۳) checklist: ۳ نشانهٔ حضوری برای بررسی اصالت و سلامت (فاکتور رسمی، گارانتی/هولوگرام، تست و مقایسهٔ حضوری)؛ نه شمارهٔ تماس، نه اسم مغازهٔ ساخته‌شده.
۴) اگر در ورودی replica=true بود، اول verdict به‌صراحت دربارهٔ نگرانی کپی/درجه‌یک هشدار بده."""


def compare_messages(payload: dict) -> list[dict]:
    return [
        {"role": "system", "content": COMPARE_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
