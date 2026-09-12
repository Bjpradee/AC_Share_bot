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
            # Check if it's a batch link or single file link
            decoded_payload = decode_id(encoded_payload)
            
            if "-" in decoded_payload:
                # Batch link handling (e.g., start_id-end_id)
                start_str, end_str = decoded_payload.split("-")
                start_id, end_id = int(start_str), int(end_str)
                
                # Fetch and send files in range
                for file_db_id in range(start_id, end_id + 1):
                    file_data = await db.get_file(str(file_db_id))
                    if file_data:
                        await client.send_cached_media(
                            chat_id=message.chat.id,
                            file_id=file_data["file_id"],
                            caption=f"📁 **{file_data['file_name']}**\n\n📥 Downloaded via @Anime_Control_Tamil Store Bot"
                        )
                        await asyncio.sleep(0.8) # Prevent flood wait
            else:
                # Single file link handling
                file_data = await db.get_file(decoded_payload)
                if file_data:
                    await client.send_cached_media(
                        chat_id=message.chat.id,
                        file_id=file_data["file_id"],
                        caption=f"📁 **{file_data['file_name']}**\n\n📥 Downloaded via @Anime_Control_Tamil Store Bot"
                    )
                else:
                    await message.reply_text("❌ File not found or deleted from database!")
        except Exception as e:
            await message.reply_text("❌ Invalid link or expired batch!")
    else:
        await message.reply_text(
            "👋 Vanakkam da mapla!\n"
            "Enna use panni files-ah store pannikalam. Oru file-ah forward pannu, illana `/genlink` / `/batch` use pannu!"
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

# /batch command handler for multiple files
@app.on_message(filters.command("batch") & filters.private)
async def batch_handler(client: Client, message: Message):
    await message.reply_text(
        "⚡ **Batch Link Creator**\n\n"
        "Oru channel-la irunthu 2 messages-oda links-ah anuppu (First Post link & Last Post link) or use format: `first_id - last_id`"
    )

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
