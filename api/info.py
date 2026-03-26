"""
/api/info — Direct JSON endpoint for Blogger widget
Widget calls this directly, no Telegram polling needed.
"""

import tempfile # මේක උඩින්ම import කරගන්න

def get_ydl_opts(audio_only=False):
    opts = {
        'format': 'bestaudio/best' if audio_only else 'best',
        'noplaylist': True,
        'quiet': True,
    }

    # Cookies පරීක්ෂා කිරීම
    cookies_content = os.environ.get("YT_COOKIES")
    if cookies_content:
        # Vercel වල ලියන්න පුළුවන් එකම තැන /tmp
        tmp = tempfile.NamedTemporaryFile(delete=False, mode='w', dir='/tmp')
        tmp.write(cookies_content)
        tmp.close()
        opts['cookiefile'] = tmp.name

    return opts

def get_info(url, audio_only=False):
    ydl_opts = get_ydl_opts(audio_only)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # ... ඔයාගේ ඉතිරි code එක ...


import json, os, re, sys, subprocess
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

def pip(pkg):
    subprocess.check_call([sys.executable,"-m","pip","install",pkg,"-q"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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

def fmt_size(b):
    if not b or b<=0: return ""
    if b<1024**2: return f"{b/1024:.0f} KB"
    if b<1024**3: return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"

def fmt_dur(s):
    if not s: return ""
    h,r = divmod(int(s),3600); m,sec = divmod(r,60)
    return f"{h}:{m:02}:{sec:02}" if h else f"{m}:{sec:02}"

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
        r = requests.head(url, timeout=5, allow_redirects=True,
                          headers={"User-Agent":"Mozilla/5.0"})
        cl = r.headers.get("content-length")
        return int(cl) if cl else 0
    except: return 0

def get_info(url, audio_only=False):
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

    if not audio_only:
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
                            "size":sz,"size_fmt":fmt_size(sz)})
            if len(seen)>=4: break

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


class handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_OPTIONS(self):
        self.send_response(204)
        for k,v in CORS.items(): self.send_header(k,v)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        url        = (params.get("url",   [None])[0] or "").strip()
        audio_only = params.get("audio",  ["0"])[0] == "1"

        if not url:
            self._resp(400, {"ok":False,"error":"Missing ?url= parameter"})
            return
        try:
            data = get_info(url, audio_only=audio_only)
            self._resp(200, {"ok":True, **data})
        except yt_dlp.utils.DownloadError as e:
            err = str(e)
            if "bot" in err.lower() or "sign in" in err.lower():
                msg = "YouTube bot detection — VPN try කරන්න හෝ ටිකක් ඉඳලා retry."
            elif "private" in err.lower():
                msg = "Video private / restricted."
            elif "unavailable" in err.lower():
                msg = "Video unavailable (deleted / region blocked)."
            else:
                msg = err[:300]
            self._resp(422, {"ok":False,"error":msg})
        except Exception as e:
            self._resp(500, {"ok":False,"error":str(e)[:300]})

    def _resp(self, status, body):
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        for k,v in CORS.items(): self.send_header(k,v)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
