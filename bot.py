import os
import io
import uuid
import logging
import subprocess
import asyncio
import tempfile
from PIL import Image, ImageDraw
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
PORT        = int(os.environ.get("PORT", 8443))
TMPDIR      = tempfile.gettempdir()

RATIOS = {
    "1080x1080": (1080, 1080, "1:1  Square"),
    "1080x1920": (1080, 1920, "9:16  Story / Reel"),
    "1920x1080": (1920, 1080, "16:9  Landscape"),
    "1080x1350": (1080, 1350, "4:5  Portrait"),
    "720x720":   (720,  720,  "720p Square"),
}

RADIUS_RATIO = 0.06


def tmp(ext):
    return os.path.join(TMPDIR, f"{uuid.uuid4().hex}.{ext}")


def create_mask(w, h, radius):
    img = Image.new("RGB", (w, h), "black")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([(0, 0), (w - 1, h - 1)], radius=radius, fill="white")
    path = tmp("png")
    img.save(path)
    return path


def run_ffmpeg(*args):
    cmd = ["ffmpeg", "-y", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])
    return result


def get_video_dimensions(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error",
         "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0", path],
        capture_output=True, text=True
    )
    w, h = r.stdout.strip().split(",")
    return int(w), int(h)


def process_video(input_path, out_w, out_h):
    src_w, src_h = get_video_dimensions(input_path)

    src_ratio = src_w / src_h
    dst_ratio = out_w / out_h

    if src_ratio > dst_ratio:
        crop_h = src_h
        crop_w = int(src_h * dst_ratio)
    else:
        crop_w = src_w
        crop_h = int(src_w / dst_ratio)

    crop_x = (src_w - crop_w) // 2
    crop_y = (src_h - crop_h) // 2

    cropped = tmp("mp4")
    run_ffmpeg(
        "-i", input_path,
        "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={out_w}:{out_h},setsar=1",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        cropped,
    )

    radius = int(min(out_w, out_h) * RADIUS_RATIO)
    mask_path = create_mask(out_w, out_h, radius)

    output_path = tmp("mp4")
    run_ffmpeg(
        "-i", cropped,
        "-i", mask_path,
        "-filter_complex",
        "[0:v]format=rgb24[v];"
        "[1:v]scale=%d:%d[m];"
        "[v][m]blend=all_mode=multiply[out]" % (out_w, out_h),
        "-map", "[out]",
        "-map", "0:a?",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    )

    for f in (cropped, mask_path):
        try: os.remove(f)
        except: pass

    return output_path


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Video Rounded Corners Bot*\n\n"
        "Send me any video and I'll:\n"
        "1️⃣ Ask you for the output ratio\n"
        "2️⃣ Crop it to that size\n"
        "3️⃣ Apply smooth rounded corners\n\n"
        "Just send a video to get started! 🚀",
        parse_mode="Markdown"
    )


async def handle_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    video = msg.video or (
        msg.document if msg.document and msg.document.mime_type
        and msg.document.mime_type.startswith("video/") else None
    )

    if not video:
        await msg.reply_text("Please send a video file.")
        return

    ctx.user_data["pending_file_id"] = video.file_id

    keyboard = [
        [InlineKeyboardButton(f"📐 {info[2]}", callback_data=f"ratio:{key}")]
        for key, info in RATIOS.items()
    ]
    await msg.reply_text(
        "✅ Video received!\n\n*Choose your output ratio:*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def handle_ratio_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    key = query.data.split(":", 1)[1]
    if key not in RATIOS:
        await query.edit_message_text("❌ Unknown ratio.")
        return

    file_id = ctx.user_data.get("pending_file_id")
    if not file_id:
        await query.edit_message_text("❌ No video found. Please send a video again.")
        return

    out_w, out_h, label = RATIOS[key]
    await query.edit_message_text(
        f"⏳ Processing *{label}* ({out_w}×{out_h})…\nPlease wait.",
        parse_mode="Markdown"
    )

    input_path = tmp("mp4")
    output_path = None

    try:
        file = await ctx.bot.get_file(file_id)
        await file.download_to_drive(input_path)

        loop = asyncio.get_event_loop()
        output_path = await loop.run_in_executor(
            None, process_video, input_path, out_w, out_h
        )

        with open(output_path, "rb") as f:
            await query.message.reply_video(
                video=f,
                caption=f"✨ Done! *{label}* ({out_w}×{out_h}) with rounded corners 🎉",
                parse_mode="Markdown",
                supports_streaming=True,
            )

    except Exception as e:
        logger.error("Error: %s", e)
        await query.message.reply_text(f"❌ Error: `{str(e)[:300]}`", parse_mode="Markdown")
    finally:
        for f in (input_path, output_path):
            if f:
                try: os.remove(f)
                except: pass
        ctx.user_data.pop("pending_file_id", None)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set!")

    # ✅ KEY FIX: increased timeouts so Render's slow cold-start doesn't fail
    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.add_handler(CallbackQueryHandler(handle_ratio_choice, pattern=r"^ratio:"))

    if WEBHOOK_URL:
        logger.info("Starting webhook mode on port %d", PORT)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/webhook",
            url_path="/webhook",
            drop_pending_updates=True,
        )
    else:
        logger.info("Starting polling mode (local dev)")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
