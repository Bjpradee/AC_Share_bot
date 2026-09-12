@app.on_message(filters.document | filters.video | filters.audio)
async def store_file(client: Client, message: Message):
    try:
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
    except Exception as e:
        await message.reply_text(f"❌ Error vanthiruchu da: `{e}`")
