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
from pyrogram.errors import UserNotParticipant
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
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

# Robust Force Sub Checker supporting both Public Usernames and Private Invite Links / IDs
async def check_force_sub(client: Client, user_id: int):
    channels = await db.get_fsub_channels()
    if not channels:
        return True
        
    buttons = []
    for channel in channels:
        channel = channel.strip()
        try:
            chat_id = channel
            if channel.startswith("https://t.me/+"):
                chat = await client.get_chat(channel)
                chat_id = chat.id
                invite_link = channel
            elif channel.startswith("@") or not channel.startswith("-"):
                chat = await client.get_chat(channel)
                chat_id = chat.id
                invite_link = chat.invite_link or f"https://t.me/{channel.replace('@', '')}"
            else:
                chat = await client.get_chat(int(channel))
                chat_id = chat.id
                invite_link = chat.invite_link or f"https://t.me/{chat.username}" if chat.username else None

            member = await client.get_chat_member(chat_id, user_id)
            if member.status in ["left", "kicked"]:
                if invite_link:
                    buttons.append([InlineKeyboardButton(f"📢 Join {chat.title}", url=invite_link)])
        except UserNotParticipant:
            try:
                chat = await client.get_chat(chat_id)
                invite_link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else channel)
                if invite_link.startswith("http"):
                    buttons.append([InlineKeyboardButton(f"📢 Join {chat.title}", url=invite_link)])
            except Exception:
                pass
        except Exception as e:
            logging.error(f"FSub check error for {channel}: {e}")
            pass
            
    if buttons:
        buttons.append([InlineKeyboardButton("🔄 Try Again", callback_data="check_fs")])
        return InlineKeyboardMarkup(buttons)
    return True

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    await db.add_user(user_id)
    
    # OWNER CAN ALWAYS BYPASS FORCE SUB TO TEST OR NAVIGATE
    if user_id != OWNER_ID:
        fs_check = await check_force_sub(client, user_id)
        if fs_check is not True:
            await message.reply_text(
                "🔒 **Access Denied!**\n\n"
                "You must join our channels below to use this bot and access files. After joining, click **'🔄 Try Again'**.",
                reply_markup=fs_check
            )
            return

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
                        # Send file cleanly WITHOUT any forced extra download buttons
                        sent_msg = await client.send_cached_media(
                            chat_id=message.chat.id,
                            file_id=file_data["file_id"]
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
                    sent_msg = await client.send_cached_media(
                        chat_id=message.chat.id,
                        file_id=file_data["file_id"]
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
        if user_id == OWNER_ID:
            await message.reply_text(
                "👋 Vanakkam da mapla!\n"
                "Use `/genlink`, `/batch`, `/addfsub`, `/remfsub`, `/fsublist`, or `/stats`."
            )
        else:
            await message.reply_text(
                "👋 Welcome! Send or click file links provided by our channel to access content."
            )

@app.on_callback_query(filters.regex(r"^check_fs$"))
async def check_fs_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    fs_check = await check_force_sub(client, user_id)
    if fs_check is True:
        await callback_query.message.delete()
        await callback_query.message.reply_text("✅ Thank you for joining! Now you can access your files. Click your file link again.")
    else:
        await callback_query.answer("❌ You haven't joined all required channels yet!", show_alert=True)

@app.on_message(filters.command("settings") & filters.private)
async def settings_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
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
    if callback_query.from_user.id != OWNER_ID:
        return
    seconds = int(callback_query.data.split("_")[2])
    BOT_SETTINGS["auto_delete_time"] = seconds
    mins_text = int(seconds / 60) if seconds > 0 else "Disabled"
    
    await callback_query.message.edit_text(
        f"✅ **Settings Updated Successfully!**\n\n"
        f"⏱️ **New Auto Delete Time:** {mins_text}"
    )
    await callback_query.answer("Settings updated!", show_alert=False)

# Admin Commands
@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    count = await db.total_users_count()
    channels = await db.get_fsub_channels()
    await message.reply_text(f"📊 **Bot Statistics**\n\n👥 Total Users: `{count}`\n📢 Active FSub Channels: `{len(channels)}`")

@app.on_message(filters.command("addfsub") & filters.private)
async def add_fsub_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if len(message.command) < 2:
        await message.reply_text("❌ Usage:\n• `/addfsub @channelname`\n• `/addfsub https://t.me/+invite_hash`")
        return
    
    new_channel = message.text.split(None, 1)[1].strip()
    channels = await db.get_fsub_channels()
    if len(channels) >= 4:
        await message.reply_text("❌ Maximum 4 Force Sub channels are allowed!")
        return
    if new_channel in channels:
        await message.reply_text("⚠️ This channel is already in Force Sub list!")
        return
        
    channels.append(new_channel)
    await db.set_fsub_channels(channels)
    await message.reply_text(f"✅ Successfully added `{new_channel}` to Force Sub channels!")

@app.on_message(filters.command("remfsub") & filters.private)
async def rem_fsub_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if len(message.command) < 2:
        await message.reply_text("❌ Usage: `/remfsub @channelname` or invite link")
        return
        
    target = message.text.split(None, 1)[1].strip()
    channels = await db.get_fsub_channels()
    if target in channels:
        channels.remove(target)
        await db.set_fsub_channels(channels)
        await message.reply_text(f"✅ Removed `{target}` from Force Sub list!")
    else:
        await message.reply_text("❌ Channel/Link not found in Force Sub list!")

@app.on_message(filters.command("fsublist") & filters.private)
async def fsub_list_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    channels = await db.get_fsub_channels()
    if not channels:
        await message.reply_text("📂 Force Sub is currently disabled (No channels added).")
        return
    
    text = "📢 **Current Force Sub Channels:**\n\n"
    for idx, ch in enumerate(channels, 1):
        text += f"{idx}. `{ch}`\n"
    await message.reply_text(text)

@app.on_message(filters.command("broadcast") & filters.private)
async def broadcast_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    reply = message.reply_to_message
    if not reply:
        await message.reply_text("❌ Oru message-ah reply panni `/broadcast` nu podu da mapla!")
        return
        
    sent = 0
    users = await db.get_all_users()
    async for user in users:
        try:
            await reply.copy(chat_id=user["user_id"])
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.reply_text(f"✅ Broadcast completed successfully to `{sent}` users!")

@app.on_message(filters.command("genlink") & filters.private)
async def genlink_prompt(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    USER_BATCH_STATE[message.from_user.id] = {"state": "waiting_genlink"}
    await message.reply_text("📤 **Send Any Message (Video, Photo, Text with buttons, etc.) To Get Your Shareable Link**")

@app.on_message(filters.command("batch") & filters.private)
async def batch_prompt(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    USER_BATCH_STATE[message.from_user.id] = {"state": "waiting_batch_first"}
    await message.reply_text("Forward The Batch **First Message** From Your Batch Channel (With Forward Tag), or Give Me Batch First Message link from your batch channel")

# Unified Media & General Message Handler (Supports Videos, Photos, Documents, Audio, Text with Buttons)
@app.on_message(filters.private & ~filters.command(["addfsub", "remfsub", "fsublist", "genlink", "batch", "settings", "stats", "start", "broadcast"]))
async def unified_media_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    # ONLY OWNER CAN CREATE LINKS / STORE FILES
    if user_id != OWNER_ID:
        return

    await db.add_user(user_id)
    
    if user_id in USER_BATCH_STATE:
        state_data = USER_BATCH_STATE[user_id]
        current_state = state_data.get("state")

        if current_state == "waiting_genlink":
            custom_id = extract_message_id(message)
            # Store the entire message object reference in database by saving message ID or copying message
            # For robust multi-type support, we copy/store message details
            inserted_id = await db.save_file(
                file_id=message.id, # storing message ID from owner chat or channel
                file_name=getattr(message.document or message.video or message.audio, "file_name", "Media Message"),
                file_size=getattr(message.document or message.video or message.audio, "file_size", 0),
                custom_id=custom_id
            )
            encoded_payload = encode_id(str(inserted_id))
            bot_username = (await client.get_me()).username
            share_link = f"https://t.me/{bot_username}?start={encoded_payload}"
            
            del USER_BATCH_STATE[user_id]
            await message.reply_text(
                f"Here is your link:\n`{share_link}`",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 SHARE URL", url=f"https://t.me/share/url?url={share_link}")]])
            )
            return

        elif current_state == "waiting_batch_first":
            custom_id = extract_message_id(message)
            await db.save_file(
                file_id=message.id,
                file_name="Batch First",
                file_size=0,
                custom_id=custom_id
            )

            msg_id = extract_message_id(message)
            USER_BATCH_STATE[user_id]["first_id"] = msg_id
            USER_BATCH_STATE[user_id]["state"] = "waiting_batch_last"
            await message.reply_text("Forward The Batch **Last Message** From Your Batch Channel (With Forward Tag), or Give Me Batch last message link from your batch channel")
            return

        elif current_state == "waiting_batch_last":
            custom_id = extract_message_id(message)
            await db.save_file(
                file_id=message.id,
                file_name="Batch Last",
                file_size=0,
                custom_id=custom_id
            )

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
            return
            
        return

    # Direct single file store for owner when not in interactive state
    custom_id = extract_message_id(message)
    inserted_id = await db.save_file(
        file_id=message.id,
        file_name="Direct Media",
        file_size=0,
        custom_id=custom_id
    )
    encoded_payload = encode_id(str(inserted_id))
    bot_username = (await client.get_me()).username
    share_link = f"https://t.me/{bot_username}?start={encoded_payload}"
    
    await message.reply_text(
        f"Here is your link:\n`{share_link}`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 SHARE URL", url=f"https://t.me/share/url?url={share_link}")]])
    )

# Override start_handler file sender to support copying ANY message type (Photos, Videos, Text with buttons)
async def send_stored_item(client, chat_id, file_db_id):
    try:
        # We copy the exact message sent by the owner from the owner's chat or source
        # Since owner forwards or sends messages in chat, we can copy message directly using message id
        sent_msg = await client.copy_message(
            chat_id=chat_id,
            from_chat_id=OWNER_ID,
            message_id=int(file_db_id)
        )
        return sent_msg
    except Exception as e:
        logging.error(f"Error copying message {file_db_id}: {e}")
        return None

# Update start_handler logic to use send_stored_item for robust multi-format support
@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    await db.add_user(user_id)
    
    if user_id != OWNER_ID:
        fs_check = await check_force_sub(client, user_id)
        if fs_check is not True:
            await message.reply_text(
                "🔒 **Access Denied!**\n\n"
                "You must join our channels below to use this bot and access files. After joining, click **'🔄 Try Again'**.",
                reply_markup=fs_check
            )
            return

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
                        sent_msg = await send_stored_item(client, message.chat.id, file_data["_id"])
                        if sent_msg:
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
                    sent_msg = await send_stored_item(client, message.chat.id, file_data["_id"])
                    if sent_msg:
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
        if user_id == OWNER_ID:
            await message.reply_text(
                "👋 Vanakkam da mapla!\n"
                "Use `/genlink`, `/batch`, `/addfsub`, `/remfsub`, `/fsublist`, or `/stats`."
            )
        else:
            await message.reply_text(
                "👋 Welcome! Send or click file links provided by our channel to access content."
            )

async def main():
    await app.start()
    commands = [
        BotCommand("start", "Check i am alive"),
        BotCommand("genlink", "To store a single message or file"),
        BotCommand("batch", "To store multiple messages from a channel"),
        BotCommand("settings", "Customize your settings as your need"),
        BotCommand("stats", "View bot statistics"),
        BotCommand("addfsub", "Add channel to force sub"),
        BotCommand("remfsub", "Remove channel from force sub"),
        BotCommand("fsublist", "View active force sub channels")
    ]
    await app.set_bot_commands(commands)
    print("🔥 Bot Commands Menu set successfully & Bot is running!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    print("🤖 Bot is starting cleanlyy...")
    asyncio.get_event_loop().run_until_complete(main())
