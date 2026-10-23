from pyrogram import Client, filters
from pyrogram.enums import ChatType, ChatMemberStatus

OWNER_ID = 6250064764  # apni ID daalo

@Client.on_message(filters.command("getlinks") & filters.private & filters.user(OWNER_ID))
async def get_all_links(client, message):
    await message.reply("Groups dhund raha hu, thoda time lagega...")
    text = "Bot admin hai in groups me:\n\n"
    count = 0
    async for dialog in client.get_dialogs():
        chat = dialog.chat
        if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            try:
                member = await client.get_chat_member(chat.id, "me")
                if member.status == ChatMemberStatus.ADMINISTRATOR:
                    link = await client.export_chat_invite_link(chat.id)
                    text += f"• {chat.title}: {link}\n"
                    count += 1
            except Exception:
                continue
    if count == 0:
        text = "Koi group nahi mila jaha bot admin ho."
    await message.reply(text)
