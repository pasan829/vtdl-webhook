"""
Video Downloader — Telegram Webhook on Vercel
No polling = No conflicts. Ever.
"""

import json, os, re, tempfile, shutil, subprocess, sys
from http.server import BaseHTTPRequestHandler

# ── deps ──────────────────────────────────────────────────────────────────
def pip(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "-q"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try:
    import requests
except ImportError:
    pip("requests"); import requests

try:
    import yt_dlp
except ImportError:
    pip("yt-dlp"); import yt_dlp

# ── config ────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TG         = f"https://api.telegram.org/bot{BOT_TOKEN}"
URL_RE     = re.compile(r'https?://[^\s]+')

# ── helpers ───────────────────────────────────────────────────────────────
def tg(method, **kw):
    try:
        r = requests.post(f"{TG}/{method}", json=kw, timeout=20)
        return r.json()
    except Exception as e:
        return {"ok": False, "description": str(e)}

def send(chat_id, text, parse_mode="Markdown"):
    return tg("sendMessage", chat_id=chat_id, text=text, parse_mode=parse_mode)

def edit(chat_id, msg_id, text, parse_mode="Markdown"):
    return tg("editMessageText", chat_id=chat_id, message_id=msg_id,
              text=text, parse_mode=parse_mode)

def platform_of(url):
    for pat, name in [
        (r'youtube\.com|youtu\.be', "YouTube"),
        (r'facebook\.com|fb\.watch', "Facebook"),
        (r'instagram\.com',          "Instagram"),
        (r'twitter\.com|x\.com',     "Twitter/X"),
        (r'tiktok\.com',             "TikTok"),
    ]:
        if re.search(pat, url, re.I): return name
    return "Video"

def fmt_size(b):
    if not b or b <= 0: return ""
    if b < 1024**2: return f"{b/1024:.0f} KB"
    if b < 1024**3: return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"

def fmt_dur(s):
    if not s: return ""
    h, r = divmod(int(s), 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"

def head_size(url):
    try:
        r = requests.head(url, timeout=6, allow_redirects=True,
                          headers={"User-Agent": "Mozilla/5.0"})
        cl = r.headers.get("content-length")
        return int(cl) if cl else 0
    except:
        return 0

def quality_label(h):
    if not h: return "Best"
    s = f"{h}p"
    if h >= 2160: s += " 4K"
    elif h >= 1080: s += " Full HD"
    elif h >= 720:  s += " HD"
    elif h >= 480:  s += " SD"
    return s

# ── yt-dlp info extraction ─────────────────────────────────────────────────
def get_info(url):
    opts = {
        "quiet": True, "no_warnings": True,
        "skip_download": True, "noplaylist": True,
        "http_headers": {"User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"},
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    fmts = info.get("formats", [])
    options = []
    seen = set()

    combined = [f for f in fmts
                if f.get("vcodec") not in (None,"none")
                and f.get("acodec") not in (None,"none")
                and f.get("url")
                and f.get("ext") in ("mp4","webm","mov")]
    combined.sort(key=lambda f: f.get("height") or 0, reverse=True)

    for f in combined:
        h = f.get("height") or 0
        if h in seen: continue
        seen.add(h)
        sz = f.get("filesize") or f.get("filesize_approx") or head_size(f["url"])
        options.append({"type":"video","label":quality_label(h),
                        "ext":f.get("ext","mp4"),"url":f["url"],
                        "size":sz,"size_fmt":fmt_size(sz),"height":h})
        if len(seen) >= 4: break

    if not options:
        best = next((f for f in reversed(fmts)
                     if f.get("vcodec") not in (None,"none") and f.get("url")), None)
        if best:
            sz = best.get("filesize") or head_size(best["url"])
            options.append({"type":"video","label":quality_label(best.get("height")),
                            "ext":best.get("ext","mp4"),"url":best["url"],
                            "size":sz,"size_fmt":fmt_size(sz)})

    af = [f for f in fmts if f.get("vcodec") in (None,"none")
          and f.get("acodec") not in (None,"none") and f.get("url")]
    af.sort(key=lambda f: f.get("abr") or 0, reverse=True)
    if af:
        a = af[0]
        sz = a.get("filesize") or head_size(a["url"])
        options.append({"type":"audio","label":"Audio Only (MP3)",
                        "ext":a.get("ext","m4a"),"url":a["url"],
                        "size":sz,"size_fmt":fmt_size(sz)})

    return {"title":info.get("title","Video"),
            "thumbnail":info.get("thumbnail",""),
            "duration":info.get("duration",0),
            "dur_fmt":fmt_dur(info.get("duration")),
            "uploader":info.get("uploader",""),
            "platform":info.get("extractor_key",""),
            "options":options}

# ── message handler ────────────────────────────────────────────────────────
def handle_update(update):
    msg = update.get("message") or update.get("edited_message")
    if not msg: return

    chat_id = msg["chat"]["id"]
    text    = (msg.get("text") or "").strip()

    # /start
    if text.startswith("/start"):
        send(chat_id,
            f"👋 *Video Downloader Bot*\n\n"
            f"Supported: YouTube · Facebook · Instagram · Twitter/X · TikTok\n\n"
            f"• Video URL paste කරන්න\n"
            f"• `/audio <URL>` → MP3\n"
            f"• `/id` → Chat ID\n\n"
            f"🆔 Your Chat ID: `{chat_id}`")
        return

    # /id
    if text.startswith("/id"):
        send(chat_id, f"🆔 Your Chat ID: `{chat_id}`\n\nBlogger widget config ගෙ `CHAT_ID` ගෙ මේ දාන්න.")
        return

    # /audio
    if text.startswith("/audio"):
        parts = text.split(None, 1)
        if len(parts) < 2:
            send(chat_id, "Usage: `/audio <URL>`"); return
        _do_download(chat_id, parts[1].strip(), audio_only=True)
        return

    # API request from Blogger widget
    # Format: APIGET:<req_id>:<url>  or  APIGET_AUDIO:<req_id>:<url>
    if text.startswith("APIGET"):
        parts = text.split(":", 2)
        if len(parts) < 3: return
        mode, req_id, url = parts[0], parts[1], parts[2].strip()
        audio_only = (mode == "APIGET_AUDIO")
        try:
            data = get_info(url)
            if audio_only:
                data["options"] = [o for o in data["options"] if o["type"]=="audio"]
            result = {"ok":True, "req_id":req_id, **data}
        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if "bot" in err.lower() or "sign in" in err.lower():
                msg_txt = "Platform bot detection — ටිකක් ඉඳලා retry කරන්න."
            elif "private" in err.lower():
                msg_txt = "Video private / restricted."
            elif "unavailable" in err.lower():
                msg_txt = "Video unavailable (deleted / region blocked)."
            else:
                msg_txt = err[:200]
            result = {"ok":False, "req_id":req_id, "error":msg_txt}
        except Exception as e:
            result = {"ok":False, "req_id":req_id, "error":str(e)[:200]}

        send(chat_id, f"APIRESULT:{json.dumps(result, ensure_ascii=False)}")
        return

    # Plain URL — direct download to Telegram
    m = URL_RE.search(text)
    if m:
        _do_download(chat_id, m.group(0), audio_only=False)
    else:
        send(chat_id, "⚠️ Valid video URL එකක් paste කරන්න.")


def _do_download(chat_id, url, audio_only):
    platform = platform_of(url)
    r = send(chat_id, f"⏳ *{platform}* {'audio' if audio_only else 'video'} download කරනවා...")
    msg_id = r.get("result", {}).get("message_id")
    tmpdir = tempfile.mkdtemp()

    try:
        opts = {
            "outtmpl": os.path.join(tmpdir, "%(title).60s.%(ext)s"),
            "quiet": True, "no_warnings": True, "noplaylist": True,
            "http_headers": {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        }
        if audio_only:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key":"FFmpegExtractAudio",
                                        "preferredcodec":"mp3","preferredquality":"192"}]
        else:
            opts["format"] = ("bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
                               "best[height<=720][ext=mp4]/best[height<=720]/best")

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        files = [os.path.join(tmpdir,f) for f in os.listdir(tmpdir)
                 if os.path.isfile(os.path.join(tmpdir,f))]
        if not files: raise RuntimeError("No file downloaded")

        fp = files[0]
        size_mb = os.path.getsize(fp) / 1024**2
        title = (info.get("title") or "Video")[:100]

        if size_mb > 49.5:
            if msg_id: edit(chat_id, msg_id,
                f"⚠️ File {size_mb:.1f}MB — Telegram 50MB limit ඉක්මවා ගියා.\n"
                "Blogger site ගෙ download button use කරන්න.")
            return

        if msg_id: edit(chat_id, msg_id, f"📤 Uploading {size_mb:.1f}MB...")

        ext = os.path.splitext(fp)[1].lower()
        with open(fp,"rb") as fh:
            if audio_only or ext==".mp3":
                tg("sendAudio", chat_id=chat_id,
                   caption=f"🎵 *{title}*", parse_mode="Markdown",
                   **{"audio": None})
                # use requests directly for file upload
                requests.post(f"{TG}/sendAudio",
                    data={"chat_id":chat_id,"caption":f"🎵 *{title}*","parse_mode":"Markdown"},
                    files={"audio": fh}, timeout=120)
            elif ext in (".mp4",".mov",".webm",".mkv"):
                requests.post(f"{TG}/sendVideo",
                    data={"chat_id":chat_id,
                          "caption":f"🎬 *{title}*\n_via Video Downloader Bot_",
                          "parse_mode":"Markdown","supports_streaming":"true"},
                    files={"video": fh}, timeout=120)
            else:
                requests.post(f"{TG}/sendDocument",
                    data={"chat_id":chat_id,"caption":f"📎 *{title}*","parse_mode":"Markdown"},
                    files={"document": fh}, timeout=120)

        if msg_id:
            tg("deleteMessage", chat_id=chat_id, message_id=msg_id)

    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if "bot" in err.lower() or "sign in" in err.lower():
            friendly = "❌ Bot detection — ටිකක් ඉඳලා retry කරන්න."
        elif "private" in err.lower():
            friendly = "❌ Video private / restricted."
        elif "unavailable" in err.lower():
            friendly = "❌ Video unavailable."
        else:
            friendly = f"❌ `{err[:200]}`"
        if msg_id: edit(chat_id, msg_id, friendly)
        else: send(chat_id, friendly)

    except Exception as e:
        txt = f"❌ Error: `{str(e)[:200]}`"
        if msg_id: edit(chat_id, msg_id, txt)
        else: send(chat_id, txt)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Vercel handler ─────────────────────────────────────────────────────────
CORS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
}

class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            update = json.loads(body)
            handle_update(update)
        except Exception as e:
            print(f"Handler error: {e}")
        self._ok()

    def do_GET(self):
        self._ok({"status": "Video Downloader Bot is running ✅"})

    def _ok(self, body=None):
        payload = json.dumps(body or {"ok": True}).encode()
        self.send_response(200)
        for k,v in CORS.items(): self.send_header(k,v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
