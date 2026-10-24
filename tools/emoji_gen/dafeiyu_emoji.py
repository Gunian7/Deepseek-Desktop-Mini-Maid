#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
大肥鱼（DeepSeek 鲸鱼娘）表情资源生成器 —— Arcs-Mini3 / 200x104 透明 PNG 帧序列

设计约束（来自官方 res/arcs-mini/emoji 与 emoji_anim.c）：
  - 画布 200x104，透明背景
  - 每个情绪一个目录，文件名为 frame-%06d.png，从 0 开始连续
  - emoji.json 里 name -> 中文目录 alias，loop.range / interval_ms 控制循环

绘制方式：4x 超采样后 LANCZOS 缩小，得到干净的扁平插画边缘。
输出：RGBA PNG（LVGL lodepng 直接支持），另存一份 palette 版备选。
"""
import os
import math
from PIL import Image, ImageDraw, ImageFilter

SS = 4                     # 超采样倍数
W, H = 200, 104            # 目标画布
CW, CH = W * SS, H * SS    # 超采样画布

# ---------- 配色 ----------
HAIR_D   = (52, 84, 168)
HAIR_M   = (86, 132, 226)
HAIR_L   = (140, 186, 250)
HAIR_HI  = (196, 226, 255)
SKIN     = (255, 228, 214)
SKIN_SH  = (240, 198, 178)
EYE_IRIS = (40, 96, 214)
EYE_DEEP = (24, 58, 150)
WHITE    = (255, 255, 255)
MOUTH    = (214, 104, 110)
BLUSH    = (255, 158, 158)
DRESS_D  = (38, 54, 110)
DRESS    = (52, 74, 148)
APRON    = (246, 249, 255)
RICE     = (252, 252, 248)
RICE_SH  = (222, 228, 238)
BOWL     = (58, 74, 128)
BOWL_L   = (96, 120, 190)
TAIL_D   = (58, 96, 190)
TAIL_L   = (122, 164, 236)
FIN      = (74, 116, 208)
WOOD     = (198, 170, 138)
WOOD_D   = (166, 138, 108)
NOTE     = (255, 244, 214)


def s(v):
    """把 200x104 设计坐标换算到超采样坐标"""
    return v * SS


def P(x, y):
    return (s(x), s(y))


def ellipse(d, cx, cy, rx, ry, fill, outline=None, width=1):
    d.ellipse([s(cx - rx), s(cy - ry), s(cx + rx), s(cy + ry)],
              fill=fill, outline=outline, width=int(width * SS))


def polygon(d, pts, fill, outline=None, width=1):
    d.polygon([P(x, y) for x, y in pts], fill=fill,
              outline=outline, width=int(width * SS))


def rounded(d, x1, y1, x2, y2, r, fill, outline=None, width=1):
    d.rounded_rectangle([s(x1), s(y1), s(x2), s(y2)], radius=s(r), fill=fill,
                        outline=outline, width=int(width * SS))


def arc(d, x1, y1, x2, y2, a1, a2, fill, width):
    d.arc([s(x1), s(y1), s(x2), s(y2)], a1, a2, fill=fill, width=int(width * SS))


# ---------- 角色部件 ----------

def draw_tail(img, d, sway=0.0):
    """鲸尾：从右下伸出，sway = -1..1 摆动相位"""
    bx, by = 132, 92
    tip_x = bx + 34 + sway * 4
    tip_y = 74 - sway * 3

    # 尾柄
    polygon(d, [(bx - 4, by + 4), (bx + 18, by - 4), (tip_x, tip_y),
                (tip_x + 3, tip_y + 7), (bx + 16, by + 6), (bx - 5, by + 9)], TAIL_D)
    polygon(d, [(bx - 2, by + 4), (bx + 17, by - 2), (tip_x - 2, tip_y + 2),
                (bx + 15, by + 4)], TAIL_L)

    # 尾鳍两瓣
    f1 = [(tip_x, tip_y), (tip_x + 14, tip_y - 13 + sway * 2), (tip_x + 15, tip_y + 1),
          (tip_x + 2, tip_y + 6)]
    f2 = [(tip_x, tip_y + 3), (tip_x + 11, tip_y + 15 + sway * 2), (tip_x + 1, tip_y + 10)]
    polygon(d, f1, TAIL_D)
    polygon(d, f2, TAIL_D)
    polygon(d, [(tip_x + 1, tip_y + 1), (tip_x + 11, tip_y - 10 + sway * 2),
                (tip_x + 12, tip_y - 1)], TAIL_L)


def draw_body(d, bob=0.0, arm_up=False):
    """女仆装半身（在桌面以下的部分被桌面/碗遮住）"""
    y0 = 76 + bob
    # 肩膀 / 袖子
    ellipse(d, 100, y0 + 16, 30, 20, DRESS)
    ellipse(d, 100, y0 + 20, 22, 15, APRON)
    # 领口白边
    polygon(d, [(88, y0 + 3), (112, y0 + 3), (100, y0 + 14)], WHITE)
    # 蝴蝶结
    ellipse(d, 100, y0 + 12, 4, 3, HAIR_M)
    ellipse(d, 96, y0 + 12, 3, 2, HAIR_L)
    ellipse(d, 104, y0 + 12, 3, 2, HAIR_L)
    if arm_up:
        # 举起的双手（抱碗）
        ellipse(d, 76, y0 + 6, 8, 7, SKIN)
        ellipse(d, 124, y0 + 6, 8, 7, SKIN)


def draw_head(d, bob=0.0, blink=0.0, mood="idle", sway=0.0):
    """
    blink: 0=睁眼, 1=完全闭眼
    mood: idle / happy / angry / sad / listening / speaking / sleep / wait
    """
    cy = 44 + bob

    # ---- 长发（后层）----
    polygon(d, [(70, cy - 8), (130, cy - 8), (140, cy + 40), (60, cy + 40)], HAIR_D)
    ellipse(d, 100, cy + 2, 40, 38, HAIR_D)

    # ---- 头鳍（两侧鲸类鳍状耳）----
    fin_l = [(66, cy + 2), (52, cy + 10 + sway), (58, cy + 20)]
    fin_r = [(134, cy + 2), (148, cy + 10 - sway), (142, cy + 20)]
    polygon(d, fin_l, FIN)
    polygon(d, fin_r, FIN)
    polygon(d, [(67, cy + 4), (57, cy + 10 + sway * 0.6), (61, cy + 16)], HAIR_L)
    polygon(d, [(133, cy + 4), (143, cy + 10 - sway * 0.6), (139, cy + 16)], HAIR_L)

    # ---- 脸 ----
    ellipse(d, 100, cy + 6, 30, 29, SKIN)
    # 下巴收一点
    ellipse(d, 100, cy + 14, 24, 20, SKIN)

    # ---- 刘海（渐变三层）----
    ellipse(d, 100, cy - 12, 33, 24, HAIR_M)
    ellipse(d, 100, cy - 15, 30, 18, HAIR_L)
    # 刘海分缕
    polygon(d, [(72, cy - 14), (86, cy + 6), (94, cy - 6), (88, cy - 16)], HAIR_M)
    polygon(d, [(128, cy - 14), (114, cy + 6), (106, cy - 6), (112, cy - 16)], HAIR_M)
    polygon(d, [(92, cy - 18), (100, cy - 2), (108, cy - 18)], HAIR_L)
    # 高光
    ellipse(d, 88, cy - 18, 9, 4, HAIR_HI)
    ellipse(d, 114, cy - 16, 6, 3, HAIR_HI)

    # ---- 呆毛 ----
    d.line([P(100, cy - 26), P(97, cy - 38), P(104, cy - 40), P(108, cy - 34)],
           fill=HAIR_M, width=int(2.2 * SS), joint="curve")

    # ---- 侧发蝴蝶结 ----
    ellipse(d, 70, cy - 6, 5, 4, HAIR_L)
    ellipse(d, 66, cy - 8, 4, 3, HAIR_HI)
    ellipse(d, 130, cy - 6, 5, 4, HAIR_L)
    ellipse(d, 134, cy - 8, 4, 3, HAIR_HI)

    # ---- 眼睛 ----
    ey = cy + 6
    elx, erx = 88, 112
    if blink > 0.75:
        for ex in (elx, erx):
            arc(d, ex - 8, ey - 4, ex + 8, ey + 6, 200, 340, EYE_DEEP, 2.2)
    elif mood == "sleep":
        for ex in (elx, erx):
            arc(d, ex - 8, ey - 3, ex + 8, ey + 7, 200, 340, EYE_DEEP, 2.2)
    elif mood == "happy":
        for ex in (elx, erx):
            arc(d, ex - 8, ey - 6, ex + 8, ey + 6, 200, 340, EYE_DEEP, 2.4)
    elif mood == "angry":
        for ex in (elx, erx):
            ellipse(d, ex, ey, 7, 8, EYE_IRIS)
            ellipse(d, ex, ey + 1, 4, 5, EYE_DEEP)
            ellipse(d, ex - 2, ey - 3, 2.2, 2.2, WHITE)
        # 怒眉
        d.line([P(elx - 8, ey - 12), P(elx + 7, ey - 8)], fill=EYE_DEEP, width=int(2.4 * SS))
        d.line([P(erx + 8, ey - 12), P(erx - 7, ey - 8)], fill=EYE_DEEP, width=int(2.4 * SS))
    elif mood == "sad":
        for ex in (elx, erx):
            ellipse(d, ex, ey + 1, 6.5, 7, EYE_IRIS)
            ellipse(d, ex, ey + 2, 3.6, 4.5, EYE_DEEP)
            ellipse(d, ex - 2, ey - 2, 2, 2, WHITE)
        d.line([P(elx - 7, ey - 11), P(elx + 6, ey - 9)], fill=EYE_DEEP, width=int(2 * SS))
        d.line([P(erx + 7, ey - 11), P(erx - 6, ey - 9)], fill=EYE_DEEP, width=int(2 * SS))
    else:
        # 常态：亮蓝大眼
        for ex in (elx, erx):
            ellipse(d, ex, ey, 7.2, 8.2, WHITE)
            ellipse(d, ex, ey + 0.5, 6.2, 7.2, EYE_IRIS)
            ellipse(d, ex, ey + 2.4, 3.4, 4.0, EYE_DEEP)
            ellipse(d, ex - 2.4, ey - 2.6, 2.3, 2.3, WHITE)
            ellipse(d, ex + 2.2, ey + 3.4, 1.2, 1.2, WHITE)

    # ---- 腮红 ----
    if mood in ("happy", "listening"):
        ellipse(d, 76, ey + 8, 6, 3.4, BLUSH)
        ellipse(d, 124, ey + 8, 6, 3.4, BLUSH)
    elif mood == "angry":
        ellipse(d, 76, ey + 8, 5, 3, BLUSH)
        ellipse(d, 124, ey + 8, 5, 3, BLUSH)
    else:
        ellipse(d, 77, ey + 8, 4.6, 2.6, BLUSH)
        ellipse(d, 123, ey + 8, 4.6, 2.6, BLUSH)

    # ---- 嘴 ----
    my = cy + 20
    if mood == "speaking":
        ellipse(d, 100, my, 4.2, 3.6, MOUTH)
        ellipse(d, 100, my + 1.2, 2.6, 1.8, (168, 62, 74))
    elif mood == "happy":
        arc(d, 93, my - 5, 107, my + 6, 20, 160, MOUTH, 2.2)
    elif mood == "angry":
        arc(d, 94, my + 1, 106, my + 7, 200, 340, MOUTH, 2.0)
    elif mood == "sad":
        arc(d, 95, my + 2, 105, my + 8, 200, 340, MOUTH, 1.8)
    elif mood == "sleep":
        ellipse(d, 100, my, 2.6, 2.6, MOUTH)
    else:
        arc(d, 96, my - 3, 104, my + 3, 20, 160, MOUTH, 1.8)


def draw_props(d, kind="rice", bob=0.0, t=0.0):
    """桌面 + 道具"""
    # 桌面
    d.rectangle([0, s(92), CW, CH], fill=WOOD)
    d.rectangle([0, s(92), CW, s(95)], fill=WOOD_D)

    if kind in ("rice", "rice_full"):
        # 左侧一碗白饭
        ellipse(d, 32, 92, 20, 5.5, BOWL_L)
        ellipse(d, 32, 90, 18, 4.6, BOWL)
        ellipse(d, 32, 88, 17, 6.5, RICE)
        for dx, dy in [(-8, -1), (0, -2), (8, -1), (-4, 1), (5, 1)]:
            ellipse(d, 32 + dx, 87 + dy, 3.4, 2.4, RICE)
        # 热气
        for i, off in enumerate((0, 6, 12)):
            yy = 82 - off * 0.8 - math.sin(t * 2 + i) * 1.5
            arc(d, 27 + i * 4, yy - 5, 33 + i * 4, yy + 3, 200, 340,
                (255, 255, 255), 1.2)

    if kind == "rice_full":
        # 右侧 token 堆（＝吃剩的饭粒）
        for i, (dx, dy, r) in enumerate([(0, 0, 4), (6, 1, 3.4), (-5, 1.5, 3),
                                         (2, 4, 3.6), (9, 4, 2.6)]):
            ellipse(d, 168 + dx, 89 + dy, r, r * 0.8, NOTE)

    if kind == "empty":
        # 空碗
        ellipse(d, 32, 92, 20, 5.5, BOWL_L)
        ellipse(d, 32, 90, 18, 4.6, BOWL)
        ellipse(d, 32, 89, 15, 4.0, (30, 42, 90))


def draw_fx(d, kind, t=0.0, bob=0.0):
    """情绪特效"""
    cy = 44 + bob
    if kind == "zzz":
        for i, (dx, dy, sz) in enumerate([(0, 0, 1.0), (10, -9, 0.8), (18, -18, 0.6)]):
            x = 138 + dx
            y = cy - 26 + dy
            d.text if False else None
            # 用手绘 Z
            w = 7 * sz
            d.line([P(x, y), P(x + w, y)], fill=HAIR_L, width=int(2 * sz * SS))
            d.line([P(x + w, y), P(x, y + w)], fill=HAIR_L, width=int(2 * sz * SS))
            d.line([P(x, y + w), P(x + w, y + w)], fill=HAIR_L, width=int(2 * sz * SS))
    elif kind == "anger":
        # 十字怒气
        x, y = 142, cy - 18
        for a in (0, 90):
            pass
        d.line([P(x - 5, y), P(x + 5, y)], fill=(238, 88, 88), width=int(2.4 * SS))
        d.line([P(x, y - 5), P(x, y + 5)], fill=(238, 88, 88), width=int(2.4 * SS))
        d.line([P(x - 4, y - 4), P(x + 4, y + 4)], fill=(238, 88, 88), width=int(1.6 * SS))
        d.line([P(x + 4, y - 4), P(x - 4, y + 4)], fill=(238, 88, 88), width=int(1.6 * SS))
    elif kind == "note":
        x, y = 145, cy - 20
        ellipse(d, x, y + 5, 3.2, 2.6, HAIR_M)
        d.line([P(x + 3, y + 5), P(x + 3, y - 2)], fill=HAIR_M, width=int(1.6 * SS))
        d.line([P(x + 3, y - 2), P(x + 7, y - 1)], fill=HAIR_M, width=int(1.4 * SS))
    elif kind == "spark":
        for dx, dy, r in [(0, 0, 4), (-9, 5, 2.6), (8, -6, 2.2)]:
            x, y = 145 + dx, cy - 22 + dy
            d.line([P(x - r, y), P(x + r, y)], fill=NOTE, width=int(1.4 * SS))
            d.line([P(x, y - r), P(x, y + r)], fill=NOTE, width=int(1.4 * SS))
    elif kind == "bubble":
        # 内心 OS 气泡（"我去吃饭…"的视觉替代）
        bx, by = 150, cy - 24 + math.sin(t * 3) * 1.5
        ellipse(d, bx, by, 12, 8, (255, 255, 255))
        polygon(d, [(bx - 9, by + 6), (bx - 13, by + 12), (bx - 4, by + 7)], (255, 255, 255))
        for i in range(3):
            ellipse(d, bx - 5 + i * 5, by, 1.3, 1.3, HAIR_M)


def render(mood="idle", blink=0.0, bob=0.0, sway=0.0, prop="rice",
           fx=None, arm_up=False, t=0.0):
    img = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    draw_tail(img, d, sway)
    draw_body(d, bob, arm_up)
    draw_head(d, bob, blink, mood, sway)
    draw_props(d, prop, bob, t)
    if fx:
        draw_fx(d, fx, t, bob)

    return img.resize((W, H), Image.LANCZOS)


# ---------- 各情绪动画序列 ----------
# 返回 [(frame_img, interval_ms), ...]
def anim_idle():
    frames = []
    for i in range(10):
        ph = i / 10.0
        bob = math.sin(ph * 2 * math.pi) * 0.9
        sway = math.sin(ph * 2 * math.pi) * 1.0
        blink = 1.0 if i in (6, 7) else 0.0
        frames.append((render("idle", blink, bob, sway, "rice", None, False, ph), 150))
    return frames


def anim_happy():
    frames = []
    for i in range(7):
        ph = i / 7.0
        bob = -abs(math.sin(ph * 2 * math.pi)) * 2.0
        sway = math.sin(ph * 2 * math.pi)
        frames.append((render("happy", 0.0, bob, sway, "rice_full", "note", True, ph), 150))
    return frames


def anim_angry():
    frames = []
    for i in range(8):
        ph = i / 8.0
        bob = abs(math.sin(ph * 4 * math.pi)) * 1.2
        sway = math.sin(ph * 4 * math.pi) * 1.4
        frames.append((render("angry", 0.0, bob, sway, "rice", "anger", False, ph), 150))
    return frames


def anim_speaking():
    frames = []
    for i in range(10):
        ph = i / 10.0
        bob = math.sin(ph * 4 * math.pi) * 0.6
        blink = 1.0 if i == 8 else 0.0
        frames.append((render("speaking", blink, bob, 0.3, "rice", "bubble", False, ph), 100))
    return frames


def anim_listening():
    frames = []
    for i in range(10):
        ph = i / 10.0
        sway = math.sin(ph * 6 * math.pi) * 1.8
        bob = math.sin(ph * 2 * math.pi) * 0.5
        frames.append((render("listening", 0.0, bob, sway, "rice", "spark", False, ph), 100))
    return frames


def anim_wait():
    frames = []
    for i in range(10):
        ph = i / 10.0
        bob = math.sin(ph * 2 * math.pi) * 1.2
        frames.append((render("wait", 0.0, bob, 0.4, "rice", "bubble", False, ph), 150))
    return frames


def anim_sleep():
    frames = []
    for i in range(9):
        ph = i / 9.0
        bob = math.sin(ph * 2 * math.pi) * 1.6
        frames.append((render("sleep", 0.0, bob, 0.2, "rice", "zzz", False, ph), 200))
    return frames


def anim_sad():
    frames = []
    for i in range(10):
        ph = i / 10.0
        bob = math.sin(ph * 2 * math.pi) * 0.7
        frames.append((render("sad", 0.0, bob, -0.6, "empty", None, False, ph), 200))
    return frames


def anim_battery():
    frames = []
    for i in range(2):
        bob = -1.0 if i == 0 else 0.0
        frames.append((render("happy", 0.0, bob, 0.8, "rice_full", "spark", True, i), 100))
    return frames


def anim_laugh():
    frames = []
    for i in range(10):
        ph = i / 10.0
        bob = -abs(math.sin(ph * 4 * math.pi)) * 2.6
        sway = math.sin(ph * 4 * math.pi) * 1.6
        frames.append((render("laugh", 0.0, bob, sway, "rice_full", "note", True, ph), 100))
    return frames


# mood "laugh" 复用 happy 眼型
_laugh_orig = draw_head


ANIMS = {
    "待机": anim_idle,
    "大笑": anim_laugh,
    "开心": anim_happy,
    "聆听": anim_listening,
    "生气": anim_angry,
    "伤心": anim_sad,
    "充电": anim_battery,
    "等待": anim_wait,
    "休眠": anim_sleep,
    "说话": anim_speaking,
}


def main(outdir, only=None):
    os.makedirs(outdir, exist_ok=True)
    for name, fn in ANIMS.items():
        if only and name not in only:
            continue
        sub = os.path.join(outdir, name)
        os.makedirs(sub, exist_ok=True)
        # 清掉旧帧
        for f in os.listdir(sub):
            if f.endswith(".png"):
                os.remove(os.path.join(sub, f))
        frames = fn()
        for i, (img, _ms) in enumerate(frames):
            img.save(os.path.join(sub, f"frame-{i:06d}.png"))
        print(f"{name}: {len(frames)} frames")


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "./out"
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
    main(out, only)
