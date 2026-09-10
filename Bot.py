import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from motor.motor_asyncio import AsyncIOMotorClient
from thefuzz import process

API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8906094926:AAHYrv9lJgYcSxn6vXXcqo9b_60HQVgDUTk")
ADMINS = [914605248]

FORCE_SUB_CHANNEL = "@manishdahiya01"
STORAGE_CHAT_ID = int(os.environ.get("STORAGE_CHAT_ID", "-1001987654321"))
SESSION_STRING = os.environ.get("SESSION_STRING", "")
AUTO_DELETE_SECONDS = int(os.environ.get("AUTO_DELETE_SECONDS", "60"))

DATABASE_URI = os.environ.get("DATABASE_URI", "mongodb+srv://admin:pass@cluster0.mongodb.net/?retryWrites=true&w=majority")
DATABASE_NAME = "MovieBot"

dbclient = AsyncIOMotorClient(DATABASE_URI)
db = dbclient[DATABASE_NAME]
movie_collection = db["files"]

app = Client("AdvancedMovieBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
BOT_STATUS = True

# Helper: Auto-deletes both user request and bot reply after delay (default 60s / 1 min)
async def auto_delete_messages(messages, delay=60):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except Exception:
            pass

# Helper: Channel membership verification for Force-Sub
async def is_subscribed(client, user_id):
    try:
        user = await client.get_chat_member(FORCE_SUB_CHANNEL, user_id)
        if user.status in ["banned", "left", "kicked"]:
            return False
        return True
    except Exception:
        return False

# Main Search Keyboard
def get_main_keyboard(page=1, total_pages=9):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Send All 🚀", callback_data="send_all"),
            InlineKeyboardButton("Languages 🌐", callback_data="langs"),
            InlineKeyboardButton("Years 📅", callback_data="years")
        ],
        [
            InlineKeyboardButton("Quality 🖥️", callback_data="quality"),
            InlineKeyboardButton("Episodes 📺", callback_data="episodes_range_0"),
            InlineKeyboardButton("Seasons 🍿", callback_data="seasons_range_0")
        ],
        [
            InlineKeyboardButton(f"PAGE {page}/{total_pages}", callback_data=f"page_{page}"),
            InlineKeyboardButton("NEXT ➡️", callback_data=f"next_{page + 1}")
        ],
        [
            InlineKeyboardButton("⬅️ BACK TO FILES 📂", callback_data="back_to_files")
        ]
    ])

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    global BOT_STATUS
    if not BOT_STATUS:
        return await message.reply("⚠️ Bot is currently turned OFF by Admin (Maintenance Mode).")
    
    if not await is_subscribed(client, message.from_user.id):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_SUB_CHANNEL.replace('@','')}") ]])
        return await message.reply("⚠️ Pehle aap hamare channel ko join karein, tabhi bot kaam karega!", reply_markup=btn)

    welcome_text = (
        f"✨ **Just type any movie name here my bot send this movie.**\n\n"
        "✨ First see movie name from google and type right spelling\n\n"
        "✨ You can request any movie/webseries here use #request or @admin\n\n"
        f"🔥 **POWERED BY :** {FORCE_SUB_CHANNEL}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 MOVIES EERA 🦋", url=f"https://t.me/{FORCE_SUB_CHANNEL.replace('@','')}")]
    ])
    await message.reply(welcome_text, reply_markup=keyboard)

@app.on_message(filters.command("toggle") & filters.user(ADMINS))
async def toggle_bot(client, message):
    global BOT_STATUS
    BOT_STATUS = not BOT_STATUS
    status_text = "STARTED 🟢" if BOT_STATUS else "STOPPED 🔴"
    await message.reply(f"Bot status successfully changed to: {status_text}")

# Auto-Index Old Chat History using Pyrogram User Session String
@app.on_message(filters.command("index") & filters.user(ADMINS))
async def index_chat_history(client, message):
    if not SESSION_STRING:
        return await message.reply("⚠️ SESSION_STRING set nahi hai environment me! Please configure SESSION_STRING.")
    
    status_msg = await message.reply("⏳ Connecting via User Session String to scan old chat history...")
    try:
        user_client = Client("indexer_user", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
        await user_client.start()
        
        indexed_count = 0
        await status_msg.edit_text(f"🔍 Scanning Storage Channel ({STORAGE_CHAT_ID})...")
        
        async for msg in user_client.get_chat_history(STORAGE_CHAT_ID):
            media = msg.video or msg.document
            if media:
                file_name = getattr(media, "file_name", None) or f"File_{msg.id}.mkv"
                file_size = f"{round(media.file_size / (1024 * 1024), 1)} MB"
                
                exists = await movie_collection.find_one({"file_name": file_name})
                if not exists:
                    await movie_collection.insert_one({
                        "file_name": file_name,
                        "file_size": file_size,
                        "file_id": media.file_id,
                        "chat_id": STORAGE_CHAT_ID,
                        "message_id": msg.id
                    })
                    indexed_count += 1
        
        await user_client.stop()
        await status_msg.edit_text(f"✅ **Auto-Indexing Complete!**\n\n🎉 Successfully indexed and saved " + str(indexed_count) + " files from old chat history into MongoDB!")
    except Exception as e:
        await status_msg.edit_text("❌ Indexing Failed: " + str(e))

@app.on_message(filters.text & filters.private & ~filters.command(["start", "toggle", "index"]))
async def search_handler(client, message):
    global BOT_STATUS
    if not BOT_STATUS:
        return

    # Strict Force-Sub check on all messages
    if not await is_subscribed(client, message.from_user.id):
        join_url = f"https://t.me/{FORCE_SUB_CHANNEL.replace('@','')}"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("📢 Join Channel Now", url=join_url)]])
        return await message.reply(
            f"⚠️ **Access Denied!**\n\nPehle aapko hamare official channel {FORCE_SUB_CHANNEL} ko join karna hoga, tabhi bot files bhejega!",
            reply_markup=btn
        )
    
    query = message.text.strip()
    all_files = await movie_collection.find({}).to_list(length=None)
    
    if not all_files:
        return await message.reply(
            "🔍 Searching For: " + query + "\n\n" +
            "❌ No database files found yet!\n\n" +
            "🔥 **POWERED BY :** " + FORCE_SUB_CHANNEL
        )

    file_names = [f["file_name"] for f in all_files]
    matches = process.extract(query, file_names, limit=6)
    
    channel_url = f"https://t.me/{FORCE_SUB_CHANNEL.replace('@','')}"
    user_name = getattr(message.from_user, "first_name", "User")
    user_mention = getattr(message.from_user, "mention", f"[{user_name}](tg://user?id={message.from_user.id})")

    result_text = "👤 **Requested by :** " + str(user_mention) + "\n"
    result_text += "📂 **Search Results for:** " + query + "\n\n"
    found = False
    
    for match, score in matches:
        if score > 50:
            result_text += f"📁 [{match}]({channel_url})\n\n"
            found = True
            
    if not found:
        result_text += "No matching movie found!\n\n"
        
    result_text += "⏳ **Auto-Delete :** This result & your request will auto-delete in 1 minute (" + str(AUTO_DELETE_SECONDS) + "s)!\n\n"
    result_text += f"🔥 **POWERED BY :** {FORCE_SUB_CHANNEL}"
    reply_msg = await message.reply(result_text, reply_markup=get_main_keyboard(1, 9), disable_web_page_preview=True)

    # Auto-delete both user request and bot reply after 1 minute (60 seconds)
    asyncio.create_task(auto_delete_messages([message, reply_msg], delay=AUTO_DELETE_SECONDS))

print("Bot is ready and running...")
app.run()
