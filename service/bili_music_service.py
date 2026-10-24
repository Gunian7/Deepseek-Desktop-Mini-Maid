#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B 站音乐中转服务（给 Arcs-Mini3 用）

为什么需要它：B 站的 search / playurl 接口强制 WBI 签名，设备端算不了（要 MD5 + 混淆表），
所以让电脑算签名、拿直链，设备只负责拉 URL 播放。

实测（2026-10-24）：
  - 不带 WBI 签名 -> HTTP 412 反爬页
  - 带 WBI 签名   -> search/type 200，playurl 200
  - 拿到的 mcdn CDN 直链【不校验 Referer】，裸请求也 200，所以设备可以直接播

接口：
  GET /play?q=稻香          -> {"ok":true,"title":"...","url":"https://...","duration":224}
  GET /search?q=稻香&n=5    -> {"ok":true,"items":[{"title","bvid","url"}...]}
  GET /health               -> {"ok":true}
"""
import hashlib
import json
import re
import sys
import time
import threading
import urllib.parse
import urllib.request
import uuid
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
REFERER = "https://www.bilibili.com"
PORT = 8000
MAX_SECONDS = 600           # 超过 10 分钟的多半是合集/直播回放，转码慢且没意义
LAN_IP = "10.43.131.195"        # 设备要能访问到的地址，换网络时改这里
_stream_cache = {}              # token -> 本地 mp3 路径
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# WBI 混淆表（B 站固定）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]

_lock = threading.Lock()
_state = {"cookie": "", "img": "", "sub": "", "ts": 0}


def http_get(url, cookie=None, timeout=20):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", REFERER)
    ck = cookie if cookie is not None else _state["cookie"]
    if ck:
        req.add_header("Cookie", ck)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def refresh_credentials():
    """取一次首页 cookie（buvid3），再从 nav 拿 WBI keys。"""
    with _lock:
        if _state["img"] and time.time() - _state["ts"] < 3600:
            return
        # 1) 拿 cookie
        try:
            req = urllib.request.Request("https://www.bilibili.com/")
            req.add_header("User-Agent", UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.headers.get_all("Set-Cookie") or []
            cookie = "; ".join(c.split(";")[0] for c in raw if "=" in c)
        except Exception:
            cookie = ""
        # 2) 拿 wbi keys（未登录也返回 keys）
        d = json.loads(http_get("https://api.bilibili.com/x/web-interface/nav",
                                cookie=cookie))
        w = (d.get("data") or {}).get("wbi_img") or {}
        img = w["img_url"].rsplit("/", 1)[-1].split(".")[0]
        sub = w["sub_url"].rsplit("/", 1)[-1].split(".")[0]
        _state.update({"cookie": cookie, "img": img, "sub": sub, "ts": time.time()})
        print(f"[wbi] refreshed cookie={bool(cookie)} img={img[:8]}…", flush=True)


def wbi_sign(params):
    mk_raw = _state["img"] + _state["sub"]
    mk = "".join(mk_raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]
    p = dict(params)
    p["wts"] = int(time.time())
    p = dict(sorted(p.items()))
    p = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in p.items()}
    query = urllib.parse.urlencode(p)
    p["w_rid"] = hashlib.md5((query + mk).encode()).hexdigest()
    return urllib.parse.urlencode(p)


def clean_title(t):
    return re.sub(r"<[^>]+>", "", t or "").strip()


def search_videos(keyword, limit=5):
    refresh_credentials()
    url = ("https://api.bilibili.com/x/web-interface/wbi/search/type?"
           + wbi_sign({"search_type": "video", "keyword": keyword}))
    d = json.loads(http_get(url))
    if d.get("code") != 0:
        raise RuntimeError(f"search code={d.get('code')} {d.get('message')}")
    res = [r for r in ((d.get("data") or {}).get("result") or []) if r.get("type") == "video"]
    out = []
    for r in res:
        if len(out) >= limit:
            break
        secs = 0
        m = re.match(r"(\d+):(\d+)", str(r.get("duration") or ""))
        if m:
            secs = int(m.group(1)) * 60 + int(m.group(2))
        if secs > MAX_SECONDS:
            continue        # 合集/直播回放，跳过长音频
        out.append({
            "title": clean_title(r.get("title")),
            "bvid": r.get("bvid"),
            "author": r.get("author"),
            "duration": secs,
        })
    return out


def audio_url(bvid):
    refresh_credentials()
    d = json.loads(http_get(f"https://api.bilibili.com/x/player/pagelist?bvid={bvid}"))
    cid = d["data"][0]["cid"]
    url = ("https://api.bilibili.com/x/player/wbi/playurl?"
           + wbi_sign({"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1}))
    d = json.loads(http_get(url))
    if d.get("code") != 0:
        raise RuntimeError(f"playurl code={d.get('code')} {d.get('message')}")
    dash = (d.get("data") or {}).get("dash") or {}
    audio = dash.get("audio") or []
    if not audio:
        raise RuntimeError("no dash audio stream")
    # 设备 PSRAM 只有 8MB（AP 核 3MB），最高码率那档一首歌 6MB+ 撑不住；
    # 1.5 寸屏的小喇叭也不需要 320kbps，取最低档。
    a = min(audio, key=lambda x: x.get("bandwidth", 0))
    return a.get("baseUrl") or a.get("base_url"), a.get("bandwidth"), cid


def get_mp3(bvid, src_url):
    """把 B 站的 m4s(AAC) 转成 mp3。

    为什么转：固件里的提示音全是 mp3，说明 mp3 解码一定没问题；
    而直接把 m4s 流给设备，它会立刻断开连接（实测 ConnectionReset）。
    一首歌 2MB 转码约 1~3 秒，转好缓存，重复点同一首就不用再转。
    """
    path = os.path.join(CACHE_DIR, f"{bvid}.mp3")
    if os.path.exists(path) and os.path.getsize(path) > 20000:
        print(f"[cache] hit {bvid}", flush=True)
        return path

    t0 = time.time()
    req = urllib.request.Request(src_url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", REFERER)
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()

    tmp = path + ".tmp"
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", "pipe:0", "-vn",
         "-f", "mp3", "-b:a", "96k", "-ar", "44100", "-ac", "2", tmp],
        input=data, capture_output=True, timeout=180)
    if proc.returncode != 0 or not os.path.exists(tmp):
        err = (proc.stderr or b"")[:300].decode("utf-8", "replace")
        raise RuntimeError(f"ffmpeg failed: {err}")
    os.replace(tmp, path)
    print(f"[transcode] {bvid} {len(data)}B -> {os.path.getsize(path)}B in {time.time()-t0:.1f}s", flush=True)
    return path


def video_info(bvid):
    """按 bvid 取标题/时长，供列表点播用。"""
    url = ("https://api.bilibili.com/x/web-interface/view"
           f"?bvid={bvid}")
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", REFERER)
    with urllib.request.urlopen(req, timeout=15) as r:
        d = json.loads(r.read().decode("utf-8"))
    if d.get("code") != 0:
        raise RuntimeError(f"view {d.get('code')}: {d.get('message')}")
    v = d["data"]
    return {
        "title": v.get("title", ""),
        "author": (v.get("owner") or {}).get("name", ""),
        "duration": v.get("duration", 0),
        "bvid": bvid,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[http] {self.address_string()} {fmt % args}", flush=True)

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path):
        """标准文件服务，支持 Range。设备播放器做 seek / 分片请求时必须支持。"""
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        try:
            if rng and rng.startswith("bytes="):
                part = rng[6:].split("-")
                start = int(part[0]) if part[0] else 0
                end = int(part[1]) if len(part) > 1 and part[1] else size - 1
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(path, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))
                print(f"[range] {start}-{end}/{size}", flush=True)
            else:
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(64 * 1024)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                print(f"[file] sent {size} bytes", flush=True)
        except (BrokenPipeError, ConnectionResetError):
            print("[file] client closed", flush=True)
        except Exception as e:
            print(f"[file] error {type(e).__name__}: {e}", flush=True)

    def _proxy(self, src):
        """把 B 站的 m4s 音频流边下边转给设备，设备只看到一个短 URL。"""
        req = urllib.request.Request(src)
        req.add_header("User-Agent", UA)
        req.add_header("Referer", REFERER)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                total = r.headers.get("Content-Length")
                self.send_response(200)
                self.send_header("Content-Type", "audio/mp4")
                self.send_header("Accept-Ranges", "none")
                if total:
                    self.send_header("Content-Length", total)
                self.end_headers()
                sent = 0
                while True:
                    chunk = r.read(32 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    sent += len(chunk)
                print(f"[stream] done {sent} bytes", flush=True)
        except BrokenPipeError:
            print("[stream] client closed", flush=True)
        except Exception as e:
            print(f"[stream] error {type(e).__name__}: {e}", flush=True)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        q = (qs.get("q") or [""])[0].strip()

        try:
            if parsed.path == "/health":
                return self._json({"ok": True, "port": PORT})

            if parsed.path == "/play":
                # 列表点播：直接按 bvid 播放（列表里选定那首）
                bvid = qs.get("bv", [""])[0]
                if bvid:
                    t0 = time.time()
                    try:
                        it = video_info(bvid)
                    except Exception as e:
                        return self._json({"ok": False, "error": f"view failed: {e}"}, 502)
                    src, bw, cid = audio_url(bvid)
                    local = get_mp3(bvid, src)
                    token = uuid.uuid4().hex[:12]
                    _stream_cache[token] = local
                    print(f"[play-bv] {bvid} {it['title'][:24]} {time.time()-t0:.1f}s", flush=True)
                    return self._json({
                        "ok": True,
                        "title": it["title"],
                        "author": it["author"],
                        "duration": it["duration"],
                        "url": f"http://{LAN_IP}:{PORT}/stream/{token}",
                        "bitrate": bw,
                    })

                if not q:
                    return self._json({"ok": False, "error": "missing q"}, 400)
                t0 = time.time()
                items = search_videos(q, limit=1)
                if not items:
                    return self._json({"ok": False, "error": "no result"}, 404)
                it = items[0]
                src, bw, cid = audio_url(it["bvid"])
                # 转成 mp3 再给设备（m4s 设备不收），本地缓存
                local = get_mp3(it["bvid"], src)
                token = uuid.uuid4().hex[:12]
                _stream_cache[token] = local
                short = f"http://{LAN_IP}:{PORT}/stream/{token}"
                print(f"[play] '{q}' -> {it['title'][:30]} ({bw}bps) {time.time()-t0:.1f}s token={token}", flush=True)
                return self._json({
                    "ok": True,
                    "title": it["title"],
                    "author": it["author"],
                    "duration": it["duration"],
                    "url": short,
                    "bitrate": bw,
                })

            if parsed.path == "/search":
                if not q:
                    return self._json({"ok": False, "error": "missing q"}, 400)
                n = int((qs.get("n") or ["5"])[0])
                items = search_videos(q, limit=max(1, min(n, 10)))
                for it in items:
                    it["url"], _, _ = audio_url(it["bvid"])
                return self._json({"ok": True, "items": items})

            if parsed.path.startswith("/stream/"):
                token = parsed.path.rsplit("/", 1)[-1]
                path = _stream_cache.get(token)
                if not path or not os.path.exists(path):
                    return self._json({"ok": False, "error": "token expired"}, 404)
                self._serve_file(path)
                return

            return self._json({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            print(f"[err] {type(e).__name__}: {e}", flush=True)
            return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 500)


def main():
    print(f"B 站音乐中转服务启动： http://0.0.0.0:{PORT}")
    print(f"  健康检查 http://127.0.0.1:{PORT}/health")
    refresh_credentials()
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
