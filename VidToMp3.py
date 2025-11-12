import os
import asyncio
import logging
import tempfile
import time
import gc
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

BOT_TOKEN = os.getenv("bot")
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_cookies():
    if YOUTUBE_COOKIES:
        with open("cookies.txt", "w") as f:
            f.write(YOUTUBE_COOKIES)
        logger.info("cookies.txt created")

setup_cookies()
progress = {}

def progress_bar(p, length=20):
    filled = int(length * p / 100)
    return f"[{'█'*filled}{'░'*(length-filled)}] {p:.1f}%"

ANIM = ["🔄","🌀","💿","⏳","➡️"]

async def animate(uid, msg):
    frame = 0
    last = ""
    while uid in progress:
        txt = progress[uid]["text"]
        text = f"{ANIM[frame%len(ANIM)]} {txt}"
        if text != last:
            try:
                await msg.edit_text(text)
            except:
                pass
            last = text
        frame += 1
        await asyncio.sleep(0.6)

async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send a YouTube link and I’ll extract the audio (no heavy conversion, super-light)."
    )

def fetch_audio(url, uid):
    tmp = tempfile.gettempdir()
    start = time.time()

    def hook(d):
        if d["status"] == "downloading":
            pct = d.get("downloaded_bytes",0)/max(d.get("total_bytes",1),1)*100
            progress[uid]["text"] = f"📥 Downloading… {progress_bar(pct)}"

    ydl_opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": os.path.join(tmp, f"{uid}_%(id)s.%(ext)s"),
        "quiet": True,
        "progress_hooks": [hook],
        "noplaylist": True,
        "concurrent_fragment_downloads": 1,
        "no_warnings": True,
        "cachedir": False,
    }
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    audio_file = None
    for f in os.listdir(tmp):
        if f.startswith(f"{uid}_") and f.endswith((".m4a",".webm",".opus")):
            audio_file = os.path.join(tmp,f)
            break

    title = info.get("title","audio")
    dur = round(time.time()-start,1)
    size = os.path.getsize(audio_file)/(1024*1024) if audio_file else 0
    return audio_file, title, dur, size

async def handle(update: Update, _: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if not url.startswith(("http://","https://")):
        await update.message.reply_text("❌ Send a valid link.")
        return

    uid = update.effective_user.id
    msg = await update.message.reply_text("📡 Starting...")
    progress[uid] = {"text":"Preparing..."}
    asyncio.create_task(animate(uid,msg))

    try:
        path,title,dur,size = await asyncio.to_thread(fetch_audio,url,uid)
        if not path: raise Exception("Failed to get audio")

        if size > 40:
            os.remove(path)
            raise Exception("File too large (>40 MB). Try shorter video.")

        progress[uid]["text"] = "📤 Uploading..."
        await asyncio.sleep(0.4)

        with open(path,"rb") as a:
            await update.message.reply_audio(
                a,
                title=title,
                caption=f"✅ {title}\n⏱ {dur}s | 💾 {size:.2f} MB"
            )
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
        logger.error(e)
    finally:
        progress.pop(uid,None)
        try: await msg.delete()
        except: pass
        tmp=tempfile.gettempdir()
        for f in os.listdir(tmp):
            if f.startswith(f"{uid}_"):
                try: os.remove(os.path.join(tmp,f))
                except: pass
        gc.collect()

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    logger.info("Bot running")
    app.run_polling()

if __name__ == "__main__":
    main()
            
