"""Shared user-language helpers.

This module lives at project root intentionally: bot.py auto-loads every
plugins/*.py as a handler module, so shared language code must not be placed
inside plugins/.
"""
import re
import logging

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from database.users_chats_db import db

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Exactly the languages already offered by the Premium language system.
# Labels remain in English so users can identify them before selecting one.
DEFAULT_LANGUAGE = "en"

LANGUAGES = {
    "en": "🇬🇧 English",
    "hi": "🇮🇳 Hindi",
    "ta": "🇮🇳 Tamil",
    "te": "🇮🇳 Telugu",
    "kn": "🇮🇳 Kannada",
    "ml": "🇮🇳 Malayalam",
    "bn": "🇮🇳 Bengali",
    "mr": "🇮🇳 Marathi",
    "gu": "🇮🇳 Gujarati",
    "pa": "🇮🇳 Punjabi",
    "ur": "🇮🇳 Urdu",
    "as": "🇮🇳 Assamese",
    "ne": "🇳🇵 Nepali",
    "hinglish": "🇮🇳 Hinglish",
}

ALIASES = {
    "en": "en", "en-us": "en", "en-gb": "en",
    "hi": "hi", "hi-in": "hi", "hi-latn": "hinglish",
    "ta": "ta", "te": "te", "kn": "kn", "ml": "ml",
    "bn": "bn", "mr": "mr", "gu": "gu", "pa": "pa",
    "ur": "ur", "as": "as", "ne": "ne", "hinglish": "hinglish",
}


def language_markup(callback_prefix="global_lang:"):
    codes = list(LANGUAGES)
    rows = []
    for i in range(0, len(codes), 2):
        row = [InlineKeyboardButton(LANGUAGES[codes[i]], callback_data=f"{callback_prefix}{codes[i]}")]
        if i + 1 < len(codes):
            row.append(InlineKeyboardButton(LANGUAGES[codes[i + 1]], callback_data=f"{callback_prefix}{codes[i + 1]}"))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


async def get_user_language(user_id, telegram_user=None):
    try:
        data = await db.get_user(int(user_id))
        saved = (data or {}).get("language") or (data or {}).get("language_code")
        if saved in LANGUAGES:
            return saved
    except Exception:
        logger.exception("LANGUAGE_LOOKUP_FAILED user=%s; falling back to Telegram language/default", user_id)
    code = str(getattr(telegram_user, "language_code", "") or "").lower().replace("_", "-")
    return ALIASES.get(code) or ALIASES.get(code.split("-", 1)[0]) or "en"


async def has_saved_language(user_id):
    try:
        data = await db.get_user(int(user_id))
        saved = (data or {}).get("language") or (data or {}).get("language_code")
        return saved in LANGUAGES
    except Exception:
        logger.exception("LANGUAGE_SAVED_CHECK_FAILED user=%s; treating language as not saved", user_id)
        return False


# Core global UI translations. Labels are intentionally kept short so the
# existing button layout remains unchanged.
UI = {
    "en": {
        "language_title": "🌐 <b>Choose Your Language</b>",
        "language_body": "Select the language you want the bot to use. You can change it anytime.",
        "language_saved": "🌐 Language updated successfully.",
        "language_button": "🌐 Language",
        "back": "⋞ Back",
        "home": "⋞ Back to Home",
        "language": "Language",
        "quality": "Quality",
        "season": "Season",
        "send_all": "Send All Files",
        "no_more": "↭ No More Pages Available ↭",
        "choose_language": "<b>Choose a language from below ↓↓</b>",
        "select_first": "🌐 <b>Please choose your language first.</b>", "season_choose":"Choose the season you want ↓↓", "quality_choose":"Choose the quality you want ↓↓", "language_choose":"Choose the content language you want ↓↓",
    },
    "hi": {
        "language_title": "🌐 <b>अपनी भाषा चुनें</b>", "language_body": "Bot किस भाषा में इस्तेमाल करना है, वह चुनें। आप इसे कभी भी बदल सकते हैं।", "language_saved": "🌐 भाषा सफलतापूर्वक बदल दी गई।", "language_button": "🌐 भाषा", "back": "⋞ वापस", "home": "⋞ होम पर वापस", "language": "भाषा", "quality": "क्वालिटी", "season": "सीज़न", "send_all": "सभी फाइल भेजें", "no_more": "↭ और पेज उपलब्ध नहीं ↭", "choose_language": "<b>नीचे से अपनी भाषा चुनें ↓↓</b>", "select_first": "🌐 <b>पहले अपनी भाषा चुनें।</b>"},
    "ta": {
        "language_title": "🌐 <b>உங்கள் மொழியைத் தேர்வு செய்யவும்</b>", "language_body": "Bot பயன்படுத்த வேண்டிய மொழியைத் தேர்வு செய்யவும். எப்போது வேண்டுமானாலும் மாற்றலாம்.", "language_saved": "🌐 மொழி வெற்றிகரமாக மாற்றப்பட்டது.", "language_button": "🌐 மொழி", "back": "⋞ பின்செல்", "home": "⋞ முகப்புக்கு", "language": "மொழி", "quality": "தரம்", "season": "சீசன்", "send_all": "அனைத்து கோப்புகளையும் அனுப்பு", "no_more": "↭ மேலும் பக்கங்கள் இல்லை ↭", "choose_language": "<b>கீழே இருந்து மொழியைத் தேர்வு செய்யவும் ↓↓</b>", "select_first": "🌐 <b>முதலில் உங்கள் மொழியைத் தேர்வு செய்யவும்.</b>"},
    "te": {
        "language_title": "🌐 <b>మీ భాషను ఎంచుకోండి</b>", "language_body": "Bot ఏ భాషలో ఉండాలో ఎంచుకోండి. ఎప్పుడైనా మార్చవచ్చు.", "language_saved": "🌐 భాష విజయవంతంగా మార్చబడింది.", "language_button": "🌐 భాష", "back": "⋞ వెనక్కి", "home": "⋞ హోమ్‌కు", "language": "భాష", "quality": "క్వాలిటీ", "season": "సీజన్", "send_all": "అన్ని ఫైళ్లను పంపు", "no_more": "↭ మరిన్ని పేజీలు లేవు ↭", "choose_language": "<b>కింద నుంచి భాషను ఎంచుకోండి ↓↓</b>", "select_first": "🌐 <b>ముందుగా మీ భాషను ఎంచుకోండి.</b>"},
    "kn": {
        "language_title": "🌐 <b>ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ</b>", "language_body": "Bot ಯಾವ ಭಾಷೆಯಲ್ಲಿ ಇರಬೇಕು ಎಂದು ಆಯ್ಕೆಮಾಡಿ. ಯಾವಾಗ ಬೇಕಾದರೂ ಬದಲಾಯಿಸಬಹುದು.", "language_saved": "🌐 ಭಾಷೆ ಯಶಸ್ವಿಯಾಗಿ ಬದಲಾಯಿಸಲಾಗಿದೆ.", "language_button": "🌐 ಭಾಷೆ", "back": "⋞ ಹಿಂದೆ", "home": "⋞ ಹೋಮ್‌ಗೆ", "language": "ಭಾಷೆ", "quality": "ಗುಣಮಟ್ಟ", "season": "ಸೀಸನ್", "send_all": "ಎಲ್ಲಾ ಫೈಲ್‌ಗಳನ್ನು ಕಳುಹಿಸಿ", "no_more": "↭ ಇನ್ನಷ್ಟು ಪುಟಗಳಿಲ್ಲ ↭", "choose_language": "<b>ಕೆಳಗಿನಿಂದ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ ↓↓</b>", "select_first": "🌐 <b>ಮೊದಲು ನಿಮ್ಮ ಭಾಷೆಯನ್ನು ಆಯ್ಕೆಮಾಡಿ.</b>"},
    "ml": {
        "language_title": "🌐 <b>നിങ്ങളുടെ ഭാഷ തിരഞ്ഞെടുക്കുക</b>", "language_body": "Bot ഉപയോഗിക്കേണ്ട ഭാഷ തിരഞ്ഞെടുക്കുക. എപ്പോൾ വേണമെങ്കിലും മാറ്റാം.", "language_saved": "🌐 ഭാഷ വിജയകരമായി മാറ്റി.", "language_button": "🌐 ഭാഷ", "back": "⋞ തിരികെ", "home": "⋞ ഹോമിലേക്ക്", "language": "ഭാഷ", "quality": "ക്വാളിറ്റി", "season": "സീസൺ", "send_all": "എല്ലാ ഫയലുകളും അയയ്ക്കുക", "no_more": "↭ കൂടുതൽ പേജുകളില്ല ↭", "choose_language": "<b>താഴെ നിന്ന് ഭാഷ തിരഞ്ഞെടുക്കുക ↓↓</b>", "select_first": "🌐 <b>ആദ്യം നിങ്ങളുടെ ഭാഷ തിരഞ്ഞെടുക്കുക.</b>"},
    "bn": {
        "language_title": "🌐 <b>আপনার ভাষা বেছে নিন</b>", "language_body": "Bot কোন ভাষায় ব্যবহার করবেন তা বেছে নিন। পরে যেকোনো সময় বদলাতে পারবেন।", "language_saved": "🌐 ভাষা সফলভাবে পরিবর্তন হয়েছে।", "language_button": "🌐 ভাষা", "back": "⋞ ফিরে যান", "home": "⋞ হোমে ফিরে যান", "language": "ভাষা", "quality": "কোয়ালিটি", "season": "সিজন", "send_all": "সব ফাইল পাঠান", "no_more": "↭ আর কোনো পেজ নেই ↭", "choose_language": "<b>নিচ থেকে ভাষা বেছে নিন ↓↓</b>", "select_first": "🌐 <b>আগে আপনার ভাষা বেছে নিন।</b>"},
    "mr": {
        "language_title": "🌐 <b>तुमची भाषा निवडा</b>", "language_body": "Bot कोणत्या भाषेत वापरायचा ते निवडा. कधीही बदलू शकता.", "language_saved": "🌐 भाषा यशस्वीपणे बदलली.", "language_button": "🌐 भाषा", "back": "⋞ मागे", "home": "⋞ होमवर", "language": "भाषा", "quality": "क्वालिटी", "season": "सीझन", "send_all": "सर्व फाइल्स पाठवा", "no_more": "↭ आणखी पेज उपलब्ध नाहीत ↭", "choose_language": "<b>खालीलमधून भाषा निवडा ↓↓</b>", "select_first": "🌐 <b>आधी तुमची भाषा निवडा.</b>"},
    "gu": {
        "language_title": "🌐 <b>તમારી ભાષા પસંદ કરો</b>", "language_body": "Bot કઈ ભાષામાં વાપરવો તે પસંદ કરો. તમે ક્યારે પણ બદલી શકો છો.", "language_saved": "🌐 ભાષા સફળતાપૂર્વક બદલાઈ ગઈ.", "language_button": "🌐 ભાષા", "back": "⋞ પાછા", "home": "⋞ હોમ પર", "language": "ભાષા", "quality": "ક્વોલિટી", "season": "સીઝન", "send_all": "બધી ફાઇલો મોકલો", "no_more": "↭ વધુ પેજ ઉપલબ્ધ નથી ↭", "choose_language": "<b>નીચેથી ભાષા પસંદ કરો ↓↓</b>", "select_first": "🌐 <b>પહેલા તમારી ભાષા પસંદ કરો.</b>"},
    "pa": {
        "language_title": "🌐 <b>ਆਪਣੀ ਭਾਸ਼ਾ ਚੁਣੋ</b>", "language_body": "Bot ਲਈ ਆਪਣੀ ਭਾਸ਼ਾ ਚੁਣੋ। ਤੁਸੀਂ ਇਸਨੂੰ ਕਦੇ ਵੀ ਬਦਲ ਸਕਦੇ ਹੋ।", "language_saved": "🌐 ਭਾਸ਼ਾ ਸਫਲਤਾਪੂਰਵਕ ਬਦਲ ਦਿੱਤੀ ਗਈ।", "language_button": "🌐 ਭਾਸ਼ਾ", "back": "⋞ ਵਾਪਸ", "home": "⋞ ਹੋਮ ਤੇ", "language": "ਭਾਸ਼ਾ", "quality": "ਕੁਆਲਿਟੀ", "season": "ਸੀਜ਼ਨ", "send_all": "ਸਾਰੀਆਂ ਫਾਈਲਾਂ ਭੇਜੋ", "no_more": "↭ ਹੋਰ ਪੇਜ ਨਹੀਂ ਹਨ ↭", "choose_language": "<b>ਹੇਠਾਂ ਤੋਂ ਭਾਸ਼ਾ ਚੁਣੋ ↓↓</b>", "select_first": "🌐 <b>ਪਹਿਲਾਂ ਆਪਣੀ ਭਾਸ਼ਾ ਚੁਣੋ।</b>"},
    "ur": {
        "language_title": "🌐 <b>اپنی زبان منتخب کریں</b>", "language_body": "Bot کے لیے اپنی پسند کی زبان منتخب کریں۔ آپ اسے کبھی بھی تبدیل کر سکتے ہیں۔", "language_saved": "🌐 زبان کامیابی سے تبدیل ہو گئی۔", "language_button": "🌐 زبان", "back": "⋞ واپس", "home": "⋞ ہوم پر", "language": "زبان", "quality": "کوالٹی", "season": "سیزن", "send_all": "تمام فائلیں بھیجیں", "no_more": "↭ مزید صفحات دستیاب نہیں ↭", "choose_language": "<b>نیچے سے زبان منتخب کریں ↓↓</b>", "select_first": "🌐 <b>پہلے اپنی زبان منتخب کریں۔</b>"},
    "as": {
        "language_title": "🌐 <b>আপোনাৰ ভাষা বাছক</b>", "language_body": "Bot কোন ভাষাত ব্যৱহাৰ কৰিব বিচাৰে বাছক। পিছত যিকোনো সময়ত সলনি কৰিব পাৰে।", "language_saved": "🌐 ভাষা সফলভাৱে সলনি কৰা হৈছে।", "language_button": "🌐 ভাষা", "back": "⋞ পিছলৈ", "home": "⋞ হোমলৈ", "language": "ভাষা", "quality": "কোৱালিটি", "season": "ছিজন", "send_all": "সকলো ফাইল পঠাওক", "no_more": "↭ আৰু পৃষ্ঠা নাই ↭", "choose_language": "<b>তলৰ পৰা ভাষা বাছক ↓↓</b>", "select_first": "🌐 <b>আগতে আপোনাৰ ভাষা বাছক।</b>"},
    "ne": {
        "language_title": "🌐 <b>आफ्नो भाषा छान्नुहोस्</b>", "language_body": "Bot कुन भाषामा प्रयोग गर्ने हो छान्नुहोस्। पछि जुनसुकै बेला बदल्न सक्नुहुन्छ।", "language_saved": "🌐 भाषा सफलतापूर्वक बदलियो।", "language_button": "🌐 भाषा", "back": "⋞ पछाडि", "home": "⋞ होममा", "language": "भाषा", "quality": "क्वालिटी", "season": "सिजन", "send_all": "सबै फाइल पठाउनुहोस्", "no_more": "↭ थप पेज उपलब्ध छैन ↭", "choose_language": "<b>तलबाट भाषा छान्नुहोस् ↓↓</b>", "select_first": "🌐 <b>पहिले आफ्नो भाषा छान्नुहोस्।</b>"},
    "hinglish": {
        "language_title": "🌐 <b>Apni Language Choose Karo</b>", "language_body": "Bot ko kis language mein use karna hai choose karo. Baad mein kabhi bhi change kar sakte ho.", "language_saved": "🌐 Language successfully update ho gayi.", "language_button": "🌐 Language", "back": "⋞ Back", "home": "⋞ Home Par", "language": "Language", "quality": "Quality", "season": "Season", "send_all": "Saari Files Send Karo", "no_more": "↭ Aur Pages Available Nahi Hain ↭", "choose_language": "<b>Neeche se language choose karo ↓↓</b>", "select_first": "🌐 <b>Pehle apni language choose karo.</b>"},
}


_SMALL_CAPS = str.maketrans({
    "a":"ᴀ","b":"ʙ","c":"ᴄ","d":"ᴅ","e":"ᴇ","f":"ғ","g":"ɢ",
    "h":"ʜ","i":"ɪ","j":"ᴊ","k":"ᴋ","l":"ʟ","m":"ᴍ","n":"ɴ",
    "o":"ᴏ","p":"ᴘ","q":"ǫ","r":"ʀ","s":"ꜱ","t":"ᴛ","u":"ᴜ",
    "v":"ᴠ","w":"ᴡ","x":"x","y":"ʏ","z":"ᴢ",
})

def small_caps(text):
    """Apply Unicode small-caps to ordinary visible text only.

    This function is intentionally for plain text/buttons. Telegram HTML
    messages must use :func:`small_caps_html` so markup and dynamic values are
    preserved.
    """
    if text is None:
        return text
    return str(text).lower().translate(_SMALL_CAPS)


_HTML_TOKEN_RE = re.compile(r"(<[^>]*>|&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);|\{[^{}]+\}|https?://[^\s<>]+|/[_A-Za-z][_A-Za-z0-9-]*)")


def small_caps_html(text):
    """Safely style visible Latin text in a Telegram HTML message.

    HTML tags, entities, and Python ``{placeholders}`` are left byte-for-byte
    unchanged. This is important because the same translation helper is used
    by /start, search/filter alerts, and verification messages.
    """
    if text is None:
        return text
    value = str(text)
    parts = _HTML_TOKEN_RE.split(value)
    for i, part in enumerate(parts):
        if not part or _HTML_TOKEN_RE.fullmatch(part):
            continue
        parts[i] = part.lower().translate(_SMALL_CAPS)
    return "".join(parts)


def tr(lang, key):
    return small_caps(UI.get(lang, UI["en"]).get(key, UI["en"].get(key, key)))


# User-facing core text used throughout the normal bot flow.  English is the
# safe default for old accounts and for helper/system contexts that have no
# saved language yet.
CORE = {
    "en": {
        "start": "ʜᴇʏ {mention}, {status}\n\nɪ ᴀᴍ ᴀ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ. ᴜsᴇ ᴍᴇ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ ᴘᴍ ᴛᴏ ғɪɴᴅ ᴍᴏᴠɪᴇs ᴀɴᴅ sᴇʀɪᴇs. 😍\n<blockquote>🌿 ᴍᴀɪɴᴛᴀɪɴᴇᴅ ʙʏ : <a href=\"https://t.me/+DiOcxJnNQXdmNDdl\">sandy Bots &lt;/&gt;</a></blockquote>",
        "help": "<b>ᴄʟɪᴄᴋ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ᴠɪᴇᴡ ᴛʜᴇ ʙᴏᴛ ᴅᴏᴄᴜᴍᴇɴᴛᴀᴛɪᴏɴ.</b>",
        "about": "‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]",
        "alert": "ᴡʜᴀᴛ ᴀʀᴇ ʏᴏᴜ sᴇᴀʀᴄʜɪɴɢ!?",
        "old_alert": "ʏᴏᴜ ᴀʀᴇ ᴜsɪɴɢ ᴀɴ ᴏʟᴅ ᴍᴇssᴀɢᴇ. sᴇɴᴅ ᴀ ɴᴇᴡ ʀᴇǫᴜᴇsᴛ.",
        "no_result": "<b>ᴛʜɪs ᴍᴏᴠɪᴇ ᴏʀ sᴇʀɪᴇs ᴡᴀs ɴᴏᴛ ғᴏᴜɴᴅ ɪɴ ᴛʜᴇ ᴅᴀᴛᴀʙᴀsᴇ. 🙄</b>",
        "quality_choose": "<b>ᴄʜᴏᴏsᴇ ᴛʜᴇ ǫᴜᴀʟɪᴛʏ ʏᴏᴜ ᴡᴀɴᴛ ↓↓</b>",
        "season_choose": "<b>ᴄʜᴏᴏsᴇ ᴛʜᴇ sᴇᴀsᴏɴ ʏᴏᴜ ᴡᴀɴᴛ ↓↓</b>",
        "language_choose": "<b>ᴄʜᴏᴏsᴇ ᴛʜᴇ ᴄᴏɴᴛᴇɴᴛ ʟᴀɴɢᴜᴀɢᴇ ʏᴏᴜ ᴡᴀɴᴛ ↓↓</b>",
        "not_found": "sᴏʀʀʏ, {kind} {value} ɴᴏᴛ ғᴏᴜɴᴅ ғᴏʀ {search}.",
        "back_main": "⋞ ʙᴀᴄᴋ ᴛᴏ ᴍᴀɪɴ ᴘᴀɢᴇ",
        "back": "⋞ ʙᴀᴄᴋ",
        "next": "ɴᴇxᴛ ⋟",
        "send_all": "sᴇɴᴅ ᴀʟʟ ғɪʟᴇs",
        "language": "ʟᴀɴɢᴜᴀɢᴇ",
        "quality": "ǫᴜᴀʟɪᴛʏ",
        "season": "sᴇᴀsᴏɴ",
        "no_more": "↭ ɴᴏ ᴍᴏʀᴇ ᴘᴀɢᴇs ᴀᴠᴀɪʟᴀʙʟᴇ ↭",
    },

    "hi": {"start":"ʜᴇʏ {mention}, {status}\n\nʏᴇ ᴇᴋ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ ʜᴀɪ. ɢʀᴏᴜᴘ ᴀᴜʀ ᴘᴍ ᴍᴇɪɴ ᴍᴏᴠɪᴇs ᴀᴜʀ sᴇʀɪᴇs ᴋᴇ ʟɪʏᴇ ᴍᴜᴊʜᴇ ᴜsᴇ ᴋᴀʀᴇɴ. 😍"},
    "ta": {"start":"ʜᴇʏ {mention}, {status}\n\nɪᴛᴜ ᴏʀᴜ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ. ɢʀᴏᴜᴘ ᴍᴀᴛᴛʀᴜᴍ ᴘᴍ-ɪʟ ᴍᴏᴠɪᴇs ᴍᴀᴛᴛʀᴜᴍ sᴇʀɪᴇs ᴛᴇᴛᴀ ᴇɴɴᴀɪ ᴜsᴇ ᴘᴀɴɴᴀʟᴀᴍ. 😍"},
    "te": {"start":"ʜᴇʏ {mention}, {status}\n\nɪᴅɪ ᴏᴋᴀ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ. ɢʀᴏᴜᴘ ᴀʟᴀɢᴇ ᴘᴍʟᴏ ᴍᴏᴠɪᴇs ᴍᴀʀɪʏᴜ sᴇʀɪᴇs ᴋᴏsᴀᴍ ᴜsᴇ ᴄʜᴇʏᴀɴᴅɪ. 😍"},
    "kn": {"start":"ʜᴇʏ {mention}, {status}\n\nɪᴅᴜ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ. ɢʀᴏᴜᴘ ʜᴀɢᴜ ᴘᴍ-ɴᴀʟʟɪ ᴍᴏᴠɪᴇ ʜᴀɢᴜ sᴇʀɪᴇs ᴘᴀᴅᴇʏᴀʟᴜ ᴜsᴇ ᴍᴀᴅɪ. 😍"},
    "ml": {"start":"ʜᴇʏ {mention}, {status}\n\nɪᴛʜᴜ ᴏʀᴜ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ ᴀᴀɴᴜ. ɢʀᴏᴜᴘɪʟᴜᴍ ᴘᴍ-ɪʟᴜᴍ ᴍᴏᴠɪᴇsᴜᴍ sᴇʀɪᴇsᴜᴍ ᴛʜᴇᴛᴀᴀɴ ᴜsᴇ ᴄʜᴇʏʏᴀᴀᴍ. 😍"},
    "bn": {"start":"ʜᴇʏ {mention}, {status}\n\nএটি একটি শক্তিশালী অটোফিল্টার বট। গ্রুপ ও PM-এ মুভি এবং সিরিজ খুঁজতে আমাকে ব্যবহার করুন। 😍"},
    "mr": {"start":"ʜᴇʏ {mention}, {status}\n\nʜᴀ ᴇᴋ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ ᴀʜᴇ. ɢʀᴜᴘ ᴀɴɪ ᴘᴍ ᴍᴀᴅʜʏᴇ ᴍᴏᴠɪᴇs ᴀᴀɴɪ sᴇʀɪᴇs sʜᴏᴅɴʏᴀsᴀᴛʜɪ ᴠᴀᴘʀᴀ. 😍"},
    "gu": {"start":"ʜᴇʏ {mention}, {status}\n\nᴀᴀ ᴇᴋ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ ᴄʜᴇ. ɢʀᴏᴜᴘ ᴀɴᴇ ᴘᴍ ᴍᴀɴ ᴍᴏᴠɪᴇ ᴀɴᴇ sᴇʀɪᴇs sʜᴏᴅᴠᴀ ᴍᴀᴛᴇ ᴍᴀɴᴇ ᴠᴀᴘʀᴏ. 😍"},
    "pa": {"start":"ʜᴇʏ {mention}, {status}\n\nᴇʜ ᴇᴋ ᴘᴏᴡᴇʀғᴜʟ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ ʜᴀɪ. ɢʀᴏᴜᴘ ᴀᴛᴇ ᴘᴍ ᴠɪᴄʜ ᴍᴏᴠɪᴇᴀɴ ᴛᴇ sᴇʀɪᴇs ʟᴀʙʜᴀɴ ʟᴀɪ ᴠᴀʀᴛᴏ. 😍"},
    "ur": {"start":"ʜᴇʏ {mention}, {status}\n\nʏᴇ ᴇᴋ ᴛᴀǫᴀᴛᴡᴀʀ ᴀᴜᴛᴏғɪʟᴛᴇʀ ʙᴏᴛ ʜᴀɪ. ɢʀᴏᴜᴘ ᴀᴜʀ ᴘᴍ ᴍᴇɪɴ ᴍᴏᴠɪᴇs ᴀᴜʀ sᴇʀɪᴇs ᴛᴀʟᴀsʜ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ ᴜsᴇ ᴋᴀʀᴇɪɴ. 😍"},
    "as": {"start":"ʜᴇʏ {mention}, {status}\n\nই এটা শক্তিশালী অটোফিল্টাৰ বট। গ্ৰুপ আৰু PM-ত মুভি আৰু ছিৰিজ বিচাৰিবলৈ মোক ব্যৱহাৰ কৰক। 😍"},
    "ne": {"start":"ʜᴇʏ {mention}, {status}\n\nयो एउटा शक्तिशाली अटोफिल्टर बोट हो। ग्रुप र PM मा चलचित्र तथा सिरिज खोज्न मलाई प्रयोग गर्नुहोस्। 😍"},
    "hinglish": {"start":"ʜᴇʏ {mention}, {status}\n\nYeh ek powerful AutoFilter bot hai. Group aur PM mein movies aur series find karne ke liye mujhe use karo. 😍"},
}
# For the remaining languages, keep the complete UI controls localized via UI;
# core long-form text falls back to English until an exact translation exists.
for _code, _ui in UI.items():
    CORE.setdefault(_code, {})
    for _key in ("back","send_all","language","quality","season","no_more"):
        CORE[_code][_key] = _ui.get(_key, CORE["en"][_key])

# Direct alert shown by Season/Quality/Content-Language filters.  The searched
# title/value is inserted unchanged; only the surrounding bot text is localized.
_NOT_FOUND = {
 "en":"sᴏʀʀʏ, {kind} {value} ɴᴏᴛ ғᴏᴜɴᴅ ғᴏʀ {search}.",
 "hi":"माफ़ कीजिए, {search} के लिए {kind} {value} नहीं मिला।",
 "ta":"மன்னிக்கவும், {search} க்கு {kind} {value} கிடைக்கவில்லை.",
 "te":"క్షమించండి, {search} కోసం {kind} {value} కనుగొనబడలేదు.",
 "kn":"ಕ್ಷಮಿಸಿ, {search} ಗೆ {kind} {value} ಕಂಡುಬಂದಿಲ್ಲ.",
 "ml":"ക്ഷമിക്കണം, {search} ന് {kind} {value} കണ്ടെത്താനായില്ല.",
 "bn":"দুঃখিত, {search}-এর জন্য {kind} {value} পাওয়া যায়নি।",
 "mr":"माफ करा, {search} साठी {kind} {value} सापडले नाही.",
 "gu":"માફ કરશો, {search} માટે {kind} {value} મળ્યું નથી.",
 "pa":"ਮਾਫ਼ ਕਰਨਾ, {search} ਲਈ {kind} {value} ਨਹੀਂ ਮਿਲਿਆ।",
 "ur":"معذرت، {search} کے لیے {kind} {value} نہیں ملا۔",
 "as":"ক্ষমা কৰিব, {search}ৰ বাবে {kind} {value} পোৱা নগ'ল।",
 "ne":"माफ गर्नुहोस्, {search} का लागि {kind} {value} फेला परेन।",
 "hinglish":"Sorry, {search} ke liye {kind} {value} nahi mila.",
}
for _code, _text in _NOT_FOUND.items():
    CORE.setdefault(_code, {})["not_found"] = _text


def core_tr(lang, key, **values):
    data = CORE.get(lang) or CORE[DEFAULT_LANGUAGE]
    text = data.get(key) or CORE[DEFAULT_LANGUAGE].get(key, key)
    try:
        return small_caps_html(text.format(**values))
    except Exception:
        # Keep placeholders intact if a caller omitted a value; never turn
        # ``{mention}`` into a different key while styling the message.
        return small_caps_html(text)


# Unified Premium plan-page template.  The layout/benefit structure is kept
# identical for every user; only the language is selected from that user's
# saved global language preference.
PREMIUM_PLAN_PAGE = {
    "en": """<b>👋 ʜᴇʏ {mention},</b>\n\n<b>🎁 ᴘʀᴇᴍɪᴜᴍ ғᴇᴀᴛᴜʀᴇ ʙᴇɴɪꜰɪᴛs:</b>\n<b>❏ ɴᴏ ɴᴇᴇᴅ ᴛᴏ ᴏᴘᴇɴ ʟɪɴᴋꜱ
❏ ɢᴇᴛ ᴅɪʀᴇᴄᴛ ғɪʟᴇs
❏ ᴀᴅ-ғʀᴇᴇ ᴇxᴘᴇʀɪᴇɴᴄᴇ
❏ ʜɪɢʜ-sᴘᴇᴇᴅ ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋ
❏ ᴍᴜʟᴛɪ-ᴘʟᴀʏᴇʀ sᴛʀᴇᴀᴍɪɴɢ ʟɪɴᴋs
❏ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏᴠɪᴇs ᴀɴᴅ sᴇʀɪᴇs
❏ ꜰᴜʟʟ ᴀᴅᴍɪɴ sᴜᴘᴘᴏʀᴛ
❏ ʀᴇǫᴜᴇsᴛ ᴡɪʟʟ ʙᴇ ᴄᴏᴍᴘʟᴇᴛᴇᴅ ɪɴ 𝟷ʜ [ ɪꜰ ᴀᴠᴀɪʟᴀʙʟᴇ ]</b>\n\n<b>⛽️ ᴄʜᴇᴄᴋ ʏᴏᴜʀ ᴀᴄᴛɪᴠᴇ ᴘʟᴀɴ: /myplan</b>""",
    "hi": """<b>👋 ʜᴇʏ {mention},</b>\n\n<b>🎁 ᴘʀᴇᴍɪᴜᴍ ғᴇᴀᴛᴜʀᴇ ʙᴇɴᴇғɪᴛs:</b>\n<b>❏ ʟɪɴᴋ ᴋʜᴏʟɴᴇ ᴋɪ ᴢᴀʀᴜʀᴀᴛ ɴᴀʜɪ
❏ ᴅɪʀᴇᴄᴛ ғɪʟᴇs ᴍɪʟᴇɴɢɪ
❏ ᴀᴅ-ғʀᴇᴇ ᴇxᴘᴇʀɪᴇɴᴄᴇ
❏ ʜɪɢʜ-sᴘᴇᴇᴅ ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋ
❏ ᴍᴜʟᴛɪ-ᴘʟᴀʏᴇʀ sᴛʀᴇᴀᴍɪɴɢ ʟɪɴᴋs
❏ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏᴠɪᴇs ᴀᴜʀ sᴇʀɪᴇs
❏ ꜰᴜʟʟ ᴀᴅᴍɪɴ sᴜᴘᴘᴏʀᴛ
❏ ʀᴇǫᴜᴇsᴛ 𝟷ʜ ᴍᴇɪɴ ᴄᴏᴍᴘʟᴇᴛᴇ ʜᴏɢɪ [ ɪғ ᴀᴠᴀɪʟᴀʙʟᴇ ]</b>\n\n<b>⛽️ ᴀᴘɴᴀ ᴀᴄᴛɪᴠᴇ ᴘʟᴀɴ ᴄʜᴇᴄᴋ ᴋᴀʀᴇɴ: /myplan</b>""",
    "hinglish": """<b>👋 ʜᴇʏ {mention},</b>\n\n<b>🎁 ᴘʀᴇᴍɪᴜᴍ ғᴇᴀᴛᴜʀᴇ ʙᴇɴᴇғɪᴛs:</b>\n<b>❏ ʟɪɴᴋ ᴋʜᴏʟɴᴇ ᴋɪ ɴᴇᴇᴅ ɴᴀʜɪ
❏ ᴅɪʀᴇᴄᴛ ғɪʟᴇs ᴍɪʟᴇɴɢɪ
❏ ᴀᴅ-ғʀᴇᴇ ᴇxᴘᴇʀɪᴇɴᴄᴇ
❏ ʜɪɢʜ-sᴘᴇᴇᴅ ᴅᴏᴡɴʟᴏᴀᴅ ʟɪɴᴋ
❏ ᴍᴜʟᴛɪ-ᴘʟᴀʏᴇʀ sᴛʀᴇᴀᴍɪɴɢ ʟɪɴᴋs
❏ ᴜɴʟɪᴍɪᴛᴇᴅ ᴍᴏᴠɪᴇs ᴀᴜʀ sᴇʀɪᴇs
❏ ꜰᴜʟʟ ᴀᴅᴍɪɴ sᴜᴘᴘᴏʀᴛ
❏ ʀᴇǫᴜᴇsᴛ 𝟷ʜ ᴍᴇɪɴ ᴄᴏᴍᴘʟᴇᴛᴇ ʜᴏɢᴀ [ ɪғ ᴀᴠᴀɪʟᴀʙʟᴇ ]</b>\n\n<b>⛽️ ᴀᴘɴᴀ ᴀᴄᴛɪᴠᴇ ᴘʟᴀɴ ᴄʜᴇᴄᴋ ᴋᴀʀᴏ: /myplan</b>""",
}
for _code in LANGUAGES:
    PREMIUM_PLAN_PAGE.setdefault(_code, PREMIUM_PLAN_PAGE["en"])

def premium_plan_tr(lang, mention):
    text = PREMIUM_PLAN_PAGE.get(lang, PREMIUM_PLAN_PAGE["en"])
    return text.format(mention=mention)


# User-facing pages that are shown when navigating back from Home.  These are
# deliberately separate from admin/settings text; the selected language belongs
# to the Telegram user and never changes another user's UI.
PAGE_I18N = {
    "en": {
        "help": "<b>ᴄʟɪᴄᴋ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ ᴠɪᴇᴡ ᴛʜᴇ ʙᴏᴛ ᴅᴏᴄᴜᴍᴇɴᴛᴀᴛɪᴏɴ.</b>",
        "about": "‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]",
    },
    "hi": {"help":"<b>नीचे दिए गए बटन दबाकर Bot की जानकारी देखें।</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "ta": {"help":"<b>கீழே உள்ள பொத்தான்களை அழுத்தி Bot தகவல்களைப் பார்க்கவும்.</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "te": {"help":"<b>Bot వివరాలను చూడటానికి క్రింద ఉన్న బటన్లను నొక్కండి.</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "kn": {"help":"<b>Bot ಮಾಹಿತಿಯನ್ನು ನೋಡಲು ಕೆಳಗಿನ ಬಟನ್‌ಗಳನ್ನು ಒತ್ತಿರಿ.</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "ml": {"help":"<b>Bot വിവരങ്ങൾ കാണാൻ താഴെയുള്ള ബട്ടണുകൾ അമർത്തുക.</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "bn": {"help":"<b>Bot-এর তথ্য দেখতে নিচের বাটনগুলো চাপুন।</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "mr": {"help":"<b>Bot ची माहिती पाहण्यासाठी खालील बटणे दाबा.</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "gu": {"help":"<b>Bot ની માહિતી જોવા નીચેના બટનો દબાવો.</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "pa": {"help":"<b>Bot ਦੀ ਜਾਣਕਾਰੀ ਦੇਖਣ ਲਈ ਹੇਠਾਂ ਦਿੱਤੇ ਬਟਨ ਦਬਾਓ।</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "ur": {"help":"<b>Bot کی معلومات دیکھنے کے لیے نیچے دیے گئے بٹن دبائیں۔</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "as": {"help":"<b>Bot-ৰ তথ্য চাবলৈ তলৰ বুটামসমূহ টিপক।</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "ne": {"help":"<b>Bot को जानकारी हेर्न तलका बटनहरू थिच्नुहोस्।</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
    "hinglish": {"help":"<b>Bot ki information dekhne ke liye neeche diye buttons par click karo.</b>","about":"‣ ᴍʏ ɴᴀᴍᴇ : ᴊɪꜱꜱʜᴜ ꜰɪʟᴛᴇʀ ʙᴏᴛ\n‣ ᴄʀᴇᴀᴛᴏʀ : ᴊɪꜱꜱʜᴜ\n‣ ʟɪʙʀᴀʀʏ : ᴘʏʀᴏɢʀᴀᴍ\n‣ ʟᴀɴɢᴜᴀɢᴇ : ᴘʏᴛʜᴏɴ\n‣ ᴅᴀᴛᴀʙᴀꜱᴇ : ᴍᴏɴɢᴏ ᴅʙ\n‣ ʙᴜɪʟᴅ : ᴠ-𝟺.𝟷 [ꜱᴛᴀʙʟᴇ]"},
}

def page_tr(lang, key):
    return small_caps(PAGE_I18N.get(lang, PAGE_I18N[DEFAULT_LANGUAGE]).get(key, PAGE_I18N[DEFAULT_LANGUAGE].get(key, key)))

HOME_LABELS = {
"en": {"add_group":"⇋ Add Me To Your Group ⇋","disable_ads":"• Disable Ads •","special":"• Special •","help":"• Help •","about":"• About •","earn":"• Earn Unlimited Money •"},
"hi": {"add_group":"⇋ मुझे अपने ग्रुप में जोड़ें ⇋","disable_ads":"• Ads बंद करें •","special":"• विशेष •","help":"• मदद •","about":"• जानकारी •","earn":"• कमाई करें •"},
"ta": {"add_group":"⇋ உங்கள் குழுவில் என்னை சேர்க்கவும் ⇋","disable_ads":"• Ads நீக்கு •","special":"• சிறப்பு •","help":"• உதவி •","about":"• பற்றி •","earn":"• சம்பாதிக்கவும் •"},
"te": {"add_group":"⇋ నన్ను మీ గ్రూప్‌లో చేర్చండి ⇋","disable_ads":"• Ads ఆపండి •","special":"• ప్రత్యేకం •","help":"• సహాయం •","about":"• గురించి •","earn":"• సంపాదించండి •"},
"kn": {"add_group":"⇋ ನನ್ನನ್ನು ನಿಮ್ಮ ಗ್ರೂಪ್‌ಗೆ ಸೇರಿಸಿ ⇋","disable_ads":"• Ads ನಿಲ್ಲಿಸಿ •","special":"• ವಿಶೇಷ •","help":"• ಸಹಾಯ •","about":"• ಬಗ್ಗೆ •","earn":"• ಸಂಪಾದಿಸಿ •"},
"ml": {"add_group":"⇋ എന്നെ നിങ്ങളുടെ ഗ്രൂപ്പിൽ ചേർക്കുക ⇋","disable_ads":"• Ads ഒഴിവാക്കുക •","special":"• പ്രത്യേകത •","help":"• സഹായം •","about":"• കുറിച്ച് •","earn":"• സമ്പാദിക്കുക •"},
"bn": {"add_group":"⇋ আমাকে আপনার গ্রুপে যোগ করুন ⇋","disable_ads":"• Ads বন্ধ করুন •","special":"• বিশেষ •","help":"• সাহায্য •","about":"• সম্পর্কে •","earn":"• আয় করুন •"},
"mr": {"add_group":"⇋ मला तुमच्या ग्रुपमध्ये जोडा ⇋","disable_ads":"• Ads बंद करा •","special":"• विशेष •","help":"• मदत •","about":"• माहिती •","earn":"• कमवा •"},
"gu": {"add_group":"⇋ મને તમારા ગ્રુપમાં ઉમેરો ⇋","disable_ads":"• Ads બંધ કરો •","special":"• ખાસ •","help":"• મદદ •","about":"• વિશે •","earn":"• કમાઓ •"},
"pa": {"add_group":"⇋ ਮੈਨੂੰ ਆਪਣੇ ਗਰੁੱਪ ਵਿੱਚ ਜੋੜੋ ⇋","disable_ads":"• Ads ਬੰਦ ਕਰੋ •","special":"• ਖਾਸ •","help":"• ਮਦਦ •","about":"• ਜਾਣਕਾਰੀ •","earn":"• ਕਮਾਓ •"},
"ur": {"add_group":"⇋ مجھے اپنے گروپ میں شامل کریں ⇋","disable_ads":"• Ads بند کریں •","special":"• خاص •","help":"• مدد •","about":"• تعارف •","earn":"• کمائیں •"},
"as": {"add_group":"⇋ মোক আপোনাৰ গ্ৰুপত যোগ কৰক ⇋","disable_ads":"• Ads বন্ধ কৰক •","special":"• বিশেষ •","help":"• সহায় •","about":"• পৰিচয় •","earn":"• উপাৰ্জন কৰক •"},
"ne": {"add_group":"⇋ मलाई आफ्नो ग्रुपमा थप्नुहोस् ⇋","disable_ads":"• Ads बन्द गर्नुहोस् •","special":"• विशेष •","help":"• मद्दत •","about":"• परिचय •","earn":"• कमाउनुहोस् •"},
"hinglish": {"add_group":"⇋ Mujhe Apne Group Mein Add Karo ⇋","disable_ads":"• Ads Disable Karo •","special":"• Special •","help":"• Help •","about":"• About •","earn":"• Earn Karo •"},
}
for _code in LANGUAGES:
    HOME_LABELS.setdefault(_code, {})
    HOME_LABELS[_code].setdefault("clean", {
        "en": "🧹 Clean Home",
        "hi": "🧹 Home साफ करें",
        "hinglish": "🧹 Home Clean Karo",
    }.get(_code, "🧹 Clean Home"))


def home_tr(lang, key):
    return small_caps(HOME_LABELS.get(lang, HOME_LABELS[DEFAULT_LANGUAGE]).get(key, HOME_LABELS[DEFAULT_LANGUAGE][key]))

VERIFY = {
"en": {
 "verify1":"<b>👋 Hey {mention}, {status},\n\n📌 You are not verified today. Click Verify to get unlimited access until the next verification.\n\n#Verification: 1/3 ✓\n\nIf you want direct files without verification, buy Premium. 😊\n\n💎 Send /plan to buy Premium.</b>",
 "verify2":"<b>👋 Hey {mention}, {status},\n\n📌 You are not verified. Tap the verification link to get unlimited access until the next verification.\n\n#Verification: 2/3\n\nIf you want direct files without verification, buy Premium. 😊\n\n💎 Send /plan to buy Premium.</b>",
 "verify3":"<b>👋 Hey {mention},\n\n📌 You are not verified today. Tap the verification link to get unlimited access for the next full day.\n\n#Verification: 3/3\n\nWant direct files? Premium gives you direct access with no verification.</b>",
 "done":"<b>👋 Hey {mention},\n\nYou completed verification {num} ✓\n\nYou now have unlimited access for the next <code>{duration}</code>.</b>",
 "short1":"<b>👋 Good {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 Complete the step below to unlock it.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🟢 <b>1 / 3</b>\n\n🔹 <b>Step 1:</b> Complete the verification below.</b>",
 "short2":"<b>👋 Good {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 One step is complete. Continue with the next step.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🟡 <b>2 / 3</b>\n\n🔹 <b>Step 2:</b> Complete the next verification.</b>",
 "short3":"<b>👋 Good {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 This is the final step to unlock your file.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🔴 <b>3 / 3</b>\n\n🔹 <b>Step 3:</b> Complete the final verification to unlock the file.</b>",
},
}
# Concise translations for the actual verification gate. The layout and placeholders
# stay identical so existing links/file information remain untouched.
VERIFY.update({
"hi":{"verify1":"<b>👋 Hey {mention}, {status},\n\n📌 आज आप verified नहीं हैं। Verify करके अगले verification तक unlimited access पाएं।\n\n#Verification: 1/3 ✓\n\nबिना verification direct files चाहिए तो Premium खरीदें। 😊\n\n💎 Premium के लिए /plan भेजें।</b>","verify2":"<b>👋 Hey {mention}, {status},\n\n📌 आप verified नहीं हैं। Verification link खोलकर अगली verification तक unlimited access पाएं।\n\n#Verification: 2/3\n\nबिना verification direct files चाहिए तो Premium खरीदें। 😊\n\n💎 Premium के लिए /plan भेजें।</b>","verify3":"<b>👋 Hey {mention},\n\n📌 आज आप verified नहीं हैं। Verification link खोलकर अगले पूरे दिन का access पाएं।\n\n#Verification: 3/3\n\nDirect files के लिए Premium लें; verification की जरूरत नहीं होगी।</b>","done":"<b>👋 Hey {mention},\n\nआपने verification {num} पूरा कर लिया ✓\n\nअब आपके पास अगले <code>{duration}</code> तक unlimited access है।</b>"},
"hinglish":{"verify1":"<b>👋 Hey {mention}, {status},\n\n📌 Aaj aap verified nahi ho. Verify karo aur next verification tak unlimited access pao.\n\n#Verification: 1/3 ✓\n\nBina verification direct files chahiye to Premium lo. 😊\n\n💎 Premium ke liye /plan bhejo.</b>","verify2":"<b>👋 Hey {mention}, {status},\n\n📌 Aap verified nahi ho. Verification link open karo aur next verification tak unlimited access pao.\n\n#Verification: 2/3\n\nBina verification direct files chahiye to Premium lo. 😊\n\n💎 Premium ke liye /plan bhejo.</b>","verify3":"<b>👋 Hey {mention},\n\n📌 Aaj aap verified nahi ho. Verification link open karke next full day ka access pao.\n\n#Verification: 3/3\n\nDirect files ke liye Premium lo; verification ki zarurat nahi hogi.</b>","done":"<b>👋 Hey {mention},\n\nAapne verification {num} complete kar liya ✓\n\nAb aapke paas next <code>{duration}</code> tak unlimited access hai.</b>"},
})
# Complete verification/shortlink translations.  Callback URLs, file IDs and
# database values are never translated; only the surrounding user-facing copy is.
VERIFY.update({
"ta":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 இன்று நீங்கள் verified செய்யப்படவில்லை. Verify செய்து அடுத்த verification வரை unlimited access பெறுங்கள்.\n\n#Verification: 1/3 ✓\n\nVerification இல்லாமல் direct files வேண்டுமெனில் Premium வாங்குங்கள். 😊\n\n💎 Premium வாங்க /plan அனுப்புங்கள்.</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 நீங்கள் verified செய்யப்படவில்லை. Verification link-ஐ திறந்து அடுத்த verification வரை unlimited access பெறுங்கள்.\n\n#Verification: 2/3\n\nVerification இல்லாமல் direct files வேண்டுமெனில் Premium வாங்குங்கள். 😊\n\n💎 Premium வாங்க /plan அனுப்புங்கள்.</b>",
"verify3":"<b>👋 {mention},\n\n📌 இன்று நீங்கள் verified செய்யப்படவில்லை. Verification link-ஐ திறந்து அடுத்த முழு நாளுக்கான access பெறுங்கள்.\n\n#Verification: 3/3\n\nDirect files வேண்டுமெனில் Premium வாங்குங்கள்; verification தேவையில்லை.</b>",
"done":"<b>👋 {mention},\n\nநீங்கள் verification {num} முடித்துவிட்டீர்கள் ✓\n\nஅடுத்த <code>{duration}</code> வரை unlimited access கிடைக்கும்.</b>",
"short1":"<b>👋 {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 File-ஐ பெற கீழே உள்ள படியை முடிக்கவும்.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🟢 <b>1 / 3</b>\n\n🔹 <b>Step 1:</b> கீழே உள்ள verification-ஐ முடிக்கவும்.</b>",
"short2":"<b>👋 {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 ஒரு படி முடிந்தது. அடுத்த படியை தொடரவும்.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🟡 <b>2 / 3</b>\n\n🔹 <b>Step 2:</b> அடுத்த verification-ஐ முடிக்கவும்.</b>",
"short3":"<b>👋 {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 File-ஐ பெற இது இறுதி படி.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🔴 <b>3 / 3</b>\n\n🔹 <b>Step 3:</b> இறுதி verification-ஐ முடிக்கவும்.</b>"},
"te":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 ఈరోజు మీరు verified కాదు. Verify చేసి తదుపరి verification వరకు unlimited access పొందండి.\n\n#Verification: 1/3 ✓\n\nVerification లేకుండా direct files కావాలంటే Premium కొనండి. 😊\n\n💎 Premium కోసం /plan పంపండి.</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 మీరు verified కాదు. Verification link తెరిచి తదుపరి verification వరకు unlimited access పొందండి.\n\n#Verification: 2/3\n\nVerification లేకుండా direct files కావాలంటే Premium కొనండి. 😊\n\n💎 Premium కోసం /plan పంపండి.</b>",
"verify3":"<b>👋 {mention},\n\n📌 ఈరోజు మీరు verified కాదు. Verification link తెరిచి తదుపరి పూర్తి రోజు access పొందండి.\n\n#Verification: 3/3\n\nDirect files కోసం Premium కొనండి; verification అవసరం లేదు.</b>",
"done":"<b>👋 {mention},\n\nమీరు verification {num} పూర్తి చేశారు ✓\n\nతదుపరి <code>{duration}</code> వరకు unlimited access ఉంది.</b>",
"short1":"<b>👋 {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 File పొందడానికి క్రింది step పూర్తి చేయండి.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🟢 <b>1 / 3</b>\n\n🔹 <b>Step 1:</b> క్రింది verification పూర్తి చేయండి.</b>",
"short2":"<b>👋 {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 ఒక step పూర్తైంది. తదుపరి step కొనసాగించండి.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🟡 <b>2 / 3</b>\n\n🔹 <b>Step 2:</b> తదుపరి verification పూర్తి చేయండి.</b>",
"short3":"<b>👋 {greeting}, {mention}!\n\n🎬 <b>File Ready</b>\n\n📁 <b>{name}</b>\n📦 <b>Size:</b> {size}\n\n🔗 File పొందడానికి ఇది చివరి step.\n\n🔐 <b>Shortlink Verification</b>\n📊 <b>Progress:</b> 🔴 <b>3 / 3</b>\n\n🔹 <b>Step 3:</b> చివరి verification పూర్తి చేయండి.</b>"},
"kn":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 ಇಂದು ನೀವು verified ಆಗಿಲ್ಲ. Verify ಮಾಡಿ ಮುಂದಿನ verification ವರೆಗೆ unlimited access ಪಡೆಯಿರಿ.\n\n#Verification: 1/3 ✓\n\nVerification ಇಲ್ಲದೆ direct files ಬೇಕಾದರೆ Premium ಖರೀದಿಸಿ. 😊\n\n💎 Premiumಗಾಗಿ /plan ಕಳುಹಿಸಿ.</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 ನೀವು verified ಆಗಿಲ್ಲ. Verification link ತೆರೆಯಿರಿ ಮತ್ತು ಮುಂದಿನ verification ವರೆಗೆ unlimited access ಪಡೆಯಿರಿ.\n\n#Verification: 2/3\n\nVerification ಇಲ್ಲದೆ direct files ಬೇಕಾದರೆ Premium ಖರೀದಿಸಿ. 😊\n\n💎 Premiumಗಾಗಿ /plan ಕಳುಹಿಸಿ.</b>",
"verify3":"<b>👋 {mention},\n\n📌 ಇಂದು ನೀವು verified ಆಗಿಲ್ಲ. Verification link ತೆರೆಯಿರಿ ಮತ್ತು ಮುಂದಿನ ಪೂರ್ಣ ದಿನದ access ಪಡೆಯಿರಿ.\n\n#Verification: 3/3\n\nDirect filesಗಾಗಿ Premium ಖರೀದಿಸಿ; verification ಅಗತ್ಯವಿಲ್ಲ.</b>",
"done":"<b>👋 {mention},\n\nನೀವು verification {num} ಪೂರ್ಣಗೊಳಿಸಿದ್ದೀರಿ ✓\n\nಮುಂದಿನ <code>{duration}</code> ವರೆಗೆ unlimited access ಇದೆ.</b>"},
"ml":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 ഇന്ന് നിങ്ങൾ verified അല്ല. Verify ചെയ്ത് അടുത്ത verification വരെ unlimited access നേടുക.\n\n#Verification: 1/3 ✓\n\nVerification ഇല്ലാതെ direct files വേണമെങ്കിൽ Premium വാങ്ങുക. 😊\n\n💎 Premium വാങ്ങാൻ /plan അയയ്ക്കുക.</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 നിങ്ങൾ verified അല്ല. Verification link തുറന്ന് അടുത്ത verification വരെ unlimited access നേടുക.\n\n#Verification: 2/3\n\nVerification ഇല്ലാതെ direct files വേണമെങ്കിൽ Premium വാങ്ങുക. 😊\n\n💎 Premium വാങ്ങാൻ /plan അയയ്ക്കുക.</b>",
"verify3":"<b>👋 {mention},\n\n📌 ഇന്ന് നിങ്ങൾ verified അല്ല. Verification link തുറന്ന് അടുത്ത മുഴുവൻ ദിവസത്തേക്കുള്ള access നേടുക.\n\n#Verification: 3/3\n\nDirect files വേണമെങ്കിൽ Premium വാങ്ങുക; verification ആവശ്യമില്ല.</b>",
"done":"<b>👋 {mention},\n\nനിങ്ങൾ verification {num} പൂർത്തിയാക്കി ✓\n\nഅടുത്ത <code>{duration}</code> വരെ unlimited access ലഭിക്കും.</b>"},
"bn":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 আজ আপনি verified নন। Verify করে পরবর্তী verification পর্যন্ত unlimited access পান।\n\n#Verification: 1/3 ✓\n\nVerification ছাড়া direct files চাইলে Premium কিনুন। 😊\n\n💎 Premium কিনতে /plan পাঠান।</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 আপনি verified নন। Verification link খুলে পরবর্তী verification পর্যন্ত unlimited access পান।\n\n#Verification: 2/3\n\nVerification ছাড়া direct files চাইলে Premium কিনুন। 😊\n\n💎 Premium কিনতে /plan পাঠান।</b>",
"verify3":"<b>👋 {mention},\n\n📌 আজ আপনি verified নন। Verification link খুলে পরবর্তী পুরো দিনের access পান।\n\n#Verification: 3/3\n\nDirect files-এর জন্য Premium কিনুন; verification লাগবে না.</b>",
"done":"<b>👋 {mention},\n\nআপনি verification {num} সম্পূর্ণ করেছেন ✓\n\nপরবর্তী <code>{duration}</code> পর্যন্ত unlimited access পাবেন।</b>"},
"mr":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 आज तुम्ही verified नाही. Verify करून पुढील verification पर्यंत unlimited access मिळवा.\n\n#Verification: 1/3 ✓\n\nVerification शिवाय direct files हव्या असल्यास Premium घ्या. 😊\n\n💎 Premium साठी /plan पाठवा.</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 तुम्ही verified नाही. Verification link उघडून पुढील verification पर्यंत unlimited access मिळवा.\n\n#Verification: 2/3\n\nVerification शिवाय direct files हव्या असल्यास Premium घ्या. 😊\n\n💎 Premium साठी /plan पाठवा.</b>",
"verify3":"<b>👋 {mention},\n\n📌 आज तुम्ही verified नाही. Verification link उघडून पुढील पूर्ण दिवसाचा access मिळवा.\n\n#Verification: 3/3\n\nDirect files साठी Premium घ्या; verification आवश्यक नाही.</b>",
"done":"<b>👋 {mention},\n\nतुम्ही verification {num} पूर्ण केले ✓\n\nपुढील <code>{duration}</code> पर्यंत unlimited access मिळेल.</b>"},
"gu":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 આજે તમે verified નથી. Verify કરીને આગામી verification સુધી unlimited access મેળવો.\n\n#Verification: 1/3 ✓\n\nVerification વગર direct files જોઈએ તો Premium ખરીદો. 😊\n\n💎 Premium માટે /plan મોકલો.</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 તમે verified નથી. Verification link ખોલીને આગામી verification સુધી unlimited access મેળવો.\n\n#Verification: 2/3\n\nVerification વગર direct files જોઈએ તો Premium ખરીદો. 😊\n\n💎 Premium માટે /plan મોકલો.</b>",
"verify3":"<b>👋 {mention},\n\n📌 આજે તમે verified નથી. Verification link ખોલીને આગામી આખા દિવસનું access મેળવો.\n\n#Verification: 3/3\n\nDirect files માટે Premium ખરીદો; verification જરૂરી નથી.</b>",
"done":"<b>👋 {mention},\n\nતમે verification {num} પૂર્ણ કર્યું ✓\n\nઆગામી <code>{duration}</code> સુધી unlimited access મળશે.</b>"},
"pa":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 ਅੱਜ ਤੁਸੀਂ verified ਨਹੀਂ ਹੋ। Verify ਕਰਕੇ ਅਗਲੀ verification ਤੱਕ unlimited access ਲਵੋ।\n\n#Verification: 1/3 ✓\n\nVerification ਤੋਂ ਬਿਨਾਂ direct files ਚਾਹੀਦੀਆਂ ਹਨ ਤਾਂ Premium ਲਵੋ। 😊\n\n💎 Premium ਲਈ /plan ਭੇਜੋ।</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 ਤੁਸੀਂ verified ਨਹੀਂ ਹੋ। Verification link ਖੋਲ੍ਹੋ ਅਤੇ ਅਗਲੀ verification ਤੱਕ unlimited access ਲਵੋ।\n\n#Verification: 2/3\n\nVerification ਤੋਂ ਬਿਨਾਂ direct files ਚਾਹੀਦੀਆਂ ਹਨ ਤਾਂ Premium ਲਵੋ। 😊\n\n💎 Premium ਲਈ /plan ਭੇਜੋ।</b>",
"verify3":"<b>👋 {mention},\n\n📌 ਅੱਜ ਤੁਸੀਂ verified ਨਹੀਂ ਹੋ। Verification link ਖੋਲ੍ਹੋ ਅਤੇ ਅਗਲੇ ਪੂਰੇ ਦਿਨ ਦਾ access ਲਵੋ।\n\n#Verification: 3/3\n\nDirect files ਲਈ Premium ਲਵੋ; verification ਦੀ ਲੋੜ ਨਹੀਂ।</b>",
"done":"<b>👋 {mention},\n\nਤੁਸੀਂ verification {num} ਪੂਰੀ ਕਰ ਲਈ ✓\n\nਅਗਲੇ <code>{duration}</code> ਤੱਕ unlimited access ਮਿਲੇਗਾ।</b>"},
"ur":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 آج آپ verified نہیں ہیں۔ Verify کریں اور اگلی verification تک unlimited access حاصل کریں۔\n\n#Verification: 1/3 ✓\n\nVerification کے بغیر direct files چاہئیں تو Premium خریدیں۔ 😊\n\n💎 Premium کے لیے /plan بھیجیں۔</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 آپ verified نہیں ہیں۔ Verification link کھولیں اور اگلی verification تک unlimited access حاصل کریں۔\n\n#Verification: 2/3\n\nVerification کے بغیر direct files چاہئیں تو Premium خریدیں۔ 😊\n\n💎 Premium کے لیے /plan بھیجیں۔</b>",
"verify3":"<b>👋 {mention},\n\n📌 آج آپ verified نہیں ہیں۔ Verification link کھولیں اور اگلے پورے دن کا access حاصل کریں۔\n\n#Verification: 3/3\n\nDirect files کے لیے Premium خریدیں؛ verification کی ضرورت نہیں۔</b>",
"done":"<b>👋 {mention},\n\nآپ نے verification {num} مکمل کر لی ✓\n\nاگلے <code>{duration}</code> تک unlimited access حاصل ہے۔</b>"},
"as":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 আজি আপুনি verified নহয়। Verify কৰি পৰৱৰ্তী verification লৈ unlimited access লওক।\n\n#Verification: 1/3 ✓\n\nVerification নকৰাকৈ direct files বিচাৰিলে Premium ক্ৰয় কৰক। 😊\n\n💎 Premiumৰ বাবে /plan পঠাওক।</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 আপুনি verified নহয়। Verification link খুলি পৰৱৰ্তী verification লৈ unlimited access লওক।\n\n#Verification: 2/3\n\nVerification নকৰাকৈ direct files বিচাৰিলে Premium ক্ৰয় কৰক। 😊\n\n💎 Premiumৰ বাবে /plan পঠাওক।</b>",
"verify3":"<b>👋 {mention},\n\n📌 আজি আপুনি verified নহয়। Verification link খুলি পৰৱৰ্তী সম্পূৰ্ণ দিনৰ access লওক।\n\n#Verification: 3/3\n\nDirect filesৰ বাবে Premium ক্ৰয় কৰক; verificationৰ প্ৰয়োজন নাই।</b>",
"done":"<b>👋 {mention},\n\nআপুনি verification {num} সম্পূৰ্ণ কৰিছে ✓\n\nপৰৱৰ্তী <code>{duration}</code> লৈ unlimited access পাব।</b>"},
"ne":{
"verify1":"<b>👋 {mention}, {status},\n\n📌 आज तपाईं verified हुनुहुन्न। Verify गरेर अर्को verification सम्म unlimited access पाउनुहोस्।\n\n#Verification: 1/3 ✓\n\nVerification बिना direct files चाहनुहुन्छ भने Premium किन्नुहोस्। 😊\n\n💎 Premium का लागि /plan पठाउनुहोस्।</b>",
"verify2":"<b>👋 {mention}, {status},\n\n📌 तपाईं verified हुनुहुन्न। Verification link खोलेर अर्को verification सम्म unlimited access पाउनुहोस्।\n\n#Verification: 2/3\n\nVerification बिना direct files चाहनुहुन्छ भने Premium किन्नुहोस्। 😊\n\n💎 Premium का लागि /plan पठाउनुहोस्।</b>",
"verify3":"<b>👋 {mention},\n\n📌 आज तपाईं verified हुनुहुन्न। Verification link खोलेर अर्को पूरा दिनको access पाउनुहोस्।\n\n#Verification: 3/3\n\nDirect files का लागि Premium किन्नुहोस्; verification आवश्यक छैन।</b>",
"done":"<b>👋 {mention},\n\nतपाईंले verification {num} पूरा गर्नुभयो ✓\n\nअब <code>{duration}</code> सम्म unlimited access छ।</b>"},
})

# Shortlink mode uses the same visual structure as Script.py: the file name,
# size, boxed progress area, emojis and 1/3 -> 2/3 -> 3/3 flow stay unchanged.
# Only the natural-language text is translated.
_SHORTLINK_LOCALIZED = {
    "en": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ", "ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇ sᴛᴇᴘ ʙᴇʟᴏᴡ ᴛᴏ ᴜɴʟᴏᴄᴋ ɪᴛ.", "ᴏɴᴇ sᴛᴇᴘ ɪs ᴄᴏᴍᴘʟᴇᴛᴇᴅ — ᴄᴏɴᴛɪɴᴜᴇ ᴡɪᴛʜ ᴛʜᴇ ɴᴇxᴛ sᴛᴇᴘ.", "ᴛʜɪs ɪs ᴛʜᴇ ғɪɴᴀʟ sᴛᴇᴘ ᴛᴏ ᴜɴʟᴏᴄᴋ ʏᴏᴜʀ ғɪʟᴇ.", "ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ ʙᴇʟᴏᴡ.", "ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇ ɴᴇxᴛ sᴛᴇᴘ ᴛᴏ ᴄᴏɴᴛɪɴᴜᴇ.", "ᴄᴏᴍᴘʟᴇᴛᴇ ᴛʜᴇ ғɪɴᴀʟ ᴠᴇʀɪғɪᴄᴀᴛɪᴏɴ ᴛᴏ ᴜɴʟᴏᴄᴋ ᴛʜᴇ ғɪʟᴇ."),
    "hi": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ ɴᴇᴇᴄʜᴇ ᴅɪʏᴀ sᴛᴇᴘ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀᴇɴ.", "ᴇᴋ sᴛᴇᴘ ᴄᴏᴍᴘʟᴇᴛᴇ ʜᴏ ɢᴀʏᴀ — ᴀɢʟᴇ sᴛᴇᴘ ᴘᴀʀ ᴊᴀᴀᴇɴ.", "ʏᴇ ᴀɴᴛɪᴍ sᴛᴇᴘ ʜᴀɪ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴇɴ.", "ɴᴇᴇᴄʜᴇ ᴅɪʏᴀ ɢᴀʏᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀᴇɴ.", "ᴀɢʟᴀ sᴛᴇᴘ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀᴇɴ.", "ғɪɴᴀʟ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀᴇɴ."),
    "hinglish": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀɴᴇ ᴋᴇ ʟɪʏᴇ ɴᴇᴇᴄʜᴇ ᴡᴀʟᴀ sᴛᴇᴘ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀᴏ.", "ᴇᴋ sᴛᴇᴘ ᴄᴏᴍᴘʟᴇᴛᴇ ʜᴏ ɢᴀʏᴀ — ᴀɢʟᴇ sᴛᴇᴘ ᴘᴀʀ ᴊᴀᴏ.", "ʏᴇ ғɪɴᴀʟ sᴛᴇᴘ ʜᴀɪ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴏ.", "ɴᴇᴇᴄʜᴇ ᴡᴀʟɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀᴏ.", "ɴᴇxᴛ sᴛᴇᴘ ᴋɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀᴏ.", "ғɪɴᴀʟ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇ ᴋᴀʀᴏ."),
    "ta": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴘᴀɴɴᴀ ᴋᴇᴇᴢʜᴇ ᴜʟʟᴀ sᴛᴇᴘ-ᴀɪ ᴍᴜᴅɪᴋᴋᴀᴠᴜᴍ.", "ᴏʀᴜ sᴛᴇᴘ ᴍᴜᴅɪɴᴛʜᴀᴛᴜ — ᴀᴅᴜᴛʜᴀ sᴛᴇᴘ-ᴋᴜ ᴘᴏɴɢᴀʟ.", "ɪᴛʜᴜ ᴋᴀᴅᴀɪsɪ sᴛᴇᴘ — ғɪʟᴇ-ᴀɪ ᴜɴʟᴏᴄᴋ ᴘᴀɴɴᴜɴɢᴀʟ.", "ᴋᴇᴇᴢʜᴇ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ-ᴀɪ ᴍᴜᴅɪᴋᴋᴀᴠᴜᴍ.", "ᴀᴅᴜᴛʜᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ-ᴀɪ ᴍᴜᴅɪᴋᴋᴀᴠᴜᴍ.", "ᴋᴀᴅᴀɪsɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ-ᴀɪ ᴍᴜᴅɪᴋᴋᴀᴠᴜᴍ."),
    "te": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴄʜᴇʏᴀᴅᴀɴɪᴋɪ ᴋɪɴᴅᴀ ɪᴄᴄʜɪɴ sᴛᴇᴘ-ɴɪ ᴄᴏᴍᴘʟᴇᴛᴇ ᴄʜᴇʏᴀɴᴅɪ.", "ᴏᴋᴀ sᴛᴇᴘ ᴄᴏᴍᴘʟᴇᴛᴇ ᴀʏɪɴᴅɪ — ᴛᴀʀᴜᴠᴀᴛɪ sᴛᴇᴘ-ᴛᴏ ᴋᴏɴᴀsᴀɢᴀɴᴅɪ.", "ɪᴅɪ ғɪɴᴀʟ sᴛᴇᴘ — ғɪʟᴇ-ɴɪ ᴜɴʟᴏᴄᴋ ᴄʜᴇʏᴀɴᴅɪ.", "ᴋɪɴᴅᴀ ɪᴄᴄʜɪɴ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ-ɴɪ ᴄᴏᴍᴘʟᴇᴛᴇ ᴄʜᴇʏᴀɴᴅɪ.", "ᴛᴀʀᴜᴠᴀᴛɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ-ɴɪ ᴄᴏᴍᴘʟᴇᴛᴇ ᴄʜᴇʏᴀɴᴅɪ.", "ᴄʜɪᴠᴀʀɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ-ɴɪ ᴄᴏᴍᴘʟᴇᴛᴇ ᴄʜᴇʏᴀɴᴅɪ."),
    "kn": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴍᴀᴅᴀʟᴜ ᴋᴇʟᴀɢɪɴᴀ sᴛᴇᴘ ᴘᴜʀᴛɪ ᴍᴀᴅɪ.", "ᴏɴᴅᴜ sᴛᴇᴘ ᴍᴜɢɪᴅɪᴅᴇ — ᴍᴜɴᴅɪɴᴀ sᴛᴇᴘ ᴍᴀᴅɪ.", "ɪᴅᴜ ᴋᴏɴᴇʏᴀ sᴛᴇᴘ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴍᴀᴅɪ.", "ᴋᴇʟᴀɢɪɴᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴛɪ ᴍᴀᴅɪ.", "ᴍᴜɴᴅɪɴᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴛɪ ᴍᴀᴅɪ.", "ᴋᴏɴᴇʏᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴛɪ ᴍᴀᴅɪ."),
    "ml": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴄᴇʏʏᴀɴ ᴛᴀᴢʜᴇ ᴋᴏᴅᴜᴛᴛɪʟᴜʟʟᴀ sᴛᴇᴘ ᴘᴜʀᴛʜɪʏᴀᴀᴋᴋᴜᴋᴀ.", "ᴏʀᴜ sᴛᴇᴘ ᴘᴜʀᴛʜɪʏᴀᴀʏɪ — ᴀᴅᴜᴛᴛʜᴀ sᴛᴛᴇᴘ ᴛᴜᴅᴀʀᴜᴋᴀ.", "ɪᴛʜᴜ ᴀᴠᴀsᴀɴᴀ sᴛᴇᴘ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴄᴇʏʏᴜᴋᴀ.", "ᴛᴀᴢʜᴇ ᴋᴏᴅᴜᴛᴛᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴛʜɪʏᴀᴀᴋᴋᴜᴋᴀ.", "ᴀᴅᴜᴛᴛʜᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴛʜɪʏᴀᴀᴋᴋᴜᴋᴀ.", "ᴀᴠᴀsᴀɴᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴛʜɪʏᴀᴀᴋᴋᴜᴋᴀ."),
    "bn": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴏʀᴛᴇ ɴɪᴄʜᴇʀ sᴛᴇᴘ-ᴛɪ sᴍᴘᴜʀɴ ᴋʀᴜɴ.", "ᴇᴋᴛɪ sᴛᴇᴘ sᴍᴘᴜʀɴ ʜᴏʏᴇᴄʜᴇ — ᴘᴇʀᴇʀ sᴛᴇᴘ ᴄʜᴀʟɪʏᴇ ʏᴀɴ.", "ᴇᴛɪ sʜᴇsʜ sᴛᴇᴘ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋʀᴜɴ.", "ɴɪᴄʜᴇʀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ sᴍᴘᴜʀɴ ᴋʀᴜɴ.", "ᴘᴇʀᴇʀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ sᴍᴘᴜʀɴ ᴋʀᴜɴ.", "sʜᴇsʜ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ sᴍᴘᴜʀɴ ᴋʀᴜɴ."),
    "mr": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀɴʏᴀsᴀᴛʜɪ ᴋᴀʟɪʟ sᴛᴇᴘ ᴘᴜʀɴ ᴋᴀʀᴀ.", "ᴇᴋ sᴛᴇᴘ ᴘᴜʀɴ ᴢᴀʟᴀ — ᴘᴜᴅʜɪʟ sᴛᴇᴘ ᴋᴀᴅᴇ ᴢᴀ.", "ʜᴀ sʜᴇᴠᴀᴛᴄʜᴀ sᴛᴇᴘ ᴀʜᴇ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴀ.", "ᴋᴀʟɪʟ ᴅɪʟᴇʟɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɴ ᴋᴀʀᴀ.", "ᴘᴜᴅʜɪʟ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɴ ᴋᴀʀᴀ.", "sʜᴇᴠᴀᴛᴄʜɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɴ ᴋᴀʀᴀ."),
    "gu": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴠᴀ ᴍᴀᴛᴇ ɴɪᴄʜᴇɴᴏ sᴛᴇᴘ ᴘᴜʀᴏ ᴋᴀʀᴏ.", "ᴇᴋ sᴛᴇᴘ ᴘᴜʀᴏ ᴛʜᴀʏᴏ — ᴀɢᴀᴜɴᴀ sᴛᴇᴘ ᴄʜᴀʟᴜ ᴋᴀʀᴏ.", "ᴀᴀ ғɪɴᴀʟ sᴛᴇᴘ ᴄʜᴇ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴏ.", "ɴɪᴄʜᴇɴᴜ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɪ ᴋᴀʀᴏ.", "ᴀᴀɢᴀʟɴɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɪ ᴋᴀʀᴏ.", "ᴄʜᴇʟʟɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɪ ᴋᴀʀᴏ."),
    "pa": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄ ᴋᴀʀɴ ʟᴀɪ ʜᴇᴛʜᴀɴ ᴅᴀ  sᴛᴇᴘ ᴘᴜʀᴀ ᴋᴀʀᴏ.", "ᴇᴋ sᴛᴇᴘ ᴘᴜʀᴀ ʜᴏ ɢɪᴀ — ᴀɢʟᴇ sᴛᴇᴘ ᴠᴀʟ ᴠᴀᴅʜᴏ.", "ᴇʜ ғɪɴᴀʟ sᴛᴇᴘ ʜᴀɪ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴏ.", "ʜᴇᴛʜᴀɴ ᴅɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɪ ᴋᴀʀᴏ.", "ᴀɢʟɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɪ ᴋᴀʀᴏ.", "ᴀᴋʜɪʀɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɪ ᴋᴀʀᴏ."),
    "ur": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴇ ʟɪʏᴇ ɴᴇᴇᴄʜᴇ ᴅɪᴀ ɢᴀʏᴀ sᴛᴇᴘ ᴍᴜᴋᴀᴍᴍᴀʟ ᴋᴀʀᴇɪɴ.", "ᴇᴋ sᴛᴇᴘ ᴍᴜᴋᴀᴍᴍᴀʟ ʜᴏ ɢᴀʏᴀ — ᴀɢʟᴇ sᴛᴇᴘ ᴋᴇ sᴀᴀᴛʜ ᴊᴀᴀᴇɪɴ.", "ʏᴇʜ ғɪɴᴀʟ sᴛᴇᴘ ʜᴀɪ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴇɪɴ.", "ɴᴇᴇᴄʜᴇ ᴅɪ ɢᴀɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴍᴜᴋᴀᴍᴍᴀʟ ᴋᴀʀᴇɪɴ.", "ᴀɢʟɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴍᴜᴋᴀᴍᴍᴀʟ ᴋᴀʀᴇɪɴ.", "ᴀᴀᴋʜɪʀɪ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴍᴜᴋᴀᴍᴍᴀʟ ᴋᴀʀᴇɪɴ."),
    "as": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀɪʙʟᴇ ᴛʟᴏᴛ ᴅɪʏᴀ sᴛᴇᴘ-ᴛᴏ ᴘূʀɴ ᴋᴀʀᴋ.", "ᴇᴋᴛᴀ sᴛᴇᴘ ᴘᴜʀɴ ʜᴏʟ — ᴘᴏʀᴏʀᴛᴏ sᴛᴇᴘ-ᴛ ᴊᴀᴜᴋ.", "ᴇᴛᴏ ʜᴏʟ ᴍᴀᴛɪᴍ sᴛᴇᴘ — ғɪʟᴇ ᴜɴʟᴏᴄᴋ ᴋᴀʀᴋ.", "ᴛʟᴏᴛ ᴅɪʏᴀ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɴ ᴋᴀʀᴋ.", "ᴘᴏʀᴏʀᴛᴏ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɴ ᴋᴀʀᴋ.", "ᴍᴀᴛɪᴍ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀɴ ᴋᴀʀᴋ."),
    "ne": ("ғɪʟᴇ ʀᴇᴀᴅʏ", "sʜᴏʀᴛʟɪɴᴋ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ", "ғɪʟᴇ ᴜɴʟᴏᴄ ɢᴀʀɴ ᴛʟᴀʟ ᴅɪʏᴇᴋᴏ sᴛᴇᴘ ᴘᴜʀᴀ ɢᴀʀɴᴜʜᴏs.", "ᴇᴜᴛᴀ sᴛᴇᴘ ᴘᴜʀᴀ ʙʜᴀʏᴏ — ᴀʀᴋᴏ sᴛᴇᴘᴛɪʀᴀ ᴊᴀᴀɴᴜʜᴏs.", "ʏᴏ ᴀɴᴛɪᴍ sᴛᴇᴘ ʜᴏ — ғɪʟᴇ ᴜɴʟᴏᴄ ɢᴀʀɴᴜʜᴏs.", "ᴛʟᴀᴋᴏ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴀ ɢᴀʀɴᴜʜᴏs.", "ᴀʀᴋᴏ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴀ ɢᴀʀɴᴜʜᴏs.", "ᴀɴᴛɪᴍ ᴠᴇʀɪғɪᴋᴀᴛɪᴏɴ ᴘᴜʀᴀ ɢᴀʀɴᴜʜᴏs."),
}

# Build missing shortlink keys without changing any existing translation.
for _code, _parts in _SHORTLINK_LOCALIZED.items():
    _greeting, _title, _s1, _s2, _s3, _step1, _step2, _step3 = _parts
    VERIFY.setdefault(_code, {})
    VERIFY[_code].setdefault("short1", f"<b>👋 {{greeting}}, {{mention}}!</b>\n\n╭━━━━━━━━━━━━━━━━━━╮\n│ 🎬 <b>{_title}</b>\n╰━━━━━━━━━━━━━━━━━━╯\n\n📁 <b>{{name}}</b>\n📦 <b>sɪᴢᴇ:</b> {{size}}\n\n🔗 <b>{_s1}</b>\n\n╭──────────────────╮\n│ 🔐 <b>{_title}</b>\n│ 📊 <b>ᴘʀᴏɢʀᴇss:</b> 🟢 <b>1 / 3</b>\n╰──────────────────╯\n\n🔹 <b>sᴛᴇᴘ 1:</b> {_step1}</b>")
    VERIFY[_code].setdefault("short2", f"<b>👋 {{greeting}}, {{mention}}!</b>\n\n╭━━━━━━━━━━━━━━━━━━╮\n│ 🎬 <b>{_title}</b>\n╰──────────────────╯\n\n📁 <b>{{name}}</b>\n📦 <b>sɪᴢᴇ:</b> {{size}}\n\n🔗 <b>{_s2}</b>\n\n╭──────────────────╮\n│ 🔐 <b>{_title}</b>\n│ 📊 <b>ᴘʀᴏɢʀᴇss:</b> 🟡 <b>2 / 3</b>\n╰──────────────────╯\n\n🔹 <b>sᴛᴇᴘ 2:</b> {_step2}</b>")
    VERIFY[_code].setdefault("short3", f"<b>👋 {{greeting}}, {{mention}}!</b>\n\n╭━━━━━━━━━━━━━━━━━━╮\n│ 🎬 <b>{_title}</b>\n╰━━━━━━━━━━━━━━━━━━╯\n\n📁 <b>{{name}}</b>\n📦 <b>sɪᴢᴇ:</b> {{size}}\n\n🔗 <b>{_s3}</b>\n\n╭──────────────────╮\n│ 🔐 <b>{_title}</b>\n│ 📊 <b>ᴘʀᴏɢʀᴇss:</b> 🔴 <b>3 / 3</b>\n╰──────────────────╯\n\n🔹 <b>sᴛᴇᴘ 3:</b> {_step3}</b>")

for _c in LANGUAGES:
    VERIFY.setdefault(_c, {})
    # Never silently replace a supported language with English user-facing text.
    # Missing shortlink keys are handled by verify_tr with localized fallbacks.


def verify_tr(lang, key, **values):
    data = VERIFY.get(lang) or VERIFY[DEFAULT_LANGUAGE]
    text = data.get(key)
    if text is None:
        localized = {
            "hi": {"short1":"<b>🔐 Shortlink Verification • चरण 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nनीचे की verification पूरी करें।",
                   "short2":"<b>🔐 Shortlink Verification • चरण 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nअगली verification पूरी करें।",
                   "short3":"<b>🔐 Shortlink Verification • चरण 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nअंतिम verification पूरी करें।"},
            "kn": {"short1":"<b>🔐 Shortlink Verification • ಹಂತ 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nಕೆಳಗಿನ verification ಪೂರ್ಣಗೊಳಿಸಿ.",
                   "short2":"<b>🔐 Shortlink Verification • ಹಂತ 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nಮುಂದಿನ verification ಪೂರ್ಣಗೊಳಿಸಿ.",
                   "short3":"<b>🔐 Shortlink Verification • ಹಂತ 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nಕೊನೆಯ verification ಪೂರ್ಣಗೊಳಿಸಿ."},
            "ml": {"short1":"<b>🔐 Shortlink Verification • ഘട്ടം 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nതാഴെയുള്ള verification പൂർത്തിയാക്കുക.",
                   "short2":"<b>🔐 Shortlink Verification • ഘട്ടം 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nഅടുത്ത verification പൂർത്തിയാക്കുക.",
                   "short3":"<b>🔐 Shortlink Verification • ഘട്ടം 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nഅവസാന verification പൂർത്തിയാക്കുക."},
            "bn": {"short1":"<b>🔐 Shortlink Verification • ধাপ ১ / ৩</b>\n📁 {name}\n📦 Size: {size}\nনিচের verification সম্পূর্ণ করুন।",
                   "short2":"<b>🔐 Shortlink Verification • ধাপ ২ / ৩</b>\n📁 {name}\n📦 Size: {size}\nপরের verification সম্পূর্ণ করুন।",
                   "short3":"<b>🔐 Shortlink Verification • ধাপ ৩ / ৩</b>\n📁 {name}\n📦 Size: {size}\nশেষ verification সম্পূর্ণ করুন।"},
            "mr": {"short1":"<b>🔐 Shortlink Verification • टप्पा 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nखालील verification पूर्ण करा.",
                   "short2":"<b>🔐 Shortlink Verification • टप्पा 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nपुढील verification पूर्ण करा.",
                   "short3":"<b>🔐 Shortlink Verification • टप्पा 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nशेवटचे verification पूर्ण करा."},
            "gu": {"short1":"<b>🔐 Shortlink Verification • પગલું 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nનીચેનું verification પૂર્ણ કરો.",
                   "short2":"<b>🔐 Shortlink Verification • પગલું 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nઆગલું verification પૂર્ણ કરો.",
                   "short3":"<b>🔐 Shortlink Verification • પગલું 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nછેલ્લું verification પૂર્ણ કરો."},
            "pa": {"short1":"<b>🔐 Shortlink Verification • ਕਦਮ 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nਹੇਠਾਂ verification ਪੂਰੀ ਕਰੋ।",
                   "short2":"<b>🔐 Shortlink Verification • ਕਦਮ 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nਅਗਲੀ verification ਪੂਰੀ ਕਰੋ।",
                   "short3":"<b>🔐 Shortlink Verification • ਕਦਮ 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nਆਖਰੀ verification ਪੂਰੀ ਕਰੋ।"},
            "ur": {"short1":"<b>🔐 Shortlink Verification • مرحلہ 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nنیچے verification مکمل کریں۔",
                   "short2":"<b>🔐 Shortlink Verification • مرحلہ 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nاگلی verification مکمل کریں۔",
                   "short3":"<b>🔐 Shortlink Verification • مرحلہ 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nآخری verification مکمل کریں۔"},
            "as": {"short1":"<b>🔐 Shortlink Verification • ধাপ 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nতলৰ verification সম্পূৰ্ণ কৰক।",
                   "short2":"<b>🔐 Shortlink Verification • ধাপ 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nপৰৱৰ্তী verification সম্পূৰ্ণ কৰক।",
                   "short3":"<b>🔐 Shortlink Verification • ধাপ 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nশেষ verification সম্পূৰ্ণ কৰক।"},
            "ne": {"short1":"<b>🔐 Shortlink Verification • चरण 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nतलको verification पूरा गर्नुहोस्।",
                   "short2":"<b>🔐 Shortlink Verification • चरण 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nअर्को verification पूरा गर्नुहोस्।",
                   "short3":"<b>🔐 Shortlink Verification • चरण 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nअन्तिम verification पूरा गर्नुहोस्।"},
            "te": {"short1":"<b>🔐 Shortlink Verification • దశ 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nక్రింది verification పూర్తి చేయండి.",
                   "short2":"<b>🔐 Shortlink Verification • దశ 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nతదుపరి verification పూర్తి చేయండి.",
                   "short3":"<b>🔐 Shortlink Verification • దశ 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nచివరి verification పూర్తి చేయండి."},
            "ta": {"short1":"<b>🔐 Shortlink Verification • படி 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nகீழே உள்ள verification-ஐ முடிக்கவும்.",
                   "short2":"<b>🔐 Shortlink Verification • படி 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nஅடுத்த verification-ஐ முடிக்கவும்.",
                   "short3":"<b>🔐 Shortlink Verification • படி 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nஇறுதி verification-ஐ முடிக்கவும்."},
            "as": {"short1":"<b>🔐 Shortlink Verification • ধাপ 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nতলৰ verification সম্পূৰ্ণ কৰক.",
                   "short2":"<b>🔐 Shortlink Verification • ধাপ 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nপৰৱৰ্তী verification সম্পূৰ্ণ কৰক.",
                   "short3":"<b>🔐 Shortlink Verification • ধাপ 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nশেষ verification সম্পূৰ্ণ কৰক."},
            "hinglish": {"short1":"<b>🔐 Shortlink Verification • Step 1 / 3</b>\n📁 {name}\n📦 Size: {size}\nNeeche wali verification complete karo.",
                         "short2":"<b>🔐 Shortlink Verification • Step 2 / 3</b>\n📁 {name}\n📦 Size: {size}\nNext verification complete karo.",
                         "short3":"<b>🔐 Shortlink Verification • Step 3 / 3</b>\n📁 {name}\n📦 Size: {size}\nFinal verification complete karo."},
        }
        text = localized.get(lang, {}).get(key)
    if text is None:
        text = VERIFY.get("en", {}).get(key, key)
    try:
        return small_caps_html(text.format(**values))
    except Exception:
        return small_caps_html(text)
