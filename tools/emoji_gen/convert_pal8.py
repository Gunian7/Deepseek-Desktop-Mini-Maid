#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 RGBA 表情帧压缩成 8-bit 调色板 PNG（带透明索引），压进 emoji 分区预算。

emoji 分区容量 = 786,432 字节（0x380000 -> 0x440000），86 帧。
"""
import os
import sys
from PIL import Image

def to_pal(im, colors=255):
    im = im.convert("RGBA")
    alpha = im.split()[3]
    mask = alpha.point(lambda a: 255 if a > 110 else 0)   # 半透明按实心处理
    rgb = im.convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT)
    out = rgb.copy()
    # 全透明区 -> 索引 colors
    inv = Image.eval(mask, lambda v: 255 - v)
    out.paste(colors, mask=inv)
    out.info["transparency"] = colors
    return out


def main(src, dst, colors=255):
    total = 0
    n = 0
    for mood in sorted(os.listdir(src)):
        sd = os.path.join(src, mood)
        if not os.path.isdir(sd):
            continue
        dd = os.path.join(dst, mood)
        os.makedirs(dd, exist_ok=True)
        for f in sorted(os.listdir(sd)):
            if not f.endswith(".png"):
                continue
            im = Image.open(os.path.join(sd, f))
            p = to_pal(im, colors)
            op = os.path.join(dd, f)
            p.save(op, optimize=True)
            total += os.path.getsize(op)
            n += 1
    print(f"{n} frames -> {total:,} bytes ({total/n:.0f} B/frame)  colors={colors}")
    return total


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2]
    colors = int(sys.argv[3]) if len(sys.argv) > 3 else 255
    main(src, dst, colors)
