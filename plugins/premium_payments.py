"""
Premium plan selection, payment screenshot intake, subscription lifecycle and
admin controls. This module is intentionally additive: it uses the bot's
existing users collection and db.has_premium_access/remove_premium_access.
"""
import asyncio
import datetime
import hashlib
import io
import logging
import re
import os
import shutil
import subprocess
import time
from html import escape

import pytz
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
import pytesseract

from database.config_db import mdb

from info import (
    ADMINS,
    LOG_CHANNEL,
    PAYMENT_BOT_TOKEN,
    PAYMENT_BOT_USERNAME,
    PAYMENT_ADMIN_IDS,
    OWNER_USERNAME,
    PREMIUM_PLANS,
    PAYMENT_OCR_ENABLED,
    PAYMENT_MAX_DELAY_MINUTES,
    PAYMENT_FUTURE_TOLERANCE_MINUTES,
    PAYMENT_TIME_APPROVAL_ENABLED,
    PAYMENT_OCR_PASS_TIMEOUT,
    PAYMENT_OCR_JOB_TIMEOUT_SECONDS,
    API_ID,
    API_HASH,
)
from database.users_chats_db import db
from language import (
    LANGUAGES as GLOBAL_LANGUAGES,
    get_user_language as get_global_user_language,
    small_caps,
    small_caps_html,
)

LOGGER = logging.getLogger(__name__)

# Screenshot OCR is intentionally kept identical to the original analysis
# (all OCR variants and PSM passes remain). These limits only protect the bot
# from CPU/RAM spikes when screenshots arrive close together.
PAYMENT_OCR_MAX_CONCURRENT = max(
    1, int(os.getenv("PAYMENT_OCR_MAX_CONCURRENT", "1"))
)
_PAYMENT_OCR_SEMAPHORE = asyncio.Semaphore(PAYMENT_OCR_MAX_CONCURRENT)

# Tesseract can otherwise create several native worker threads per pass.
# Limiting native parallelism prevents one screenshot from exhausting a small
# Koyeb instance. It does not change the OCR variants or matching logic.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OMP_DYNAMIC", "FALSE")

IST = pytz.timezone("Asia/Kolkata")
UTC = datetime.timezone.utc
LIFETIME_EXPIRY = datetime.datetime(9999, 12, 31, 23, 59, 59)


def _now():
    # Existing Premium code stores naive datetimes in MongoDB. Keep the same
    # convention for compatibility, representing UTC.
    return datetime.datetime.utcnow()




def _naive_utc(value):
    if not isinstance(value, datetime.datetime):
        return value
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value

def _aware_ist(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(IST)


def _fmt_dt(value):
    value = _aware_ist(value)
    return value.strftime("%d %b %Y %I:%M %p") if value else "N/A"


def _admins():
    return set(ADMINS) | set(PAYMENT_ADMIN_IDS)


_AUTO_PAYMENT_MODE_ID = "global_auto_payment_mode"


async def get_auto_payment_enabled():
    """Read the globally-scoped auto-payment switch from Devil's original DB."""
    try:
        doc = await db.misc.find_one({"_id": _AUTO_PAYMENT_MODE_ID})
    except Exception as exc:
        LOGGER.warning("Could not read global auto-payment setting (%s)", type(exc).__name__)
        return True
    return bool(doc.get("enabled", True)) if doc else True


async def set_auto_payment_enabled(enabled):
    """Persist the global auto-payment switch in Devil's original DB."""
    now = datetime.datetime.utcnow()
    document = {"_id": _AUTO_PAYMENT_MODE_ID, "enabled": bool(enabled), "updated_at": now}
    await db.misc.update_one(
        {"_id": _AUTO_PAYMENT_MODE_ID}, {"$set": document}, upsert=True
    )
    return bool(enabled)

LANGUAGES = dict(GLOBAL_LANGUAGES)

LANGUAGE_ALIASES = {
    "en": "en", "en-us": "en", "en-gb": "en",
    "hi": "hi", "ta": "ta", "te": "te", "kn": "kn", "ml": "ml",
    "bn": "bn", "mr": "mr", "gu": "gu", "pa": "pa", "ur": "ur",
}

I18N = {
    "en": {
        "progress_title": "🔎 <b>Payment screenshot received</b>",
        "progress_body": "⏳ Your payment is being securely analyzed.\nThis may take <b>1–2 minutes</b>. Please do not resend the screenshot or switch to another bot.\n\n✅ You will receive the final result automatically.",
        "no_order_title": "⚠️ <b>No Premium order found</b>",
        "no_order_body": "We could not find an active Premium order linked to your account.\nPlease select a Premium plan first, complete the payment, and then send the screenshot here.\n\n🧹 This notice will disappear automatically after 10 seconds.",
        "manual_title": "⚠️ <b>Premium Activated — Payment Under Review</b>",
        "manual_body": "Your payment screenshot could not be automatically approved and has been sent to the admin for manual review. Your selected Premium plan is already active temporarily. If the payment or screenshot is found to be invalid or misleading, this access may be removed.",
        "activated": "Thank you for purchasing Premium!",
        "renewed": "Thank you for renewing Premium!",
        "approved": "Your payment has been confirmed. Your Premium access remains active.",
        "rejected": "The Premium access added for this payment has been removed. Please contact the admin if you think this is a mistake.",
        "expired": "Your Premium access has ended.\n\n🔄 Purchase a new Premium plan to continue.",
        "expiring": "Renew your Premium plan to continue using the service.",
        "language_title": "🌐 <b>Choose Your Language</b>",
        "language_body": "Select the language you want the bot to use for normal messages. You can change it anytime.",
        "language_saved": "🌐 Language updated successfully.",
        "contact": "💬 CONTACT ADMIN",
    },
    "hi": {
        "progress_title": "🔎 <b>भुगतान स्क्रीनशॉट प्राप्त हुआ</b>",
        "progress_body": "⏳ आपके भुगतान की सुरक्षित जाँच की जा रही है।\nइसमें <b>1–2 मिनट</b> लग सकते हैं। कृपया स्क्रीनशॉट दोबारा न भेजें और दूसरा बॉट न खोलें।\n\n✅ जाँच पूरी होने पर आपको परिणाम अपने आप मिल जाएगा।",
        "no_order_title": "⚠️ <b>कोई Premium Order नहीं मिला</b>",
        "no_order_body": "आपके खाते से कोई सक्रिय Premium Order जुड़ा नहीं मिला।\nकृपया पहले Premium Plan चुनें, भुगतान पूरा करें और फिर स्क्रीनशॉट भेजें।\n\n🧹 यह संदेश 10 सेकंड बाद अपने आप हट जाएगा।",
        "manual_title": "⚠️ <b>Premium सक्रिय — भुगतान जाँच में</b>",
        "manual_body": "आपका भुगतान स्क्रीनशॉट अपने आप स्वीकृत नहीं हो सका और इसे Admin की मैनुअल जाँच के लिए भेज दिया गया है। आपका चुना हुआ Premium Plan अस्थायी रूप से सक्रिय है। भुगतान गलत या भ्रामक मिलने पर यह access हटाया जा सकता है।",
        "activated": "Premium खरीदने के लिए धन्यवाद!",
        "renewed": "Premium renew करने के लिए धन्यवाद!",
        "approved": "आपका भुगतान पुष्टि हो गया है। आपका Premium access सक्रिय है।",
        "rejected": "इस भुगतान से दिया गया Premium access हटा दिया गया है। यदि आपको लगता है कि यह गलती है, तो Admin से संपर्क करें।",
        "expired": "आपका Premium access समाप्त हो गया है।\n\n🔄 जारी रखने के लिए नया Premium Plan खरीदें।",
        "expiring": "सेवा जारी रखने के लिए अपना Premium Plan renew करें।",
        "language_title": "🌐 <b>अपनी भाषा चुनें</b>",
        "language_body": "सामान्य bot messages के लिए अपनी पसंदीदा भाषा चुनें। आप इसे कभी भी बदल सकते हैं।",
        "language_saved": "🌐 भाषा सफलतापूर्वक बदल दी गई।",
        "contact": "💬 ADMIN से संपर्क करें",
    },
    "ta": {
        "progress_title": "🔎 <b>Payment Screenshot பெறப்பட்டது</b>",
        "progress_body": "⏳ உங்கள் payment பாதுகாப்பாக சரிபார்க்கப்படுகிறது.\nஇதற்கு <b>1–2 நிமிடங்கள்</b> ஆகலாம். Screenshot-ஐ மீண்டும் அனுப்ப வேண்டாம்; வேறு bot-க்கு மாற வேண்டாம்.\n\n✅ சரிபார்ப்பு முடிந்ததும் முடிவு தானாக வரும்.",
        "no_order_title": "⚠️ <b>Premium Order கிடைக்கவில்லை</b>",
        "no_order_body": "உங்கள் கணக்குடன் செயலில் உள்ள Premium Order எதுவும் இணைக்கப்படவில்லை.\nமுதலில் Premium Plan-ஐ தேர்வு செய்து payment முடித்த பிறகு screenshot அனுப்பவும்.\n\n🧹 இந்த செய்தி 10 விநாடிகளில் தானாக நீக்கப்படும்.",
        "manual_title": "⚠️ <b>Premium செயல்படுத்தப்பட்டது — Payment சரிபார்ப்பில்</b>",
        "manual_body": "உங்கள் payment screenshot தானாக approve செய்யப்படவில்லை; Admin manual review-க்கு அனுப்பப்பட்டுள்ளது. உங்கள் தேர்ந்தெடுத்த Premium Plan தற்காலிகமாக active-ஆக உள்ளது. Payment தவறானது என கண்டறியப்பட்டால் access நீக்கப்படலாம்.",
        "activated": "Premium வாங்கியதற்கு நன்றி!", "renewed": "Premium renew செய்ததற்கு நன்றி!",
        "approved": "உங்கள் payment உறுதிப்படுத்தப்பட்டது. Premium access active-ஆக உள்ளது.",
        "rejected": "இந்த payment மூலம் வழங்கப்பட்ட Premium access நீக்கப்பட்டது. தவறு என நினைத்தால் Admin-ஐ தொடர்புகொள்ளவும்.",
        "expired": "உங்கள் Premium access முடிந்துவிட்டது.\n\n🔄 தொடர புதிய Premium Plan வாங்கவும்.",
        "expiring": "சேவையைத் தொடர Premium Plan-ஐ renew செய்யவும்.",
        "language_title": "🌐 <b>உங்கள் மொழியைத் தேர்வு செய்யவும்</b>", "language_body": "Bot-ன் சாதாரண messages-க்கு விருப்பமான மொழியைத் தேர்வு செய்யவும்.", "language_saved": "🌐 மொழி வெற்றிகரமாக மாற்றப்பட்டது.", "contact": "💬 ADMIN-ஐ தொடர்புகொள்ளவும்",
    },
    "te": {
        "progress_title": "🔎 <b>Payment Screenshot అందింది</b>", "progress_body": "⏳ మీ payment సురక్షితంగా పరిశీలించబడుతోంది.\nదీనికి <b>1–2 నిమిషాలు</b> పట్టవచ్చు. Screenshot మళ్లీ పంపవద్దు మరియు మరో bot‌కి మారవద్దు.\n\n✅ పరిశీలన పూర్తయ్యాక ఫలితం ఆటోమేటిక్‌గా వస్తుంది.",
        "no_order_title": "⚠️ <b>Premium Order కనుగొనబడలేదు</b>", "no_order_body": "మీ ఖాతాతో active Premium Order ఏదీ కనుగొనబడలేదు.\nముందుగా Premium Plan ఎంచుకుని payment పూర్తి చేసి, తర్వాత screenshot పంపండి.\n\n🧹 ఈ సందేశం 10 సెకన్లలో ఆటోమేటిక్‌గా తొలగించబడుతుంది.",
        "manual_title": "⚠️ <b>Premium యాక్టివ్ — Payment Reviewలో ఉంది</b>", "manual_body": "మీ payment screenshot ఆటోమేటిక్‌గా approve కాలేదు; Admin manual reviewకి పంపబడింది. మీరు ఎంచుకున్న Premium Plan తాత్కాలికంగా active‌లో ఉంది. Payment తప్పుగా ఉంటే access తొలగించబడవచ్చు.",
        "activated": "Premium కొనుగోలు చేసినందుకు ధన్యవాదాలు!", "renewed": "Premium renew చేసినందుకు ధన్యవాదాలు!", "approved": "మీ payment నిర్ధారించబడింది. Premium access active‌లో ఉంది.", "rejected": "ఈ payment ద్వారా ఇచ్చిన Premium access తొలగించబడింది. ఇది పొరపాటు అనుకుంటే Admin‌ను సంప్రదించండి.", "expired": "మీ Premium access ముగిసింది.\n\n🔄 కొనసాగడానికి కొత్త Premium Plan కొనండి.", "expiring": "సేవను కొనసాగించడానికి మీ Premium Plan‌ను renew చేయండి.", "language_title": "🌐 <b>మీ భాషను ఎంచుకోండి</b>", "language_body": "సాధారణ bot messages కోసం మీ భాషను ఎంచుకోండి.", "language_saved": "🌐 భాష విజయవంతంగా మార్చబడింది.", "contact": "💬 ADMIN‌ను సంప్రదించండి",
    },
    "kn": {
        "progress_title": "🔎 <b>Payment Screenshot ಸ್ವೀಕರಿಸಲಾಗಿದೆ</b>", "progress_body": "⏳ ನಿಮ್ಮ payment ಅನ್ನು ಸುರಕ್ಷಿತವಾಗಿ ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ.\nಇದಕ್ಕೆ <b>1–2 ನಿಮಿಷಗಳು</b> ಬೇಕಾಗಬಹುದು. Screenshot ಅನ್ನು ಮತ್ತೆ ಕಳುಹಿಸಬೇಡಿ ಮತ್ತು ಬೇರೆ bot ಗೆ ಬದಲಾಯಿಸಬೇಡಿ.\n\n✅ ಪರಿಶೀಲನೆ ಮುಗಿದ ನಂತರ ಫಲಿತಾಂಶ ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಬರುತ್ತದೆ.",
        "no_order_title": "⚠️ <b>Premium Order ಕಂಡುಬಂದಿಲ್ಲ</b>", "no_order_body": "ನಿಮ್ಮ ಖಾತೆಗೆ ಯಾವುದೇ active Premium Order ಕಂಡುಬಂದಿಲ್ಲ.\nಮೊದಲು Premium Plan ಆಯ್ಕೆ ಮಾಡಿ, payment ಪೂರ್ಣಗೊಳಿಸಿ, ನಂತರ screenshot ಕಳುಹಿಸಿ.\n\n🧹 ಈ ಸಂದೇಶ 10 ಸೆಕೆಂಡುಗಳ ನಂತರ ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಅಳಿಸಲಾಗುತ್ತದೆ.",
        "manual_title": "⚠️ <b>Premium ಸಕ್ರಿಯ — Payment ಪರಿಶೀಲನೆಯಲ್ಲಿದೆ</b>", "manual_body": "ನಿಮ್ಮ payment screenshot ಸ್ವಯಂಚಾಲಿತವಾಗಿ approve ಆಗಲಿಲ್ಲ; Admin manual review ಗೆ ಕಳುಹಿಸಲಾಗಿದೆ. ನೀವು ಆಯ್ಕೆ ಮಾಡಿದ Premium Plan ತಾತ್ಕಾಲಿಕವಾಗಿ active ಆಗಿದೆ. Payment ತಪ್ಪಾಗಿದೆ ಎಂದು ಕಂಡುಬಂದರೆ access ತೆಗೆದುಹಾಕಬಹುದು.",
        "activated": "Premium ಖರೀದಿಸಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು!", "renewed": "Premium renew ಮಾಡಿದ್ದಕ್ಕಾಗಿ ಧನ್ಯವಾದಗಳು!", "approved": "ನಿಮ್ಮ payment ದೃಢೀಕರಿಸಲಾಗಿದೆ. Premium access active ಆಗಿದೆ.", "rejected": "ಈ payment ಮೂಲಕ ನೀಡಿದ Premium access ತೆಗೆದುಹಾಕಲಾಗಿದೆ. ಇದು ತಪ್ಪು ಎಂದು ಭಾವಿಸಿದರೆ Admin ಅನ್ನು ಸಂಪರ್ಕಿಸಿ.", "expired": "ನಿಮ್ಮ Premium access ಮುಗಿದಿದೆ.\n\n🔄 ಮುಂದುವರಿಸಲು ಹೊಸ Premium Plan ಖರೀದಿಸಿ.", "expiring": "ಸೇವೆಯನ್ನು ಮುಂದುವರಿಸಲು Premium Plan renew ಮಾಡಿ.", "language_title": "🌐 <b>ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ</b>", "language_body": "ಸಾಮಾನ್ಯ bot messages ಗಾಗಿ ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ.", "language_saved": "🌐 ಭಾಷೆ ಯಶಸ್ವಿಯಾಗಿ ಬದಲಾಯಿಸಲಾಗಿದೆ.", "contact": "💬 ADMIN ಸಂಪರ್ಕಿಸಿ",
    },
    "ml": {
        "progress_title": "🔎 <b>Payment Screenshot ലഭിച്ചു</b>", "progress_body": "⏳ നിങ്ങളുടെ payment സുരക്ഷിതമായി പരിശോധിക്കുന്നു.\nഇതിന് <b>1–2 മിനിറ്റ്</b> വരെ എടുക്കാം. Screenshot വീണ്ടും അയയ്ക്കരുത്; മറ്റൊരു bot-ലേക്ക് മാറരുത്.\n\n✅ പരിശോധന പൂർത്തിയായാൽ ഫലം സ്വയമേവ ലഭിക്കും.",
        "no_order_title": "⚠️ <b>Premium Order കണ്ടെത്താനായില്ല</b>", "no_order_body": "നിങ്ങളുടെ അക്കൗണ്ടുമായി ബന്ധിപ്പിച്ച active Premium Order കണ്ടെത്താനായില്ല.\nആദ്യം Premium Plan തിരഞ്ഞെടുക്കുക, payment പൂർത്തിയാക്കി ശേഷം screenshot അയയ്ക്കുക.\n\n🧹 ഈ സന്ദേശം 10 സെക്കൻഡിന് ശേഷം സ്വയമേവ ഇല്ലാതാകും.",
        "manual_title": "⚠️ <b>Premium സജീവമാക്കി — Payment പരിശോധനയിൽ</b>", "manual_body": "നിങ്ങളുടെ payment screenshot സ്വയമേവ approve ചെയ്യാനായില്ല; Admin manual review-ലേക്ക് അയച്ചു. നിങ്ങൾ തിരഞ്ഞെടുത്ത Premium Plan താൽക്കാലികമായി active ആണ്. Payment തെറ്റാണെന്ന് കണ്ടെത്തിയാൽ access നീക്കം ചെയ്യാം.",
        "activated": "Premium വാങ്ങിയതിന് നന്ദി!", "renewed": "Premium renew ചെയ്തതിന് നന്ദി!", "approved": "നിങ്ങളുടെ payment സ്ഥിരീകരിച്ചു. Premium access active ആണ്.", "rejected": "ഈ payment വഴി നൽകിയ Premium access നീക്കം ചെയ്തു. തെറ്റാണെന്ന് തോന്നുന്നുവെങ്കിൽ Admin-നെ ബന്ധപ്പെടുക.", "expired": "നിങ്ങളുടെ Premium access അവസാനിച്ചു.\n\n🔄 തുടരാൻ പുതിയ Premium Plan വാങ്ങുക.", "expiring": "സേവനം തുടരാൻ Premium Plan renew ചെയ്യുക.", "language_title": "🌐 <b>നിങ്ങളുടെ ഭാഷ തിരഞ്ഞെടുക്കുക</b>", "language_body": "സാധാരണ bot messages-നായി നിങ്ങളുടെ ഇഷ്ടഭാഷ തിരഞ്ഞെടുക്കുക.", "language_saved": "🌐 ഭാഷ വിജയകരമായി മാറ്റി.", "contact": "💬 ADMIN-നെ ബന്ധപ്പെടുക",
    },
}

# Complete user-facing payment lifecycle translations for the remaining global
# languages. These are merged without replacing the existing translations above.
_I18N_EXTRA = {
    "bn": {
        "progress_title":"🔎 <b>Payment Screenshot পাওয়া গেছে</b>", "progress_body":"⏳ আপনার payment নিরাপদে যাচাই করা হচ্ছে। এতে <b>1–2 মিনিট</b> সময় লাগতে পারে। Screenshot আবার পাঠাবেন না। যাচাই শেষ হলে ফলাফল স্বয়ংক্রিয়ভাবে পাবেন।",
        "no_order_title":"⚠️ <b>কোনো Premium Order পাওয়া যায়নি</b>", "no_order_body":"আপনার Telegram account-এর জন্য কোনো pending Premium order পাওয়া যায়নি। প্রথমে একটি Premium plan নির্বাচন করুন এবং payment সম্পূর্ণ করে screenshot পাঠান।\n\n🧹 এই বার্তাটি 10 সেকেন্ড পরে মুছে যাবে।",
        "manual_title":"⚠️ <b>Premium সক্রিয় — Payment পর্যালোচনাধীন</b>", "manual_body":"আপনার payment screenshot স্বয়ংক্রিয়ভাবে approve করা যায়নি এবং Admin-এর manual review-তে পাঠানো হয়েছে। আপনার নির্বাচিত Premium plan সাময়িকভাবে active আছে। Payment ভুল হলে access সরিয়ে দেওয়া হতে পারে।",
        "activated":"Premium সফলভাবে সক্রিয় হয়েছে।", "renewed":"Premium সফলভাবে renew হয়েছে।", "approved":"আপনার payment approve হয়েছে এবং Premium access active রয়েছে।", "rejected":"আপনার payment reject করা হয়েছে এবং এই payment-এর Premium access সরিয়ে দেওয়া হয়েছে।", "expired":"আপনার Premium access শেষ হয়েছে।\n\n🔄 চালিয়ে যেতে একটি নতুন Premium Plan কিনুন।", "expiring":"সেবা চালিয়ে যেতে Premium Plan renew করুন।", "contact":"💬 ADMIN-এর সাথে যোগাযোগ করুন",
    },
    "mr": {
        "progress_title":"🔎 <b>Payment Screenshot मिळाला</b>", "progress_body":"⏳ तुमचा payment सुरक्षितपणे तपासला जात आहे. यासाठी <b>1–2 मिनिटे</b> लागू शकतात. Screenshot पुन्हा पाठवू नका. तपासणी पूर्ण झाल्यावर निकाल आपोआप मिळेल.",
        "no_order_title":"⚠️ <b>Premium Order सापडला नाही</b>", "no_order_body":"तुमच्या Telegram account साठी कोणताही pending Premium order सापडला नाही. आधी Premium plan निवडा, payment पूर्ण करा आणि screenshot पाठवा.\n\n🧹 हा संदेश 10 सेकंदांनी हटवला जाईल.",
        "manual_title":"⚠️ <b>Premium सक्रिय — Payment तपासणीमध्ये</b>", "manual_body":"तुमचा payment screenshot आपोआप approve झाला नाही आणि Admin manual review साठी पाठवला आहे. तुम्ही निवडलेला Premium plan तात्पुरता active आहे. Payment चुकीचा असल्यास access काढला जाऊ शकतो.",
        "activated":"Premium यशस्वीपणे सक्रिय झाला.", "renewed":"Premium यशस्वीपणे renew झाला.", "approved":"तुमचा payment approve झाला आहे आणि Premium access active आहे.", "rejected":"तुमचा payment reject झाला असून या payment मधील Premium access काढला आहे.", "expired":"तुमचा Premium access संपला आहे.\n\n🔄 सुरू ठेवण्यासाठी नवीन Premium Plan खरेदी करा.", "expiring":"सेवा सुरू ठेवण्यासाठी Premium Plan renew करा.", "contact":"💬 ADMIN शी संपर्क करा",
    },
    "gu": {
        "progress_title":"🔎 <b>Payment Screenshot મળ્યો</b>", "progress_body":"⏳ તમારો payment સુરક્ષિત રીતે તપાસાઈ રહ્યો છે. તેમાં <b>1–2 મિનિટ</b> લાગી શકે છે. Screenshot ફરી મોકલશો નહીં. તપાસ પૂર્ણ થયા પછી પરિણામ આપમેળે મળશે.",
        "no_order_title":"⚠️ <b>Premium Order મળ્યો નથી</b>", "no_order_body":"તમારા Telegram account માટે કોઈ pending Premium order મળ્યો નથી. પહેલા Premium plan પસંદ કરો, payment પૂર્ણ કરો અને screenshot મોકલો.\n\n🧹 આ સંદેશ 10 સેકન્ડ પછી દૂર થશે.",
        "manual_title":"⚠️ <b>Premium સક્રિય — Payment સમીક્ષા હેઠળ</b>", "manual_body":"તમારો payment screenshot આપમેળે approve થઈ શક્યો નથી અને Admin manual review માટે મોકલાયો છે. તમે પસંદ કરેલો Premium plan તાત્કાલિક active છે. Payment ખોટો જણાય તો access દૂર થઈ શકે છે.",
        "activated":"Premium સફળતાપૂર્વક સક્રિય થયું.", "renewed":"Premium સફળતાપૂર્વક renew થયું.", "approved":"તમારો payment approve થયો છે અને Premium access active છે.", "rejected":"તમારો payment reject થયો છે અને આ paymentનું Premium access દૂર કરવામાં આવ્યું છે.", "expired":"તમારું Premium access સમાપ્ત થયું છે.\n\n🔄 ચાલુ રાખવા નવો Premium Plan ખરીદો.", "expiring":"સેવા ચાલુ રાખવા Premium Plan renew કરો.", "contact":"💬 ADMINનો સંપર્ક કરો",
    },
    "pa": {
        "progress_title":"🔎 <b>Payment Screenshot ਮਿਲ ਗਿਆ</b>", "progress_body":"⏳ ਤੁਹਾਡੇ payment ਦੀ ਸੁਰੱਖਿਅਤ ਜਾਂਚ ਹੋ ਰਹੀ ਹੈ। ਇਸ ਵਿੱਚ <b>1–2 ਮਿੰਟ</b> ਲੱਗ ਸਕਦੇ ਹਨ। Screenshot ਦੁਬਾਰਾ ਨਾ ਭੇਜੋ। ਜਾਂਚ ਪੂਰੀ ਹੋਣ ਤੇ ਨਤੀਜਾ ਆਪਣੇ ਆਪ ਮਿਲੇਗਾ.",
        "no_order_title":"⚠️ <b>Premium Order ਨਹੀਂ ਮਿਲਿਆ</b>", "no_order_body":"ਤੁਹਾਡੇ Telegram account ਲਈ ਕੋਈ pending Premium order ਨਹੀਂ ਮਿਲਿਆ। ਪਹਿਲਾਂ Premium plan ਚੁਣੋ, payment ਪੂਰਾ ਕਰੋ ਅਤੇ screenshot ਭੇਜੋ।\n\n🧹 ਇਹ ਸੁਨੇਹਾ 10 ਸਕਿੰਟ ਬਾਅਦ ਮਿਟ ਜਾਵੇਗਾ।",
        "manual_title":"⚠️ <b>Premium ਸਰਗਰਮ — Payment ਸਮੀਖਿਆ ਵਿੱਚ</b>", "manual_body":"ਤੁਹਾਡਾ payment screenshot ਆਪਣੇ ਆਪ approve ਨਹੀਂ ਹੋਇਆ ਅਤੇ Admin manual review ਲਈ ਭੇਜਿਆ ਗਿਆ ਹੈ। ਤੁਹਾਡਾ ਚੁਣਿਆ Premium plan ਅਸਥਾਈ ਤੌਰ ਤੇ active ਹੈ। Payment ਗਲਤ ਹੋਣ ਤੇ access ਹਟਾਇਆ ਜਾ ਸਕਦਾ ਹੈ।",
        "activated":"Premium ਸਫਲਤਾਪੂਰਵਕ ਸਰਗਰਮ ਹੋ ਗਿਆ।", "renewed":"Premium ਸਫਲਤਾਪੂਰਵਕ renew ਹੋ ਗਿਆ।", "approved":"ਤੁਹਾਡਾ payment approve ਹੋ ਗਿਆ ਹੈ ਅਤੇ Premium access active ਹੈ।", "rejected":"ਤੁਹਾਡਾ payment reject ਹੋ ਗਿਆ ਹੈ ਅਤੇ ਇਸ payment ਦਾ Premium access ਹਟਾ ਦਿੱਤਾ ਗਿਆ ਹੈ।", "expired":"ਤੁਹਾਡਾ Premium access ਖਤਮ ਹੋ ਗਿਆ ਹੈ।\n\n🔄 ਜਾਰੀ ਰੱਖਣ ਲਈ ਨਵਾਂ Premium Plan ਖਰੀਦੋ।", "expiring":"ਸੇਵਾ ਜਾਰੀ ਰੱਖਣ ਲਈ Premium Plan renew ਕਰੋ।", "contact":"💬 ADMIN ਨਾਲ ਸੰਪਰਕ ਕਰੋ",
    },
    "ur": {
        "progress_title":"🔎 <b>Payment Screenshot موصول ہوگیا</b>", "progress_body":"⏳ آپ کی payment محفوظ طریقے سے چیک کی جا رہی ہے۔ اس میں <b>1–2 منٹ</b> لگ سکتے ہیں۔ Screenshot دوبارہ نہ بھیجیں۔ چیک مکمل ہونے کے بعد نتیجہ خود مل جائے گا۔",
        "no_order_title":"⚠️ <b>کوئی Premium Order نہیں ملا</b>", "no_order_body":"آپ کے Telegram account کے لیے کوئی pending Premium order نہیں ملا۔ پہلے Premium plan منتخب کریں، payment مکمل کریں اور screenshot بھیجیں۔\n\n🧹 یہ پیغام 10 سیکنڈ بعد حذف ہو جائے گا۔",
        "manual_title":"⚠️ <b>Premium فعال — Payment جائزے میں</b>", "manual_body":"آپ کا payment screenshot خودکار طور پر approve نہیں ہو سکا اور Admin کے manual review کے لیے بھیج دیا گیا ہے۔ آپ کا منتخب Premium plan عارضی طور پر active ہے۔ Payment غلط ہونے پر access ہٹایا جا سکتا ہے۔",
        "activated":"Premium کامیابی سے فعال ہوگیا۔", "renewed":"Premium کامیابی سے renew ہوگیا۔", "approved":"آپ کی payment approve ہوگئی ہے اور Premium access active ہے۔", "rejected":"آپ کی payment reject ہوگئی ہے اور اس payment کا Premium access ہٹا دیا گیا ہے۔", "expired":"آپ کا Premium access ختم ہوگیا ہے۔\n\n🔄 جاری رکھنے کے لیے نیا Premium Plan خریدیں۔", "expiring":"سروس جاری رکھنے کے لیے Premium Plan renew کریں۔", "contact":"💬 ADMIN سے رابطہ کریں",
    },
    "as": {
        "progress_title":"🔎 <b>Payment Screenshot পোৱা গ'ল</b>", "progress_body":"⏳ আপোনাৰ payment সুৰক্ষিতভাৱে পৰীক্ষা কৰা হৈছে। ইয়াত <b>1–2 মিনিট</b> লাগিব পাৰে। Screenshot পুনৰ নপঠিয়াব। পৰীক্ষা শেষ হ'লে ফলাফল স্বয়ংক্ৰিয়ভাৱে পাব।",
        "no_order_title":"⚠️ <b>কোনো Premium Order পোৱা নগ'ল</b>", "no_order_body":"আপোনাৰ Telegram account-ৰ বাবে কোনো pending Premium order পোৱা নগ'ল। প্ৰথমে Premium plan বাছক, payment সম্পূৰ্ণ কৰক আৰু screenshot পঠিয়াওক।\n\n🧹 এই বাৰ্তাটো 10 ছেকেণ্ড পিছত মচি পেলোৱা হ'ব।",
        "manual_title":"⚠️ <b>Premium সক্ৰিয় — Payment পৰ্যালোচনাত</b>", "manual_body":"আপোনাৰ payment screenshot স্বয়ংক্ৰিয়ভাৱে approve কৰিব পৰা নগ'ল আৰু Admin manual review-লৈ পঠিওৱা হৈছে। আপুনি বাছি লোৱা Premium plan সাময়িকভাৱে active আছে। Payment ভুল হ'লে access আঁতৰাব পাৰে।",
        "activated":"Premium সফলভাৱে সক্ৰিয় কৰা হৈছে।", "renewed":"Premium সফলভাৱে renew কৰা হৈছে।", "approved":"আপোনাৰ payment approve হৈছে আৰু Premium access active আছে।", "rejected":"আপোনাৰ payment reject কৰা হৈছে আৰু এই payment-ৰ Premium access আঁতৰোৱা হৈছে।", "expired":"আপোনাৰ Premium access শেষ হৈছে।\n\n🔄 চলাই যাবলৈ নতুন Premium Plan কিনক।", "expiring":"সেৱা চলাই যাবলৈ Premium Plan renew কৰক।", "contact":"💬 ADMIN-ৰ সৈতে যোগাযোগ কৰক",
    },
    "ne": {
        "progress_title":"🔎 <b>Payment Screenshot प्राप्त भयो</b>", "progress_body":"⏳ तपाईंको payment सुरक्षित रूपमा जाँच हुँदैछ। यसमा <b>1–2 मिनेट</b> लाग्न सक्छ। Screenshot फेरि नपठाउनुहोस्। जाँच पूरा भएपछि परिणाम आफैं प्राप्त हुनेछ।",
        "no_order_title":"⚠️ <b>Premium Order भेटिएन</b>", "no_order_body":"तपाईंको Telegram account का लागि कुनै pending Premium order भेटिएन। पहिले Premium plan छान्नुहोस्, payment पूरा गर्नुहोस् र screenshot पठाउनुहोस्।\n\n🧹 यो सन्देश 10 सेकेन्डपछि हटाइनेछ।",
        "manual_title":"⚠️ <b>Premium सक्रिय — Payment समीक्षा हुँदैछ</b>", "manual_body":"तपाईंको payment screenshot स्वतः approve हुन सकेन र Admin को manual review मा पठाइएको छ। तपाईंले छानेको Premium plan अस्थायी रूपमा active छ। Payment गलत भए access हटाउन सकिन्छ।",
        "activated":"Premium सफलतापूर्वक सक्रिय भयो।", "renewed":"Premium सफलतापूर्वक renew भयो।", "approved":"तपाईंको payment approve भयो र Premium access active छ।", "rejected":"तपाईंको payment reject भयो र यस payment को Premium access हटाइएको छ।", "expired":"तपाईंको Premium access समाप्त भयो।\n\n🔄 जारी राख्न नयाँ Premium Plan किन्नुहोस्।", "expiring":"सेवा जारी राख्न Premium Plan renew गर्नुहोस्।", "contact":"💬 ADMIN लाई सम्पर्क गर्नुहोस्",
    },
    "hinglish": {
        "progress_title":"🔎 <b>Payment Screenshot Received</b>", "progress_body":"⏳ Aapka payment safely check ho raha hai. Isme <b>1–2 minutes</b> lag sakte hain. Screenshot dobara mat bhejna. Check complete hone ke baad result automatically milega.",
        "no_order_title":"⚠️ <b>No Premium Order Found</b>", "no_order_body":"Aapke Telegram account ke liye koi pending Premium order nahi mila. Pehle Premium plan select karo, payment complete karo aur screenshot bhejo.\n\n🧹 Ye message 10 seconds baad delete ho jayega.",
        "manual_title":"⚠️ <b>Premium Activated — Payment Under Review</b>", "manual_body":"Aapka payment screenshot automatically approve nahi hua aur Admin manual review ke liye bheja gaya hai. Aapka selected Premium plan temporarily active hai. Payment galat hua to access remove kiya ja sakta hai.",
        "activated":"Premium successfully activate ho gaya.", "renewed":"Premium successfully renew ho gaya.", "approved":"Aapka payment approve ho gaya hai aur Premium access active hai.", "rejected":"Aapka payment reject ho gaya hai aur is payment ka Premium access remove kar diya gaya hai.", "expired":"Aapka Premium access khatam ho gaya hai.\n\n🔄 Continue karne ke liye naya Premium Plan kharido.", "expiring":"Service continue karne ke liye Premium Plan renew karo.", "contact":"💬 ADMIN se contact karo",
    },
}
for _code, _values in _I18N_EXTRA.items():
    I18N.setdefault(_code, {}).update(_values)


def _lang_from_code(code):
    code = str(code or "").lower().replace("_", "-")
    base = code.split("-", 1)[0]
    return LANGUAGE_ALIASES.get(code) or LANGUAGE_ALIASES.get(base) or "en"


async def _user_language(user_id, telegram_user=None):
    # Premium always follows the bot's existing global language preference.
    # There is deliberately no second Premium-specific language selector.
    try:
        return await get_global_user_language(user_id, telegram_user)
    except Exception:
        return "en"

def _tr(lang, key, **values):
    text = I18N.get(lang, I18N["en"]).get(key, I18N["en"].get(key, key))
    try:
        return small_caps_html(text.format(**values) if values else text)
    except Exception:
        return small_caps_html(text)


# Premium UI text is keyed to the user's GLOBAL bot language.  The Premium
# screen never asks for a second language choice.
_PREMIUM_FLOW = {
    "en": {"intro": "<b>👋 ʜᴇʏ {mention},</b>\n\n<b>🎁 ᴘʀᴇᴍɪᴜᴍ ғᴇᴀᴛᴜʀᴇ ʙᴇɴɪꜰɪᴛs:</b>\n\n❏ ɴᴏ ɴᴇᴇᴅ ᴛᴏ ᴏᴘᴇɴ ʟɪɴᴋꜱ\n❏ ɢᴇᴛ ᴅɪʀᴇᴄᴛ ғɪʟᴇs\n❏ ᴀᴅ-ғʀᴇᴇ ᴇxᴘᴇʀɪᴇɴᴄᴇ\n❏ ʜɪɢʜ-sᴘᴇᴇᴅ ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋ\n❏ ᴍᴜʟᴛɪ-ᴘʟᴀʏᴇʀ sᴛʀᴇᴀᴍɪɴɢ ʟɪɴᴋs\n❏ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏᴠɪᴇs ᴀɴᴅ sᴇʀɪᴇs\n❏ ꜰᴜʟʟ ᴀᴅᴍɪɴ sᴜᴘᴘᴏʀᴛ\n❏ ʀᴇǫᴜᴇsᴛ ᴡɪʟʟ ʙᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ɪɴ 𝟷ʜ [ ɪꜰ ᴀᴠᴀɪʟᴀʙʟᴇ ]", "continue": "🍁 ᴄʜᴇᴄᴋ ᴀʟʟ ᴘʟᴀɴs & ᴘʀɪᴄᴇs 🍁", "close": "• ᴄʟᴏsᴇ •", "plans": "<b>👋 ʜᴇʏ {mention}</b>\n\n<blockquote>🎖️ <b>AVAILABLE PREMIUM PLANS</b></blockquote>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code> [TAP TO COPY]\n\n⛽️ Check your active plan: /myplan\n\n🏷️ Premium proof\n\n‼️ Send the screenshot after payment.\n‼️ Please allow a little time for verification."},
    "hi": {"intro": "<b>👋 नमस्ते {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nनीचे Premium plan चुनकर आगे बढ़ें।", "continue": "🍁 सभी Premium Plans और कीमतें देखें 🍁", "close": "• बंद करें •", "plans": "<b>👋 नमस्ते {mention}</b>\n\n<blockquote>🎖️ <b>उपलब्ध Premium Plans</b></blockquote>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code> [कॉपी करने के लिए टैप करें]\n\n⛽️ अपना active plan देखें: /myplan\n\n‼️ Payment के बाद screenshot भेजें।\n‼️ Verification के लिए थोड़ा समय दें।"},
    "hinglish": {"intro": "<b>👋 Hey {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nNeeche Premium plan choose karke continue karo.", "continue": "🍁 Saare Premium Plans & Prices Dekho 🍁", "close": "• Close •", "plans": "<b>👋 Hey {mention}</b>\n\n<blockquote>🎖️ <b>AVAILABLE PREMIUM PLANS</b></blockquote>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code> [COPY KARNE KE LIYE TAP KARO]\n\n⛽️ Active plan check karo: /myplan\n\n‼️ Payment ke baad screenshot bhejo.\n‼️ Verification ke liye thoda time do."},
}
_PREMIUM_FLOW["hi"]["intro"] = "<b>👋 नमस्ते {mention},</b>\n\n<b>🎁 Premium फीचर्स:</b>\n\n❏ लिंक खोलने की जरूरत नहीं\n❏ डायरेक्ट फाइल्स\n❏ विज्ञापन-मुक्त अनुभव\n❏ हाई-स्पीड डाउनलोड लिंक\n❏ मल्टी-प्लेयर स्ट्रीमिंग लिंक\n❏ अनलिमिटेड मूवीज़ और सीरीज़\n❏ पूरा एडमिन सपोर्ट\n❏ अनुरोध उपलब्ध होने पर 1 घंटे में पूरा किया जाएगा"
_PREMIUM_FLOW["hinglish"]["intro"] = "<b>👋 Hey {mention},</b>\n\n<b>🎁 Premium Feature Benefits:</b>\n\n❏ Link open karne ki zarurat nahi\n❏ Direct files\n❏ Ad-free experience\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies aur series\n❏ Full admin support\n❏ Request available ho to 1h mein complete hoga"
_PREMIUM_FLOW.update({
    "ta": {"intro":"<b>👋 வணக்கம் {mention},</b>\n\n<b>🎁 Premium திட்டங்கள்</b>\n\nகீழே ஒரு Premium திட்டத்தைத் தேர்வு செய்து தொடரவும்.","continue":"🍁 அனைத்து Premium திட்டங்கள் & விலைகள் 🍁","close":"• மூடு •","plans":"<b>👋 வணக்கம் {mention}</b>\n\n🎖️ <b>கிடைக்கும் Premium திட்டங்கள்</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ உங்கள் active plan: /myplan\n\n‼️ Payment முடிந்த பிறகு screenshot அனுப்பவும்."},
    "te": {"intro":"<b>👋 నమస్తే {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nక్రింద Premium plan ఎంచుకుని కొనసాగండి.","continue":"🍁 అన్ని Premium Plans & ధరలు 🍁","close":"• మూసివేయి •","plans":"<b>👋 నమస్తే {mention}</b>\n\n🎖️ <b>అందుబాటులో ఉన్న Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment తర్వాత screenshot పంపండి."},
    "kn": {"intro":"<b>👋 ನಮಸ್ಕಾರ {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nಕೆಳಗೆ Premium plan ಆಯ್ಕೆ ಮಾಡಿ ಮುಂದುವರಿಯಿರಿ.","continue":"🍁 ಎಲ್ಲಾ Premium Plans & ಬೆಲೆಗಳು 🍁","close":"• ಮುಚ್ಚಿ •","plans":"<b>👋 ನಮಸ್ಕಾರ {mention}</b>\n\n🎖️ <b>ಲಭ್ಯವಿರುವ Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment ನಂತರ screenshot ಕಳುಹಿಸಿ."},
    "ml": {"intro":"<b>👋 നമസ്കാരം {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nതാഴെ Premium plan തിരഞ്ഞെടുത്ത് തുടരുക.","continue":"🍁 എല്ലാ Premium Plans & വിലകൾ 🍁","close":"• അടയ്ക്കുക •","plans":"<b>👋 നമസ്കാരം {mention}</b>\n\n🎖️ <b>ലഭ്യമായ Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment കഴിഞ്ഞ് screenshot അയയ്ക്കുക."},
    "bn": {"intro":"<b>👋 হ্যালো {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nনিচে একটি Premium plan বেছে নিয়ে এগিয়ে যান।","continue":"🍁 সব Premium Plans ও দাম দেখুন 🍁","close":"• বন্ধ করুন •","plans":"<b>👋 হ্যালো {mention}</b>\n\n🎖️ <b>উপলব্ধ Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment-এর পরে screenshot পাঠান।"},
    "mr": {"intro":"<b>👋 नमस्कार {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nखाली Premium plan निवडून पुढे जा.","continue":"🍁 सर्व Premium Plans आणि किंमती 🍁","close":"• बंद करा •","plans":"<b>👋 नमस्कार {mention}</b>\n\n🎖️ <b>उपलब्ध Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment नंतर screenshot पाठवा."},
    "gu": {"intro":"<b>👋 નમસ્તે {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nનીચે Premium plan પસંદ કરીને આગળ વધો.","continue":"🍁 બધા Premium Plans અને કિંમતો 🍁","close":"• બંધ કરો •","plans":"<b>👋 નમસ્તે {mention}</b>\n\n🎖️ <b>ઉપલબ્ધ Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment પછી screenshot મોકલો."},
    "pa": {"intro":"<b>👋 ਸਤ ਸ੍ਰੀ ਅਕਾਲ {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nਹੇਠਾਂ Premium plan ਚੁਣ ਕੇ ਅੱਗੇ ਵਧੋ।","continue":"🍁 ਸਾਰੇ Premium Plans ਅਤੇ ਕੀਮਤਾਂ 🍁","close":"• ਬੰਦ ਕਰੋ •","plans":"<b>👋 ਸਤ ਸ੍ਰੀ ਅਕਾਲ {mention}</b>\n\n🎖️ <b>ਉਪਲਬਧ Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment ਤੋਂ ਬਾਅਦ screenshot ਭੇਜੋ।"},
    "ur": {"intro":"<b>👋 السلام علیکم {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nنیچے Premium plan منتخب کرکے جاری رکھیں۔","continue":"🍁 تمام Premium Plans اور قیمتیں 🍁","close":"• بند کریں •","plans":"<b>👋 السلام علیکم {mention}</b>\n\n🎖️ <b>دستیاب Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment کے بعد screenshot بھیجیں۔"},
    "as": {"intro":"<b>👋 নমস্কাৰ {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nতলত এটা Premium plan বাছি আগবাঢ়ক।","continue":"🍁 সকলো Premium Plans আৰু মূল্য 🍁","close":"• বন্ধ কৰক •","plans":"<b>👋 নমস্কাৰ {mention}</b>\n\n🎖️ <b>উপলব্ধ Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment কৰাৰ পিছত screenshot পঠিয়াওক।"},
    "ne": {"intro":"<b>👋 नमस्ते {mention},</b>\n\n<b>🎁 Premium Plans</b>\n\nतल Premium plan छानेर अगाडि बढ्नुहोस्।","continue":"🍁 सबै Premium Plans र मूल्यहरू 🍁","close":"• बन्द गर्नुहोस् •","plans":"<b>👋 नमस्ते {mention}</b>\n\n🎖️ <b>उपलब्ध Premium Plans</b>\n\n🆔 UPI ID ➩ <code>lamasandeep821@okicici</code>\n\n⛽️ Active plan: /myplan\n\n‼️ Payment पछि screenshot पठाउनुहोस्।"},
})

_PREMIUM_FLOW["ta"]["intro"] = "<b>👋 வணக்கம் {mention},</b>\n\n<b>🎁 Premium அம்ச நன்மைகள்:</b>\n\n❏ இணைப்புகளை திறக்க தேவையில்லை\n❏ நேரடி கோப்புகள்\n❏ விளம்பரமில்லா அனுபவம்\n❏ அதிவேக பதிவிறக்க இணைப்பு\n❏ பல Player streaming links\n❏ வரம்பற்ற movies மற்றும் series\n❏ முழு Admin support\n❏ கிடைத்தால் request 1 மணி நேரத்தில் முடிக்கப்படும்"
_PREMIUM_FLOW["te"]["intro"] = "<b>👋 నమస్తే {mention},</b>\n\n<b>🎁 Premium ఫీచర్ ప్రయోజనాలు:</b>\n\n❏ Links open చేయాల్సిన అవసరం లేదు\n❏ Direct files\n❏ Ad-free experience\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies మరియు series\n❏ Full admin support\n❏ అందుబాటులో ఉంటే request 1 గంటలో పూర్తవుతుంది"
_PREMIUM_FLOW["kn"]["intro"] = "<b>👋 ನಮಸ್ಕಾರ {mention},</b>\n\n<b>🎁 Premium ವೈಶಿಷ್ಟ್ಯಗಳ ಪ್ರಯೋಜನಗಳು:</b>\n\n❏ Links ತೆರೆಯುವ ಅಗತ್ಯವಿಲ್ಲ\n❏ Direct files\n❏ Ad-free experience\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies ಮತ್ತು series\n❏ Full admin support\n❏ ಲಭ್ಯವಿದ್ದರೆ request 1 ಗಂಟೆಯಲ್ಲಿ ಪೂರ್ಣಗೊಳ್ಳುತ್ತದೆ"
_PREMIUM_FLOW["ml"]["intro"] = "<b>👋 നമസ്കാരം {mention},</b>\n\n<b>🎁 Premium സവിശേഷതകളുടെ നേട്ടങ്ങൾ:</b>\n\n❏ Links തുറക്കേണ്ടതില്ല\n❏ Direct files\n❏ Ad-free experience\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies and series\n❏ Full admin support\n❏ ലഭ്യമെങ്കിൽ request 1 മണിക്കൂറിൽ പൂർത്തിയാകും"
_PREMIUM_FLOW["bn"]["intro"] = "<b>👋 হ্যালো {mention},</b>\n\n<b>🎁 Premium ফিচারের সুবিধা:</b>\n\n❏ লিংক খোলার দরকার নেই\n❏ Direct files\n❏ বিজ্ঞাপনমুক্ত অভিজ্ঞতা\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies এবং series\n❏ Full admin support\n❏ পাওয়া গেলে request 1 ঘণ্টায় সম্পূর্ণ হবে"
_PREMIUM_FLOW["mr"]["intro"] = "<b>👋 नमस्कार {mention},</b>\n\n<b>🎁 Premium फीचरचे फायदे:</b>\n\n❏ लिंक उघडण्याची गरज नाही\n❏ Direct files\n❏ जाहिरात-मुक्त अनुभव\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies आणि series\n❏ Full admin support\n❏ उपलब्ध असल्यास request 1 तासात पूर्ण होईल"
_PREMIUM_FLOW["gu"]["intro"] = "<b>👋 નમસ્તે {mention},</b>\n\n<b>🎁 Premium ફીચરના ફાયદા:</b>\n\n❏ Link ખોલવાની જરૂર નથી\n❏ Direct files\n❏ Ad-free experience\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies અને series\n❏ Full admin support\n❏ ઉપલબ્ધ હોય તો request 1 કલાકમાં પૂર્ણ થશે"
_PREMIUM_FLOW["pa"]["intro"] = "<b>👋 ਸਤ ਸ੍ਰੀ ਅਕਾਲ {mention},</b>\n\n<b>🎁 Premium ਫੀਚਰ ਦੇ ਫਾਇਦੇ:</b>\n\n❏ Link ਖੋਲ੍ਹਣ ਦੀ ਲੋੜ ਨਹੀਂ\n❏ Direct files\n❏ Ad-free experience\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies ਅਤੇ series\n❏ Full admin support\n❏ ਉਪਲਬਧ ਹੋਣ ਤੇ request 1 ਘੰਟੇ ਵਿੱਚ ਪੂਰੀ ਹੋਵੇਗੀ"
_PREMIUM_FLOW["ur"]["intro"] = "<b>👋 السلام علیکم {mention},</b>\n\n<b>🎁 Premium فیچر کے فوائد:</b>\n\n❏ لنکس کھولنے کی ضرورت نہیں\n❏ Direct files\n❏ اشتہارات سے پاک تجربہ\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies اور series\n❏ Full admin support\n❏ دستیاب ہو تو request 1 گھنٹے میں مکمل ہوگی"
_PREMIUM_FLOW["as"]["intro"] = "<b>👋 নমস্কাৰ {mention},</b>\n\n<b>🎁 Premium সুবিধাসমূহ:</b>\n\n❏ Link খোলাৰ প্ৰয়োজন নাই\n❏ Direct files\n❏ বিজ্ঞাপনমুক্ত অভিজ্ঞতা\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies আৰু series\n❏ Full admin support\n❏ উপলব্ধ হ'লে request 1 ঘণ্টাত সম্পূৰ্ণ হ'ব"
_PREMIUM_FLOW["ne"]["intro"] = "<b>👋 नमस्ते {mention},</b>\n\n<b>🎁 Premium सुविधाका फाइदाहरू:</b>\n\n❏ Link खोल्न आवश्यक छैन\n❏ Direct files\n❏ विज्ञापनरहित अनुभव\n❏ High-speed download link\n❏ Multi-player streaming links\n❏ Unlimited movies र series\n❏ Full admin support\n❏ उपलब्ध भएमा request 1 घण्टामा पूरा हुनेछ"

PREMIUM_PROOF_URL = "https://t.me/+hJg4bVnzCNZiOTE1"

def _premium_flow_text(lang, key, **values):
    data = _PREMIUM_FLOW.get(lang, _PREMIUM_FLOW["en"])
    text = data.get(key, _PREMIUM_FLOW["en"].get(key, key))
    try:
        text = text.format(**values) if values else text
    except Exception:
        pass
    if key == "plans":
        proof_line = f'🏷️ <a href="{PREMIUM_PROOF_URL}">ᴘʀᴇᴍɪᴜᴍ ᴘʀᴏᴏғ</a>'
        if re.search(r"(?im)^\s*🏷️\s*(?:<[^>]+>)?premium proof(?:</[^>]+>)?\s*$", text):
            text = re.sub(
                r"(?im)^\s*🏷️\s*(?:<[^>]+>)?premium proof(?:</[^>]+>)?\s*$",
                proof_line,
                text,
            )
        elif "premium proof" not in text.lower():
            text += "\n\n" + proof_line
    return small_caps_html(text)

def premium_ads_intro(lang, mention):
    texts = {
        "en": "<blockquote>ᴛᴏ ᴇxᴘᴇʀɪᴇɴᴄᴇ ᴀᴅs ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ʏᴏᴜ ᴄᴀɴ ʙᴜʏ ᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴏʀ ʏᴏᴜ ᴄᴀɴ sʜᴀʀᴇ ᴏᴜʀ ʙᴏᴛ ᴡɪᴛʜ ʏᴏᴜʀ ғʀɪᴇɴᴅs ᴛᴏ ɢᴇᴛ ᴘʀᴇᴍɪᴜᴍ.</blockquote>",
        "hi": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴋᴀ ᴀɴᴜʙʜᴀᴠ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ ᴀᴀᴘ ʜᴀᴍᴀʀᴀ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴋʜᴀʀɪᴅ sᴀᴋᴛᴇ ʜᴀɪɴ ʏᴀ ʜᴀᴍᴀʀᴀ ʙᴏᴛ ᴅᴏsᴛᴏɴ ᴋᴇ sᴀᴀᴛʜ sʜᴀʀᴇ ᴋᴀʀᴋᴇ ᴘʀᴇᴍɪᴜᴍ ᴘᴀᴀ sᴀᴋᴛᴇ ʜᴀɪɴ.</blockquote>",
        "ta": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴘᴇʀ ᴇxᴘᴇʀɪᴇɴᴄᴇ ᴘᴇʀᴀ ᴇɴɢᴀʟ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴠᴀɴɢᴀʟᴀᴍ ᴀʟʟᴀᴛʜᴜ ᴇɴɢᴀʟ ʙᴏᴛᴀɪ ᴜɴɢᴀʟ ɴᴀɴʙᴀʀɢᴀʟᴜᴅᴀɴ sʜᴀʀᴇ sᴇʏᴛʜᴜ ᴘʀᴇᴍɪᴜᴍ ᴘᴇʀᴀʟᴀᴍ.</blockquote>",
        "te": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴀɴᴜʙʜᴀᴠɪɴᴄʜᴀᴅᴀɴɪᴋɪ ᴍᴇᴇʀᴜ ᴍᴀ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇɴɪ ᴋᴏɴᴜɢᴏʟᴜ ᴄʜᴇʏᴀᴠᴀᴄᴄʜᴜ ʟᴇᴋᴀ ᴍᴀ ʙᴏᴛɴɪ ᴍᴇᴇ sɴᴇʜɪᴛᴜʟᴀᴛᴏ sʜᴀʀᴇ ᴄʜᴇsɪ ᴘʀᴇᴍɪᴜᴍ ᴘᴏɴᴅᴀᴠᴀᴄᴄʜᴜ.</blockquote>",
        "kn": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴀɴᴜʙʜᴀᴠɪsᴀʟᴜ ɴɪᴍᴍᴀ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪsᴇ ᴋʜᴀʀɪᴅɪsɪ ᴀᴛʜᴀᴠᴀ ɴɪᴍᴍᴀ ʙᴏᴛᴀɴɴᴜ sɴᴇʜɪᴛᴀʀᴏᴛᴛɪɢᴇ sʜᴀʀᴇ ᴍᴀᴅɪ ᴘʀᴇᴍɪᴜᴍ ᴘᴀᴅᴇʏᴀʙᴀʜᴜᴅᴜ.</blockquote>",
        "ml": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴀɴᴜʙʜᴀᴠɪᴋᴋᴀɴ ɴɪɴɢᴀʟᴋᴋᴜ ɴᴀᴍᴍᴜᴅᴇ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴠᴀɴɢᴀᴍ ᴀʟʟᴇɴᴋɪʟ ɴᴀᴍᴍᴜᴅᴇ ʙᴏᴛᴛ ᴄʜᴜɴᴋᴀʟᴋᴋᴀʏᴜᴍᴀʏɪ sʜᴀʀᴇ ᴄʜᴇʏᴛʜᴜ ᴘʀᴇᴍɪᴜᴍ ɴᴇᴛᴀᴍ.</blockquote>",
        "bn": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴘᴇᴛᴇ ᴀᴘɴɪ ᴀᴍᴀᴅᴇʀ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴋɪɴᴛᴇ ᴘᴀʀᴇɴ ʙᴀ ʙɴᴅʜᴜᴅᴇʀ sᴀᴛʜᴇ ᴀᴍᴀᴅᴇʀ ʙᴏᴛ sʜᴀʀᴇ ᴋᴏʀᴇ ᴘʀᴇᴍɪᴜᴍ ᴘᴇᴛᴇ ᴘᴀʀᴇɴ.</blockquote>",
        "mr": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴀɴᴜʙʜᴀᴠɴʏᴀsᴀᴛʜɪ ᴛᴜᴍʜɪ ᴀᴍᴄʜɪ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴠɪᴋᴀᴛ ɢʜᴇᴜ sʜᴀᴋᴛᴀ ᴋɪᴍᴠᴀ ᴛᴜᴍᴄʜʏᴀ ᴍɪᴛʀᴀɴsᴏʙᴀᴛ ᴀᴍᴄʜᴀ ʙᴏᴛ sʜᴇᴀʀ ᴋᴀʀᴜɴ ᴘʀᴇᴍɪᴜᴍ ᴍɪʟᴀᴠᴜ sʜᴀᴋᴛᴀ.</blockquote>",
        "gu": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴍᴀᴛᴇ ᴛᴍᴇ ᴀᴍᴀʀᴜ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴋʜᴀʀɪᴅɪ sʜᴀᴋᴏ ᴀᴛʜᴠᴀ ᴍɪᴛʀᴏ sᴀᴛʜᴇ ᴀᴍᴀʀᴏ ʙᴏᴛ sʜᴀʀᴇ ᴋᴀʀɪ ᴘʀᴇᴍɪᴜᴍ ᴍᴇʟᴠɪ sʜᴀᴋᴏ.</blockquote>",
        "pa": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴅᴀ ᴇxᴘᴇʀɪᴇɴᴄᴇ ʟᴀɪ ᴛᴜsɪ ᴀᴘɴɪ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴋʜᴀʀɪᴅ sᴀᴋᴅᴇ ʜᴏ ʏᴀ ᴀᴘɴᴇ ᴅᴏsᴛᴀɴ ɴᴀʟ ᴀᴘɴᴀ ʙᴏᴛ sʜᴀʀᴇ ᴋᴀʀᴋᴇ ᴘʀᴇᴍɪᴜᴍ ʟᴇ sᴀᴋᴅᴇ ʜᴏ.</blockquote>",
        "ur": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴋᴇ ʟɪʏᴇ ᴀᴘ ʜᴀᴍᴀʀɪ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴋʜᴀʀɪᴅ sᴀᴋᴛᴇ ʜᴀɪɴ ʏᴀ ᴅᴏsᴛᴏɴ ᴋᴇ sᴀᴛʜ ʙᴏᴛ sʜᴇᴀʀ ᴋᴀʀᴋᴇ ᴘʀᴇᴍɪᴜᴍ ʜᴀsɪʟ ᴋᴀʀ sᴀᴋᴛᴇ ʜᴀɪɴ.</blockquote>",
        "as": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴘাবলৈ ᴀᴘᴜɴɪ ᴀᴍᴀʀ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴋʀɪᴋ ᴋᴏʀɪʙ ᴘᴀʀᴇ ʙᴀ ʙɴᴅʜᴜʀ sᴀᴛʜᴀᴛ ᴀᴍᴀʀ ʙᴏᴛ sʜᴀʀᴇ ᴋᴏʀɪ ᴘʀᴇᴍɪᴜᴍ ᴘᴀʙ ᴘᴀʀᴇ.</blockquote>",
        "ne": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴋᴏ ᴀɴᴜʙʜᴀᴠᴋᴏ ʟᴀɢɪ ᴛᴀᴘᴀɪʟᴇ ʜᴀᴍʀᴏ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ᴋɪɴɴᴀ sᴀᴋɴᴜʜᴜɴᴄʜᴀ ᴠᴀ ᴀᴘɴᴀ sᴀᴛʜɪʜᴀʀᴜsᴀɴɢᴀ ʜᴀᴍʀᴏ ʙᴏᴛ sʜᴀʀᴇ ɢᴀʀᴇʀᴀ ᴘʀᴇᴍɪᴜᴍ ᴘᴀᴜɴᴀ sᴀᴋɴᴜʜᴜɴᴄʜᴀ.</blockquote>",
        "hinglish": "<blockquote>ᴀᴅs-ғʀᴇᴇ sᴇʀᴠɪᴄᴇ ᴋᴇ ʟɪʏᴇ ᴀᴀᴘ ʜᴀᴍᴀʀᴀ ᴘʀᴇᴍɪᴜᴍ sᴇʀᴠɪᴄᴇ ʙᴜʏ ᴋᴀʀᴏ ʏᴀ ᴀᴘɴᴇ ғʀɪᴇɴᴅs ᴋᴇ sᴀᴀᴛʜ ʙᴏᴛ sʜᴀʀᴇ ᴋᴀʀᴋᴇ ᴘʀᴇᴍɪᴜᴍ ɢᴇᴛ ᴋᴀʀᴏ.</blockquote>",
    }
    return texts.get(lang, texts["en"]).format(mention=mention)

def _language_button_text(lang):
    return small_caps("🌐 LANGUAGE")

# Extra plan/order labels used by the existing Premium screen.
for _code in list(_PREMIUM_FLOW):
    _PREMIUM_FLOW[_code].update({
        "order_created_title": _PREMIUM_FLOW[_code].get("order_created_title", "Premium Order Created"),
        "plan_label": _PREMIUM_FLOW[_code].get("plan_label", "Plan"),
        "duration_label": _PREMIUM_FLOW[_code].get("duration_label", "Duration"),
        "price_label": _PREMIUM_FLOW[_code].get("price_label", "Price"),
        "user_id_label": _PREMIUM_FLOW[_code].get("user_id_label", "Order User ID"),
        "payment_status_label": _PREMIUM_FLOW[_code].get("payment_status_label", "Payment status"),
        "send_payment_help": _PREMIUM_FLOW[_code].get("send_payment_help", "Complete the payment, then send the payment screenshot to the dedicated payment bot."),
        "submission_note": _PREMIUM_FLOW[_code].get("submission_note", "Your screenshot is treated only as a payment submission and will be verified."),
    })

async def _replace_user_notice(client, user_id, notice_id, text, reply_markup=None):
    """Send a new Premium status message, then delete the previous status message."""
    try:
        fresh = await client.send_message(
            int(user_id), text, parse_mode=enums.ParseMode.HTML,
            reply_markup=reply_markup,
        )
    except Exception as exc:
        LOGGER.warning("Could not send Premium user notice to %s: %s", user_id, exc)
        return False, None
    if notice_id and int(notice_id) != int(fresh.id):
        try:
            await client.delete_messages(int(user_id), int(notice_id))
        except Exception as exc:
            LOGGER.warning("Could not delete previous Premium user notice %s/%s: %s", user_id, notice_id, exc)
    return True, int(fresh.id)


async def _update_user_notice(client, user_id, notice_id, text, reply_markup=None):
    # Compatibility wrapper: payment states now always use a fresh message.
    ok, _ = await _replace_user_notice(client, user_id, notice_id, text, reply_markup)
    return ok

for _code, _labels in {
    "en": {"order_created_title":"Premium Order Created","plan_label":"Plan","duration_label":"Duration","price_label":"Price","user_id_label":"Order User ID","payment_status_label":"Payment status","send_payment_help":"Complete the payment, then send the payment screenshot to the dedicated payment bot.","submission_note":"Your screenshot is treated only as a payment submission and will be verified.","approved_title":"Payment Approved Successfully!","expires_label":"Expires","status_label":"Status","rejected_title":"Payment Rejected"},
    "hi": {"order_created_title":"Premium Order बनाया गया","plan_label":"प्लान","duration_label":"अवधि","price_label":"कीमत","user_id_label":"Order User ID","payment_status_label":"Payment स्थिति","send_payment_help":"Payment पूरा करें, फिर dedicated payment bot पर screenshot भेजें।","submission_note":"आपका screenshot केवल payment submission है और इसकी जाँच की जाएगी।","approved_title":"Payment सफलतापूर्वक Approve हुआ!","expires_label":"समाप्ति","status_label":"स्थिति","rejected_title":"Payment Reject कर दिया गया"},
    "hinglish": {"order_created_title":"Premium Order Created","plan_label":"Plan","duration_label":"Duration","price_label":"Price","user_id_label":"Order User ID","payment_status_label":"Payment Status","send_payment_help":"Payment complete karo, phir dedicated payment bot par screenshot bhejo.","submission_note":"Aapka screenshot sirf payment submission hai aur verify kiya jayega.","approved_title":"Payment Successfully Approved!","expires_label":"Expires","status_label":"Status","rejected_title":"Payment Rejected"},
}.items():
    _PREMIUM_FLOW.setdefault(_code, {}).update(_labels)

# All other supported languages inherit the same field names; their main status
# messages are translated in I18N above.
_NAV_LABELS = {
    "en":{"back":"• ʙᴀᴄᴋ •","home":"⪻ ʙᴀᴄᴋ ᴛᴏ ʜᴏᴍᴇ","send_screenshot":"📸 SEND PAYMENT SCREENSHOT"},
    "hi":{"back":"• वापस •","home":"⪻ होम पर वापस","send_screenshot":"📸 PAYMENT SCREENSHOT भेजें"},
    "ta":{"back":"• பின்செல் •","home":"⪻ முகப்புக்கு திரும்பு","send_screenshot":"📸 PAYMENT SCREENSHOT அனுப்பவும்"},
    "te":{"back":"• వెనక్కి •","home":"⪻ హోమ్‌కు తిరిగి","send_screenshot":"📸 PAYMENT SCREENSHOT పంపండి"},
    "kn":{"back":"• ಹಿಂದೆ •","home":"⪻ ಹೋಮ್‌ಗೆ ಹಿಂತಿರುಗಿ","send_screenshot":"📸 PAYMENT SCREENSHOT ಕಳುಹಿಸಿ"},
    "ml":{"back":"• പിന്നിലേക്ക് •","home":"⪻ ഹോമിലേക്ക് മടങ്ങുക","send_screenshot":"📸 PAYMENT SCREENSHOT അയയ്ക്കുക"},
    "bn":{"back":"• ফিরে যান •","home":"⪻ হোমে ফিরে যান","send_screenshot":"📸 PAYMENT SCREENSHOT পাঠান"},
    "mr":{"back":"• मागे •","home":"⪻ होमवर परत जा","send_screenshot":"📸 PAYMENT SCREENSHOT पाठवा"},
    "gu":{"back":"• પાછા •","home":"⪻ હોમ પર પાછા","send_screenshot":"📸 PAYMENT SCREENSHOT મોકલો"},
    "pa":{"back":"• ਵਾਪਸ •","home":"⪻ ਹੋਮ ਤੇ ਵਾਪਸ","send_screenshot":"📸 PAYMENT SCREENSHOT ਭੇਜੋ"},
    "ur":{"back":"• واپس •","home":"⪻ ہوم پر واپس","send_screenshot":"📸 PAYMENT SCREENSHOT بھیجیں"},
    "as":{"back":"• পিছলৈ •","home":"⪻ হোমলৈ উভতি যাওক","send_screenshot":"📸 PAYMENT SCREENSHOT পঠিয়াওক"},
    "ne":{"back":"• पछाडि •","home":"⪻ होममा फर्कनुहोस्","send_screenshot":"📸 PAYMENT SCREENSHOT पठाउनुहोस्"},
    "hinglish":{"back":"• Back •","home":"⪻ Home Par Wapas","send_screenshot":"📸 PAYMENT SCREENSHOT Bhejo"},
}

_FIELD_LABELS = {
    "en":{"plan_label":"Plan","duration_label":"Duration","price_label":"Price","user_id_label":"Order User ID","payment_status_label":"Payment status","expires_label":"Expires","status_label":"Status"},
    "hi":{"plan_label":"प्लान","duration_label":"अवधि","price_label":"कीमत","user_id_label":"Order User ID","payment_status_label":"Payment स्थिति","expires_label":"समाप्ति","status_label":"स्थिति"},
    "ta":{"plan_label":"திட்டம்","duration_label":"காலம்","price_label":"விலை","user_id_label":"Order User ID","payment_status_label":"Payment நிலை","expires_label":"காலாவதி","status_label":"நிலை"},
    "te":{"plan_label":"ప్లాన్","duration_label":"వ్యవధి","price_label":"ధర","user_id_label":"Order User ID","payment_status_label":"Payment స్థితి","expires_label":"గడువు","status_label":"స్థితి"},
    "kn":{"plan_label":"ಪ್ಲಾನ್","duration_label":"ಅವಧಿ","price_label":"ಬೆಲೆ","user_id_label":"Order User ID","payment_status_label":"Payment ಸ್ಥಿತಿ","expires_label":"ಅವಧಿ ಮುಗಿಯುತ್ತದೆ","status_label":"ಸ್ಥಿತಿ"},
    "ml":{"plan_label":"പ്ലാൻ","duration_label":"കാലാവധി","price_label":"വില","user_id_label":"Order User ID","payment_status_label":"Payment നില","expires_label":"കാലാവസ്ഥ","status_label":"നില"},
    "bn":{"plan_label":"প্ল্যান","duration_label":"সময়কাল","price_label":"মূল্য","user_id_label":"Order User ID","payment_status_label":"Payment status","expires_label":"মেয়াদ শেষ","status_label":"অবস্থা"},
    "mr":{"plan_label":"प्लॅन","duration_label":"कालावधी","price_label":"किंमत","user_id_label":"Order User ID","payment_status_label":"Payment स्थिती","expires_label":"समाप्ती","status_label":"स्थिती"},
    "gu":{"plan_label":"પ્લાન","duration_label":"સમયગાળો","price_label":"કિંમત","user_id_label":"Order User ID","payment_status_label":"Payment સ્થિતિ","expires_label":"સમાપ્તિ","status_label":"સ્થિતિ"},
    "pa":{"plan_label":"ਪਲਾਨ","duration_label":"ਮਿਆਦ","price_label":"ਕੀਮਤ","user_id_label":"Order User ID","payment_status_label":"Payment ਸਥਿਤੀ","expires_label":"ਮਿਆਦ ਖਤਮ","status_label":"ਸਥਿਤੀ"},
    "ur":{"plan_label":"پلان","duration_label":"مدت","price_label":"قیمت","user_id_label":"Order User ID","payment_status_label":"Payment کی حالت","expires_label":"میعاد ختم","status_label":"حالت"},
    "as":{"plan_label":"প্লেন","duration_label":"সময়কাল","price_label":"মূল্য","user_id_label":"Order User ID","payment_status_label":"Payment অৱস্থা","expires_label":"ম্যাদ শেষ","status_label":"অৱস্থা"},
    "ne":{"plan_label":"प्लान","duration_label":"अवधि","price_label":"मूल्य","user_id_label":"Order User ID","payment_status_label":"Payment स्थिति","expires_label":"म्याद","status_label":"स्थिति"},
    "hinglish":{"plan_label":"Plan","duration_label":"Duration","price_label":"Price","user_id_label":"Order User ID","payment_status_label":"Payment Status","expires_label":"Expires","status_label":"Status"},
}
for _code in LANGUAGES:
    _PREMIUM_FLOW.setdefault(_code, {})
    for _key, _default in _PREMIUM_FLOW["en"].items():
        _PREMIUM_FLOW[_code].setdefault(_key, _default)
    _PREMIUM_FLOW[_code].update(_FIELD_LABELS.get(_code, _FIELD_LABELS["en"]))
    _PREMIUM_FLOW[_code].update(_NAV_LABELS.get(_code, _NAV_LABELS["en"]))

for _code, _labels in {
    "en":{"activated_title":"Premium Activated Successfully!","renewed_title":"Premium Renewed Successfully!"},
    "hi":{"activated_title":"Premium सफलतापूर्वक सक्रिय हुआ!","renewed_title":"Premium सफलतापूर्वक Renew हुआ!"},
    "hinglish":{"activated_title":"Premium Successfully Activated!","renewed_title":"Premium Successfully Renewed!"},
}.items():
    _PREMIUM_FLOW.setdefault(_code, {}).update(_labels)
for _code in LANGUAGES:
    _PREMIUM_FLOW.setdefault(_code, {})
    _PREMIUM_FLOW[_code].setdefault("activated_title", _PREMIUM_FLOW["en"]["activated_title"])
    _PREMIUM_FLOW[_code].setdefault("renewed_title", _PREMIUM_FLOW["en"]["renewed_title"])

TEMP_MESSAGE_DELETE_SECONDS = 10


def _language_markup():
    codes = list(LANGUAGES)
    rows = []
    for i in range(0, len(codes), 2):
        rows.append([InlineKeyboardButton(LANGUAGES[codes[i]], callback_data=f"paylang:{codes[i]}")])
        if i + 1 < len(codes):
            rows[-1].append(InlineKeyboardButton(LANGUAGES[codes[i + 1]], callback_data=f"paylang:{codes[i+1]}"))
    return InlineKeyboardMarkup(rows)


async def _delete_message_later(sent_message, delay=TEMP_MESSAGE_DELETE_SECONDS):
    """Delete a temporary bot message after a fixed retention window.

    Telegram bots do not receive a reliable private-chat "message seen/read"
    event, so deletion is scheduled from send time rather than pretending to
    know when the user viewed it.
    """
    try:
        await asyncio.sleep(delay)
        await sent_message.delete()
    except Exception:
        pass


def _schedule_temp_delete(sent_message, delay=TEMP_MESSAGE_DELETE_SECONDS):
    if sent_message is not None:
        asyncio.create_task(_delete_message_later(sent_message, delay))
    return sent_message


async def _reply_temp(message, text, **kwargs):
    sent = await message.reply_text(text, **kwargs)
    return _schedule_temp_delete(sent)


async def _send_user_temp(client, user_id, text, **kwargs):
    sent = await client.send_message(user_id, text, **kwargs)
    return _schedule_temp_delete(sent)

def _contact_admin_markup(lang="en", screenshot_message_id=None):
    """Contact-admin + close controls for the final user-side payment message."""
    username = (OWNER_USERNAME or "").strip().lstrip("@")
    rows = []
    if username:
        rows.append([InlineKeyboardButton(
            _tr(lang, "contact"), url=f"https://t.me/{username}"
        )])
    if screenshot_message_id:
        close_label = _premium_flow_text(lang, "close") or "✖️ CLOSE"
        rows.append([InlineKeyboardButton(
            close_label, callback_data=f"payclose:{screenshot_message_id}"
        )])
    return InlineKeyboardMarkup(rows) if rows else None


def _plan_key(value):
    value = str(value).lower().strip()
    aliases = {
        "7": "week", "7day": "week", "7days": "week", "week": "week",
        "30": "month", "30day": "month", "30days": "month", "month": "month",
        "90": "3month", "3month": "3month", "3months": "3month",
        "180": "6month", "6month": "6month", "6months": "6month",
        "365": "year", "1year": "year", "year": "year", "12month": "year",
        "lifetime": "lifetime", "life": "lifetime",
    }
    return aliases.get(value, value if value in PREMIUM_PLANS else None)


def _expiry_from(base, plan):
    days = PREMIUM_PLANS[plan]["days"]
    if days is None:
        return LIFETIME_EXPIRY
    return base + datetime.timedelta(days=days)


def _remaining_label(expires_at):
    seconds = max(0, int((expires_at - _now()).total_seconds()))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"



def _money_number(value):
    """Normalize a displayed amount to numeric rupees.

    Currency symbols and leading zeroes are formatting, not value.  Thus
    ₹23, ₹23.00, Rs 23, INR 23 and ₹023 all normalize to 23.00.
    """
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    text = re.sub(r"(?i)(?:₹|rs\.?|inr)\s*", "", text)
    m = re.search(r"(?<!\d)(\d+(?:[.]\d{1,2})?)(?!\d)", text)
    if not m:
        return None
    try:
        return round(float(m.group(1)), 2)
    except ValueError:
        return None


def _expected_amount(plan_price):
    return _money_number(plan_price)


def _extract_amount(text, expected):
    """Extract the most plausible payment amount from varied OCR output.

    Payment apps often omit the currency symbol.  We therefore consider
    standalone numeric candidates, currency-labelled candidates, and common
    OCR corruptions.  A candidate matching the pending order amount is strongly
    preferred, which prevents transaction/reference numbers from being chosen.
    """
    if not text:
        return None
    expected = _money_number(expected)
    normalized = text.replace("\u00a0", " ")
    lines = [re.sub(r"\s+", " ", x.strip()) for x in normalized.splitlines() if x.strip()]
    candidates = []

    def add(value, score, source):
        if value is None or value < 0 or value >= 10000000:
            return
        candidates.append((round(value, 2), score, source))

    currency_patterns = [
        r"(?:₹|rs\.?|inr)\s*([0-9][0-9,]*(?:[.]\d{1,2})?)",
        r"(?:amount\s*(?:paid|sent|debited|received)?|paid\s*(?:amount)?|sent\s*amount|total|payment)\D{0,40}([0-9][0-9,]*(?:[.]\d{1,2})?)",
    ]
    for line in lines:
        for pat in currency_patterns:
            for m in re.finditer(pat, line, re.I):
                add(_money_number(m.group(1)), 100, "labelled")

    # Standalone amount lines. OCR may turn ₹23.00 into <23:00.
    for line in lines:
        stripped = line.strip()
        m = re.fullmatch(r"[^0-9]{0,8}(\d{1,7})(?:[.,:]([0-9]{1,2}))?[^0-9]{0,8}", stripped)
        if m:
            whole, frac = m.groups()
            value = float(f"{whole}.{frac}") if frac is not None else float(whole)
            add(value, 85, "standalone")

    # A bare amount can be embedded beside a payment label.
    for line in lines:
        if re.search(r"\b(?:amount|paid|sent|received|debited|credited|total|payment)\b", line, re.I):
            for token in re.findall(r"(?<!\d)\d{1,7}(?:[.]\d{1,2})?(?!\d)", line):
                add(_money_number(token), 80, "labelled_bare")

    # If OCR removed line breaks, search the whole OCR text for currency forms.
    flat = re.sub(r"\s+", " ", normalized)
    for pat in currency_patterns:
        for m in re.finditer(pat, flat, re.I):
            add(_money_number(m.group(1)), 95, "flat_labelled")

    # On some screenshots Tesseract reads the rupee glyph as a leading 2, so
    # visible ₹23 may become 223. Only apply this correction for the exact
    # selected ₹23 plan and only as a payment-candidate pattern.
    if expected is not None and abs(expected - 23.00) < 0.01:
        if re.search(r"(?<!\d)223(?:[.,:]00)?(?!\d)", normalized):
            add(23.00, 82, "rupee_glyph_ocr")
        if re.search(r"[¥₹]\s*23(?:[.,]00)?", normalized, re.I):
            add(23.00, 105, "currency_23")

    if not candidates:
        return None
    if expected is not None:
        matches = [c for c in candidates if abs(c[0] - expected) < 0.01]
        if matches:
            matches.sort(key=lambda c: c[1], reverse=True)
            return matches[0][0]
        return None
    candidates.sort(key=lambda c: c[1], reverse=True)
    return candidates[0][0]


def _parse_transaction_datetime(text, reference, expected_amount=None):
    """Extract the actual transaction date/time from repeated payment OCR text.

    Priority is given to a complete date+AM/PM time pair that appears together
    in the screenshot text. This avoids selecting an unrelated OCR clock value.
    """
    if not text:
        return None, False

    normalized = text.replace("\u00a0", " ")
    ref_ist = _aware_ist(reference) or reference

    month_names = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    date_time_pat = re.compile(
        rf"\b(\d{{1,2}})\s*,?\s*({month_names})\s*,?\s*(\d{{2,4}})\s*,?\s*"
        rf"(\d{{1,2}})\s*[:.]\s*(\d{{2}})(?:\s*[:.]\s*(\d{{2}}))?\s*(AM|PM|A\.M\.|P\.M\.)\b",
        re.I,
    )

    # First: exact date+time pairs. These are the strongest candidates because
    # the time is physically attached to the transaction date in the screenshot.
    exact = {}
    for m in date_time_pat.finditer(normalized):
        try:
            day = int(m.group(1))
            month = datetime.datetime.strptime(m.group(2)[:3].title(), "%b").month
            year = int(m.group(3))
            if year < 100:
                year += 2000
            raw_hour, minute, second = int(m.group(4)), int(m.group(5)), int(m.group(6) or 0)
            ap = m.group(7).upper().replace(".", "")
            if not (1 <= raw_hour <= 12 and minute <= 59 and second <= 59):
                continue
            hour = raw_hour % 12 + (12 if ap == "PM" else 0)
            dt = datetime.datetime(year, month, day, hour, minute, second)
            exact[dt] = exact.get(dt, 0) + 1
        except (ValueError, TypeError):
            continue

    if exact:
        # Most repeated exact transaction date+time wins. This directly handles
        # OCR output where the same screenshot is read multiple times.
        best_dt, best_count = max(exact.items(), key=lambda item: item[1])
        if best_count >= 2:
            return best_dt, True
        # Even a single complete date+time pair is stronger than a stray time.
        return best_dt, True

    # Fallback only when OCR did not produce a complete date+time pair.
    cleaned = re.sub(r"\s+", " ", normalized).strip()
    date_candidates = []
    for pat in (
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b",
        r"\b(\d{1,2})[.](\d{1,2})[.](\d{2,4})\b",
    ):
        for m in re.finditer(pat, cleaned):
            d, mo, y = map(int, m.groups())
            if y < 100:
                y += 2000
            try:
                date_candidates.append((datetime.date(y, mo, d), m.start()))
            except ValueError:
                pass

    month_pat = re.compile(
        rf"\b(\d{{1,2}})\s*,?\s*({month_names})\s*,?\s*(\d{{2,4}})?\b|"
        rf"\b({month_names})\s*,?\s*(\d{{1,2}})\s*,?\s*(\d{{2,4}})?\b", re.I)
    for m in month_pat.finditer(cleaned):
        try:
            if m.group(1):
                d, mon, year = int(m.group(1)), m.group(2), m.group(3)
            else:
                mon, d, year = m.group(4), int(m.group(5)), m.group(6)
            y = int(year) if year else ref_ist.year
            if y < 100:
                y += 2000
            mo = datetime.datetime.strptime(mon[:3].title(), "%b").month
            date_candidates.append((datetime.date(y, mo, d), m.start()))
        except (ValueError, TypeError):
            pass

    time_pat = re.compile(
        r"(?<!\d)(\d{1,2})\s*[:.]\s*(\d{2})(?:\s*[:.]\s*(\d{2}))?\s*(AM|PM|A\.M\.|P\.M\.)(?!\w)", re.I)
    times = {}
    for m in time_pat.finditer(cleaned):
        try:
            raw_hour, minute, second = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
            ap = m.group(4).upper().replace(".", "")
            if not (1 <= raw_hour <= 12 and minute <= 59 and second <= 59):
                continue
            hour = raw_hour % 12 + (12 if ap == "PM" else 0)
            key = datetime.time(hour, minute, second)
            times[key] = times.get(key, 0) + 1
        except (ValueError, TypeError):
            pass

    if not date_candidates or not times:
        return None, bool(date_candidates)

    best_time = max(times.items(), key=lambda item: item[1])[0]
    best_date = max(date_candidates, key=lambda item: -abs(item[1] - cleaned.find(best_time.strftime("%I:%M"))))[0]
    return datetime.datetime.combine(best_date, best_time), True

def _payment_success_signal(text):
    """Detect a clear payment-success status from OCR text.

    Supports common wording used by GPay, PhonePe, Paytm, BHIM, UPI and bank
    payment apps. A clear failure/pending status always overrides positives.
    """
    lower = re.sub(r"\s+", " ", (text or "").lower()).strip()

    # These indicate that the payment is not successfully completed.
    negative = [
        "payment failed", "transaction failed", "transfer failed", "failed",
        "declined", "reversed", "cancelled", "canceled",
        "pending", "processing", "in progress",
    ]
    if any(word in lower for word in negative):
        return False

    # Common explicit success statuses across payment apps.
    positive = [
        "payment successful", "payment success",
        "payment completed", "payment complete",
        "transaction successful", "transaction success",
        "transaction completed", "transaction complete",
        "transfer successful", "transfer success",
        "transfer completed", "transfer complete",
        "paid successfully", "paid successfully",
        "payment done", "transaction done",
        "completed successfully", "successfully completed",
        "completed", "successful", "success",
    ]
    return any(phrase in lower for phrase in positive)


def _payment_match_result(order, ocr_text, received_at):
    """Match payment evidence without trusting OCR blindly.

    Amount is always required. The OCR transaction date is anchored to when the
    screenshot was received, not when the user originally opened the order.
    Optional timestamp approval checks the full date+time against a bounded
    window and therefore also catches wrong day/month/year selections.
    """
    expected = _expected_amount(order.get("plan_price"))
    found = _extract_amount(ocr_text, expected)
    amount_match = None if found is None else (expected is not None and abs(found - expected) < 0.01)

    parsed_tx_dt, parsed_confident = _parse_transaction_datetime(ocr_text, received_at, expected)
    tx_dt = parsed_tx_dt if parsed_confident else None
    reference = _aware_ist(received_at)
    date_match = None
    time_match = None
    date_note = "Transaction date could not be read."

    if tx_dt is not None and reference is not None:
        tx_aware = IST.localize(tx_dt) if tx_dt.tzinfo is None else tx_dt.astimezone(IST)
        # Date is tied to the screenshot submission, avoiding stale order-created
        # dates and UTC/IST day-boundary errors.
        date_match = tx_aware.date() == reference.date()
        date_note = f"Transaction date: {tx_aware.date().isoformat()}"
        if PAYMENT_TIME_APPROVAL_ENABLED:
            earliest = reference - datetime.timedelta(minutes=PAYMENT_MAX_DELAY_MINUTES)
            latest = reference + datetime.timedelta(minutes=PAYMENT_FUTURE_TOLERANCE_MINUTES)
            time_match = earliest <= tx_aware <= latest
    elif tx_dt is not None:
        date_match = True

    success_signal = _payment_success_signal(ocr_text) if ocr_text else None
    if not PAYMENT_OCR_ENABLED:
        return True, {"ocr_status": "disabled", "amount_found": found, "amount_match": None,
                      "transaction_at": tx_dt, "date_match": None, "time_match": None,
                      "success_signal": None, "confidence": 0, "date_note": "OCR checks disabled; sender/order matching used."}

    hard_fail = amount_match is False or date_match is False or (PAYMENT_TIME_APPROVAL_ENABLED and time_match is False)
    score = 0
    if amount_match: score += 60
    if date_match: score += 30
    if success_signal: score += 10
    if PAYMENT_TIME_APPROVAL_ENABLED and time_match:
        score += 10
    passed = (not hard_fail) and amount_match is True and date_match is True and success_signal is True and (not PAYMENT_TIME_APPROVAL_ENABLED or time_match is True)
    return passed, {
        "ocr_status": "matched" if passed else "manual_review",
        "amount_found": found, "amount_match": amount_match,
        "transaction_at": tx_dt, "date_match": date_match, "time_match": time_match,
        "success_signal": success_signal, "confidence": min(score, 100),
        "date_note": date_note,
        "date_detected": tx_dt.date().isoformat() if tx_dt else None,
        "time_detected": tx_dt.strftime("%I:%M %p") if tx_dt else None,
    }


async def _ocr_payment_message(payment_client, message):
    """Run the original payment OCR safely without starving the bot.

    IMPORTANT: The OCR analysis itself is intentionally unchanged:
    - same 3600px image limit
    - same grayscale/contrast/upscaled/threshold variants
    - same PSM 6/11/12 passes for every variant
    - same image_to_data pass
    - same OCR output and perceptual hash generation

    The only changes here are resource-safety measures:
    - one screenshot OCR job at a time by default;
    - CPU-heavy Pillow/Tesseract work runs in a worker thread;
    - large temporary Pillow objects are released as soon as each phase ends.
    """
    if not PAYMENT_OCR_ENABLED:
        return "", "disabled", None, None

    async with _PAYMENT_OCR_SEMAPHORE:
        try:
            raw = await payment_client.download_media(message, in_memory=True)
            if raw is None:
                return "", "download_failed", None, None

            raw.seek(0)
            blob = raw.read()
            if not blob:
                return "", "download_failed", None, None

            sha256 = hashlib.sha256(blob).hexdigest()

            # Keep the download outside the CPU worker, then do all CPU-heavy
            # image/Tesseract work away from the main Pyrogram event loop.
            try:
                return await asyncio.to_thread(
                    _run_original_payment_ocr_sync,
                    blob,
                    sha256,
                )
            except Exception as exc:
                LOGGER.exception("Payment screenshot OCR worker failed: %s", exc)
                return "", "ocr_failed", sha256, None

        except Exception as exc:
            LOGGER.exception("Payment screenshot OCR failed: %s", exc)
            return "", "ocr_failed", None, None


def _run_original_payment_ocr_sync(blob, sha256):
    """Original OCR algorithm, executed outside the asyncio event loop."""
    tess_cmd = shutil.which("tesseract")
    if not tess_cmd:
        LOGGER.error("Tesseract executable was not found in PATH.")
        return "", "tesseract_missing", sha256, None

    pytesseract.pytesseract.tesseract_cmd = tess_cmd

    try:
        version = subprocess.run(
            [tess_cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.splitlines()[0]
    except Exception:
        version = "unknown"
    LOGGER.info("Payment OCR using %s (%s)", tess_cmd, version)

    image = None
    gray = None
    enlarged = None
    deadline = time.monotonic() + PAYMENT_OCR_JOB_TIMEOUT_SECONDS
    try:
        image = ImageOps.exif_transpose(
            Image.open(io.BytesIO(blob)).convert("RGB")
        )
        image.thumbnail((3600, 3600), Image.Resampling.LANCZOS)

        gray = ImageOps.grayscale(image)

        # Preserve the original four OCR variants and their exact order.
        # Process them one at a time so temporary variants do not all remain
        # resident in RAM simultaneously.
        variant_builders = [
            ("gray", lambda: gray),
            ("contrast", lambda: ImageOps.autocontrast(gray)),
        ]

        enlarged = gray.resize(
            (max(1, gray.width * 2), max(1, gray.height * 2)),
            Image.Resampling.LANCZOS,
        )
        enlarged = ImageEnhance.Contrast(enlarged).enhance(1.6)
        enlarged = enlarged.filter(ImageFilter.SHARPEN)

        variant_builders.extend([
            ("upscaled", lambda: enlarged),
            (
                "threshold",
                lambda: ImageOps.autocontrast(enlarged).point(
                    lambda px: 255 if px >= 175 else 0
                ),
            ),
        ])

        texts = []
        errors = []
        successful_passes = 0

        # EXACTLY the original 4 x 3 OCR passes.
        for name, build_variant in variant_builders:
            if time.monotonic() >= deadline:
                errors.append("OCR job deadline reached")
                break
            variant = build_variant()
            try:
                for psm in (6, 11, 12):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        errors.append("OCR job deadline reached")
                        break
                    try:
                        value = pytesseract.image_to_string(
                            variant,
                            lang="eng",
                            config=f"--oem 3 --psm {psm}",
                            timeout=max(1, min(PAYMENT_OCR_PASS_TIMEOUT, int(remaining))),
                        )
                        if value and value.strip():
                            successful_passes += 1
                            texts.append(value.strip())
                    except Exception as exc:
                        errors.append(f"{name}/psm{psm}: {exc}")
                        LOGGER.warning(
                            "Payment OCR pass failed (%s/psm%s): %s",
                            name,
                            psm,
                            exc,
                        )
            finally:
                # Do not close shared gray/enlarged objects here.
                if name not in ("gray", "upscaled"):
                    try:
                        variant.close()
                    except Exception:
                        pass

        # Preserve the original OCR-data recovery pass.
        try:
            if time.monotonic() >= deadline:
                raise RuntimeError("OCR job deadline reached before recovery pass")
            data = pytesseract.image_to_data(
                ImageOps.autocontrast(enlarged),
                lang="eng",
                config="--oem 3 --psm 11",
                output_type=pytesseract.Output.DICT,
                timeout=PAYMENT_OCR_PASS_TIMEOUT,
            )
            words = [
                x.strip() for x in data.get("text", [])
                if x and x.strip()
            ]
            if words:
                texts.append(" ".join(words))
                successful_passes += 1
        except Exception as exc:
            errors.append(f"data: {exc}")
            LOGGER.warning("Payment OCR data pass failed: %s", exc)

        text = "\n".join(dict.fromkeys(texts))[:30000]

        # Preserve the original perceptual fingerprint algorithm.
        tiny = ImageOps.grayscale(image).resize(
            (32, 32), Image.Resampling.LANCZOS
        )
        pixels = list(tiny.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if px >= avg else "0" for px in pixels)
        perceptual = hex(int(bits, 2))[2:].zfill(256)
        try:
            tiny.close()
        except Exception:
            pass

        if text:
            LOGGER.info(
                "Payment OCR succeeded: %d passes, %d characters",
                successful_passes,
                len(text),
            )
            return text, "ok", sha256, perceptual

        if errors:
            LOGGER.error(
                "Payment OCR produced no text. First error: %s",
                errors[0],
            )
        else:
            LOGGER.error(
                "Payment OCR produced no text and no exception was reported."
            )
        return "", "ocr_no_text", sha256, perceptual

    except Exception as exc:
        LOGGER.exception("Payment screenshot OCR failed: %s", exc)
        return "", "ocr_failed", sha256, None
    finally:
        # Explicitly release large Pillow buffers after the OCR job.
        for obj in (gray, enlarged, image):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass


async def _activate_order(client, order, screenshot_message_id):
    """Grant Premium using the exact plan stored on the payment order.

    Older orders may contain a display name (for example ``01 WEEK``) instead
    of the internal plan key (``week``), so resolve both forms before touching
    the user or order. This prevents manual approval from falsely failing.
    """
    user_id = int(order["user_id"])
    now = _now()

    raw_plan = str(order.get("selected_plan") or "").strip()
    plan_key = _plan_key(raw_plan)
    if not plan_key:
        raw_lower = raw_plan.lower()
        for key, item in PREMIUM_PLANS.items():
            if raw_lower == str(item.get("name", "")).lower():
                plan_key = key
                break
    if not plan_key:
        # Final compatibility fallback for records that only preserved duration.
        raw_duration = str(order.get("plan_duration") or "").lower().strip()
        for key, item in PREMIUM_PLANS.items():
            if raw_duration == str(item.get("duration", "")).lower().strip():
                plan_key = key
                break
    if not plan_key or plan_key not in PREMIUM_PLANS:
        raise RuntimeError(f"Unknown Premium plan on payment order: {raw_plan or order.get('plan_duration')!r}")

    # Renewal rule: preserve remaining time. If current Premium is active,
    # add the selected duration to its existing expiry instead of overwriting it.
    current = await db.get_user(user_id)
    current_expiry = _naive_utc(current.get("expiry_time")) if current else None
    temporary_review = bool(order.get("temporary_review_access"))
    if (not temporary_review) and isinstance(current_expiry, datetime.datetime) and current_expiry > now:
        base = current_expiry
    else:
        base = now

    new_expiry = _expiry_from(base, plan_key)

    # This is the existing Premium access store used by the rest of the bot.
    await db.update_user({
        "id": user_id,
        "expiry_time": new_expiry,
        "premium_plan": plan_key,
        "premium_plan_name": order["plan_duration"],
        "premium_price": order["plan_price"],
    })

    await db.set_order_activation(user_id, now, new_expiry)
    await db.premium_orders.update_one(
        {"user_id": user_id},
        {"$set": {
            "screenshot_message_id": int(screenshot_message_id),
            "selected_plan": plan_key,
            "payment_status": "manually_verified",
            "premium_status": "active",
            "temporary_review_access": False,
            "temporary_review_expires_at": None,
        }},
    )

    is_renewal = (not temporary_review) and isinstance(current_expiry, datetime.datetime) and current_expiry > now
    plan = PREMIUM_PLANS[plan_key]
    lang = await _user_language(user_id)
    if is_renewal:
        text = (
            f"♻️ <b>{_premium_flow_text(lang, 'renewed_title')}</b>\n\n"
            f"📦 {_premium_flow_text(lang, 'plan_label')}: <b>{escape(plan['name'])}</b>\n"
            f"⏳ {_premium_flow_text(lang, 'duration_label')}: <b>{escape(plan['duration'])}</b>\n"
            f"📅 {_premium_flow_text(lang, 'expires_label')}: <b>{_fmt_dt(new_expiry)}</b>\n"
            f"🟢 {_premium_flow_text(lang, 'status_label')}: Active\n\n" +
            _tr(lang, "renewed")
        )
    else:
        text = (
            f"✅ <b>{_premium_flow_text(lang, 'activated_title')}</b>\n\n"
            f"📦 {_premium_flow_text(lang, 'plan_label')}: <b>{escape(plan['name'])}</b>\n"
            f"⏳ {_premium_flow_text(lang, 'duration_label')}: <b>{escape(plan['duration'])}</b>\n"
            f"📅 Activated: <b>{_fmt_dt(now)}</b>\n"
            f"⏳ {_premium_flow_text(lang, 'expires_label')}: <b>{_fmt_dt(new_expiry)}</b>\n"
            f"🟢 {_premium_flow_text(lang, 'status_label')}: Active\n\n" +
            _tr(lang, "activated")
        )
    try:
        submission = await db.get_payment_submission(user_id, screenshot_message_id)
        notice_id = (submission or {}).get("user_notice_message_id")
        ok, new_notice_id = await _replace_user_notice(client, user_id, notice_id, text)
        if ok and new_notice_id:
            await db.update_payment_submission(
                user_id, screenshot_message_id, {"user_notice_message_id": new_notice_id}
            )
    except Exception as exc:
        LOGGER.warning("Could not update Premium activation notice for %s: %s", user_id, exc)

    try:
        await client.send_message(
            LOG_CHANNEL,
            f"#PREMIUM_PAYMENT_SUBMITTED\n"
            f"User ID: <code>{user_id}</code>\n"
            f"Plan: {escape(plan['name'])}\n"
            f"Price: {escape(plan['price'])}\n"
            f"Screenshot message: <code>{screenshot_message_id}</code>\n"
            f"Payment status: <code>manually_verified</code>\n"
            f"Premium status: <code>active</code>\n"
            f"Expires: {_fmt_dt(new_expiry)}\n\n"
            "⚠️ Screenshot is a payment submission only. Manual transaction "
            "verification is still required.",
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception as exc:
        LOGGER.warning("Could not write payment log: %s", exc)


async def process_payment_submission(payment_client, message):
    """Handle a screenshot, verify sender/order and perform a soft OCR check."""
    sender = message.from_user
    if not sender:
        return

    user_id = int(sender.id)
    received_at = _now()
    media_kind = "photo" if message.photo else "document"
    file_id = None
    file_unique_id = None
    if message.photo:
        file_id = message.photo.file_id
        file_unique_id = message.photo.file_unique_id
    elif message.document:
        file_id = message.document.file_id
        file_unique_id = message.document.file_unique_id

    order = await db.get_pending_premium_order(user_id)
    submission = {
        "user_id": user_id,
        "username": sender.username or "",
        "full_name": (sender.first_name or "") + ((" " + sender.last_name) if sender.last_name else ""),
        "payment_bot_message_id": int(message.id),
        "payment_chat_id": int(message.chat.id),
        "media_type": media_kind,
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "caption": message.caption or "",
        "received_at": received_at,
        "matched_order": bool(order),
        "status": "matched" if order else "unmatched",
        "review_status": "pending" if order else "not_required",
    }
    recorded = await db.record_payment_submission(submission)
    if not recorded:
        LOGGER.info("Ignoring duplicate payment screenshot update for %s/%s", user_id, message.id)
        return

    if not order:
        unmatched_report = (
            "⚠️ <b>Unmatched payment screenshot</b>\n\n"
            f"👤 User ID: <code>{user_id}</code>\n"
            f"👤 Username: @{escape(sender.username) if sender.username else 'none'}\n"
            f"🆔 Message ID: <code>{message.id}</code>"
        )
        for admin_id in _admins():
            try:
                admin_notice = await payment_client.send_message(
                    admin_id, unmatched_report, parse_mode=enums.ParseMode.HTML
                )
                _schedule_temp_delete(admin_notice, 10)
                admin_screenshot = await payment_client.copy_message(
                    admin_id, message.chat.id, message.id
                )
                _schedule_temp_delete(admin_screenshot, 10)
            except Exception as exc:
                LOGGER.warning("Could not send unmatched payment to admin %s: %s", admin_id, exc)
        # Tell the sender why nothing started. This is especially important
        # when an order has changed between payment attempts.
        try:
            lang = await _user_language(user_id, sender)
            notice = await payment_client.send_message(
                user_id,
                "⚠️ <b>No pending Premium order was found.</b>\n\n"
                "Please return to the main bot, select your Premium plan first, "
                "then send the screenshot to this payment bot. If you already "
                "selected a plan, please retry once or contact the owner.",
                parse_mode=enums.ParseMode.HTML,
            )
            _schedule_temp_delete(notice, 30)
        except Exception as exc:
            LOGGER.warning("Could not explain unmatched payment screenshot to %s (%s)", user_id, type(exc).__name__)
        _schedule_temp_delete(message, TEMP_MESSAGE_DELETE_SECONDS)
        return

    # Working baseline preserved: only matched Premium orders enter OCR.
    # Show the multilingual processing notice immediately before OCR begins.
    try:
        lang = await _user_language(user_id, sender)
        progress_message = await message.reply_text(
            _tr(lang, "progress_title") + "\n\n" + _tr(lang, "progress_body"),
            parse_mode=enums.ParseMode.HTML,
        )
        await db.update_payment_submission(
            user_id, message.id, {"user_notice_message_id": int(progress_message.id)}
        )
    except Exception:
        pass

    ocr_text, ocr_status, file_sha256, perceptual_hash = await _ocr_payment_message(payment_client, message)
    passed, check = _payment_match_result(order, ocr_text, received_at)

    # A perceptual image hash alone is too aggressive: two genuinely different
    # payment screenshots can look almost identical except for the transaction
    # time or other small text. Only treat an exact file match as an automatic
    # duplicate. Similar-image matches require the OCR transaction details to
    # agree as well, so a new payment with a different transaction time is not
    # incorrectly sent to manual review.
    duplicate = await db.find_duplicate_payment_submission(file_sha256, None, user_id, message.id)
    if duplicate:
        passed = False
        check["duplicate_suspected"] = True
    else:
        check["duplicate_suspected"] = False
    await db.update_payment_submission(
        user_id,
        message.id,
        {
            "ocr_status": check["ocr_status"],
            "ocr_text": ocr_text[:4000],
            "amount_found": check["amount_found"],
            "amount_match": check["amount_match"],
            "transaction_at": check["transaction_at"],
            "time_match": check.get("time_match"),
            "date_match": check.get("date_match"),
            "ocr_engine_status": ocr_status,
            "file_sha256": file_sha256,
            "perceptual_hash": perceptual_hash,
            "confidence": check.get("confidence"),
            "success_signal": check.get("success_signal"),
            "duplicate_suspected": check.get("duplicate_suspected", False),
        },
    )

    if not passed:
        await db.update_payment_submission(
            user_id, message.id,
            {"review_status": "manual_review_required"}
        )
        await db.update_order_payment_review(user_id, message.id, check)
        # Failed/uncertain screenshots still receive short temporary Premium
        # while the owner manually checks the submitted screenshot.
        review_expiry = await _grant_review_access(user_id, order, minutes=PAYMENT_MAX_DELAY_MINUTES)
        # Build an admin-only verification report. Keep the exact technical reason
        # visible to reviewers so they can understand why auto-approval stopped.
        reason = []
        if check["amount_match"] is False:
            reason.append("The detected amount does not match the selected plan.")
        elif check["amount_match"] is None:
            reason.append("The payment amount was not detected in the screenshot.")
        if check.get("date_match") is False:
            reason.append("Transaction date does not match the screenshot submission date.")
        elif check.get("date_match") is None:
            reason.append("Transaction date could not be read confidently.")
        if PAYMENT_TIME_APPROVAL_ENABLED:
            if check.get("time_match") is False:
                reason.append("Transaction time is outside the allowed approval window.")
            elif check.get("time_match") is None:
                reason.append("Transaction time could not be read confidently.")
        if check.get("success_signal") is False:
            reason.append("A payment-success confirmation was not detected.")
        if check.get("duplicate_suspected"):
            reason.append("The same or a very similar screenshot was already submitted.")
        if check.get("ocr_status") == "disabled":
            reason.append("OCR verification is disabled, so automatic evidence checks were unavailable.")
        elif ocr_status == "download_failed":
            reason.append("The screenshot could not be downloaded for analysis.")
        elif ocr_status == "ocr_failed":
            reason.append("OCR analysis failed while reading this screenshot.")
        elif not reason:
            reason.append("The available evidence did not reach the automatic approval threshold.")

        amount_found = check.get("amount_found")
        tx_at = check.get("transaction_at")
        amount_result = "Matched" if check.get("amount_match") is True else ("Not matched" if check.get("amount_match") is False else "Not confidently detected")
        if PAYMENT_TIME_APPROVAL_ENABLED:
            time_result = "Matched" if check.get("time_match") is True else ("Not matched" if check.get("time_match") is False else "Not confidently detected")
        else:
            time_result = "Not used for approval (setting OFF)"
        success_result = "Detected" if check.get("success_signal") is True else ("Not detected" if check.get("success_signal") is False else "Not available")
        duplicate_result = "Suspected duplicate" if check.get("duplicate_suspected") else "No duplicate detected"
        ocr_result = str(ocr_status or "unknown").replace("_", " ").title()
        confidence = check.get("confidence")
        confidence_text = f"{confidence}%" if isinstance(confidence, (int, float)) else "N/A"
        reasons_block = "\n".join(f"• {item}" for item in reason)

        sender_name = " ".join(part for part in [sender.first_name, sender.last_name] if part) or "Unknown"
        sender_username = f"@{sender.username}" if sender.username else "none"
        review_text = (
            "🟡 <b>PREMIUM PAYMENT — MANUAL REVIEW</b>\n\n"
            f"👤 User: {escape(sender_name)}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"📦 Plan: {escape(str(order.get('plan_duration', 'N/A')))}\n"
            f"💰 Amount: {escape(str(order.get('plan_price', 'N/A')))}\n\n"
            f"⚠️ <b>Why review?</b> {escape(reasons_block)}\n\n"
            "📸 Screenshot is attached below. Choose an action."
        )
        review_buttons = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ APPROVE PAYMENT", callback_data=f"payapprove:{user_id}:{message.id}"),
                InlineKeyboardButton("❌ REJECT PAYMENT", callback_data=f"payreject:{user_id}:{message.id}"),
            ]
        ])
        for admin_id in _admins():
            try:
                await payment_client.send_message(
                    admin_id,
                    review_text,
                    parse_mode=enums.ParseMode.HTML,
                    reply_markup=review_buttons,
                )
                await payment_client.copy_message(
                    admin_id,
                    message.chat.id,
                    message.id,
                )
            except Exception as exc:
                LOGGER.warning("Could not send manual payment review to %s: %s", admin_id, exc)
        try:
            lang = await _user_language(user_id, sender)
            plan_key = _plan_key(order.get("selected_plan"))
            plan = PREMIUM_PLANS.get(plan_key, {}) if plan_key else {}
            activated_at = order.get("review_started_at") or _now()
            user_text = (
                f"{_tr(lang, 'manual_title')}\n\n"
                f"📦 {_premium_flow_text(lang, 'plan_label')}: {escape(str(plan.get('name') or order.get('plan_duration', 'N/A')))}\n"
                f"⏳ {_premium_flow_text(lang, 'duration_label')}: {escape(str(plan.get('duration') or order.get('plan_duration', 'N/A')))}\n"
                f"📅 Activated: {_fmt_dt(activated_at)}\n"
                f"⏳ Expires: {_fmt_dt(review_expiry)}\n"
                f"🟢 {_premium_flow_text(lang, 'status_label')}: Active\n\n" +
                _tr(lang, "manual_body")
            )
            submission_now = await db.get_payment_submission(user_id, message.id)
            notice_id = (submission_now or {}).get("user_notice_message_id")
            ok, new_notice_id = await _replace_user_notice(
                payment_client, user_id, notice_id, user_text, _contact_admin_markup(lang, message.id)
            )
            if ok and new_notice_id:
                await db.update_payment_submission(
                    user_id, message.id, {"user_notice_message_id": new_notice_id}
                )
        except Exception:
            pass
        return

    await db.update_payment_submission(
        user_id, message.id,
        {"review_status": "auto_approved"}
    )
    claimed = await db.activate_premium_order(user_id, message.id)
    if not claimed:
        await db.update_payment_submission(
            user_id, message.id, {"status": "duplicate_after_activation"}
        )
        return

    try:
        await payment_client.copy_message(
            chat_id=LOG_CHANNEL,
            from_chat_id=message.chat.id,
            message_id=message.id,
        )
    except Exception as exc:
        LOGGER.warning("Could not copy payment screenshot to LOG_CHANNEL: %s", exc)

    # Auto-approved payments are presented to admins in the same review format
    # as manual payments: report first, then the exact original screenshot. The
    # only difference is that approval already happened, so only Reject remains.
    tx_at = check.get("transaction_at")
    sender_name = " ".join(part for part in [sender.first_name, sender.last_name] if part) or "Unknown"
    sender_username = f"@{sender.username}" if sender.username else "none"
    amount_found = check.get("amount_found")
    amount_result = "Matched" if check.get("amount_match") is True else ("Not matched" if check.get("amount_match") is False else "Not confidently detected")
    if PAYMENT_TIME_APPROVAL_ENABLED:
        time_result = "Matched" if check.get("time_match") is True else ("Not matched" if check.get("time_match") is False else "Not confidently detected")
    else:
        time_result = "Not used for approval (setting OFF)"
    success_result = "Detected" if check.get("success_signal") is True else ("Not detected" if check.get("success_signal") is False else "Not available")
    confidence = check.get("confidence")
    confidence_text = f"{confidence}%" if isinstance(confidence, (int, float)) else "N/A"

    detected_report = (
        "🟢 <b>PREMIUM PAYMENT — AUTO VERIFIED</b>\n\n"
        f"👤 User: {escape(sender_name)}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📦 Plan: {escape(str(order.get('plan_duration', 'N/A')))}\n"
        f"💰 Amount: {escape(str(order.get('plan_price', 'N/A')))}\n\n"
        "✅ Payment passed automatic verification.\n"
        "📸 Screenshot is attached below. You can still reject this payment if needed."
    )
    auto_reject_buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ REJECT PAYMENT", callback_data=f"payreject:{user_id}:{message.id}")]
    ])
    for admin_id in _admins():
        try:
            await payment_client.send_message(
                admin_id,
                detected_report,
                parse_mode=enums.ParseMode.HTML,
                reply_markup=auto_reject_buttons,
            )
            await payment_client.copy_message(
                admin_id,
                message.chat.id,
                message.id,
            )
        except Exception as exc:
            LOGGER.warning("Could not send auto-approved payment review to %s: %s", admin_id, exc)

    await _activate_order(payment_client, claimed, message.id)


async def _grant_review_access(user_id, order, minutes=None):
    """Grant the exact selected plan during manual payment review.

    This is never lifetime access. Reject removes only this payment-created
    Premium record so normal PM/group verification can continue unchanged.
    """
    now = _now()
    plan_key = _plan_key(order.get("selected_plan"))
    if not plan_key:
        raise ValueError("Invalid selected Premium plan for payment review")
    expires = _expiry_from(now, plan_key)
    await db.update_user({
        "id": int(user_id),
        "expiry_time": expires,
        "premium_plan": _plan_key(order.get("selected_plan")) or order.get("selected_plan"),
        "premium_plan_name": order.get("plan_duration", "Review"),
        "premium_price": order.get("plan_price"),
    })
    await db.premium_orders.update_one(
        {"user_id": int(user_id)},
        {"$set": {
            "premium_status": "active",
            "temporary_review_access": True,
            "temporary_review_expires_at": None,
            "payment_status": "manual_review_required",
            "expires_at": expires,
            "review_started_at": now,
        }},
    )
    return expires


async def _notify_admins(client, text):
    for admin_id in _admins():
        try:
            await client.send_message(admin_id, text, parse_mode=enums.ParseMode.HTML)
        except Exception as exc:
            LOGGER.warning("Could not notify admin %s: %s", admin_id, exc)


@Client.on_callback_query(filters.regex(r"^buyplan_"), group=1)
async def select_premium_plan(client, query):
    plan_key = _plan_key(query.data.split("_", 1)[1])
    if not plan_key:
        return await query.answer("Invalid Premium plan.", show_alert=True)

    plan = PREMIUM_PLANS[plan_key]
    user = query.from_user
    order = await db.create_or_update_premium_order(
        user.id,
        user.username,
        plan_key,
        plan["duration"],
        plan["price"],
    )

    auto_payment_enabled = await get_auto_payment_enabled()
    buttons = []
    if auto_payment_enabled and PAYMENT_BOT_USERNAME:
        buttons.append([
            InlineKeyboardButton(
                "📸 SEND PAYMENT SCREENSHOT",
                url=f"https://t.me/{PAYMENT_BOT_USERNAME}",
            )
        ])
    elif not auto_payment_enabled and OWNER_USERNAME:
        owner_username = str(OWNER_USERNAME).strip().lstrip("@")
        buttons.append([
            InlineKeyboardButton(
                "📩 SEND PAYMENT SCREENSHOT TO OWNER",
                url=f"https://t.me/{owner_username}",
            )
        ])
    buttons.append([
        InlineKeyboardButton("• ʙᴀᴄᴋ ᴛᴏ ᴘʟᴀɴꜱ •", callback_data="free"),
        InlineKeyboardButton("• ᴄʟᴏꜱᴇ •", callback_data="close_data"),
    ])

    lang = await _user_language(user.id, user)
    payment_text = (
        f"💳 <b>{_premium_flow_text(lang, 'order_created_title')}</b>\n\n"
        f"📦 {_premium_flow_text(lang, 'plan_label')}: <b>{escape(plan['name'])}</b>\n"
        f"⏳ {_premium_flow_text(lang, 'duration_label')}: <b>{escape(plan['duration'])}</b>\n"
        f"💰 {_premium_flow_text(lang, 'price_label')}: <b>{escape(str(plan['price']))}</b>\n"
        f"🆔 {_premium_flow_text(lang, 'user_id_label')}: <code>{user.id}</code>\n"
        f"🟡 {_premium_flow_text(lang, 'payment_status_label')}: <code>waiting_for_payment</code>\n\n"
        f"{('Complete the payment, then send the screenshot to the dedicated payment bot.' if auto_payment_enabled else 'Auto-payment is OFF. Send your payment screenshot directly to the owner for manual verification.')}\n\n"
        f"⚠️ {_premium_flow_text(lang, 'submission_note')}"
    )
    try:
        await query.message.edit_caption(
            caption=payment_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        await query.message.edit_text(
            payment_text,
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode=enums.ParseMode.HTML,
        )
    await query.answer("Premium plan selected.")


@Client.on_message(filters.command("pending"))
async def pending_payments(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")

    rows = []
    async for order in db.get_pending_manual_verifications():
        rows.append(
            f"👤 <code>{order['user_id']}</code> | "
            f"{escape(order.get('username') or 'no username')}\n"
            f"📦 {escape(order.get('plan_duration', 'N/A'))} | "
            f"💰 {escape(order.get('plan_price', 'N/A'))}\n"
            f"💳 Status: <code>{escape(order.get('payment_status', 'N/A'))}</code>\n"
            f"🖼️ Screenshot: <code>{order.get('screenshot_message_id', 'N/A')}</code>\n"
            f"⏳ Expires: {_fmt_dt(order.get('expires_at'))}\n"
        )
    if not rows:
        return await message.reply_text("No Premium payments are waiting for manual verification.")
    text = "🧾 <b>Pending Manual Payment Verification</b>\n\n" + "\n".join(rows)
    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("premium"))
async def premium_details(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    if len(message.command) != 2:
        return await message.reply_text("Usage: /premium USER_ID")

    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("USER_ID must be numeric.")

    order = await db.get_premium_order(user_id)
    user = await db.get_user(user_id)
    if not order and not user:
        return await message.reply_text("User was not found.")

    expiry = _naive_utc(user.get("expiry_time")) if user else None
    active = isinstance(expiry, datetime.datetime) and expiry > _now()
    text = (
        "👤 <b>Premium Details</b>\n\n"
        f"🆔 User ID: <code>{user_id}</code>\n"
        f"👤 Username: @{escape((order or {}).get('username') or 'unknown')}\n"
        f"📦 Plan: {escape((order or {}).get('plan_duration') or user.get('premium_plan_name', 'N/A'))}\n"
        f"💰 Price: {escape((order or {}).get('plan_price') or str(user.get('premium_price', 'N/A')))}\n"
        f"🟢 Premium: {'Active' if active else 'Expired/Inactive'}\n"
        f"📅 Activated: {_fmt_dt((order or {}).get('activated_at'))}\n"
        f"⏳ Expires: {_fmt_dt(expiry)}\n"
        f"💳 Payment: {escape((order or {}).get('payment_status', 'N/A'))}\n"
        f"🔎 Manually verified: {bool((order or {}).get('manually_verified', False))}\n"
        f"🖼️ Screenshot message: {escape(str((order or {}).get('screenshot_message_id', 'N/A')))}"
    )
    await message.reply_text(text, parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("approve"))
async def approve_payment(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    if len(message.command) != 2:
        return await message.reply_text("Usage: /approve USER_ID")
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("USER_ID must be numeric.")

    order = await db.get_premium_order(user_id)
    if not order:
        return await message.reply_text("No Premium payment record found for this user.")

    screenshot_id = order.get("screenshot_message_id")
    if not screenshot_id:
        return await message.reply_text("No payment screenshot is attached to this order.")
    approved = await db.approve_manual_payment(user_id, screenshot_id)
    if not approved.modified_count:
        return await message.reply_text("This payment is not waiting for manual approval.")
    try:
        fresh = await db.get_premium_order(user_id)
        await _activate_order(client, fresh, screenshot_id)
    except Exception as exc:
        LOGGER.exception("Command approval activation failed for %s", user_id)
        await db.premium_orders.update_one({"user_id": user_id, "screenshot_message_id": screenshot_id}, {"$set": {"payment_status": "manual_review_required", "premium_status": "inactive"}})
        return await message.reply_text("Premium activation failed; the review was restored to pending.")
    await message.reply_text(f"✅ Payment approved and Premium activated for <code>{user_id}</code>.", parse_mode=enums.ParseMode.HTML)


@Client.on_message(filters.command("remove"))
async def remove_premium_payment(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    if len(message.command) != 2:
        return await message.reply_text("Usage: /remove USER_ID")
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("USER_ID must be numeric.")

    result = await db.remove_premium_access(user_id)
    if not result:
        return await message.reply_text("Premium user was not found.")
    await db.set_subscription_expired(user_id)
    await message.reply_text(f"❌ Premium access removed for <code>{user_id}</code>.", parse_mode=enums.ParseMode.HTML)
    try:
        lang = await _user_language(user_id)
        await _send_user_temp(
            client, user_id,
            "❌ <b>Premium Plan Removed</b>\n\n" + _tr(lang, "rejected"),
            parse_mode=enums.ParseMode.HTML,
        )
    except Exception:
        pass


@Client.on_message(filters.command("expire"))
async def expire_now(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    await run_expiry_check(client, notify=True)
    await message.reply_text("✅ Premium expiry check completed.")


@Client.on_message(filters.command("renew"))
async def manual_renew(client, message):
    if message.from_user.id not in _admins():
        return await message.reply_text("You are not authorized to use this command.")
    if len(message.command) != 3:
        return await message.reply_text(
            "Usage: /renew USER_ID PLAN\n"
            "PLAN: week, month, 3month, 6month, year, lifetime"
        )
    try:
        user_id = int(message.command[1])
    except ValueError:
        return await message.reply_text("USER_ID must be numeric.")
    plan_key = _plan_key(message.command[2])
    if not plan_key:
        return await message.reply_text("Unknown plan.")

    now = _now()
    user = await db.get_user(user_id)
    current = _naive_utc(user.get("expiry_time")) if user else None
    if not isinstance(current, datetime.datetime) or current <= now:
        base = now
    else:
        base = current
    new_expiry = _expiry_from(base, plan_key)
    plan = PREMIUM_PLANS[plan_key]

    await db.update_user({
        "id": user_id,
        "expiry_time": new_expiry,
        "premium_plan": plan_key,
        "premium_plan_name": plan["duration"],
        "premium_price": plan["price"],
    })
    await db.premium_orders.update_one(
        {"user_id": user_id},
        {"$set": {
            "selected_plan": plan_key,
            "plan_duration": plan["duration"],
            "plan_price": plan["price"],
            "premium_status": "active",
            "payment_status": "manually_renewed",
            "activated_at": now,
            "expires_at": new_expiry,
            "reminder_sent": False,
            "manually_verified": True,
            "manually_verified_at": now,
        }},
        upsert=True,
    )
    await message.reply_text(
        f"♻️ Premium renewed for <code>{user_id}</code>.\n"
        f"📦 Plan: {escape(plan['name'])}\n"
        f"⏳ New expiry: {_fmt_dt(new_expiry)}",
        parse_mode=enums.ParseMode.HTML,
    )


async def _claim_legacy_expiry_notice(user_id, expiry):
    """Deduplicate legacy-expiry notices in Devil's original general-data DB."""
    stamp = _naive_utc(expiry)
    stamp_key = stamp.isoformat() if isinstance(stamp, datetime.datetime) else "unknown"
    marker_id = f"legacy_premium_expired:{int(user_id)}:{stamp_key}"
    if await db.misc.find_one({"_id": marker_id}):
        return False
    marker = {
        "_id": marker_id,
        "user_id": int(user_id),
        "expiry_time": stamp,
        "notice_attempted_at": datetime.datetime.utcnow(),
    }
    result = await db.misc.update_one(
        {"_id": marker_id}, {"$setOnInsert": marker}, upsert=True
    )
    return bool(getattr(result, "acknowledged", False))


async def run_expiry_check(client, notify=True):
    now = _now()

    # New payment/subscription records.
    cursor = db.premium_orders.find({
        "premium_status": "active",
        "expires_at": {"$lte": now},
    })
    async for order in cursor:
        user_id = int(order["user_id"])
        await db.remove_premium_access(user_id)
        await db.set_subscription_expired(user_id, order.get("expires_at") or now)
        if notify:
            try:
                await client.send_message(
                    user_id,
                    "❌ <b>Premium Plan Expired</b>\n\n"
                    f"📦 Plan: {escape(order.get('plan_duration', 'Premium'))}\n"
                    f"📅 Expired: {_fmt_dt(order.get('expires_at') or now)}\n"
                    "🔴 Status: Expired\n\n"
                    "Your Premium access has ended.\n\n"
                    "🔄 Purchase a new Premium plan to continue.",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as exc:
                LOGGER.warning("Could not send expiry notice to %s: %s", user_id, exc)

    # Four-day reminder. On restart, a missed exact moment is recovered by
    # sending once while the subscription is still active and inside the window.
    four_days = datetime.timedelta(days=4)
    cursor = db.premium_orders.find({
        "premium_status": "active",
        "reminder_sent": {"$ne": True},
        "expires_at": {"$gt": now},
    })
    async for order in cursor:
        expires_at = _naive_utc(order.get("expires_at"))
        if not isinstance(expires_at, datetime.datetime):
            continue
        if expires_at - now <= four_days:
            user_id = int(order["user_id"])
            try:
                await client.send_message(
                    user_id,
                    "⚠️ <b>Premium Expiring Soon</b>\n\n"
                    f"📦 Plan: {escape(order.get('plan_duration', 'Premium'))}\n"
                    "⏳ Remaining: 4 Days or less\n"
                    f"📅 Expiry: {_fmt_dt(expires_at)}\n\n"
                    "Renew your Premium plan to continue using the service.",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as exc:
                LOGGER.warning("Could not send 4-day reminder to %s: %s", user_id, exc)
            await db.mark_reminder_sent(user_id)

    # Legacy/manual Premium records not created through the payment flow.
    # This keeps the existing /add_premium feature working exactly as before.
    legacy = await db.get_expired(now)
    for user in legacy:
        user_id = int(user["id"])
        current = await db.get_premium_order(user_id)
        # Don't overwrite a newer active payment subscription.
        if current and current.get("premium_status") == "active":
            continue
        expiry = _naive_utc(user.get("expiry_time"))
        await db.remove_premium_access(user_id)
        if notify:
            # Persist a per-user/per-expiry marker so the 10-second worker
            # cannot spam the user or LOG_CHANNEL on every scan.
            if not await _claim_legacy_expiry_notice(user_id, expiry):
                continue
            try:
                target = await client.get_users(user_id)
                await client.send_message(
                    user_id,
                    f"<b>ʜᴇʏ {target.mention},\n\n"
                    "ʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇss ʜᴀs ᴇxᴘɪʀᴇᴅ, "
                    "ᴛʜᴀɴᴋ ʏᴏᴜ ꜰᴏʀ ᴜsɪɴɢ ᴏᴜʀ sᴇʀᴠɪᴄᴇ 😊\n\n"
                    "ɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴛᴀᴋᴇ ᴛʜᴇ ᴘʀᴇᴍɪᴜᴍ ᴀɢᴀɪɴ, "
                    "ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ /plan ꜰᴏʀ ᴛʜᴇ ᴅᴇᴛᴀɪʟs ᴏꜰ ᴛʜᴇ ᴘʟᴀɴs...</b>",
                    parse_mode=enums.ParseMode.HTML,
                )
                await client.send_message(
                    LOG_CHANNEL,
                    f"<b>#Premium_Expire\n\nUser name: {target.mention}\n"
                    f"User id: <code>{user_id}</code></b>",
                    parse_mode=enums.ParseMode.HTML,
                )
            except Exception as exc:
                LOGGER.warning("Could not send legacy expiry notice for %s: %s", user_id, exc)


async def premium_expiry_worker(client):
    while True:
        try:
            await run_expiry_check(client, notify=True)
        except Exception:
            LOGGER.exception("Premium expiry checker failed; retrying.")
        await asyncio.sleep(10)


def register_payment_bot_handlers(payment_client):
    @payment_client.on_callback_query(filters.regex(r"^pay(close|approve|reject):"))
    async def manual_payment_review_callback(client, query):
        parts = query.data.split(":")
        try:
            action = parts[0]
            if action == "payclose":
                user_id = int(query.from_user.id)
                screenshot_message_id = int(parts[1])
            else:
                if not query.from_user or query.from_user.id not in _admins():
                    return await query.answer("You are not authorized.", show_alert=True)
                user_id = int(parts[1])
                screenshot_message_id = int(parts[2]) if len(parts) > 2 else None
        except (ValueError, IndexError):
            return await query.answer("Invalid payment request.", show_alert=True)

        if action == "payclose":
            try:
                await query.message.delete()
            except Exception:
                pass
            submission = await db.get_payment_submission(user_id, screenshot_message_id)
            if submission:
                await db.update_payment_submission(
                    user_id, screenshot_message_id, {"user_notice_message_id": None}
                )
            return await query.answer("Closed.")

        submission = await db.get_payment_submission(user_id, screenshot_message_id)
        if not submission:
            return await query.answer("This payment screenshot was not found.", show_alert=True)

        if action == "payapprove":
            # Lock this exact screenshot while activation is running. Do NOT mark
            # it approved until Premium access and the user notification succeed.
            result = await db.claim_payment_review(user_id, screenshot_message_id, "processing")
            if not result.modified_count:
                current = await db.get_payment_submission(user_id, screenshot_message_id)
                status = ((current or {}).get("review_status") or "processed").replace("_", " ")
                return await query.answer(f"This screenshot is already {status}.", show_alert=True)

            order = await db.get_premium_order(user_id)
            if not order or int(order.get("screenshot_message_id") or -1) != screenshot_message_id:
                await db.update_payment_submission(
                    user_id, screenshot_message_id, {"review_status": "manual_review_required"}
                )
                return await query.answer("The matching payment order changed. Review was kept pending.", show_alert=True)

            # The exact screenshot must still belong to a pending manual-review
            # order. Activate Premium first; only then finalize the review as approved.
            approved = await db.approve_manual_payment(user_id, screenshot_message_id)
            if not approved.modified_count:
                await db.update_payment_submission(
                    user_id, screenshot_message_id, {"review_status": "manual_review_required"}
                )
                return await query.answer("The order could not be approved. Review is still pending.", show_alert=True)

            try:
                order = await db.get_premium_order(user_id)
                if not order:
                    raise RuntimeError("Premium order disappeared during approval")

                # The selected plan was already activated for this exact manual review.
                # Approval confirms the payment only; it must not restart or extend expiry.
                if not (
                    order.get("temporary_review_access") is True
                    and str(order.get("premium_status") or "").lower() == "active"
                ):
                    await _activate_order(client, order, screenshot_message_id)
                else:
                    await db.premium_orders.update_one(
                        {"user_id": user_id, "screenshot_message_id": screenshot_message_id},
                        {"$set": {
                            "payment_status": "manually_verified",
                            "temporary_review_access": False,
                            "temporary_review_expires_at": None,
                        }},
                    )
                    try:
                        lang = await _user_language(user_id)
                        plan = PREMIUM_PLANS.get(_plan_key(order.get("selected_plan")), {})
                        approved_text = (
                            f"✅ <b>{_premium_flow_text(lang, 'approved_title')}</b>\n\n"
                            f"📦 {_premium_flow_text(lang, 'plan_label')}: <b>{escape(str(plan.get('name') or order.get('plan_duration', 'Premium')))}</b>\n"
                            f"⏳ {_premium_flow_text(lang, 'duration_label')}: <b>{escape(str(plan.get('duration') or order.get('plan_duration', 'N/A')))}</b>\n"
                            f"📅 {_premium_flow_text(lang, 'expires_label')}: <b>{_fmt_dt(order.get('expires_at'))}</b>\n"
                            "🟢 Status: Active\n\n"
                            + _tr(lang, "approved")
                        )
                        submission_now = await db.get_payment_submission(user_id, screenshot_message_id)
                        old_notice_id = (submission_now or {}).get("user_notice_message_id")
                        ok, new_notice_id = await _replace_user_notice(
                            client, user_id, old_notice_id, approved_text
                        )
                        if ok and new_notice_id:
                            await db.update_payment_submission(
                                user_id, screenshot_message_id, {"user_notice_message_id": new_notice_id}
                            )
                    except Exception:
                        pass
            except Exception as exc:
                LOGGER.exception("Manual Premium activation failed for %s", user_id)
                # Never leave a review falsely approved when activation failed.
                await db.premium_orders.update_one(
                    {"user_id": user_id, "screenshot_message_id": screenshot_message_id},
                    {"$set": {
                        "payment_status": "manual_review_required",
                        "premium_status": "inactive",
                    }},
                )
                await db.update_payment_submission(
                    user_id, screenshot_message_id,
                    {"review_status": "manual_review_required", "approval_error": str(exc)[:500]},
                )
                return await query.answer("Premium activation failed. Review was restored to pending.", show_alert=True)

            await db.update_payment_submission(
                user_id, screenshot_message_id,
                {"review_status": "approved", "approval_error": None},
            )
            text = (
                f"✅ <b>Payment approved</b>\n\n"
                f"User ID: <code>{user_id}</code>\n"
                "Premium has been activated successfully."
            )
        else:
            # Auto-approved screenshots can also be rejected later, so claim
            # both manual-review and auto-approved review states atomically.
            result = await db.payment_submissions.update_one(
                {
                    "user_id": user_id,
                    "payment_bot_message_id": screenshot_message_id,
                    "review_status": {"$in": ["pending", "manual_review_required", "auto_approved"]},
                },
                {"$set": {"review_status": "rejected", "reviewed_at": _now()}},
            )
            if not result.modified_count:
                current = await db.get_payment_submission(user_id, screenshot_message_id)
                status = ((current or submission).get("review_status") or "processed").replace("_", " ")
                return await query.answer(f"This screenshot was already {status}.", show_alert=True)

            # Reject only this exact payment/order and remove only the Premium
            # access created by this payment. No PM/group verification state,
            # user identity or normal bot access data is touched.
            order = await db.get_premium_order(user_id)
            if order and int(order.get("screenshot_message_id") or -1) == screenshot_message_id:
                await db.premium_orders.update_one(
                    {"user_id": user_id, "screenshot_message_id": screenshot_message_id},
                    {"$set": {
                        "payment_status": "manually_rejected",
                        "premium_status": "inactive",
                        "rejected_at": _now(),
                    }},
                )
                await db.remove_premium_access(user_id)
            try:
                lang = await _user_language(user_id)
                rejected_text = (
                    f"❌ <b>{_premium_flow_text(lang, 'rejected_title')}</b>\n\n"
                    + _tr(lang, "rejected")
                )
                submission_now = await db.get_payment_submission(user_id, screenshot_message_id)
                notice_id = (submission_now or {}).get("user_notice_message_id")
                ok, new_notice_id = await _replace_user_notice(
                    client, user_id, notice_id, rejected_text, _contact_admin_markup(lang, screenshot_message_id)
                )
                if ok and new_notice_id:
                    await db.update_payment_submission(
                        user_id, screenshot_message_id, {"user_notice_message_id": new_notice_id}
                    )
            except Exception:
                pass
            text = (
                f"❌ <b>Payment rejected</b>\n\n"
                f"User ID: <code>{user_id}</code>"
            )

        await query.answer("Payment review completed.")
        try:
            await query.message.edit_text(
                text,
                parse_mode=enums.ParseMode.HTML,
            )
        except Exception:
            pass

    @payment_client.on_message(
        filters.private & (filters.photo | filters.document)
    )
    async def payment_screenshot_handler(client, message):
        if message.document and not (
            (message.document.mime_type or "").lower().startswith("image/")
        ):
            return
        try:
            await process_payment_submission(client, message)
        except Exception as exc:
            LOGGER.exception("Payment screenshot processing failed.")
            # If the order lookup/database/OCR path raises before it can send a
            # status, do not leave regular users with a silent screenshot.
            try:
                if message.from_user:
                    error_notice = await client.send_message(
                        message.from_user.id,
                        "⚠️ <b>We couldn't process this screenshot right now.</b>\n\n"
                        "Your screenshot was received, but a temporary processing or database error occurred. "
                        "Please try again shortly or contact the owner if it keeps happening.",
                        parse_mode=enums.ParseMode.HTML,
                    )
                    _schedule_temp_delete(error_notice, 30)
            except Exception as notify_exc:
                LOGGER.warning("Could not send screenshot error notice (%s)", type(notify_exc).__name__)
        finally:
            # Keep the original screenshot in the payment bot chat for only
            # the requested 10-second retention window.
            _schedule_temp_delete(message, TEMP_MESSAGE_DELETE_SECONDS)
