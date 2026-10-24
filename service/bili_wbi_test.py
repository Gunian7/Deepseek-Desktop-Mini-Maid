#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B 站 WBI 签名可行性验证：nav 取 key -> 签名 -> 搜搜索/取音频流"""
import hashlib
import json
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]


def http_get(url, cookie=""):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Referer", "https://www.bilibili.com")
    if cookie:
        req.add_header("Cookie", cookie)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def get_wbi_keys(cookie):
    d = json.loads(http_get("https://api.bilibili.com/x/web-interface/nav", cookie))
    w = (d.get("data") or {}).get("wbi_img") or {}
    img = w["img_url"].rsplit("/", 1)[-1].split(".")[0]
    sub = w["sub_url"].rsplit("/", 1)[-1].split(".")[0]
    return img, sub


def mixin_key(img_key, sub_key):
    raw = img_key + sub_key
    return "".join(raw[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def wbi_sign(params, img_key, sub_key):
    mk = mixin_key(img_key, sub_key)
    p = dict(params)
    p["wts"] = int(time.time())
    p = dict(sorted(p.items()))
    # 过滤特殊字符
    p = {k: "".join(c for c in str(v) if c not in "!'()*") for k, v in p.items()}
    query = urllib.parse.urlencode(p)
    p["w_rid"] = hashlib.md5((query + mk).encode()).hexdigest()
    return urllib.parse.urlencode(p)


def main(cookie):
    img, sub = get_wbi_keys(cookie)
    print(f"[1] wbi keys: img={img[:12]}... sub={sub[:12]}...")

    # --- 搜索 ---
    q = {"search_type": "video", "keyword": "稻香 周杰伦", "page": 1}
    url = "https://api.bilibili.com/x/web-interface/wbi/search/type?" + wbi_sign(q, img, sub)
    try:
        d = json.loads(http_get(url, cookie))
        res = (d.get("data") or {}).get("result") or []
        print(f"[2] 搜索 code={d.get('code')} 结果={len(res)}")
        for r in res[:3]:
            title = (r.get("title") or "").replace('<em class="keyword">', "").replace("</em>", "")
            print(f"     {r.get('bvid')} | {title[:30]} | {r.get('duration')}")
        if not res:
            return
        bvid = res[0]["bvid"]
    except Exception as e:
        print(f"[2] 搜索失败: {e}")
        return

    # --- 取 cid ---
    try:
        d = json.loads(http_get(f"https://api.bilibili.com/x/player/pagelist?bvid={bvid}", cookie))
        cid = d["data"][0]["cid"]
        print(f"[3] cid={cid}")
    except Exception as e:
        print(f"[3] cid 失败: {e}")
        return

    # --- 取音频流 ---
    q2 = {"bvid": bvid, "cid": cid, "fnval": 16, "fourk": 1}
    url2 = "https://api.bilibili.com/x/player/wbi/playurl?" + wbi_sign(q2, img, sub)
    try:
        d = json.loads(http_get(url2, cookie))
        print(f"[4] playurl code={d.get('code')} msg={d.get('message')}")
        dash = (d.get("data") or {}).get("dash") or {}
        audio = dash.get("audio") or []
        print(f"     audio streams: {len(audio)}")
        if audio:
            a = sorted(audio, key=lambda x: x.get("bandwidth", 0))[-1]
            print(f"     最高码率 {a.get('bandwidth')} bps, codec={a.get('codecs')}")
            print(f"     url={a.get('baseUrl','')[:90]}...")
    except Exception as e:
        print(f"[4] playurl 失败: {e}")


if __name__ == "__main__":
    import sys
    ck = sys.argv[1] if len(sys.argv) > 1 else ""
    main(ck)
