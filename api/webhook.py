"""
Video Downloader — Telegram Webhook
"""
import json, os, re, tempfile, shutil, subprocess, sys
from http.server import BaseHTTPRequestHandler

def pip(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try: import requests
except ImportError: pip("requests"); import requests
try: import yt_dlp
except ImportError: pip("yt-dlp"); import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TG = f"https://api.telegram.org/bot{BOT_TOKEN}"
URL_RE = re.compile(r'https?://[^\s]+')

def get_cookie_file():
    cookie_data = os.environ.get("YT_COOKIES")
    if not cookie_data: return None
    fd, path = tempfile.mkstemp(suffix=".txt", dir="/tmp")
    with os.fdopen(fd, 'w') as tmp:
        tmp.write(cookie_data)
    os.chmod(path, 0o644)
    return path

def tg(method, **kw):
    try: return requests.post(f"{TG}/{method}", json=kw, timeout=20).json()
    except: return {"ok": False}

def send(chat_id, text): return tg("sendMessage", chat_id=chat_id, text=text, parse_mode="Markdown")

def _do_download(chat_id, url, audio_only=False):
    cookie_path = get_cookie_file()
    status_msg = send(chat_id, "⏳ Video එක සකසමින් පවතී...")
    msg_id = status_msg.get("result", {}).get("message_id")
    tmpdir = tempfile.mkdtemp()

    opts = {
        "outtmpl": os.path.join(tmpdir, "%(title).60s.%(ext)s"),
        "quiet": True, "noplaylist": True,
        "cookiefile": cookie_path,
        "extractor_args": {"youtube": {"player_client": ["android", "web"], "po_token": ["web+guest"]}}
    }

    if audio_only:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}]
    else:
        opts["format"] = "best[height<=720][ext=mp4]/best"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if audio_only: filename = os.path.splitext(filename)[0] + ".mp3"

        with open(filename, "rb") as f:
            if audio_only: requests.post(f"{TG}/sendAudio", data={"chat_id":chat_id}, files={"audio":f})
            else: requests.post(f"{TG}/sendVideo", data={"chat_id":chat_id, "supports_streaming":"true"}, files={"video":f})

        if msg_id: tg("deleteMessage", chat_id=chat_id, message_id=msg_id)
    except Exception as e:
        err_msg = str(e)
        if "sign in" in err_msg.lower(): err_msg = "YouTube Error: Cookies update කරන්න."
        tg("editMessageText", chat_id=chat_id, message_id=msg_id, text=f"❌ {err_msg[:100]}")
    finally:
        if cookie_path and os.path.exists(cookie_path): os.remove(cookie_path)
        shutil.rmtree(tmpdir, ignore_errors=True)

def handle_update(update):
    msg = update.get("message")
    if not msg or "text" not in msg: return
    chat_id, text = msg["chat"]["id"], msg["text"].strip()

    if text.startswith("/start"): send(chat_id, "Welcome! YouTube Link එකක් එවන්න.")
    elif text.startswith("/audio"):
        url = text.split(" ", 1)[1] if " " in text else ""
        if url: _do_download(chat_id, url, True)
    else:
        m = URL_RE.search(text)
        if m: _do_download(chat_id, m.group(0))

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        handle_update(json.loads(body))
        self.send_response(200); self.end_headers()
    def do_GET(self):
        self.send_response(200); self.send_header("Content-type","application/json"); self.end_headers()
        self.wfile.write(json.dumps({"status":"running"}).encode())
