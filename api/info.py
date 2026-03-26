import json, os, re, sys, subprocess, tempfile
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

def pip(pkg):
    try:
        subprocess.check_call([sys.executable,"-m","pip","install",pkg,"-q"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except: pass

try: import yt_dlp
except ImportError: pip("yt-dlp"); import yt_dlp

try: import requests
except ImportError: pip("requests"); import requests

CORS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

def get_cookie_file():
    # 1. මුලින්ම බලනවා Environment Variable එකේ cookies තියෙනවද කියලා
    cookie_data = os.environ.get("YT_COOKIES")

    # 2. එහෙම නැත්නම් මේ පහත තියෙන variable එකට direct cookies දාන්න පුළුවන්
    if not cookie_data:
        cookie_data = """# Netscape HTTP Cookie File
.youtube.com	TRUE	/	TRUE	1790084856	LOGIN_INFO	AFmmF2swRQIhAKaFU5ML7QEJdOjgkFHmdMmSKEaZrGOCp0g1LXAn1qmhAiBiZTOcoJZEhixFl8kPThGLWMtJYsfwtsM_TO7Cz7wOWQ:QUQ3MjNmemRJaElCQ1d2OXFnblhEUnp5R1diRU96NG4yNFpianRJay1EbEFkWldVc2FYRnBNd1duaEFDOW9QcjNHS080bk1XZ0F1Ni04TzNocUxENXpnZ0dhbG5DRFVrRU5UejlidEE2WWhoLTdfaDJZVFlDem1"""

    if not cookie_data or len(cookie_data) < 10: return None

    try:
        fd, path = tempfile.mkstemp(suffix=".txt", dir="/tmp")
        with os.fdopen(fd, 'w') as tmp:
            tmp.write(cookie_data)
        os.chmod(path, 0o644)
        return path
    except: return None

# ... (ඉතිරි functions ඔක්කොම කලින් වගේමයි)

def fmt_size(b):
    if not b or b<=0: return ""
    if b<1024**2: return f"{b/1024:.0f} KB"
    if b<1024**3: return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"

def fmt_dur(s):
    if not s: return ""
    try:
        h,r = divmod(int(s),3600); m,sec = divmod(r,60)
        return f"{h}:{m:02}:{sec:02}" if h else f"{m}:{sec:02}"
    except: return ""

def quality_label(h):
    if not h: return "Best"
    s = f"{h}p"
    if h>=2160: s+=" 4K"
    elif h>=1080: s+=" Full HD"
    elif h>=720:  s+=" HD"
    elif h>=480:  s+=" SD"
    return s

def head_size(url):
    try:
        r = requests.head(url, timeout=5, allow_redirects=True, headers={"User-Agent":"Mozilla/5.0"})
        cl = r.headers.get("content-length")
        return int(cl) if cl else 0
    except: return 0

def get_info(url, audio_only=False):
    cookie_path = get_cookie_file()
    opts = {
        "quiet": True, "no_warnings": True,
        "skip_download": True, "noplaylist": True,
        "cookiefile": cookie_path,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "po_token": ["web+guest"]
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        fmts = info.get("formats", [])
        options = []
        seen = set()

        if not audio_only:
            combined = [f for f in fmts if f.get("vcodec") not in (None,"none") and f.get("acodec") not in (None,"none") and f.get("url")]
            combined.sort(key=lambda f: f.get("height") or 0, reverse=True)
            for f in combined:
                h = f.get("height") or 0
                if h in seen: continue
                seen.add(h)
                sz = f.get("filesize") or f.get("filesize_approx") or head_size(f["url"])
                options.append({"type":"video","label":quality_label(h),"ext":f.get("ext","mp4"),"url":f["url"],"size":sz,"size_fmt":fmt_size(sz)})
                if len(seen)>=4: break

        af = [f for f in fmts if f.get("vcodec") in (None,"none") and f.get("acodec") not in (None,"none") and f.get("url")]
        af.sort(key=lambda f: f.get("abr") or 0, reverse=True)
        if af:
            a = af[0]
            sz = a.get("filesize") or a.get("filesize_approx") or head_size(a["url"])
            options.append({"type":"audio","label":"Audio Only (MP3)","ext":a.get("ext","m4a"),"url":a["url"],"size":sz,"size_fmt":fmt_size(sz)})

        return {"title":info.get("title","Video"), "thumbnail":info.get("thumbnail",""), "dur_fmt":fmt_dur(info.get("duration")), "options":options}
    finally:
        if cookie_path and os.path.exists(cookie_path):
            try: os.remove(cookie_path)
            except: pass

class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_OPTIONS(self):
        self.send_response(204)
        for k,v in CORS.items(): self.send_header(k,v)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        url = (params.get("url", [None])[0] or "").strip()

        if not url:
            self._resp(400, {"ok":False, "error":"Missing ?url= parameter"})
            return

        try:
            data = get_info(url)
            self._resp(200, {"ok":True, **data})
        except Exception as e:
            self._resp(500, {"ok":False, "error":str(e)[:200]})

    def _resp(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        for k,v in CORS.items(): self.send_header(k,v)
        self.send_header("Content-Length", len(payload))
        self.end_headers()
        self.wfile.write(payload)
