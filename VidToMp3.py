import os
import asyncio
import logging
import tempfile
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

BOT_TOKEN = os.getenv("bot")  # 🔑 Replace with your bot token
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES")

# --- Logging setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Setup cookies from environment variable ---
def setup_cookies():
    """Create cookies.txt from environment variable if provided"""
    cookies_path = "cookies.txt"
    
    # If cookies.txt already exists, use it
    if os.path.exists(cookies_path):
        logger.info("Using existing cookies.txt file")
        return
    
    # Otherwise, create from environment variable if available
    if YOUTUBE_COOKIES:
        try:
            with open(cookies_path, "w") as f:
                f.write(YOUTUBE_COOKIES)
            logger.info("Created cookies.txt from YOUTUBE_COOKIES environment variable")
        except Exception as e:
            logger.warning(f"Failed to create cookies.txt: {e}")
    else:
        logger.info("No cookies configured (YOUTUBE_COOKIES env var not set)")
# Setup cookies on startup
setup_cookies()

progress = {}

# --- Progress bar ---
def progress_bar(p, length=20):
    filled = int(length * p / 100)
    return f"[{'█' * filled}{'░' * (length - filled)}] {p:.1f}%"

# --- Animated emoji frames ---
ANIM_FRAMES = ["🔄", "🌀", "💿", "📀", "⏳", "➡️"]

# --- Smooth progress animation ---
async def smooth_progress(user_id, msg):
    last = ""
    frame = 0
    while user_id in progress:
        data = progress[user_id]
        txt = data.get("text", "⏳ Working...")
        emoji = ANIM_FRAMES[frame % len(ANIM_FRAMES)]
        text = f"{emoji} {txt}"
        if text != last:
            try:
                await msg.edit_text(text, parse_mode="Markdown")
            except:
                pass
            last = text
        frame += 1
        await asyncio.sleep(0.6)

# --- /start command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Welcome to SuperFast Video → MP3 Bot!*\n\n"
        "🎥 Send a video link (YouTube, etc.) — I'll convert it into a high-quality MP3 **super fast!** 🚀",
        parse_mode="Markdown",
    )

# --- Blocking yt-dlp download (runs in a thread) ---
def download_audio(url, uid):
    tmpdir = tempfile.gettempdir()
    start_time = time.time()

    def hook(d):
        if d["status"] == "downloading":
            p = d.get("downloaded_bytes", 0) / max(d.get("total_bytes", 1), 1) * 90
            progress[uid]["text"] = f"📥 Downloading...\n{progress_bar(p)}"
        elif d["status"] == "finished":
            progress[uid]["text"] = "🔄 Converting to MP3..."

    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmpdir, f"{uid}_%(title)s.%(ext)s"),
        "progress_hooks": [hook],
        "quiet": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 5,
        "cachedir": False,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    cookies_path = "cookies.txt"
    if os.path.exists(cookies_path):
        opts["cookiefile"] = cookies_path
        
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    end_time = time.time()
    duration = round(end_time - start_time, 1)

    title = info.get("title", "audio")
    mp3 = None
    for f in os.listdir(tmpdir):
        if f.startswith(f"{uid}_") and f.endswith(".mp3"):
            mp3 = os.path.join(tmpdir, f)
            break

    file_size = os.path.getsize(mp3) / (1024 * 1024) if mp3 else 0
    return mp3, title, duration, file_size

# --- Handle URL input only ---
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    uid = update.effective_user.id

    # --- Basic URL check ---
    if not (url.startswith("http://") or url.startswith("https://")):
        await update.message.reply_text("❌ Please send a valid video link (e.g., YouTube).")
        return

    msg = await update.message.reply_text("📡 Connecting...\n" + progress_bar(0))
    progress[uid] = {"text": "Starting..."}
    asyncio.create_task(smooth_progress(uid, msg))

    try:
        mp3_path, title, duration, file_size = await asyncio.to_thread(download_audio, url, uid)
        
        if not mp3_path:
            raise Exception("Failed to convert video to MP3")
        
        progress[uid]["text"] = "📤 Uploading...\n" + progress_bar(100)
        await asyncio.sleep(0.5)

        caption = (
            f"✅ *{title}* converted successfully!\n"
            f"⏱️ Time taken: *{duration}s*\n"
            f"💾 File size: *{file_size:.2f} MB*"
        )

        with open(mp3_path, "rb") as audio_file:
            await update.message.reply_audio(
                audio=audio_file,
                title=title,
                caption=caption,
                parse_mode="Markdown",
            )
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
        logger.error(e)
    finally:
        progress.pop(uid, None)
        try:
            await msg.delete()
        except:
            pass
        # Cleanup temp files
        tmpdir = tempfile.gettempdir()
        for f in os.listdir(tmpdir):
            if f.startswith(f"{uid}_"):
                try:
                    os.remove(os.path.join(tmpdir, f))
                except:
                    pass

# --- Run bot ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    logger.info("🚀 Video → MP3 Link-only Bot Started!")
    app.run_polling()

if __name__ == "__main__":
    main()
