#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大肥鱼（DeepSeek 鲸鱼娘）表情资源生成器 v2  —— Arcs-Mini3 200x104 透明 PNG

v2 相对 v1 的修正（针对视觉评审）：
  - 全部部件加深蓝描边，结构可读
  - 头发分缕：后发 + 三层锯齿刘海 + 两侧垂发
  - 头鳍改成明确的三角带弧鳍，长在头两侧偏上，带鳍条
  - 鲸尾改成宽大左右分叉，位于身后右侧，从桌面后伸出
  - 补肩/手臂/围裙，抱白饭碗
  - 加眉毛，眼型随情绪改变（睁/弯/怒/半闭/垂）
  - 蓝色分 4 级明度：发/尾/衣/装饰

规格：透明 RGBA PNG，200x104，frame-%06d.png
"""
import os
import math
import sys
from PIL import Image, ImageDraw

SS = 4
W, H = 200, 104
CW, CH = W * SS, H * SS

# ---------- 配色（4 级蓝 + 肤色）----------
LINE     = (27, 42, 90)      # 统一描边
HAIR_D   = (44, 74, 150)
HAIR_M   = (72, 118, 206)
HAIR_L   = (118, 168, 240)
HAIR_HI  = (186, 218, 253)
SKIN     = (255, 231, 219)
SKIN_SH  = (243, 200, 180)
EYE_IRIS = (36, 92, 212)
EYE_DEEP = (20, 48, 130)
WHITE    = (255, 255, 255)
MOUTH    = (206, 96, 104)
MOUTH_IN = (150, 54, 66)
BLUSH    = (255, 152, 152)
BLUSH_A  = (255, 130, 130)
DRESS_D  = (30, 44, 92)
DRESS    = (46, 66, 132)
APRON    = (247, 250, 255)
TAIL_D   = (46, 82, 168)
TAIL_M   = (78, 122, 208)
TAIL_L   = (126, 170, 240)
RICE     = (253, 253, 249)
RICE_SH  = (214, 222, 236)
BOWL     = (40, 56, 116)
BOWL_L   = (96, 122, 196)
WOOD     = (206, 176, 142)
WOOD_D   = (172, 142, 110)
RED      = (236, 86, 86)
NOTE     = (255, 242, 206)


def s(v):
    return v * SS


def P(x, y):
    return (s(x), s(y))


class Pen:
    def __init__(self, d, lw=1.1):
        self.d = d
        self.lw = lw

    def ell(self, cx, cy, rx, ry, fill, outline=LINE, lw=None):
        w = int((lw if lw is not None else self.lw) * SS)
        self.d.ellipse([s(cx - rx), s(cy - ry), s(cx + rx), s(cy + ry)],
                       fill=fill, outline=outline, width=w)

    def poly(self, pts, fill, outline=LINE, lw=None):
        w = int((lw if lw is not None else self.lw) * SS)
        self.d.polygon([P(x, y) for x, y in pts], fill=fill, outline=outline, width=w)

    def rrect(self, x1, y1, x2, y2, r, fill, outline=LINE, lw=None):
        w = int((lw if lw is not None else self.lw) * SS)
        self.d.rounded_rectangle([s(x1), s(y1), s(x2), s(y2)], radius=s(r),
                                 fill=fill, outline=outline, width=w)

    def line(self, pts, fill, lw=1.2):
        self.d.line([P(x, y) for x, y in pts], fill=fill,
                    width=int(lw * SS), joint="curve")

    def arc(self, x1, y1, x2, y2, a1, a2, fill, lw=1.2):
        self.d.arc([s(x1), s(y1), s(x2), s(y2)], a1, a2, fill=fill,
                   width=int(lw * SS))


# ---------- 角色 ----------

def draw_tail(p, sway=0.0):
    """鲸尾：身后右侧，宽大左右分叉"""
    bx, by = 122, 90
    tipx = 158 + sway * 3
    tipy = 62 - sway * 2

    # 尾柄（从身体后伸向右侧）
    p.poly([(bx - 2, by - 2), (tipx - 6, tipy + 6), (tipx + 2, tipy + 12),
            (bx + 4, by + 6)], TAIL_M, lw=1.2)
    # 尾柄高光
    p.poly([(bx + 2, by + 1), (tipx - 4, tipy + 8), (tipx - 1, tipy + 11),
            (bx + 3, by + 4)], TAIL_L, outline=None)

    # 上尾鳍
    up = [(tipx - 2, tipy + 8), (tipx + 12, tipy - 8), (tipx + 20, tipy - 2),
          (tipx + 12, tipy + 6), (tipx + 4, tipy + 12)]
    p.poly(up, TAIL_D, lw=1.3)
    p.poly([(tipx + 2, tipy + 6), (tipx + 12, tipy - 6), (tipx + 17, tipy - 1),
            (tipx + 8, tipy + 6)], TAIL_L, outline=None)

    # 下尾鳍
    dn = [(tipx + 2, tipy + 12), (tipx + 16, tipy + 16), (tipx + 20, tipy + 26),
          (tipx + 8, tipy + 22)]
    p.poly(dn, TAIL_D, lw=1.3)
    p.poly([(tipx + 6, tipy + 14), (tipx + 15, tipy + 18), (tipx + 17, tipy + 23),
            (tipx + 9, tipy + 20)], TAIL_M, outline=None)


def draw_body(p, bob=0.0, arms_up=False):
    """女仆装肩颈 + 白围裙 + 手臂"""
    y = 74 + bob

    # 后发垂落（在肩后）
    p.poly([(66, y - 12), (74, y + 16), (126, y + 16), (134, y - 12)], HAIR_D, lw=1.0)

    # 肩膀
    p.ell(100, y + 8, 27, 14, DRESS, lw=1.2)
    # 白围裙
    p.ell(100, y + 12, 18, 9, APRON, lw=1.0)
    # 领口
    p.poly([(90, y - 2), (110, y - 2), (100, y + 7)], WHITE, lw=1.0)
    # 蝴蝶结
    p.ell(97, y + 3, 3.4, 2.6, HAIR_M, lw=0.8)
    p.ell(103, y + 3, 3.4, 2.6, HAIR_M, lw=0.8)
    p.ell(100, y + 3, 1.6, 1.6, HAIR_L, lw=0.7)

    if arms_up:
        p.ell(74, y + 2, 7.5, 6.5, SKIN, lw=1.1)
        p.ell(126, y + 2, 7.5, 6.5, SKIN, lw=1.1)


def draw_fin(p, side, sway=0.0):
    """头鳍：三角带弧，长在头两侧偏上"""
    if side == "L":
        pts = [(72, 22), (58, 12 + sway), (52, 26 + sway), (60, 36), (70, 34)]
        inner = [(70, 24), (60, 17 + sway), (57, 26 + sway), (63, 32), (69, 32)]
    else:
        pts = [(128, 22), (142, 12 + sway), (148, 26 + sway), (140, 36), (130, 34)]
        inner = [(130, 24), (140, 17 + sway), (143, 26 + sway), (137, 32), (131, 32)]
    p.poly(pts, TAIL_M, lw=1.3)
    p.poly(inner, TAIL_L, outline=None)
    # 鳍条
    base = (68, 30) if side == "L" else (132, 30)
    tip = (56, 18 + sway) if side == "L" else (144, 18 + sway)
    for k in (0.25, 0.5, 0.75):
        p.line([base, (base[0] + (tip[0] - base[0]) * k,
                       base[1] + (tip[1] - base[1]) * k)], TAIL_D, 0.8)


def draw_eye(p, cx, cy, mood, closed=0.0):
    """眼睛：白底 + 虹膜 + 高光；形态随情绪"""
    if closed > 0.6 or mood in ("sleep",):
        # 闭眼：下弯弧线
        p.arc(cx - 9, cy - 7, cx + 9, cy + 5, 200, 340, LINE, 1.5)
        return
    if mood == "happy":
        # ^ ^ 弯眼
        p.arc(cx - 9, cy - 8, cx + 9, cy + 5, 200, 340, LINE, 2.0)
        return

    if mood == "angry":
        rx, ry = 8.0, 6.4
    elif mood == "sad":
        rx, ry = 7.4, 8.4
    elif mood == "wait":
        rx, ry = 8.0, 7.6
    else:
        rx, ry = 7.8, 9.0

    p.ell(cx, cy, rx, ry, WHITE, lw=1.0)
    p.ell(cx, cy + (0.8 if mood == "sad" else 0.0), rx - 1.6, ry - 1.6, EYE_IRIS, outline=None)
    p.ell(cx, cy + (2.6 if mood == "sad" else 2.0), (rx - 3.4), (ry - 3.6), EYE_DEEP, outline=None)
    # 高光
    p.ell(cx - 2.6, cy - 3.4, 2.3, 2.3, WHITE, outline=None, lw=0.6)
    p.ell(cx + 2.4, cy + 3.2, 1.2, 1.2, WHITE, outline=None, lw=0.6)


def draw_head(p, bob=0.0, blink=0.0, mood="idle", sway=0.0):
    cy = 38 + bob

    # ---- 后发 ----
    p.ell(100, cy + 6, 37, 34, HAIR_D, lw=1.3)

    # ---- 头鳍 ----
    draw_fin(p, "L", sway)
    draw_fin(p, "R", -sway)

    # ---- 脸 ----
    p.ell(100, cy + 6, 28, 27, SKIN, lw=1.2)
    # 下巴
    p.ell(100, cy + 14, 22, 19, SKIN, outline=None)

    # ---- 刘海：三层锯齿分缕 ----
    # 底层
    p.poly([(68, cy - 4), (72, cy - 18), (84, cy - 24), (100, cy - 26),
            (116, cy - 24), (128, cy - 18), (132, cy - 4), (126, cy + 2),
            (118, cy - 8), (108, cy + 2), (100, cy - 6), (92, cy + 2),
            (82, cy - 8), (74, cy + 2)], HAIR_M, lw=1.2)
    # 中层高光缕
    p.poly([(74, cy - 14), (86, cy - 21), (100, cy - 23), (114, cy - 21),
            (126, cy - 14), (118, cy - 12), (108, cy - 17), (100, cy - 18),
            (92, cy - 17), (82, cy - 12)], HAIR_L, outline=None)
    # 亮点
    p.ell(86, cy - 19, 8, 3.2, HAIR_HI, outline=None)

    # ---- 两侧垂发 ----
    p.poly([(66, cy - 6), (74, cy + 2), (74, cy + 20), (64, cy + 18)], HAIR_M, lw=1.2)
    p.poly([(134, cy - 6), (126, cy + 2), (126, cy + 20), (136, cy + 18)], HAIR_M, lw=1.2)

    # ---- 呆毛 ----
    p.line([(100, cy - 25), (96, cy - 36), (104, cy - 39), (110, cy - 33)], HAIR_M, 2.0)
    p.ell(104, cy - 36, 2.2, 2.2, HAIR_L, outline=None)

    # ---- 侧蝴蝶结 ----
    p.ell(68, cy - 8, 4.6, 3.6, HAIR_L, lw=0.9)
    p.ell(63, cy - 9, 3.4, 2.6, HAIR_HI, lw=0.8)
    p.ell(132, cy - 8, 4.6, 3.6, HAIR_L, lw=0.9)
    p.ell(137, cy - 9, 3.4, 2.6, HAIR_HI, lw=0.8)

    # ---- 眉毛 ----
    ey = cy + 8
    if mood == "angry":
        p.line([(78, ey - 12), (93, ey - 8)], LINE, 1.6)
        p.line([(122, ey - 12), (107, ey - 8)], LINE, 1.6)
    elif mood == "sad":
        p.line([(78, ey - 15), (93, ey - 11)], LINE, 1.4)
        p.line([(122, ey - 15), (107, ey - 11)], LINE, 1.4)
    elif mood in ("happy", "laugh"):
        p.line([(78, ey - 13), (93, ey - 16)], LINE, 1.4)
        p.line([(122, ey - 13), (107, ey - 16)], LINE, 1.4)
    else:
        p.line([(79, ey - 13), (93, ey - 13)], LINE, 1.2)
        p.line([(121, ey - 13), (107, ey - 13)], LINE, 1.2)

    # ---- 眼睛 ----
    draw_eye(p, 86, ey, mood, blink)
    draw_eye(p, 114, ey, mood, blink)

    # ---- 腮红 ----
    col = BLUSH_A if mood in ("angry", "laugh") else BLUSH
    size = 5.0 if mood in ("happy", "laugh", "angry") else 4.2
    p.ell(77, ey + 7, size, size * 0.62, col, outline=None)
    p.ell(123, ey + 7, size, size * 0.62, col, outline=None)

    # ---- 嘴 ----
    my = cy + 19
    if mood == "speaking":
        p.ell(100, my, 4.4, 3.8, MOUTH_IN, lw=1.0)
        p.ell(100, my + 1.4, 2.4, 1.6, (172, 62, 76), outline=None)
    elif mood in ("happy", "laugh"):
        p.d.chord([s(92), s(my - 6), s(108), s(my + 7)], 0, 180, fill=MOUTH_IN, outline=LINE,
                  width=int(1.0 * SS))
        p.ell(100, my + 4.0, 3.0, 1.8, (255, 168, 168), outline=None)
    elif mood == "angry":
        p.arc(93, my + 1, 107, my + 8, 200, 340, MOUTH_IN, 1.5)
    elif mood == "sad":
        p.arc(94, my + 2, 106, my + 9, 200, 340, MOUTH_IN, 1.4)
    elif mood == "sleep":
        p.ell(100, my, 2.4, 2.4, MOUTH, lw=0.9)
    elif mood == "wait":
        p.ell(100, my, 2.2, 3.0, MOUTH, lw=0.9)
    else:
        p.arc(95, my - 4, 105, my + 4, 20, 160, MOUTH_IN, 1.5)


def draw_scene(p, prop="rice", t=0.0, arms_up=False):
    """桌面 + 道具"""
    # 桌面
    p.d.rectangle([0, s(92), CW, CH], fill=WOOD)
    p.d.rectangle([0, s(92), CW, s(95)], fill=WOOD_D)
    p.line([(0, 92), (200, 92)], LINE, 1.0)

    if prop in ("rice", "rice_full", "rice_empty"):
        # 白饭碗
        p.ell(34, 97, 19, 5.0, BOWL_L, lw=1.1)
        p.ell(34, 95, 17.5, 4.2, BOWL, outline=None)
        if prop != "rice_empty":
            p.ell(34, 93, 16, 6.0, RICE, lw=1.0)
            for dx, dy in [(-8, -1), (0, -2.5), (8, -1), (-4, 1.5), (5, 1.5)]:
                p.ell(34 + dx, 92 + dy, 3.2, 2.2, RICE, outline=None)
            # 热气
            for i, off in enumerate((0, 7, 14)):
                yy = 87 - off * 0.7 - math.sin(t * 2.2 + i) * 1.4
                p.arc(28 + i * 4, yy - 5, 34 + i * 4, yy + 3, 200, 340, WHITE, 1.2)
        else:
            p.ell(34, 93, 14, 4.2, (30, 42, 90), outline=None)

    if prop == "rice_full":
        for dx, dy, r in [(0, 0, 3.8), (6, 1, 3.2), (-5, 1.2, 2.8), (2, 3.6, 3.2)]:
            p.ell(168 + dx, 94 + dy, r, r * 0.8, NOTE, lw=0.8)


def draw_fx(p, kind, t=0.0, bob=0.0, sway=0.0):
    cy = 38 + bob
    if kind == "zzz":
        for i, (dx, dy, sz) in enumerate([(0, 0, 1.0), (9, -8, 0.78), (16, -16, 0.58)]):
            x, y, w = 132 + dx, cy - 28 + dy, 6 * sz
            p.line([(x, y), (x + w, y)], HAIR_L, 1.4 * sz)
            p.line([(x + w, y), (x, y + w)], HAIR_L, 1.4 * sz)
            p.line([(x, y + w), (x + w, y + w)], HAIR_L, 1.4 * sz)
    elif kind == "anger":
        x, y = 138, cy - 20
        p.line([(x - 5, y), (x + 5, y)], RED, 1.8)
        p.line([(x, y - 5), (x, y + 5)], RED, 1.8)
        p.line([(x - 3.6, y - 3.6), (x + 3.6, y + 3.6)], RED, 1.2)
        p.line([(x + 3.6, y - 3.6), (x - 3.6, y + 3.6)], RED, 1.2)
    elif kind == "note":
        x, y = 140, cy - 22
        p.ell(x, y + 5, 3.2, 2.6, HAIR_M, lw=0.9)
        p.line([(x + 3, y + 5), (x + 3, y - 3)], HAIR_M, 1.3)
        p.line([(x + 3, y - 3), (x + 7, y - 2)], HAIR_M, 1.2)
    elif kind == "spark":
        for dx, dy, r in [(0, 0, 4.2), (-10, 6, 2.6), (9, -7, 2.2)]:
            x, y = 140 + dx, cy - 24 + dy
            p.line([(x - r, y), (x + r, y)], NOTE, 1.3)
            p.line([(x, y - r), (x, y + r)], NOTE, 1.3)
    elif kind == "bubble":
        bx, by = 146, cy - 24 + math.sin(t * 3) * 1.6
        p.ell(bx, by, 13, 8.5, WHITE, lw=1.0)
        p.poly([(bx - 9, by + 6), (bx - 14, by + 13), (bx - 3, by + 7)], WHITE, lw=0.9)
        for i in range(3):
            p.ell(bx - 5 + i * 5, by, 1.4, 1.4, HAIR_M, outline=None)


def render(mood="idle", blink=0.0, bob=0.0, sway=0.0, prop="rice",
           fx=None, arms_up=False, t=0.0):
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    p = Pen(d)

    draw_tail(p, sway)
    draw_body(p, bob, arms_up)
    draw_head(p, bob, blink, mood, sway)
    draw_scene(p, prop, t, arms_up)
    if fx:
        draw_fx(p, fx, t, bob, sway)

    return img.resize((W, H), Image.LANCZOS)


# ---------- 动画 ----------
def a_idle():
    out = []
    for i in range(10):
        ph = i / 10
        out.append(render("idle", 1.0 if i in (6, 7) else 0.0,
                          math.sin(ph * 6.2832) * 0.8, math.sin(ph * 6.2832) * 0.9,
                          "rice", None, False, ph))
    return out


def a_happy():
    out = []
    for i in range(7):
        ph = i / 7
        out.append(render("happy", 0.0, -abs(math.sin(ph * 6.2832)) * 1.8,
                          math.sin(ph * 6.2832), "rice_full", "note", True, ph))
    return out


def a_laugh():
    out = []
    for i in range(10):
        ph = i / 10
        out.append(render("laugh", 0.0, -abs(math.sin(ph * 12.566)) * 2.4,
                          math.sin(ph * 12.566) * 1.4, "rice_full", "note", True, ph))
    return out


def a_angry():
    out = []
    for i in range(8):
        ph = i / 8
        out.append(render("angry", 0.0, abs(math.sin(ph * 12.566)) * 1.0,
                          math.sin(ph * 12.566) * 1.2, "rice", "anger", False, ph))
    return out


def a_speaking():
    out = []
    for i in range(10):
        ph = i / 10
        out.append(render("speaking", 1.0 if i == 8 else 0.0,
                          math.sin(ph * 12.566) * 0.5, 0.3, "rice", "bubble", False, ph))
    return out


def a_listening():
    out = []
    for i in range(10):
        ph = i / 10
        out.append(render("listening", 0.0, math.sin(ph * 6.2832) * 0.4,
                          math.sin(ph * 18.85) * 1.6, "rice", "spark", False, ph))
    return out


def a_wait():
    out = []
    for i in range(10):
        ph = i / 10
        out.append(render("wait", 0.0, math.sin(ph * 6.2832) * 1.1, 0.4,
                          "rice", "bubble", False, ph))
    return out


def a_sleep():
    out = []
    for i in range(9):
        ph = i / 9
        out.append(render("sleep", 0.0, math.sin(ph * 6.2832) * 1.5, 0.2,
                          "rice", "zzz", False, ph))
    return out


def a_sad():
    out = []
    for i in range(10):
        ph = i / 10
        out.append(render("sad", 0.0, math.sin(ph * 6.2832) * 0.6, -0.5,
                          "rice_empty", None, False, ph))
    return out


def a_battery():
    return [render("happy", 0.0, -1.0, 0.8, "rice_full", "spark", True, 0.0),
            render("happy", 0.0, 0.0, 0.9, "rice_full", "spark", True, 0.5)]


ANIMS = {
    "待机": a_idle, "大笑": a_laugh, "开心": a_happy, "聆听": a_listening,
    "生气": a_angry, "伤心": a_sad, "充电": a_battery, "等待": a_wait,
    "休眠": a_sleep, "说话": a_speaking,
}


def main(outdir, only=None):
    os.makedirs(outdir, exist_ok=True)
    for name, fn in ANIMS.items():
        if only and name not in only:
            continue
        sub = os.path.join(outdir, name)
        os.makedirs(sub, exist_ok=True)
        for f in os.listdir(sub):
            if f.endswith(".png"):
                os.remove(os.path.join(sub, f))
        frames = fn()
        for i, img in enumerate(frames):
            img.save(os.path.join(sub, f"frame-{i:06d}.png"))
        print(f"{name}: {len(frames)} frames")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "./out"
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    main(out, only)
