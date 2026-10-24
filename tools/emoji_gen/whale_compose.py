#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大肥鱼表情资源 合成管线
========================
角色：来自 https://github.com/aceice01/dsh-whale-pet (lib/anim/*.gif, 192x208 RGBA)
      角色素材原作者见该仓库致谢（codex-pet-DeepSeek-girl），非商业使用。
场景/道具/特效：本脚本用 Pillow 绘制，遮住素材的硬切边并补足情绪信息。

输出：Arcs-Mini3 表情资源 —— 每个情绪目录 frame-%06d.png，200x104 透明 PNG
"""
import os
import math
import sys
from PIL import Image, ImageDraw, ImageFilter, ImageChops

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dafeiyu_v2 as D   # 复用配色、Pen、桌面/道具/特效绘制

SS = 4
W, H = 200, 104
CW, CH = W * SS, H * SS

ANIM_DIR = r"F:\Output\LS26-ArcsMini3\work\ref\codex-pet-DeepSeek-girl-main\previews"

# 裁切与放置参数（来自视觉评审：y 从 8 上调到 6，底部用桌面遮硬边）
CROP = (4, 6, 188, 110)     # 184 x 104
ROLE_H = 100                # 缩放后高度（像素）
ROLE_W = None               # 自动按比例
ROLE_POS = (10, 2)          # 左上角放置位置

_cache = {}


def load_frames(name):
    """读 GIF 全部帧 -> [RGBA, ...]；支持 "a+b" 拼接多个动画"""
    if name in _cache:
        return _cache[name]
    from PIL import ImageSequence

    if "+" in name:
        frames = []
        for part in name.split("+"):
            frames.extend(load_frames(part.strip()))
        _cache[name] = frames
        return frames

    im = Image.open(os.path.join(ANIM_DIR, f"{name}.gif"))
    frames = []
    for fr in ImageSequence.Iterator(im):
        frames.append(fr.convert("RGBA"))
    _cache[name] = frames
    return frames


def despill_green(im):
    """压掉绿幕抠图残留：G 超过 max(R,B) 的部分直接削平。

    蓝发(b>g)、白领(r=g=b) 不受影响；只有那些本不该存在的绿色边缘被压掉。
    """
    r, g, b, a = im.split()
    rb_max = ImageChops.lighter(r, b)
    g_fixed = ImageChops.darker(g, rb_max)
    return Image.merge("RGBA", (r, g_fixed, b, a))


def role_layer(fr):
    """去绿边 -> 裁切 -> 等比缩放 -> 放到 4x 画布上；顺手清理抠图白边"""
    fr = despill_green(fr.convert("RGBA"))
    crop = fr.crop(CROP)
    h = ROLE_H
    w = int(round(crop.width * h / crop.height))
    small = crop.resize((w, h), Image.LANCZOS)
    big = small.resize((w * SS, h * SS), Image.LANCZOS)
    # 去白边：alpha 轻微收缩 1px（超采样空间 3px），边缘不再有亮圈
    r, g, b, a = big.split()
    a = a.filter(ImageFilter.MinFilter(3))
    big = Image.merge("RGBA", (r, g, b, a))
    return big, w


def compose(fr, prop="rice", fx=None, t=0.0, bob=0.0, tint=None, hsway=0.0):
    """
    fr    : 素材帧 RGBA(192x208)
    prop  : rice / rice_full / rice_empty
    fx    : None / zzz / anger / note / spark / bubble / tear / charge / wave
    tint  : None 或 (r,g,b) 用于整体偏色（区分复用同一动画的情绪）
    """
    canvas = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    big, w = role_layer(fr)
    if tint is not None:
        solid = Image.new("RGBA", big.size, tint + (255,))
        big = Image.blend(big, Image.composite(solid, big, big.split()[3]), 0.14)

    px = int(D.s(ROLE_POS[0] + hsway))
    py = int(D.s(ROLE_POS[1] + bob))

    # 桌面投影（角色后方，先在空白画布上画模糊椭圆，再叠角色）
    shadow = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.ellipse([int(D.s(20)), int(D.s(86)), int(D.s(180)), int(D.s(112))],
               fill=(120, 92, 64, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(D.s(3)))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(big, (px, py))

    # 角色底部接触阴影：在角色 alpha 内、靠下区域压暗，弱化硬切
    band = Image.new("RGBA", big.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    for i in range(14):
        yy = big.size[1] - 14 * SS + i * SS
        alpha = int(90 * (i / 14.0))
        bd.rectangle([0, yy, big.size[0], yy + SS], fill=(60, 44, 80, alpha))
    band = band.filter(ImageFilter.GaussianBlur(SS))
    band.putalpha(Image.composite(band.split()[3], Image.new("L", big.size, 0), big.split()[3]))
    canvas.alpha_composite(band, (px, py))

    d = ImageDraw.Draw(canvas)
    p = D.Pen(d)

    # 桌面（遮住素材底部的硬切边）
    d.rectangle([0, D.s(92), CW, CH], fill=D.WOOD)
    d.rectangle([0, D.s(92), CW, D.s(95)], fill=D.WOOD_D)
    d.rectangle([0, D.s(92), CW, D.s(93)], fill=(150, 122, 92))
    p.line([(0, 92), (200, 92)], D.LINE, 1.0)

    # 道具
    if prop == "steal_eat":
        # 待机偷吃白饭：碗里的饭随进度递减，嘴边挂饭粒，偶尔冒"嚼"符号。
        # 角色素材本身是正面坐姿（没有"低头扒饭"的帧），所以偷吃全靠道具来讲：
        # 饭在变少 + 她嘴上沾着饭 + 嚼嚼符号。
        cx, cy, rx, ry = 30, 98, 26, 6.6
        p.ell(cx, cy, rx, ry, D.BOWL_L, lw=1.2)
        p.ell(cx, cy - 2, rx - 2, ry - 1, D.BOWL, outline=None)
        p.ell(cx, cy + 4, rx - 4, 2.4, (150, 122, 92), outline=None)

        remain = max(0.06, 1.0 - t * 0.92)
        if remain > 0.01:
            h = 8.0 * remain
            p.ell(cx, cy - 4 * remain, (rx - 3) * (0.55 + 0.45 * remain), h, D.RICE, lw=1.0)
            # 饭粒堆（数量随剩余量减少）
            grains = [(dx, dy) for dx, dy in
                      [(-11, -1.5), (0, -3.5), (11, -1.5), (-6, 2), (7, 2), (-3, -6), (4, -5)]]
            keep = max(1, int(len(grains) * remain))
            for dx, dy in grains[:keep]:
                p.ell(cx + dx, cy - 5 * remain + dy * remain, 4.0, 2.7, D.RICE, outline=None)
            # 热气只在饭还多的时候冒
            if remain > 0.5:
                for i, off in enumerate((0, 8, 16)):
                    yy = cy - 14 - off * 0.7 - math.sin(t * 2.2 + i) * 1.4
                    p.arc(cx - 9 + i * 5, yy - 6, cx - 1 + i * 5, yy + 4, 200, 340, D.WHITE, 1.4)
        # 嚼东西：腮帮子快速交替鼓起（比"嘴边饭粒"明显得多——白色饭粒贴在白脸上根本看不见）
        if 0.2 < t < 0.9:
            chew = math.sin(t * 34)
            r = 4.2 + 1.8 * chew
            p.ell(119, 60, r, r * 0.82, (255, 209, 194), lw=0.9)
            p.ell(81, 60, 3.4 - 1.2 * chew, 2.6, (255, 209, 194), lw=0.7)

        # 嘴角外挂一粒米：用米黄 + 深棕描边，压在脸的下缘（背景是深色衣服才看得见）
        if 0.3 < t < 0.8:
            p.ell(104, 67, 3.2, 2.6, (250, 240, 198), lw=0.9)

        # "嚼"符号：两根短竖线 + 小点，模仿咀嚼
        if 0.3 < t < 0.75 and int(t * 10) % 2 == 0:
            bx, by = 150, 20
            p.line([(bx, by), (bx + 2, by + 6)], D.HAIR_L, 1.2)
            p.line([(bx + 5, by), (bx + 7, by + 6)], D.HAIR_L, 1.2)
            p.ell(bx + 11, by + 3, 1.6, 1.6, D.HAIR_L, outline=None)

    elif prop in ("rice", "rice_full", "rice_empty"):
        # 饭碗放大到 1.4x，靠近角色
        cx, cy, rx, ry = 30, 98, 26, 6.6
        p.ell(cx, cy, rx, ry, D.BOWL_L, lw=1.2)
        p.ell(cx, cy - 2, rx - 2, ry - 1, D.BOWL, outline=None)
        # 碗底接触阴影
        p.ell(cx, cy + 4, rx - 4, 2.4, (150, 122, 92), outline=None)
        if prop != "rice_empty":
            p.ell(cx, cy - 4, rx - 3, 8.0, D.RICE, lw=1.1)
            for dx, dy in [(-11, -1.5), (0, -3.5), (11, -1.5), (-6, 2), (7, 2)]:
                p.ell(cx + dx, cy - 5 + dy, 4.2, 2.8, D.RICE, outline=None)
            for i, off in enumerate((0, 8, 16)):
                yy = cy - 14 - off * 0.7 - math.sin(t * 2.2 + i) * 1.4
                p.arc(cx - 9 + i * 5, yy - 6, cx - 1 + i * 5, yy + 4, 200, 340, D.WHITE, 1.4)
        else:
            p.ell(cx, cy - 4, rx - 5, 5.0, (30, 42, 90), outline=None)

    if prop == "rice_full":
        for dx, dy, r in [(0, 0, 4.4), (7, 1.2, 3.6), (-6, 1.4, 3.2), (2, 4, 3.6)]:
            p.ell(170 + dx, 96 + dy, r, r * 0.8, D.NOTE, lw=0.8)

    # 特效
    if fx:
        draw_fx(p, fx, t, bob)

    return canvas.resize((W, H), Image.LANCZOS)


def draw_fx(p, kind, t=0.0, bob=0.0):
    """情绪符号（画在角色右上/头顶）"""
    if kind == "zzz":
        for i, (dx, dy, sz) in enumerate([(0, 0, 1.0), (9, -8, 0.78), (16, -16, 0.58)]):
            x, y, w = 150 + dx, 22 + dy, 6 * sz
            p.line([(x, y), (x + w, y)], D.HAIR_L, 1.4 * sz)
            p.line([(x + w, y), (x, y + w)], D.HAIR_L, 1.4 * sz)
            p.line([(x, y + w), (x + w, y + w)], D.HAIR_L, 1.4 * sz)
    elif kind == "anger":
        x, y = 152, 24
        p.line([(x - 6, y), (x + 6, y)], D.RED, 1.9)
        p.line([(x, y - 6), (x, y + 6)], D.RED, 1.9)
        p.line([(x - 4, y - 4), (x + 4, y + 4)], D.RED, 1.3)
        p.line([(x + 4, y - 4), (x - 4, y + 4)], D.RED, 1.3)
    elif kind == "wave":
        # 声波（说话专用，区别于等待的省略号气泡）
        bx, by = 158, 22
        for i, r in enumerate((3.0, 6.0, 9.0)):
            a = 120 + i * 40
            p.arc(bx - r, by - r, bx + r, by + r, 300, 60, D.HAIR_L, 1.2)
        p.ell(bx - 2, by, 1.6, 1.6, D.HAIR_M, outline=None)
    elif kind == "note":
        x, y = 164, 24
        p.ell(x, y + 5, 3.4, 2.8, D.HAIR_M, lw=0.9)
        p.line([(x + 3, y + 5), (x + 3, y - 3)], D.HAIR_M, 1.3)
        p.line([(x + 3, y - 3), (x + 7, y - 2)], D.HAIR_M, 1.2)
    elif kind == "spark":
        for dx, dy, r in [(0, 0, 4.4), (-11, 7, 2.8), (8, -8, 2.4)]:
            x, y = 164 + dx, 22 + dy
            p.line([(x - r, y), (x + r, y)], D.NOTE, 1.3)
            p.line([(x, y - r), (x, y + r)], D.NOTE, 1.3)
    elif kind == "bubble":
        bx, by = 166, 24 + math.sin(t * 3) * 1.6
        p.ell(bx, by, 13, 8.5, D.WHITE, lw=1.0)
        p.poly([(bx - 9, by + 6), (bx - 14, by + 13), (bx - 3, by + 7)], D.WHITE, lw=0.9)
        for i in range(3):
            p.ell(bx - 5 + i * 5, by, 1.4, 1.4, D.HAIR_M, outline=None)
    elif kind == "tear":
        for dx, dy in [(0, 0), (6, 9), (3, 18)]:
            x, y = 74 + dx, 62 + dy
            p.poly([(x, y - 4), (x + 2.2, y + 1), (x, y + 3), (x - 2.2, y + 1)],
                   (150, 200, 255), lw=0.6)
    elif kind == "charge":
        # 电量/吃 token：右上角三段电池
        x, y = 156, 16
        p.rrect(x, y, x + 26, y + 12, 2, D.WHITE, lw=1.0)
        p.rrect(x + 26, y + 4, x + 29, y + 8, 1, D.WHITE, lw=1.0)
        for i in range(3):
            p.rrect(x + 2 + i * 7, y + 2, x + 6 + i * 7, y + 10, 1, D.HAIR_L, outline=None)


# ---------------- 情绪 → 素材动画映射 ----------------
# (gif名, 道具, 特效, 染色)
# 9 组动画尽量一对一，避免两个情绪共用一个动作导致看起来重复。
#   idle         呼吸/眨眼/歪头      -> 待机
#   waving       挥手招呼            -> 聆听（"我听着呢"）
#   running      正面跑来/急切       -> 说话
#   jumping      蹦跳                -> 大笑
#   running-right 活泼向右           -> 开心
#   running-left  朝左走开/气冲冲    -> 生气
#   failed       失败慌张/低落       -> 伤心
#   review       端详/托腮思考       -> 等待
#   waiting      摊手等待            -> 充电（等着充满）
MOOD_MAP = {
    "待机": ("idle",         "steal_eat",  None,     None),
    "大笑": ("jumping",      "rice_full",  "note",   None),
    "开心": ("running-right+running-left", "rice_full", "spark", None),
    "聆听": ("waving",       "rice",       "spark",  None),
    "生气": ("running-left", "rice",       "anger",  None),
    "伤心": ("failed",       "rice_empty", "tear",   None),
    "充电": ("waiting",      "rice_full",  "charge", None),
    "等待": ("review",       "rice",       "bubble", None),
    "休眠": ("idle",         "rice",       "zzz",    (70, 90, 170)),
    "说话": ("running",      "rice",       "wave",   None),
}

# emoji.json 里各情绪要求的帧数（range 决定），不够就循环补
FRAME_NEED = {
    "待机": 20, "充电": 2, "聆听": 10, "说话": 10, "休眠": 9,
    "等待": 10, "开心": 16, "伤心": 10, "生气": 8, "大笑": 10,
}


def build(outdir, only=None):
    os.makedirs(outdir, exist_ok=True)
    for mood, (gif, prop, fx, tint) in MOOD_MAP.items():
        if only and mood not in only:
            continue
        frames = load_frames(gif)
        need = FRAME_NEED[mood]
        sub = os.path.join(outdir, mood)
        os.makedirs(sub, exist_ok=True)
        for f in os.listdir(sub):
            if f.endswith(".png"):
                os.remove(os.path.join(sub, f))
        for i in range(need):
            src = frames[i % len(frames)]
            t = i / max(1, need)
            bob = 0.0
            hsway = 0.0
            if gif == "jumping":
                bob = -abs(math.sin(t * math.pi * 2)) * 1.5
            if "+" in gif:
                # 左右跑：水平正弦位移 ±5px，让"往左/往右"在画面上真的动起来
                hsway = math.sin(t * math.pi * 2) * 10.0
            img = compose(src, prop, fx, t, bob, tint, hsway)
            img.save(os.path.join(sub, f"frame-{i:06d}.png"))
        print(f"{mood:4s} <- {gif:8s} frames={need} (src {len(frames)})")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "./out3"
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    build(out, only)
