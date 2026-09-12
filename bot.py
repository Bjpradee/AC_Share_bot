import asyncio
# Python 3.14 asyncio loop fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import logging
import base64
from pyrogram import Client, filters, idle
from pyrogram.types import Message, BotCommand
from config import API_ID, API_HASH, BOT_TOKEN
from database import db

logging.basicConfig(level=logging.INFO)

app = Client(
    "AnimeStoreBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def encode_id(string_id):
    return base64.urlsafe_b64encode(string_id.encode("ascii")).decode("ascii").strip("=")

def decode_id(encoded_string):
    encoded_string += "=" * (-len(encoded_string) % 4)
    return base64.urlsafe_b64decode(encoded_string.encode("ascii")).decode("ascii")

@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    if len(message.command) > 1:
        encoded_payload = message.command[1]
        try:
            file_db_id = decode_id(encoded_payload)
            file_data = await db.get_file(file_db_id)
            
            if file_data:
                await client.send_cached_media(
                    chat_id=message.chat.id,
                    file_id=file_data["file_id"],
                    caption=f"📁 **{file_data['file_name']}**\n\n📥 Downloaded via @Anime_Control_Tamil Store Bot"
                )
            else:
                await message.reply_text("❌ File not found or deleted from database!")
        except Exception as e:
            await message.reply_text("❌ Invalid link!")
    else:
        await message.reply_text(
            "👋 Vanakkam da mapla!\n"
            "Enna use panni files-ah store pannikalam. Oru file-ah forward pannu, illana `/genlink` use pannu!"
        )

# /genlink command handler
@app.on_message(filters.command("genlink") & filters.private)
async def genlink_handler(client: Client, message: Message):
    reply_message = message.reply_to_message
    if not reply_message:
        await message.reply_text("❌ Oru file-ah reply panni `/genlink` nu podu da mapla!")
        return
    
    media = reply_message.document or reply_message.video or reply_message.audio
    if not media:
        await message.reply_text("❌ Athu file/media illa da! Valid file-ah select panni reply pannu.")
        return
        
    file_id = media.file_id
    file_name = getattr(media, "file_name", "Unknown File")
    file_size = media.file_size
    
    inserted_id = await db.save_file(file_id, file_name, file_size)
    encoded_payload = encode_id(inserted_id)
    
    bot_username = (await client.get_me()).username
    share_link = f"https://t.me/{bot_username}?start={encoded_payload}"
    
    await message.reply_text(
        f"✅ **Link Generated Successfully!**\n\n"
        f"📁 **Name:** {file_name}\n"
        f"🔗 **Share Link:**\n`{share_link}`"
    )

# /batch command placeholder
@app.on_message(filters.command("batch") & filters.private)
async def batch_handler(client: Client, message: Message):
    await message.reply_text("⚙️ **Batch feature** inum konja nerathula complete-ah update panniralam da mapla!")

@app.on_message(filters.document | filters.video | filters.audio)
alias store_file(client: Client, message: Message):
    pass

@app.on_message(filters.document | filters.video | filters.audio)
async def store_file(client: Client, message: Message):
    media = message.document or message.video or message.audio
    if media:
        file_id = media.file_id
        file_name = getattr(media, "file_name", "Unknown File")
        file_size = media.file_size
        
        inserted_id = await db.save_file(file_id, file_name, file_size)
        encoded_payload = encode_id(inserted_id)
        
        bot_username = (await client.get_me()).username
        share_link = f"https://t.me/{bot_username}?start={encoded_payload}"
        
        await message.reply_text(
            f"✅ **File Saved Successfully!**\n\n"
            f"📁 **Name:** {file_name}\n"
            f"🔗 **Share Link:**\n`{share_link}`"
        )

async def main():
    await app.start()
    commands = [
        BotCommand("start", "Check i am alive"),
        BotCommand("genlink", "To store a single message or file"),
        BotCommand("batch", "To store multiple messages from a channel")
    ]
    await app.set_bot_commands(commands)
    print("🔥 Bot Commands Menu set successfully & Bot is running!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    print("🤖 Bot is starting cleanly...")
    asyncio.get_event_loop().run_until_complete(main())
