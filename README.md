# 🎬 TG Video Rounded Corners Bot

Telegram bot that crops your videos to a chosen ratio and applies smooth rounded corners.

## Features
- 📐 5 ratio presets: 1:1, 9:16, 16:9, 4:5, 720p Square
- ✂️ Smart centre-crop (no stretching)
- 🎨 Smooth rounded corners via FFmpeg
- 📤 Supports both video messages and video files

## Deploy on Render

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOU/YOUR-REPO.git
git push -u origin main
```

### 2. Create Web Service on render.com
- Connect your GitHub repo
- Render auto-reads `render.yaml`

### 3. Set Environment Variables in Render Dashboard
| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | Token from @BotFather |
| `WEBHOOK_URL` | Your Render URL, e.g. `https://tg-video-rounded-bot.onrender.com` |

### 4. Deploy!

## Local Development
```bash
pip install -r requirements.txt
# Make sure ffmpeg is installed: sudo apt install ffmpeg / brew install ffmpeg
export TELEGRAM_BOT_TOKEN=your_token_here
python bot.py   # runs in polling mode (no WEBHOOK_URL needed)
```

## Bot Flow
1. Send any video
2. Bot shows ratio buttons (1:1, 9:16, 16:9, 4:5, 720p)
3. Tap a ratio → bot crops + rounds corners
4. Receive your processed video 🎉
