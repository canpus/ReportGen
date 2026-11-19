"""生成程序图标 assets/app.ico（开发时运行；需要 Pillow）。

图案：蓝紫渐变圆角方块 + 白色报告单（表格横线）+ 绿色对勾，配色与界面主色一致。
用法：python tools/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "assets"
S = 1024                                   # 先画大图再缩小，边缘更平滑
TOP, BOTTOM = (107, 134, 255), (61, 90, 224)
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def gradient(size):
    g = Image.new("RGB", (size, size))
    px = g.load()
    for y in range(size):
        t = y / (size - 1)
        c = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = c
    return g


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
    img.paste(gradient(S), (0, 0), mask)
    d = ImageDraw.Draw(img)
    # 报告单（带折角）
    left, top, right, bottom, fold = 270, 190, 754, 834, 130
    d.polygon([(left, top + 40), (left, bottom - 40), (left + 40, bottom), (right - 40, bottom),
               (right, bottom - 40), (right, top + fold), (right - fold, top), (left + 40, top)],
              fill=(255, 255, 255))
    d.pieslice((left, top, left + 80, top + 80), 180, 270, fill=(255, 255, 255))
    d.pieslice((left, bottom - 80, left + 80, bottom), 90, 180, fill=(255, 255, 255))
    d.pieslice((right - 80, bottom - 80, right, bottom), 0, 90, fill=(255, 255, 255))
    d.polygon([(right - fold, top), (right - fold, top + fold - 20), (right - fold + 20, top + fold),
               (right, top + fold)], fill=(214, 222, 255))
    # 表格横线
    line = (164, 178, 245)
    for i, y in enumerate((345, 440, 535)):
        d.rounded_rectangle((left + 70, y, (right - 160) if i == 0 else (right - 70), y + 34), radius=17,
                            fill=line)
    # 对勾徽章
    cx, cy, r = 655, 705, 150
    d.ellipse((cx - r - 18, cy - r - 18, cx + r + 18, cy + r + 18), fill=(255, 255, 255))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(31, 178, 122))
    d.line([(cx - 72, cy + 2), (cx - 20, cy + 56), (cx + 78, cy - 52)], fill=(255, 255, 255), width=46,
           joint="curve")
    for x, y in ((cx - 72, cy + 2), (cx + 78, cy - 52)):
        d.ellipse((x - 23, y - 23, x + 23, y + 23), fill=(255, 255, 255))
    return img


def main():
    OUT.mkdir(exist_ok=True)
    big = draw()
    big.resize((256, 256), Image.LANCZOS).save(OUT / "app.ico", sizes=[(s, s) for s in SIZES])
    big.resize((256, 256), Image.LANCZOS).save(OUT / "app.png")
    big.resize((32, 32), Image.LANCZOS).save(OUT / "logo32.png")       # 顶栏标志
    print(OUT / "app.ico")


if __name__ == "__main__":
    main()
