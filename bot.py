import asyncio
# Python 3.14 asyncio loop fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import logging
import base64
from pyrogram import Client, filters, idle
from pyrogram.types import Message, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from config import API_ID, API_HASH, BOT_TOKEN
from database import db

logging.basicConfig(level=logging.INFO)

app = Client(
    "AnimeStoreBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

USER_BATCH_STATE = {}
BOT_SETTINGS = {
    "auto_delete_time": 15 * 60  # Default 15 minutes
}

def encode_id(string_id):
    return base64.urlsafe_b64encode(string_id.encode("ascii")).decode("ascii").strip("=")

def decode_id(encoded_string):
    encoded_string += "=" * (-len(encoded_string) % 4)
    return base64.urlsafe_b64decode(encoded_string.encode("ascii")).decode("ascii")

def extract_message_id(message: Message):
    if message.forward_from_message_id:
        return message.forward_from_message_id
    return message.id

async def schedule_message_deletion(client: Client, chat_id: int, message_ids: list, delay_seconds: int):
    if delay_seconds <= 0:
        return
    await asyncio.sleep(delay_seconds)
    for msg_id in message_ids:
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=msg_id)
        except Exception as e:
            pass

@app.on_message(filters.command("start"))
async def start_handler(client: Client, message: Message):
    if len(message.command) > 1:
        encoded_payload = message.command[1]
        sent_messages = []
        try:
            decoded_payload = decode_id(encoded_payload)
            
            if "-" in decoded_payload:
                start_str, end_str = decoded_payload.split("-")
                start_id, end_id = int(start_str), int(end_str)
                
                wait_msg = await message.reply_text("⏳ **Please wait... Sending your batch files.**")
                sent_messages.append(wait_msg.id)
                
                files_sent_count = 0
                for file_db_id in range(start_id, end_id + 1):
                    file_data = await db.get_file(file_db_id)
                    if not file_data:
                        file_data = await db.get_file(str(file_db_id))
                        
                    if file_data:
                        files_sent_count += 1
                        keyboard = InlineKeyboardMarkup(
                            [[InlineKeyboardButton("📥 DOWNLOAD", callback_data=f"dl_{file_db_id}")]]
                        )
                        sent_msg = await client.send_cached_media(
                            chat_id=message.chat.id,
                            file_id=file_data["file_id"],
                            caption=f"📁 **{file_data['file_name']}**\n\n📥 Downloaded via @Anime_Control_Tamil Store Bot",
                            reply_markup=keyboard
                        )
                        sent_messages.append(sent_msg.id)
                        await asyncio.sleep(0.5)
                
                if files_sent_count == 0:
                    err_msg = await message.reply_text("❌ No files found in this batch range!")
                    sent_messages.append(err_msg.id)
                else:
                    mins_text = int(BOT_SETTINGS["auto_delete_time"] / 60)
                    if BOT_SETTINGS["auto_delete_time"] > 0:
                        warning_msg = await message.reply_text(f"⚠️ **Important:**\nAll messages will be deleted after {mins_text} minutes. Please save or forward these messages to your personal saved messages to avoid losing them!")
                        sent_messages.append(warning_msg.id)
            else:
                file_data = await db.get_file(decoded_payload)
                if not file_data:
                    try:
                        file_data = await db.get_file(int(decoded_payload))
                    except:
                        pass

                if file_data:
                    keyboard = InlineKeyboardMarkup(
                        [[InlineKeyboardButton("📥 DOWNLOAD", callback_data=f"dl_{decoded_payload}")]]
                    )
                    sent_msg = await client.send_cached_media(
                        chat_id=message.chat.id,
                        file_id=file_data["file_id"],
                        caption=f"📁 **{file_data['file_name']}**\n\n📥 Downloaded via @Anime_Control_Tamil Store Bot",
                        reply_markup=keyboard
                    )
                    sent_messages.append(sent_msg.id)
                else:
                    err_msg = await message.reply_text("❌ File not found or deleted from database!")
                    sent_messages.append(err_msg.id)
            
            if BOT_SETTINGS["auto_delete_time"] > 0 and sent_messages:
                asyncio.create_task(schedule_message_deletion(client, message.chat.id, sent_messages, BOT_SETTINGS["auto_delete_time"]))
                
        except Exception as e:
            logging.error(f"Error in start link handler: {e}")
            await message.reply_text("❌ Invalid link or expired batch!")
    else:
        await message.reply_text(
            "👋 Vanakkam da mapla!\n"
            "Enna use panni files-ah store pannikalam. Use `/genlink`, `/batch` or `/settings` from the menu!"
        )

@app.on_message(filters.command("settings") & filters.private)
async def settings_handler(client: Client, message: Message):
    current_mins = int(BOT_SETTINGS["auto_delete_time"] / 60) if BOT_SETTINGS["auto_delete_time"] > 0 else "Off"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("5 Mins", callback_data="set_time_300"),
            InlineKeyboardButton("15 Mins", callback_data="set_time_900"),
            InlineKeyboardButton("30 Mins", callback_data="set_time_1800")
        ],
        [
            InlineKeyboardButton("Turn Off", callback_data="set_time_0")
        ]
    ])
    await message.reply_text(
        f"⚙️ **Bot Settings**\n\n"
        f"⏱️ **Auto Delete Time:** {current_mins} minutes\n\n"
        f"Select a new time duration below:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex(r"^set_time_"))
async def set_time_callback(client: Client, callback_query: CallbackQuery):
    seconds = int(callback_query.data.split("_")[2])
    BOT_SETTINGS["auto_delete_time"] = seconds
    mins_text = int(seconds / 60) if seconds > 0 else "Disabled"
    
    await callback_query.message.edit_text(
        f"✅ **Settings Updated Successfully!**\n\n"
        f"⏱️ **New Auto Delete Time:** {mins_text}"
    )
    await callback_query.answer("Settings updated!", show_alert=False)

@app.on_callback_query(filters.regex(r"^dl_"))
async def download_callback(client: Client, callback_query: CallbackQuery):
    file_db_id = callback_query.data.split("_")[1]
    file_data = await db.get_file(file_db_id)
    if not file_data:
        try:
            file_data = await db.get_file(int(file_db_id))
        except:
            pass
            
    if file_data:
        sent_msg = await client.send_cached_media(
            chat_id=callback_query.message.chat.id,
            file_id=file_data["file_id"],
            caption=f"📁 **{file_data['file_name']}**\n\n📥 @Anime_Control_Tamil"
        )
        if BOT_SETTINGS["auto_delete_time"] > 0:
            asyncio.create_task(schedule_message_deletion(client, callback_query.message.chat.id, [sent_msg.id], BOT_SETTINGS["auto_delete_time"]))
        await callback_query.answer("Here is your file!", show_alert=False)
    else:
        await callback_query.answer("❌ File expired or missing!", show_alert=True)

# Direct file store handler (IGNORES if user is in batch/genlink interactive state)
@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def direct_file_store(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id in USER_BATCH_STATE:
        return  # Let batch/genlink interactive handler take care of it!

    media = message.document or message.video or message.audio
    if media:
        file_id = media.file_id
        file_name = getattr(media, "file_name", "Unknown File")
        file_size = media.file_size
        
        custom_id = message.forward_from_message_id if message.forward_from_message_id else None
        inserted_id = await db.save_file(file_id, file_name, file_size, custom_id=custom_id)
        encoded_payload = encode_id(str(inserted_id))
        bot_username = (await client.get_me()).username
        share_link = f"https://t.me/{bot_username}?start={encoded_payload}"
        
        await message.reply_text(
            f"Here is your link:\n`{share_link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 SHARE URL", url=f"https://t.me/share/url?url={share_link}")]])
        )

@app.on_message(filters.command("genlink") & filters.private)
async def genlink_prompt(client: Client, message: Message):
    USER_BATCH_STATE[message.from_user.id] = {"state": "waiting_genlink"}
    await message.reply_text("📤 **Send A Message/File For To Get Your Shareable Link**")

@app.on_message(filters.command("batch") & filters.private)
async def batch_prompt(client: Client, message: Message):
    USER_BATCH_STATE[message.from_user.id] = {"state": "waiting_batch_first"}
    await message.reply_text("Forward The Batch **First Message** From Your Batch Channel (With Forward Tag), or Give Me Batch First Message link from your batch channel")

@app.on_message(filters.private & ~filters.command(["start", "genlink", "batch", "settings", "broadcast"]))
async def handle_interactive_steps(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in USER_BATCH_STATE:
        return

    state_data = USER_BATCH_STATE[user_id]
    current_state = state_data.get("state")

    if current_state == "waiting_genlink":
        media = message.document or message.video or message.audio
        if not media:
            await message.reply_text("❌ Athu file illa da! Valid file-ah forward pannu.")
            return
        
        file_id = media.file_id
        file_name = getattr(media, "file_name", "Unknown File")
        file_size = media.file_size
        
        custom_id = message.forward_from_message_id if message.forward_from_message_id else None
        inserted_id = await db.save_file(file_id, file_name, file_size, custom_id=custom_id)
        encoded_payload = encode_id(str(inserted_id))
        bot_username = (await client.get_me()).username
        share_link = f"https://t.me/{bot_username}?start={encoded_payload}"
        
        del USER_BATCH_STATE[user_id]
        await message.reply_text(
            f"Here is your link:\n`{share_link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 SHARE URL", url=f"https://t.me/share/url?url={share_link}")]])
        )

    elif current_state == "waiting_batch_first":
        media = message.document or message.video or message.audio
        if media:
            file_id = media.file_id
            file_name = getattr(media, "file_name", "Unknown File")
            file_size = media.file_size
            custom_id = extract_message_id(message)
            await db.save_file(file_id, file_name, file_size, custom_id=custom_id)

        msg_id = extract_message_id(message)
        USER_BATCH_STATE[user_id]["first_id"] = msg_id
        USER_BATCH_STATE[user_id]["state"] = "waiting_batch_last"
        await message.reply_text("Forward The Batch **Last Message** From Your Batch Channel (With Forward Tag), or Give Me Batch last message link from your batch channel")

    elif current_state == "waiting_batch_last":
        media = message.document or message.video or message.audio
        if media:
            file_id = media.file_id
            file_name = getattr(media, "file_name", "Unknown File")
            file_size = media.file_size
            custom_id = extract_message_id(message)
            await db.save_file(file_id, file_name, file_size, custom_id=custom_id)

        first_id = state_data.get("first_id")
        last_id = extract_message_id(message)
        
        start_id = min(int(first_id), int(last_id))
        end_id = max(int(first_id), int(last_id))
        
        payload = f"{start_id}-{end_id}"
        encoded_payload = encode_id(payload)
        bot_username = (await client.get_me()).username
        batch_link = f"https://t.me/{bot_username}?start={encoded_payload}"
        
        del USER_BATCH_STATE[user_id]
        await message.reply_text(
            f"Here is your link:\n`{batch_link}`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 SHARE URL", url=f"https://t.me/share/url?url={batch_link}")]])
        )

async def main():
    await app.start()
    commands = [
        BotCommand("start", "Check i am alive"),
        BotCommand("genlink", "To store a single message or file"),
        BotCommand("batch", "To store multiple messages from a channel"),
        BotCommand("settings", "Customize your settings as your need")
    ]
    await app.set_bot_commands(commands)
    print("🔥 Bot Commands Menu set successfully & Bot is running!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    print("🤖 Bot is starting cleanly...")
    asyncio.get_event_loop().run_until_complete(main())
