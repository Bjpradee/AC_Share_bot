import asyncio
# Python 3.14 asyncio loop fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

import logging
import base64
from pyrogram import Client, filters, idle
from pyrogram.enums import ChatMemberStatus
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

def encode_id(string_id):
    return base64.urlsafe_b64encode(string_id.encode("ascii")).decode("ascii").strip("=")

def decode_id(encoded_string):
    encoded_string += "=" * (-len(encoded_string) % 4)
    return base64.urlsafe_b64decode(encoded_string.encode("ascii")).decode("ascii")

# MongoDB Auto-Delete Settings Manager
async def get_auto_delete_time():
    settings = await db.settings_col.find_one({"_id": "bot_settings"})
    if settings and "auto_delete_time" in settings:
        return settings["auto_delete_time"]
    return 5 * 60  # Default 5 minutes

async def set_auto_delete_time(seconds: int):
    await db.settings_col.update_one(
        {"_id": "bot_settings"},
        {"$set": {"auto_delete_time": seconds}},
        upsert=True
    )

async def schedule_message_deletion(client: Client, chat_id: int, message_ids: list, delay_seconds: int):
    if delay_seconds <= 0:
        return
    await asyncio.sleep(delay_seconds)
    for msg_id in message_ids:
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=msg_id)
        except Exception:
            pass

# 100% Crash-Proof & Flawless Force Sub Checker
async def check_force_sub(client: Client, user_id: int):
    channels = await db.get_fsub_channels()
    if not channels:
        return True
        
    buttons = []
    is_participant = True
    
    for channel_id in channels:
        try:
            channel_id = channel_id.strip()
            chat_id = int(channel_id) if channel_id.lstrip('-').isdigit() else channel_id
                
            # Safely fetch channel info
            try:
                chat = await client.get_chat(chat_id)
                link = chat.invite_link or (f"https://t.me/{chat.username}" if chat.username else None)
                if not link:
                    link = await client.export_chat_invite_link(chat_id)
                title = chat.title or "Channel"
            except Exception as e:
                logging.error(f"Cannot access channel {chat_id}: {e}")
                link = "https://t.me/telegram"
                title = "Unknown Channel"
                
            # SAFE Membership Check (Strict ENUM matching for accuracy)
            user_joined = False
            try:
                member = await client.get_chat_member(chat_id, user_id)
                if member.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
                    user_joined = True
            except UserNotParticipant:
                user_joined = False
            except Exception as e:
                logging.error(f"FSub member check error for {channel_id}: {e}")
                user_joined = False
                
            if not user_joined:
                is_participant = False
                buttons.append([InlineKeyboardButton(f"📢 Join {title}", url=link)])
                
        except Exception as e:
            logging.error(f"FSub loop error: {e}")
            
    if not is_participant:
        buttons.append([InlineKeyboardButton("🔄 Try Again", callback_data="check_fs")])
        return InlineKeyboardMarkup(buttons)
        
    return True

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    user_id = message.from_user.id
    await db.add_user(user_id)
    
    if len(message.command) > 1:
        # OWNER BYPASS: Owner shouldn't be asked to join channels!
        if user_id != OWNER_ID:
            try:
                fs_check = await check_force_sub(client, user_id)
                if fs_check is not True:
                    await message.reply_text(
                        "🔒 **Access Denied!**\n\n"
                        "You must join our channels below to use this bot and access files. After joining, click **'🔄 Try Again'**.",
                        reply_markup=fs_check
                    )
                    return
            except Exception as e:
                logging.error(f"FSub check failed: {e}")
                await message.reply_text("❌ Connection error during channel verification. Please try again.")
                return

        encoded_payload = message.command[1]
        sent_messages = []
        auto_del_time = await get_auto_delete_time()
        
        try:
            decoded_payload = decode_id(encoded_payload)
            
            # --- BATCH FILES LOGIC ---
            if decoded_payload.startswith("batch_"):
                parts = decoded_payload.split("_")
                if len(parts) != 4:
                    raise ValueError("Invalid batch payload")
                    
                src_chat_id = int(parts[1])
                start_id = int(parts[2])
                end_id = int(parts[3])
                
                wait_msg = await message.reply_text("⏳ **Please wait... Sending your batch files.**")
                sent_messages.append(wait_msg.id)
                
                files_sent_count = 0
                for msg_id in range(start_id, end_id + 1):
                    try:
                        sent_msg = await client.copy_message(
                            chat_id=message.chat.id,
                            from_chat_id=src_chat_id,
                            message_id=msg_id,
                            reply_markup=InlineKeyboardMarkup([]) 
                        )
                        if sent_msg:
                            files_sent_count += 1
                            sent_messages.append(sent_msg.id)
                    except Exception as e:
                        logging.error(f"Batch skip msg {msg_id}: {e}")
                    await asyncio.sleep(0.5)
                
                if files_sent_count == 0:
                    err_msg = await message.reply_text("❌ No files found! Make sure the bot is an admin in the source batch channel.")
                    sent_messages.append(err_msg.id)
                else:
                    if auto_del_time > 0:
                        mins_text = int(auto_del_time / 60)
                        warning_msg = await message.reply_text(f"⚠️ **Important:**\nAll messages will be deleted after {mins_text} minutes. Please save or forward these messages to your personal saved messages to avoid losing them!")
                        sent_messages.append(warning_msg.id)
            
            # --- SINGLE FILE LOGIC ---
            else:
                file_data = await db.get_file(decoded_payload)
                if not file_data:
                    try:
                        file_data = await db.get_file(int(decoded_payload))
                    except:
                        pass

                if file_data:
                    composite_id = str(file_data["file_id"])
                    
                    if "_" in composite_id:
                        src_chat_id, src_msg_id = composite_id.split("_")
                        try:
                            sent_msg = await client.copy_message(
                                chat_id=message.chat.id,
                                from_chat_id=int(src_chat_id),
                                message_id=int(src_msg_id),
                                reply_markup=InlineKeyboardMarkup([])
                            )
                            if sent_msg:
                                sent_messages.append(sent_msg.id)
                        except Exception as e:
                            err_msg = await message.reply_text("❌ Failed to fetch file from source!")
                            sent_messages.append(err_msg.id)
                    else:
                        sent_msg = await client.send_cached_media(
                            chat_id=message.chat.id,
                            file_id=composite_id,
                            reply_markup=InlineKeyboardMarkup([])
                        )
                        sent_messages.append(sent_msg.id)
                        
                    if auto_del_time > 0 and len(sent_messages) > 0:
                        mins_text = int(auto_del_time / 60)
                        warning_msg = await message.reply_text(f"⚠️ **Important:**\nThis message will be deleted after {mins_text} minutes. Please forward it to your saved messages!")
                        sent_messages.append(warning_msg.id)
                else:
                    err_msg = await message.reply_text("❌ File not found or deleted from database!")
                    sent_messages.append(err_msg.id)
            
            if auto_del_time > 0 and sent_messages:
                asyncio.create_task(schedule_message_deletion(client, message.chat.id, sent_messages, auto_del_time))
                
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
        await callback_query.message.edit_reply_markup(reply_markup=fs_check)
        await callback_query.answer("❌ You haven't joined all required channels yet!", show_alert=True)

@app.on_message(filters.command("settings") & filters.private)
async def settings_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    current_time = await get_auto_delete_time()
    current_mins = int(current_time / 60) if current_time > 0 else "Off"
    
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
        f"⏱️ **Current Auto Delete Time:** {current_mins} minutes\n\n"
        f"Select a new time duration below (This setting is permanently saved):",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex(r"^set_time_"))
async def set_time_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.from_user.id != OWNER_ID:
        return
    seconds = int(callback_query.data.split("_")[2])
    
    await set_auto_delete_time(seconds)
    mins_text = f"{int(seconds / 60)} minutes" if seconds > 0 else "Disabled"
    
    await callback_query.message.edit_text(
        f"✅ **Settings Updated Successfully!**\n\n"
        f"⏱️ **New Auto Delete Time:** {mins_text}\n\n"
        f"(This setting is saved in your database and won't reset)"
    )
    await callback_query.answer("Settings saved to database!", show_alert=False)

# Admin Commands
@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    count = await db.total_users_count()
    channels = await db.get_fsub_channels()
    await message.reply_text(f"📊 **Bot Statistics**\n\n👥 Total Users: `{count}`\n📢 Active FSub Channels: `{len(channels)}`")

@app.on_message(filters.command("clearfsub") & filters.private)
async def clear_fsub_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await db.set_fsub_channels([])
    await message.reply_text("🧹 **All Force Sub channels have been completely cleared from the database!**\n\nYou can now add them properly using `/addfsub @username` or `/addfsub -100XXXXXXX`.")

@app.on_message(filters.command("addfsub") & filters.private)
async def add_fsub_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if len(message.command) < 2:
        await message.reply_text("❌ Usage:\n• `/addfsub @channelname` (Public)\n• `/addfsub -1001234567890` (Private IDs)")
        return
    
    target = message.text.split(None, 1)[1].strip()
    
    if "t.me" in target or "+" in target:
        await message.reply_text("❌ **ERROR:** Do not use invite links!\n\nFor private channels, you must use the `-100` ID. Please add the bot to the channel as Admin first, get its ID, and add it like `/addfsub -10012345678`.")
        return

    if not target.startswith("-100") and not target.startswith("@"):
        target = f"@{target}"
        
    try:
        chat = await client.get_chat(target)
        target_id = str(chat.id)
    except Exception as e:
        await message.reply_text(f"❌ Cannot access channel!\n\nMake sure the bot is an **Admin** in `{target}` first.\nError Details: `{e}`")
        return

    channels = await db.get_fsub_channels()
    if len(channels) >= 4:
        await message.reply_text("❌ Maximum 4 Force Sub channels are allowed!")
        return
    if target_id in channels:
        await message.reply_text("⚠️ This channel is already in Force Sub list!")
        return
        
    channels.append(target_id)
    await db.set_fsub_channels(channels)
    await message.reply_text(f"✅ Successfully added `{chat.title}` to Force Sub channels!")

@app.on_message(filters.command("remfsub") & filters.private)
async def rem_fsub_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    if len(message.command) < 2:
        await message.reply_text("❌ Usage: `/remfsub channel_id_or_username` (Check /fsublist to copy the exact ID)")
        return
        
    target = message.text.split(None, 1)[1].strip()
    channels = await db.get_fsub_channels()
    
    matched = None
    for ch in channels:
        if ch == target or ch == f"@{target}" or ch.replace("@", "") == target.replace("@", ""):
            matched = ch
            break
            
    if matched:
        channels.remove(matched)
        await db.set_fsub_channels(channels)
        await message.reply_text(f"✅ Removed `{matched}` from Force Sub list!")
    else:
        try:
            if not target.startswith("-") and not target.startswith("@"):
                target = f"@{target}"
            chat = await client.get_chat(target)
            if str(chat.id) in channels:
                channels.remove(str(chat.id))
                await db.set_fsub_channels(channels)
                await message.reply_text(f"✅ Removed `{chat.title}` from Force Sub list!")
                return
        except:
            pass
        await message.reply_text("❌ Channel not found in Force Sub list! Check `/fsublist`.")

@app.on_message(filters.command("fsublist") & filters.private)
async def fsub_list_handler(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    channels = await db.get_fsub_channels()
    if not channels:
        await message.reply_text("📂 Force Sub is currently disabled (No channels added).")
        return
    
    text = "📢 **Current Force Sub Channels:**\n\n"
    for idx, ch_id in enumerate(channels, 1):
        try:
            chat = await client.get_chat(int(ch_id) if ch_id.lstrip('-').isdigit() else ch_id)
            text += f"{idx}. {chat.title} (`{ch_id}`)\n"
        except:
            text += f"{idx}. Unknown Channel (`{ch_id}`)\n"
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
    await message.reply_text("📤 **Forward Any Message (Video, Photo, Text with buttons, etc.) From Your Channel / Chat To Get Your Shareable Link**")

@app.on_message(filters.command("batch") & filters.private)
async def batch_prompt(client: Client, message: Message):
    if message.from_user.id != OWNER_ID:
        return
    USER_BATCH_STATE[message.from_user.id] = {"state": "waiting_batch_first"}
    await message.reply_text("Forward The Batch **First Message** From Your Batch Channel (With Forward Tag)")

# Unified Media Handler
@app.on_message(filters.private & ~filters.command(["addfsub", "remfsub", "fsublist", "genlink", "batch", "settings", "stats", "start", "broadcast", "clearfsub"]))
async def unified_media_handler(client: Client, message: Message):
    user_id = message.from_user.id
    
    if user_id != OWNER_ID:
        return

    await db.add_user(user_id)
    
    if user_id in USER_BATCH_STATE:
        state_data = USER_BATCH_STATE[user_id]
        current_state = state_data.get("state")

        if current_state == "waiting_genlink":
            src_chat_id = message.chat.id
            src_msg_id = message.id
            
            composite_id = f"{src_chat_id}_{src_msg_id}"
            inserted_id = await db.save_file(
                file_id=composite_id,
                file_name="Media",
                file_size=0,
                custom_id=message.id
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
            src_chat_id = message.forward_from_chat.id if message.forward_from_chat else message.chat.id
            src_msg_id = message.forward_from_message_id if message.forward_from_message_id else message.id
            
            USER_BATCH_STATE[user_id]["first_id"] = src_msg_id
            USER_BATCH_STATE[user_id]["src_chat_id"] = src_chat_id
            USER_BATCH_STATE[user_id]["state"] = "waiting_batch_last"
            await message.reply_text("Forward The Batch **Last Message** From Your Batch Channel (With Forward Tag)")
            return

        elif current_state == "waiting_batch_last":
            src_msg_id = message.forward_from_message_id if message.forward_from_message_id else message.id
            
            first_id = state_data.get("first_id")
            saved_chat_id = state_data.get("src_chat_id")
            last_id = src_msg_id
            
            start_id = min(int(first_id), int(last_id))
            end_id = max(int(first_id), int(last_id))
            
            payload = f"batch_{saved_chat_id}_{start_id}_{end_id}"
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

    src_chat_id = message.chat.id
    src_msg_id = message.id
    
    composite_id = f"{src_chat_id}_{src_msg_id}"
    inserted_id = await db.save_file(
        file_id=composite_id,
        file_name="Direct Media",
        file_size=0,
        custom_id=message.id
    )

    encoded_payload = encode_id(str(inserted_id))
    bot_username = (await client.get_me()).username
    share_link = f"https://t.me/{bot_username}?start={encoded_payload}"
    
    await message.reply_text(
        f"Here is your link:\n`{share_link}`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 SHARE URL", url=f"https://t.me/share/url?url={share_link}")]])
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
        BotCommand("fsublist", "View active force sub channels"),
        BotCommand("clearfsub", "Wipe all buggy channels")
    ]
    await app.set_bot_commands(commands)
    print("🔥 Bot Commands Menu set successfully & Bot is running!")
    await idle()
    await app.stop()

if __name__ == "__main__":
    print("🤖 Bot is starting cleanly...")
    asyncio.get_event_loop().run_until_complete(main())
