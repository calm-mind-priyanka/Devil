import pytz
import datetime
from Script import script
from info import ADMINS, LOG_CHANNEL
from utils import get_seconds
from database.users_chats_db import db
from plugins.premium_payments import (
    _premium_flow_text, _user_language
)
from pyrogram import Client, filters
from pyrogram.errors.exceptions.bad_request_400 import MessageTooLong
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


@Client.on_message(filters.command("add_premium"))
async def give_premium_cmd_handler(client, message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        await message.reply("ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ.")
        return
    if len(message.command) == 3:
        user_id = int(message.command[1])  # Convert the user_id to integer
        user = await client.get_users(user_id)
        time = message.command[2]
        seconds = await get_seconds(time)
        if seconds > 0:
            expiry_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
            user_data = {"id": user_id, "expiry_time": expiry_time}
            await db.update_user(
                user_data
            )  # Use the update_user method to update or insert user data
            await message.reply_text(
                f"ᴘʀᴇᴍɪᴜᴍ ᴀᴅᴅᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ᴛᴏ ᴛʜᴇ ᴜꜱᴇʀꜱ.\n👤 ᴜꜱᴇʀ ɴᴀᴍᴇ : {user.mention}\n⚡ ᴜꜱᴇʀ ɪᴅ : {user.id}\n⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : {time}"
            )
            time_zone = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
            current_time = time_zone.strftime("%d-%m-%Y\n⏱️ ᴊᴏɪɴɪɴɢ ᴛɪᴍᴇ : %I:%M:%S %p")
            expiry = expiry_time
            expiry_str_in_ist = expiry.astimezone(
                pytz.timezone("Asia/Kolkata")
            ).strftime("%d-%m-%Y\n⏱️ ᴇxᴘɪʀʏ ᴛɪᴍᴇ : %I:%M:%S %p")
            await client.send_message(
                chat_id=user_id,
                text=f"ᴘʀᴇᴍɪᴜᴍ ᴀᴅᴅᴇᴅ ᴛᴏ ʏᴏᴜʀ ᴀᴄᴄᴏᴜɴᴛ ꜰᴏʀ {time} ᴇɴᴊᴏʏ 😀\n\n⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {current_time}\n\n⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expiry_str_in_ist}",
            )
            # user = await client.get_users(user_id)
            await client.send_message(
                LOG_CHANNEL,
                text=f"#Added_Premium\n\n👤 ᴜꜱᴇʀ : {user.mention}\n⚡ ᴜꜱᴇʀ ɪᴅ : {user.id}\n⏰ ᴘʀᴇᴍɪᴜᴍ ᴀᴄᴄᴇꜱꜱ : {time}\n\n⏳ ᴊᴏɪɴɪɴɢ ᴅᴀᴛᴇ : {current_time}\n\n⌛️ ᴇxᴘɪʀʏ ᴅᴀᴛᴇ : {expiry_str_in_ist}",
                disable_web_page_preview=True,
            )

        else:
            await message.reply_text(
                "Invalid time format. Please use '1day for days', '1hour for hours', or '1min for minutes', or '1month for months' or '1year for year'"
            )
    else:
        await message.reply_text(
            "Usage: /add_premium user_id time \n\nExample /add_premium 1252789 10day \n\n(e.g. for time units '1day for days', '1hour for hours', or '1min for minutes', or '1month for months' or '1year for year')"
        )


MYPLAN_I18N = {
"en": ("📝 <u>Your Premium Subscription Details</u> :", "👤 Username", "🏷️ User ID", "⏱️ Expiry Date", "⏱️ Expiry Time", "⏳ Remaining Time", "😔 You don't have any Premium subscription. If you want to buy Premium click the button below.", "To use our Premium features for 5 minutes click on Free Trial."),
"hi": ("📝 <u>आपकी Premium सदस्यता का विवरण</u> :", "👤 यूज़रनेम", "🏷️ यूज़र ID", "⏱️ समाप्ति तारीख", "⏱️ समाप्ति समय", "⏳ बाकी समय", "😔 आपके पास कोई Premium सदस्यता नहीं है। Premium खरीदने के लिए नीचे दिए बटन पर क्लिक करें।", "हमारी Premium सुविधाएँ 5 मिनट के लिए इस्तेमाल करने हेतु Free Trial बटन दबाएँ।"),
"ta": ("📝 <u>உங்கள் Premium சந்தா விவரங்கள்</u> :", "👤 பயனர் பெயர்", "🏷️ பயனர் ID", "⏱️ காலாவதி தேதி", "⏱️ காலாவதி நேரம்", "⏳ மீதமுள்ள நேரம்", "😔 உங்களிடம் Premium சந்தா இல்லை. Premium வாங்க கீழே உள்ள பொத்தானை அழுத்தவும்.", "Premium அம்சங்களை 5 நிமிடங்கள் பயன்படுத்த Free Trial பொத்தானை அழுத்தவும்."),
"te": ("📝 <u>మీ Premium సబ్‌స్క్రిప్షన్ వివరాలు</u> :", "👤 యూజర్ పేరు", "🏷️ యూజర్ ID", "⏱️ గడువు తేదీ", "⏱️ గడువు సమయం", "⏳ మిగిలిన సమయం", "😔 మీకు Premium సబ్‌స్క్రిప్షన్ లేదు. Premium కొనడానికి క్రింది బటన్‌ను నొక్కండి.", "మా Premium features ను 5 నిమిషాలు ఉపయోగించడానికి Free Trial బటన్‌ను నొక్కండి."),
"kn": ("📝 <u>ನಿಮ್ಮ Premium ಚಂದಾದಾರಿಕೆ ವಿವರಗಳು</u> :", "👤 ಬಳಕೆದಾರ ಹೆಸರು", "🏷️ ಬಳಕೆದಾರ ID", "⏱️ ಅವಧಿ ಮುಗಿಯುವ ದಿನಾಂಕ", "⏱️ ಅವಧಿ ಮುಗಿಯುವ ಸಮಯ", "⏳ ಉಳಿದ ಸಮಯ", "😔 ನಿಮ್ಮ ಬಳಿ Premium ಚಂದಾದಾರಿಕೆ ಇಲ್ಲ. Premium ಖರೀದಿಸಲು ಕೆಳಗಿನ ಬಟನ್ ಒತ್ತಿ.", "Premium ವೈಶಿಷ್ಟ್ಯಗಳನ್ನು 5 ನಿಮಿಷ ಬಳಸಲು Free Trial ಬಟನ್ ಒತ್ತಿ."),
"ml": ("📝 <u>നിങ്ങളുടെ Premium സബ്സ്ക്രിപ്ഷൻ വിശദാംശങ്ങൾ</u> :", "👤 ഉപയോക്തൃ പേര്", "🏷️ ഉപയോക്തൃ ID", "⏱️ കാലാവധി തീയതി", "⏱️ കാലാവധി സമയം", "⏳ ശേഷിക്കുന്ന സമയം", "😔 നിങ്ങൾക്ക് Premium സബ്സ്ക്രിപ്ഷൻ ഇല്ല. Premium വാങ്ങാൻ താഴെയുള്ള ബട്ടൺ അമർത്തുക.", "Premium സവിശേഷതകൾ 5 മിനിറ്റ് ഉപയോഗിക്കാൻ Free Trial ബട്ടൺ അമർത്തുക."),
"bn": ("📝 <u>আপনার Premium সাবস্ক্রিপশনের বিবরণ</u> :", "👤 ইউজারনেম", "🏷️ ইউজার ID", "⏱️ মেয়াদ শেষের তারিখ", "⏱️ মেয়াদ শেষের সময়", "⏳ বাকি সময়", "😔 আপনার কোনো Premium সাবস্ক্রিপশন নেই। Premium কিনতে নিচের বোতামে ক্লিক করুন।", "আমাদের Premium ফিচার ৫ মিনিট ব্যবহার করতে Free Trial বোতামে ক্লিক করুন।"),
"mr": ("📝 <u>तुमच्या Premium सदस्यत्वाचे तपशील</u> :", "👤 यूजरनेम", "🏷️ यूजर ID", "⏱️ समाप्ती तारीख", "⏱️ समाप्ती वेळ", "⏳ उरलेला वेळ", "😔 तुमच्याकडे Premium सदस्यत्व नाही. Premium खरेदी करण्यासाठी खालील बटण दाबा.", "Premium फीचर्स 5 मिनिटे वापरण्यासाठी Free Trial बटण दाबा."),
"gu": ("📝 <u>તમારા Premium સબ્સ્ક્રિપ્શનની વિગતો</u> :", "👤 યુઝરનેમ", "🏷️ યુઝર ID", "⏱️ સમાપ્તિ તારીખ", "⏱️ સમાપ્તિ સમય", "⏳ બાકી સમય", "😔 તમારી પાસે Premium સબ્સ્ક્રિપ્શન નથી. Premium ખરીદવા નીચેનું બટન દબાવો.", "Premium features 5 મિનિટ માટે વાપરવા Free Trial બટન દબાવો."),
"pa": ("📝 <u>ਤੁਹਾਡੀ Premium ਸਬਸਕ੍ਰਿਪਸ਼ਨ ਦੀ ਜਾਣਕਾਰੀ</u> :", "👤 ਯੂਜ਼ਰਨੇਮ", "🏷️ ਯੂਜ਼ਰ ID", "⏱️ ਮਿਆਦ ਖਤਮ ਹੋਣ ਦੀ ਤਾਰੀਖ", "⏱️ ਮਿਆਦ ਖਤਮ ਹੋਣ ਦਾ ਸਮਾਂ", "⏳ ਬਾਕੀ ਸਮਾਂ", "😔 ਤੁਹਾਡੇ ਕੋਲ Premium ਸਬਸਕ੍ਰਿਪਸ਼ਨ ਨਹੀਂ ਹੈ। Premium ਖਰੀਦਣ ਲਈ ਹੇਠਾਂ ਦਿੱਤਾ ਬਟਨ ਦਬਾਓ।", "Premium features 5 ਮਿੰਟ ਲਈ ਵਰਤਣ ਵਾਸਤੇ Free Trial ਬਟਨ ਦਬਾਓ."),
"ur": ("📝 <u>آپ کی Premium سبسکرپشن کی تفصیلات</u> :", "👤 صارف نام", "🏷️ صارف ID", "⏱️ میعاد ختم ہونے کی تاریخ", "⏱️ میعاد ختم ہونے کا وقت", "⏳ باقی وقت", "😔 آپ کے پاس Premium سبسکرپشن نہیں ہے۔ Premium خریدنے کے لیے نیچے بٹن دبائیں۔", "Premium features پانچ منٹ استعمال کرنے کے لیے Free Trial بٹن دبائیں۔"),
"as": ("📝 <u>আপোনাৰ Premium Subscription-ৰ বিৱৰণ</u> :", "👤 ব্যৱহাৰকাৰীৰ নাম", "🏷️ ব্যৱহাৰকাৰী ID", "⏱️ ম্যাদ শেষৰ তাৰিখ", "⏱️ ম্যাদ শেষৰ সময়", "⏳ বাকী সময়", "😔 আপোনাৰ কোনো Premium subscription নাই। Premium ক্ৰয় কৰিবলৈ তলৰ বুটামটো টিপক।", "আমাৰ Premium features ৫ মিনিট ব্যৱহাৰ কৰিবলৈ Free Trial বুটামটো টিপক।"),
"ne": ("📝 <u>तपाईंको Premium सदस्यताको विवरण</u> :", "👤 प्रयोगकर्ता नाम", "🏷️ प्रयोगकर्ता ID", "⏱️ म्याद सकिने मिति", "⏱️ म्याद सकिने समय", "⏳ बाँकी समय", "😔 तपाईंसँग Premium सदस्यता छैन। Premium किन्न तलको बटन थिच्नुहोस्।", "Premium features ५ मिनेट प्रयोग गर्न Free Trial बटन थिच्नुहोस्।"),
"hinglish": ("📝 <u>Aapki Premium Subscription Details</u> :", "👤 Username", "🏷️ User ID", "⏱️ Expiry Date", "⏱️ Expiry Time", "⏳ Remaining Time", "😔 Aapke paas Premium subscription nahi hai. Premium kharidne ke liye neeche button dabao.", "Hamare Premium features 5 minutes use karne ke liye Free Trial button dabao."),
}

def _myplan_text(lang, idx):
    return MYPLAN_I18N.get(lang, MYPLAN_I18N["en"])[idx]


@Client.on_message(filters.command("myplan"))
async def check_plans_cmd(client, message):
    user = message.from_user.mention
    user_id = message.from_user.id
    if await db.has_premium_access(user_id):
        remaining_time = await db.check_remaining_uasge(user_id)
        days = remaining_time.days
        hours, remainder = divmod(remaining_time.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        formatted_remaining_time = (
            f"{days} ᴅᴀʏꜱ, {hours} ʜᴏᴜʀꜱ, {minutes} ᴍɪɴᴜᴛᴇꜱ, {seconds} ꜱᴇᴄᴏɴᴅꜱ"
        )
        expiry_time = remaining_time + datetime.datetime.now()
        expiry_date = expiry_time.astimezone(pytz.timezone("Asia/Kolkata")).strftime(
            "%d-%m-%Y"
        )
        expiry_time = expiry_time.astimezone(pytz.timezone("Asia/Kolkata")).strftime(
            "%I:%M:%S %p"
        )  # Format time in IST (12-hour format)
        lang = await _user_language(user_id, message.from_user)
        await message.reply_text(
            f"{_myplan_text(lang, 0)}\n\n{_myplan_text(lang, 1)} : {user}\n{_myplan_text(lang, 2)} : <code>{user_id}</code>\n{_myplan_text(lang, 3)} : {expiry_date}\n{_myplan_text(lang, 4)} : {expiry_time}\n{_myplan_text(lang, 5)} : {formatted_remaining_time}"
        )
    else:
        btn = [
            [
                InlineKeyboardButton(
                    "ɢᴇᴛ ꜰʀᴇᴇ ᴛʀᴀɪʟ ꜰᴏʀ 𝟻 ᴍɪɴᴜᴛᴇꜱ ☺️", callback_data="give_trial"
                )
            ],
            [
                InlineKeyboardButton(
                    "ʙᴜʏ sᴜʙsᴄʀɪᴘᴛɪᴏɴ : ʀᴇᴍᴏᴠᴇ ᴀᴅs", callback_data="seeplans"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(btn)
        lang = await _user_language(user_id, message.from_user)
        await message.reply_text(
            _myplan_text(lang, 6) + "\n\n" + _myplan_text(lang, 7),
            reply_markup=reply_markup,
        )


@Client.on_message(filters.command("remove_premium"))
async def remove_premium(client, message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        await message.reply_text("ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ.")
        return
    if len(message.command) == 2:
        user_id = int(message.command[1])  # Convert the user_id to integer
        user = await client.get_users(user_id)
        if await db.remove_premium_access(user_id):
            await message.reply_text("ᴜꜱᴇʀ ʀᴇᴍᴏᴠᴇᴅ ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ !")
            await client.send_message(
                chat_id=user_id,
                text=f"<b>ʜᴇʏ {user.mention},\n\nʏᴏᴜʀ ᴘʀᴇᴍɪᴜᴍ ᴘʟᴀɴ ʜᴀꜱ ʙᴇᴇɴ ᴇxᴘɪʀᴇᴅ.\n\nɪꜰ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ʙᴜʏ ᴘʀᴇᴍɪᴜᴍ ᴀɢᴀɪɴ ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴏɴ /plan ᴛᴏ ᴄʜᴇᴄᴋ ᴏᴜᴛ ᴏᴛʜᴇʀ ᴘʟᴀɴꜱ.</b>",
            )
        else:
            await message.reply_text(
                "ᴜɴᴀʙʟᴇ ᴛᴏ ʀᴇᴍᴏᴠᴇ ᴜꜱᴇʀ !\nᴀʀᴇ ʏᴏᴜ ꜱᴜʀᴇ, ɪᴛ ᴡᴀꜱ ᴀ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀ ɪᴅ ?"
            )
    else:
        await message.reply_text("ᴜꜱᴀɢᴇ : /remove_premium user_id")


@Client.on_message(filters.command("premium_users"))
async def premium_users_info(client, message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        await message.reply("ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ.")
        return

    count = await db.all_premium_users()
    await message.reply(
        f"👥 ᴛᴏᴛᴀʟ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ - {count}\n\n<i>ᴘʟᴇᴀꜱᴇ ᴡᴀɪᴛ, ꜰᴇᴛᴄʜɪɴɢ ꜰᴜʟʟ ɪɴꜰᴏ ᴏꜰ ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ</i>"
    )

    users = await db.get_all_users()
    new = "📝 <u>ᴘʀᴇᴍɪᴜᴍ ᴜꜱᴇʀꜱ ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ</u> :\n\n"
    user_count = 1
    async for user in users:
        data = await db.get_user(user["id"])
        if data and data.get("expiry_time"):
            expiry = data.get("expiry_time")
            expiry_ist = expiry.astimezone(pytz.timezone("Asia/Kolkata"))
            current_time = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))

            if current_time > expiry_ist:
                await db.remove_premium_access(
                    user["id"]
                )  # Remove premium access if expired
                continue  # Skip the user if their expiry time has passed

            expiry_str_in_ist = expiry_ist.strftime("%d-%m-%Y")
            expiry_time_in_ist = expiry_ist.strftime("%I:%M:%S %p")
            time_left = expiry_ist - current_time

            days = time_left.days
            hours, remainder = divmod(time_left.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            time_left_str = (
                f"{days} ᴅᴀʏꜱ, {hours} ʜᴏᴜʀꜱ, {minutes} ᴍɪɴᴜᴛᴇꜱ, {seconds} ꜱᴇᴄᴏɴᴅꜱ"
            )

            new += f"{user_count}. {(await client.get_users(user['id'])).mention}\n👤 ᴜꜱᴇʀ ɪᴅ : <code>{user['id']}</code>\n⏱️ ᴇxᴘɪʀᴇᴅ ᴅᴀᴛᴇ : {expiry_str_in_ist}\n⏱️ ᴇxᴘɪʀᴇᴅ ᴛɪᴍᴇ : {expiry_time_in_ist}\n⏳ ʀᴇᴍᴀɪɴɪɴɢ ᴛɪᴍᴇ : {time_left_str}\n\n"
            user_count += 1
        else:
            pass

    try:
        await message.reply(new)
    except MessageTooLong:
        with open("premium_users_info.txt", "w+") as outfile:
            outfile.write(new)
        await message.reply_document(
            "premium_users_info.txt", caption="Premium Users Information:"
        )


# Free Trail Remove ( Give Credit To - NBBotz )
@Client.on_message(filters.command("refresh"))
async def reset_trial(client, message):
    user_id = message.from_user.id
    if user_id not in ADMINS:
        await message.reply("ʏᴏᴜ ᴅᴏɴ'ᴛ ʜᴀᴠᴇ ᴀɴʏ ᴘᴇʀᴍɪꜱꜱɪᴏɴ ᴛᴏ ᴜꜱᴇ ᴛʜɪꜱ ᴄᴏᴍᴍᴀɴᴅ.")
        return

    try:
        if len(message.command) > 1:
            target_user_id = int(message.command[1])
            updated_count = await db.reset_free_trial(target_user_id)
            message_text = (
                f"ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ʀᴇꜱᴇᴛ ꜰʀᴇᴇ ᴛʀᴀɪʟ ꜰᴏʀ ᴜꜱᴇʀꜱ {target_user_id}."
                if updated_count
                else f"ᴜꜱᴇʀ {target_user_id} ɴᴏᴛ ꜰᴏᴜɴᴅ ᴏʀ ᴅᴏɴ'ᴛ ᴄʟᴀɪᴍ ꜰʀᴇᴇ ᴛʀᴀɪʟ ʏᴇᴛ."
            )
        else:
            updated_count = await db.reset_free_trial()
            message_text = f"ꜱᴜᴄᴄᴇꜱꜱꜰᴜʟʟʏ ʀᴇꜱᴇᴛ ꜰʀᴇᴇ ᴛʀᴀɪʟ ꜰᴏʀ {updated_count} ᴜꜱᴇʀꜱ."

        await message.reply_text(message_text)
    except Exception as e:
        await message.reply_text(f"An error occurred: {e}")


@Client.on_message(filters.command("plan"))
async def plan(client, message):
    user_id = message.from_user.id
    # Premium uses the SAME global language selected from /start/Home.
    # There is intentionally no Premium-specific language button or picker.
    lang = await _user_language(user_id, message.from_user)
    btn = [
        [InlineKeyboardButton(_premium_flow_text(lang, "continue"), callback_data="free")],
        [InlineKeyboardButton(_premium_flow_text(lang, "close"), callback_data="close_data")],
    ]
    caption = _premium_flow_text(lang, "intro", mention=message.from_user.mention)

    await message.reply_photo(
        photo="https://graph.org/file/55a5392f88ec5a4bd3379.jpg",
        caption=caption,
        reply_markup=InlineKeyboardMarkup(btn),
    )
