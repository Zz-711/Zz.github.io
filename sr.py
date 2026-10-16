# -*- coding: utf-8 -*-
"""
生日祝福 · 流星雨之夜（Tkinter 单文件，Windows 下零第三方依赖）

演出流程
--------
  1. 深空渐变 + 月亮 + 满天星星闪烁，流星拖着渐变尾迹划过夜空
  2. 无数「小流星」从天而降，汇聚成 Happy Birthday
  3. 再汇聚成 生日快乐 → XX XX岁啦
  4. 蛋糕从底部缓缓升起，烛火跳动，祝福语逐字打出，流星雨继续 —— 永久停留

用法
----
    python birthday_meteor.py                    # 弹窗输入年龄/名字
    python birthday_meteor.py -a 26 -n 宝宝
    python birthday_meteor.py --windowed         # 窗口模式（默认全屏）
    python birthday_meteor.py -w "愿你被这个世界温柔以待"

快捷键：ESC / 单击 = 退出    F11 = 全屏切换    R = 重播    SPACE = 跳过当前文字
"""

import argparse
import ctypes
import math
import random
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

# ====================================================================== 配置
BG_TOP = "#1B2A4A"          # 顶部：深蓝
BG_MID = "#0B1226"          # 中部：午夜蓝
BG_BOTTOM = "#05060F"       # 底部：近黑
FRAME_MS = 33
FRAME_MS_MAX = 55

METEOR_COLORS = ("#FFFFFF", "#FFE9A8", "#FFC2D4", "#BFE3FF", "#D8B4FE", "#FFF6C0")
STAR_COLORS = ("#2A3A5E", "#3A4E78", "#4C639A", "#5E7AB8", "#7C96CF")
TEXT_COLORS = ("#FFFFFF", "#FFE9A8", "#FFC2D4", "#BFE3FF", "#FFF6C0", "#D8B4FE")

MAX_PARTICLES = 620
N_STARS = 130
N_METEORS = 9               # 常驻流星数量
DEFAULT_FONT = "Microsoft YaHei"
METEOR_ANGLE = math.radians(152.0)   # 流星飞行方向（左下 28°），与网页版一致
M_UX = math.cos(METEOR_ANGLE)
M_UY = math.sin(METEOR_ANGLE)


# ==================================================== 字形光栅化（GDI，已验证）
# 坑：CreateDIBSection 必须声明 argtypes；TEXTMETRICW 家族不能省字段。
# 这里只光栅化、不取 metrics，直接画进足够大的位图再按墨水包围盒裁剪。
class _BMIH(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint), ("biWidth", ctypes.c_int),
                ("biHeight", ctypes.c_int), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint),
                ("biSizeImage", ctypes.c_uint), ("biXPelsPerMeter", ctypes.c_int),
                ("biYPelsPerMeter", ctypes.c_int), ("biClrUsed", ctypes.c_uint),
                ("biClrImportant", ctypes.c_uint)]


class _BMI(ctypes.Structure):
    _fields_ = [("bmiHeader", _BMIH), ("bmiColors", ctypes.c_uint * 3)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_int), ("cy", ctypes.c_int)]


_HAS_GDI = False
if sys.platform == "win32":
    try:
        _gdi32 = ctypes.WinDLL("gdi32")
        _gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
        _gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
        _gdi32.CreateFontW.restype = ctypes.c_void_p
        _gdi32.CreateFontW.argtypes = ([ctypes.c_int] * 5 + [ctypes.c_uint] * 4
                                       + [ctypes.c_uint] * 4 + [ctypes.c_wchar_p])
        _gdi32.SelectObject.restype = ctypes.c_void_p
        _gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        _gdi32.CreateDIBSection.restype = ctypes.c_void_p
        _gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                            ctypes.c_uint, ctypes.c_void_p,
                                            ctypes.c_void_p, ctypes.c_uint]
        _gdi32.GetTextExtentPoint32W.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int,
            ctypes.POINTER(_SIZE)]
        _gdi32.TextOutW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_wchar_p, ctypes.c_int]
        _gdi32.SetBkMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
        _gdi32.SetTextColor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        _gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        _gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
        _gdi32.GdiFlush.argtypes = []
        _HAS_GDI = True
    except Exception:                                   # pragma: no cover
        _HAS_GDI = False

_PAD = 8
_PX_MAX = 700
_MASK_TABLE = bytes(1 if i > 110 else 0 for i in range(256))


def _raster_gdi(text, px, face, weight):
    hdc = _gdi32.CreateCompatibleDC(None)
    hfont = _gdi32.CreateFontW(-int(px), 0, 0, 0, weight, 0, 0, 0,
                               1, 0, 0, 4, 0, face)
    if not hfont:
        _gdi32.DeleteDC(hdc)
        raise RuntimeError("CreateFontW 失败：" + face)
    _gdi32.SelectObject(hdc, hfont)
    size = _SIZE()
    _gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes.byref(size))
    w = max(1, size.cx + _PAD * 2)
    h = max(1, int(px * 2.0) + _PAD * 2)
    bmi = _BMI()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BMIH)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bits = ctypes.c_void_p()
    hbmp = _gdi32.CreateDIBSection(hdc, ctypes.byref(bmi), 0,
                                   ctypes.byref(bits), None, 0)
    _gdi32.SelectObject(hdc, hbmp)
    _gdi32.SetBkMode(hdc, 1)
    _gdi32.SetTextColor(hdc, 0x00FFFFFF)
    _gdi32.TextOutW(hdc, _PAD, _PAD, text, len(text))
    _gdi32.GdiFlush()

    if not hbmp or not bits.value:
        _gdi32.DeleteObject(hfont)
        _gdi32.DeleteDC(hdc)
        raise RuntimeError("CreateDIBSection 失败")

    buf = (ctypes.c_ubyte * (w * h * 4)).from_address(bits.value)
    mv = memoryview(buf)
    y0, y1, x0, x1 = h, -1, w, -1
    for y in range(h):
        row = bytes(mv[y * w * 4:(y + 1) * w * 4:4]).translate(_MASK_TABLE)
        i, j = row.find(1), row.rfind(1)
        if i < 0:
            continue
        y0, y1 = min(y0, y), y
        x0, x1 = min(x0, i), max(x1, j)

    rows = []
    if y1 >= 0:
        for y in range(y0, y1 + 1):
            rows.append(bytearray(
                bytes(mv[y * w * 4:(y + 1) * w * 4:4]).translate(_MASK_TABLE)[x0:x1 + 1]))
    _gdi32.DeleteObject(hbmp)
    _gdi32.DeleteObject(hfont)
    _gdi32.DeleteDC(hdc)
    if not rows:
        return 0, 0, []
    return x1 - x0 + 1, y1 - y0 + 1, rows


def _raster_pillow(text, px, face, weight):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype(face, int(px))
    box = font.getbbox(text)
    w = max(1, box[2] - box[0] + _PAD * 2)
    h = max(1, box[3] - box[1] + _PAD * 2)
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((_PAD - box[0], _PAD - box[1]), text,
                             fill=255, font=font)
    data = img.tobytes()
    rows, x0, x1, y0, y1 = [], w, -1, h, -1
    for y in range(h):
        row = data[y * w:(y + 1) * w]
        i = next((x for x, v in enumerate(row) if v > 110), -1)
        if i < 0:
            continue
        j = max(x for x, v in enumerate(row) if v > 110)
        y0, y1 = min(y0, y), y
        x0, x1 = min(x0, i), max(x1, j)
        rows.append(row)
    if not rows:
        return 0, 0, []
    out = [bytearray(1 if v > 110 else 0 for v in r[x0:x1 + 1]) for r in rows]
    return x1 - x0 + 1, y1 - y0 + 1, out


def render_line(text, px, face=DEFAULT_FONT, weight=700):
    if not text or px < 4:
        return 0, 0, []
    if _HAS_GDI:
        return _raster_gdi(text, px, face, weight)
    try:
        return _raster_pillow(text, px, face, weight)
    except ImportError:
        raise RuntimeError("没有可用的光栅化后端，请安装 Pillow：pip install pillow")


def fit_text(text, box_w, box_h, face=DEFAULT_FONT, weight=700):
    px, rows = 120, []
    for _ in range(5):
        w, h, rows = render_line(text, px, face, weight)
        if not rows:
            return None
        need = min(box_w / w, box_h / h)
        if 0.94 <= need <= 1.06 or px <= 10 or px >= _PX_MAX:
            break
        px = max(8, min(_PX_MAX, int(round(px * need))))
    if not rows:
        return None
    return rows, w, h, min(box_w / w, box_h / h)


def mask_to_points(rows, mw, mh, cx, cy, scale, max_points, jitter=0.35):
    total = sum(sum(r) for r in rows)
    if not total:
        return []
    step = max(1, int(math.sqrt(total / float(max_points))))
    x_off = cx - mw * scale * 0.5
    y_off = cy - mh * scale * 0.5
    pts = []
    for my in range(0, mh, step):
        row = rows[my]
        i, j = row.find(1), row.rfind(1)
        if i < 0:
            continue
        for mx in range(i, j + 1, step):
            if row[mx]:
                pts.append((x_off + (mx + 0.5) * scale + random.uniform(-jitter, jitter),
                            y_off + (my + 0.5) * scale + random.uniform(-jitter, jitter)))
    if len(pts) > max_points:
        pts = random.sample(pts, max_points)
    return pts


def lerp_color(c1, c2, t):
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ================================================================== 流星
class Meteor:
    """一颗流星：亮头 + 渐变尾迹（多段线，颜色向背景色插值）。"""

    _seq = [0]

    def __init__(self, canvas, w, h, big=False):
        self.canvas = canvas
        self.w, self.h = w, h
        self.big = big                       # 大流星：更长更亮，用于许愿时刻
        self.tag = "meteor%d" % Meteor._seq[0]
        Meteor._seq[0] += 1
        n_seg = 8 if big else 6
        self.trail = []
        for i in range(n_seg):
            k = i / float(n_seg - 1)
            col = lerp_color("#DCEBFF" if not big else "#FFF6C0",
                             BG_BOTTOM, 0.15 + 0.75 * k)
            item = canvas.create_line(0, 0, 0, 0, fill=col, tags=(self.tag,),
                                      width=max(1, int((3 if big else 2) * (1 - k * 0.8))),
                                      capstyle="round")
            self.trail.append(item)
        self.head = canvas.create_oval(0, 0, 0, 0, fill="#FFFFFF",
                                       outline="", tags=(self.tag,))
        self.respawn(first=True)

    def respawn(self, first=False):
        w, h = self.w, self.h
        L = random.uniform(110, 190) * (1.5 if self.big else 1.0)
        self.len = L
        self.speed = random.uniform(13, 21) * (1.3 if self.big else 1.0)
        span = w * 1.6
        x = random.uniform(-span * 0.25, span * 0.75)
        y = random.uniform(-h * 0.25, h * 0.10)
        self.x, self.y = x, y
        self.life = random.uniform(0.75, 1.0)
        self._place()

    def _place(self):
        c = self.canvas
        hx, hy = self.x, self.y
        r = 3.2 if self.big else 2.2
        c.coords(self.head, hx - r, hy - r, hx + r, hy + r)
        n = len(self.trail)
        seg = self.len / n
        px, py = hx, hy
        for i, item in enumerate(self.trail):
            qx = px - M_UX * seg
            qy = py - M_UY * seg
            c.coords(item, px, py, qx, qy)
            px, py = qx, qy

    def step(self):
        self.x += M_UX * self.speed
        self.y += M_UY * self.speed
        self.life -= random.uniform(0.004, 0.010)
        self._place()
        # 飞出屏幕或燃尽 → 重生到天上看不见的地方
        if (self.life <= 0 or self.x < -self.len or self.y > self.h + self.len):
            self.respawn()
        return False

    def destroy(self):
        self.canvas.delete(self.tag)


# ================================================== 流星粒子场（文字）
class MeteorField:
    """文字粒子：每个粒子像一颗小流星，从右上方斜着划入，汇聚成字形。"""

    _seq = [0]

    def __init__(self, canvas, points, w, h, size=3.0):
        MeteorField._seq[0] += 1
        self.tag = "mf%d" % MeteorField._seq[0]
        self.canvas = canvas
        self.size = float(size)
        self.arrived = False
        diag = math.hypot(w, h)
        self.parts = []
        for tx, ty in points:
            dist = diag * random.uniform(0.45, 0.95)
            self.parts.append({
                "x": tx - M_UX * dist, "y": ty - M_UY * dist,
                "tx": tx, "ty": ty,
                "delay": random.randint(0, 18),
                "speed": random.uniform(0.10, 0.20),
                "tail": random.uniform(34, 78),
                "phase": random.uniform(0, math.tau),
            })
        self.tails = []
        self.items = []
        for _ in self.parts:
            t = canvas.create_line(0, 0, 0, 0, fill="#9FC4FF", width=1,
                                   capstyle="round", tags=(self.tag,))
            o = canvas.create_oval(0, 0, 0, 0, outline="",
                                   fill=random.choice(METEOR_COLORS),
                                   tags=(self.tag,))
            self.tails.append(t)
            self.items.append(o)
        self._place()

    def _place(self):
        c = self.canvas
        s = self.size
        for p, it, tl in zip(self.parts, self.items, self.tails):
            x, y = p["x"], p["y"]
            c.coords(it, x - s, y - s, x + s, y + s)
            if p["delay"] <= 0 and not self.arrived:
                k = p["tail"]
                c.coords(tl, x - M_UX * k, y - M_UY * k, x, y)
            else:
                c.itemconfig(tl, state="hidden")

    def step(self):
        if self.arrived:
            return True
        arrived = True
        c = self.canvas
        s = self.size
        for p, it, tl in zip(self.parts, self.items, self.tails):
            if p["delay"] > 0:
                p["delay"] -= 1
                arrived = False
                continue
            dx = p["tx"] - p["x"]
            dy = p["ty"] - p["y"]
            adx, ady = abs(dx), abs(dy)
            if adx <= 1.0 and ady <= 1.0:
                p["x"], p["y"] = p["tx"], p["ty"]
                c.itemconfig(tl, state="hidden")
                continue
            arrived = False
            mx = dx * p["speed"]
            my = dy * p["speed"]
            if 0 < adx <= 50:
                mx += math.copysign(2.2, dx)
            if 0 < ady <= 50:
                my += math.copysign(2.2, dy)
            p["x"] += max(-adx, min(adx, mx))
            p["y"] += max(-ady, min(ady, my))
            # 尾迹长度随距离收敛，越接近目标尾越短
            k = min(p["tail"], math.hypot(dx, dy) * 0.55)
            c.coords(tl, p["x"] - M_UX * k, p["y"] - M_UY * k, p["x"], p["y"])
            c.coords(it, p["x"] - s, p["y"] - s, p["x"] + s, p["y"] + s)
        if arrived:
            self.arrived = True
            for tl in self.tails:
                c.itemconfig(tl, state="hidden")
        return arrived

    def shimmer(self, t):
        """就位后呼吸微动 + 心跳式明暗。"""
        c = self.canvas
        s = self.size
        pulse = 1.0 + 0.10 * math.sin(t * 0.055)
        for p, it in zip(self.parts, self.items):
            x = p["tx"] + math.sin(t * 0.07 + p["phase"]) * 1.6
            y = p["ty"] + math.cos(t * 0.06 + p["phase"]) * 1.6
            r = s * pulse
            c.coords(it, x - r, y - r, x + r, y + r)

    def scatter(self):
        """炸开消散。"""
        for p in self.parts:
            ang = random.uniform(0, math.tau)
            spd = random.uniform(4, 15)
            p["vx"] = math.cos(ang) * spd
            p["vy"] = math.sin(ang) * spd - random.uniform(1, 5)
        self.life = 24
        return self

    def step_scatter(self):
        self.life -= 1
        for p in self.parts:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vx"] *= 0.92
            p["vy"] *= 0.92
        self.size = max(0.6, self.size * 0.9)
        s = self.size
        c = self.canvas
        for p, it, tl in zip(self.parts, self.items, self.tails):
            x, y = p["x"], p["y"]
            c.coords(it, x - s, y - s, x + s, y + s)
            c.itemconfig(tl, state="hidden")
        return self.life <= 0

    def clear(self):
        self.canvas.delete(self.tag)
        self.items.clear()
        self.tails.clear()
        self.parts.clear()


# ================================================================== 打字机
class Typewriter:
    def __init__(self, canvas, cx, y, face, size, color="#DCE8FF"):
        self.canvas = canvas
        self.cx, self.y = cx, y
        self.tkfont = tkfont.Font(family=face, size=size, weight="bold")
        self.item = canvas.create_text(cx, y, text="", font=self.tkfont,
                                       fill=color, justify="center")
        self.cursor = canvas.create_text(cx, y, text="", font=self.tkfont,
                                         fill=color)
        self.full_lines = []
        self.idx = 0
        self.n = 0
        self.tick = 0
        self.active = False

    def say(self, lines):
        self.full_lines = list(lines)
        self.idx = 0
        self.n = 0
        self.active = True
        self._show()

    def hide(self):
        self.active = False
        self.canvas.itemconfig(self.item, text="")
        self.canvas.itemconfig(self.cursor, text="")

    def _show(self):
        line = self.full_lines[self.idx][:self.n]
        self.canvas.itemconfig(self.item, text=line)

    def step(self):
        if not self.active:
            return
        self.tick += 1
        if self.tick % 3 == 0 and self.idx < len(self.full_lines):
            line = self.full_lines[self.idx]
            if self.n < len(line):
                self.n += 1
                self._show()
            else:
                # 一行打完，停一会儿换下一行
                if self.tick % 90 == 0:
                    self.idx = (self.idx + 1) % len(self.full_lines)
                    self.n = 0
                    self._show()
        # 光标：跟随当前行末，闪烁
        if self.idx < len(self.full_lines):
            shown = self.full_lines[self.idx][:self.n]
            x = self.cx + self.tkfont.measure(shown) / 2.0 + 8
            self.canvas.coords(self.cursor, x, self.y)
            blink = (self.tick // 10) % 2 == 0
            self.canvas.itemconfig(self.cursor, text="▏" if blink else "")


# ================================================================== 主演出
class MeteorShow:
    def __init__(self, root, age, name="", wish="", font=DEFAULT_FONT,
                 windowed=False):
        self.root = root
        self.age = str(age)
        self.name = name.strip()
        self.wish = wish.strip()
        self.font = font or DEFAULT_FONT
        self.w = root.winfo_screenwidth()
        self.h = root.winfo_screenheight()

        self.canvas = tk.Canvas(root, bg=BG_TOP, highlightthickness=0,
                                width=self.w, height=self.h,
                                cursor="" if windowed else "none")
        self.canvas.pack(fill="both", expand=True)

        self.t = 0
        self.running = True
        self.stage_index = -1
        self.field = None
        self.dying = []
        self.hold = 0
        self.meteors = []
        self.stars = []
        self.cake_y = 0                # 蛋糕升起进度
        self.cake_ready = False
        self.flame = self.flame_core = None
        self.flame_center = (0, 0)
        self.flame_r = (11.0, 16.0)
        self.frame_ms = FRAME_MS
        self.cost_ema = FRAME_MS / 1000.0

        self.bless_lines = ([self.wish] if self.wish else
                            ["愿你眼里总有星光 心里总有暖阳",
                             "愿所有美好 都如约而至",
                             "生日快乐 天天开心"])

        self.stages = self._build_stages()
        self.fullscreen = not windowed
        root.attributes("-fullscreen", self.fullscreen)
        root.title("流星雨之夜 · 生日快乐")

        root.bind("<Escape>", self.quit)
        root.bind("<Button-1>", self.quit)
        root.bind("<F11>", self.toggle_fullscreen)
        root.bind("<r>", self.replay)
        root.bind("<R>", self.replay)
        root.bind("<space>", self.skip)

        self.build_background()
        self.writer = Typewriter(self.canvas, self.w // 2, int(self.h * 0.60),
                                 self.font, max(15, int(self.h * 0.030)))
        self.writer.hide()
        self.root.after(150, self.next_stage)
        self.tick()

    # ------------------------------------------------------------ 剧本
    def _stage(self, text, **kw):
        st = dict(text=text, cy=0.44, bw=0.86, bh=0.30, hold=48, size=3.0,
                  cake=False)
        st.update(kw)
        return st

    def _build_stages(self):
        last = ("%s %s岁啦" % (self.name, self.age)) if self.name \
            else ("%s岁啦" % self.age)
        return [
            self._stage("Happy Birthday", cy=0.42, bh=0.22, hold=160, size=3.0),
            self._stage("生日快乐", cy=0.36, bh=0.24, hold=150, size=3.2),
            self._stage(last, cy=0.24, bh=0.17, hold=-1, size=2.8, cake=True),
        ]

    def next_stage(self):
        if not self.running:
            return
        self.stage_index += 1
        if self.stage_index >= len(self.stages):
            self.stage_index = len(self.stages) - 1        # 停在终章
        st = self.stages[self.stage_index]

        if st["cake"]:
            self.draw_cake()
            self.writer.say(self.bless_lines)

        box_w, box_h = self.w * st["bw"], self.h * st["bh"]
        fitted = fit_text(st["text"], box_w, box_h, self.font)
        if fitted is None:
            self.root.after(200, self.next_stage)
            return
        rows, mw, mh, scale = fitted
        pts = mask_to_points(rows, mw, mh, self.w * 0.5, self.h * st["cy"],
                             scale, MAX_PARTICLES)
        if not pts:
            self.root.after(200, self.next_stage)
            return
        if self.field is not None:
            self.dying.append(self.field.scatter())
            self.field = None
        self.field = MeteorField(self.canvas, pts, self.w, self.h,
                                 size=st["size"])
        self.hold = 10 ** 9 if st["hold"] < 0 else st["hold"]

    def advance(self):
        if self.field is not None:
            self.dying.append(self.field.scatter())
            self.field = None
        self.root.after(240, self.next_stage)

    # ------------------------------------------------------------ 主循环
    def tick(self):
        if not self.running:
            return
        t0 = time.perf_counter()
        self.t += 1

        for f in self.dying[:]:
            if f.step_scatter():
                f.clear()
                self.dying.remove(f)

        if self.field is not None and self.field.step():
            if self.hold > 0:
                self.hold -= 1
                self.field.shimmer(self.t)
            elif self.hold == 0:
                self.advance()
            else:
                self.field.shimmer(self.t)

        for m in self.meteors:
            m.step()

        self.update_stars()
        self.update_cake()
        self.update_flame()
        if self.stage_index >= len(self.stages) - 1:
            self.writer.step()

        cost = time.perf_counter() - t0
        self.cost_ema = self.cost_ema * 0.9 + cost * 0.1
        if self.cost_ema * 1000 > self.frame_ms * 0.75 and self.frame_ms < FRAME_MS_MAX:
            self.frame_ms += 1
        elif self.cost_ema * 1000 < self.frame_ms * 0.35 and self.frame_ms > FRAME_MS:
            self.frame_ms -= 1
        self.root.after(int(self.frame_ms), self.tick)

    # ------------------------------------------------------------ 背景
    def build_background(self):
        c = self.canvas
        bands = 30
        for i in range(bands):                      # 三段式渐变：蓝→午夜→近黑
            k = i / (bands - 1.0)
            if k < 0.55:
                col = lerp_color(BG_TOP, BG_MID, k / 0.55)
            else:
                col = lerp_color(BG_MID, BG_BOTTOM, (k - 0.55) / 0.45)
            y0 = int(self.h * i / bands)
            y1 = int(self.h * (i + 1) / bands) + 1
            c.create_rectangle(0, y0, self.w, y1, outline="", fill=col,
                               tags=("bg",))

        # 月亮 + 光晕（右上角）
        mx, my = int(self.w * 0.84), int(self.h * 0.16)
        r = max(26, int(min(self.w, self.h) * 0.035))
        for k, col in ((2.6, "#1E2C4E"), (1.9, "#2C3E68"), (1.35, "#41558A")):
            c.create_oval(mx - r * k, my - r * k, mx + r * k, my + r * k,
                          fill=col, outline="", tags=("bg",))
        c.create_oval(mx - r, my - r, mx + r, my + r,
                      fill="#F4EFD8", outline="#FFF9E3", tags=("bg",))
        for ox, oy, cr in ((-0.35, -0.2, 0.16), (0.3, 0.15, 0.11),
                           (0.05, 0.42, 0.08)):
            c.create_oval(mx + r * ox - r * cr, my + r * oy - r * cr,
                          mx + r * ox + r * cr, my + r * oy + r * cr,
                          fill="#E4DDBE", outline="", tags=("bg",))
        c.tag_lower("bg")

        for _ in range(N_STARS):
            x = random.uniform(0, self.w)
            y = random.uniform(0, self.h * 0.85)
            r2 = random.uniform(0.5, 1.7)
            item = c.create_oval(x - r2, y - r2, x + r2, y + r2, outline="",
                                 fill=random.choice(STAR_COLORS), tags=("star",))
            self.stars.append(item)

        for _ in range(N_METEORS):
            self.meteors.append(Meteor(self.canvas, self.w, self.h))

    def update_stars(self):
        if self.t % 3:
            return
        c = self.canvas
        for _ in range(8):
            c.itemconfig(random.choice(self.stars),
                         fill=random.choice(STAR_COLORS)
                         if random.random() < 0.78 else "#EAF2FF")

    # ------------------------------------------------------------ 蛋糕
    def draw_cake(self):
        if self.cake_ready or self.flame is not None:
            return
        c = self.canvas
        cx = self.w // 2
        base_y = self.h - int(self.h * 0.055)
        k = max(0.36, min(1.10, (self.h * 0.32) / 460.0))
        S = lambda v: v * k                                    # noqa: E731
        self.cake_rise = int(self.h * 0.42)                    # 从屏幕外升上来
        tag = "cake"

        c.create_oval(cx - S(275), base_y + S(8) + self.cake_rise,
                      cx + S(275), base_y + S(64) + self.cake_rise,
                      fill="#232345", outline="#4C4C7C", width=2, tags=tag)
        layers = ((228, 0, 96, "#FFB3C6", "#FF8FAB"),
                  (172, -106, 86, "#FFF3B0", "#FFE066"),
                  (118, -202, 74, "#C8E6FF", "#8ECDF7"))
        for half_w, dy, hh, body, top in layers:
            y_bottom = base_y + S(dy) + self.cake_rise
            y_top = y_bottom - S(hh)
            hw = S(half_w)
            c.create_rectangle(cx - hw, y_top, cx + hw, y_bottom,
                               fill=body, outline="", tags=tag)
            c.create_oval(cx - hw, y_top - S(16), cx + hw, y_top + S(16),
                          fill=top, outline="", tags=tag)
            n = max(5, int(hw / 24))
            step_x = 2 * hw / n
            rr = S(11)
            for i in range(n):
                px = cx - hw + (i + 0.5) * step_x
                c.create_oval(px - rr, y_top + S(2), px + rr,
                              y_top + S(2) + 2 * rr,
                              fill="#FFFFFF", outline="", tags=tag)
            br = S(5)
            for i in range(n):
                px = cx - hw + (i + 0.5) * step_x
                py = y_bottom - S(hh * 0.42)
                c.create_oval(px - br, py - br, px + br, py + br,
                              fill=random.choice(METEOR_COLORS),
                              outline="", tags=tag)

        cb = base_y - S(276) + self.cake_rise
        c.create_rectangle(cx - S(7), cb - S(72), cx + S(7), cb,
                           fill="#FF69B4", outline="", tags=tag)
        for i in range(4):
            yy = cb - S(14 + i * 16)
            c.create_line(cx - S(7), yy, cx + S(7), yy - S(8),
                          fill="#FFFFFF", width=max(1, int(S(3))), tags=tag)
        c.create_line(cx, cb - S(72), cx, cb - S(84),
                      fill="#5A3A2A", width=max(1, int(S(3))), tags=tag)

        self.flame_center = (cx, cb - S(96))
        self.flame_r = (S(11), S(16))
        self.flame = c.create_oval(0, 0, 0, 0, fill="#FFB800",
                                   outline="", tags=tag)
        self.flame_core = c.create_oval(0, 0, 0, 0, fill="#FFF6C0",
                                        outline="", tags=tag)

    def update_cake(self):
        if self.flame is None or self.cake_rise <= 0:
            return
        step = min(self.cake_rise, 7)
        self.cake_rise -= step
        self.canvas.move("cake", 0, -step)

    def update_flame(self):
        if self.flame is None:
            return
        cx, cy = self.flame_center
        s = 1.0 + 0.14 * math.sin(self.t * 0.4)
        hw, hh = self.flame_r[0] * s, self.flame_r[1] * s
        cy_now = cy - self.cake_rise
        c = self.canvas
        c.coords(self.flame, cx - hw, cy_now - hh, cx + hw, cy_now + hh)
        c.coords(self.flame_core, cx - hw * 0.45, cy_now - hh * 0.55,
                 cx + hw * 0.45, cy_now + hh * 0.45)
        if self.t % 4 == 0:
            c.itemconfig(self.flame,
                         fill=random.choice(("#FFB800", "#FF9F1C", "#FFC93C")))

    # ------------------------------------------------------------ 交互
    def quit(self, event=None):
        self.running = False
        self.root.destroy()

    def toggle_fullscreen(self, event=None):
        self.fullscreen = not self.fullscreen
        self.root.attributes("-fullscreen", self.fullscreen)
        self.canvas.configure(cursor="none" if self.fullscreen else "")
        return "break"

    def skip(self, event=None):
        if self.hold > 2:
            self.hold = 2
        return "break"

    def replay(self, event=None):
        if self.field is not None:
            self.field.clear()
            self.field = None
        for f in self.dying:
            f.clear()
        self.dying.clear()
        self.canvas.delete("cake")
        self.flame = self.flame_core = None
        self.cake_ready = False
        self.cake_rise = 0
        self.writer.hide()
        self.stage_index = -1
        self.root.after(80, self.next_stage)
        return "break"


# ================================================================== 输入框
def ask_age_name(root):
    dlg = tk.Toplevel(root)
    dlg.title("流星雨之夜")
    dlg.configure(bg="#1B2A4A")
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)

    w, h = 410, 290
    dlg.geometry("%dx%d+%d+%d" % (w, h,
                                  (dlg.winfo_screenwidth() - w) // 2,
                                  (dlg.winfo_screenheight() - h) // 2))
    frame = tk.Frame(dlg, bg="#101A33")
    frame.pack(fill="both", expand=True, padx=8, pady=8)

    tk.Label(frame, text="✦ 今天是谁的生日呀 ✦",
             font=("Microsoft YaHei", 15, "bold"),
             bg="#101A33", fg="#FFE9A8").pack(pady=(18, 10))

    row1 = tk.Frame(frame, bg="#101A33")
    row1.pack(fill="x", padx=42)
    tk.Label(row1, text="年龄", font=("Microsoft YaHei", 11),
             bg="#101A33", fg="#8FA6D9").pack(side="left")
    age_var = tk.StringVar(value="18")
    age_e = tk.Entry(row1, textvariable=age_var, font=("Microsoft YaHei", 13),
                     justify="center", bg="#1B2A4A", fg="#FFFFFF",
                     insertbackground="#FFFFFF", relief="flat")
    age_e.pack(side="left", fill="x", expand=True, padx=8, ipady=3)
    age_e.focus_set()
    age_e.select_range(0, "end")

    row2 = tk.Frame(frame, bg="#101A33")
    row2.pack(fill="x", padx=42, pady=(8, 0))
    tk.Label(row2, text="称呼", font=("Microsoft YaHei", 11),
             bg="#101A33", fg="#8FA6D9").pack(side="left")
    name_var = tk.StringVar()
    tk.Entry(row2, textvariable=name_var, font=("Microsoft YaHei", 13),
             justify="center", bg="#1B2A4A", fg="#FFFFFF",
             insertbackground="#FFFFFF", relief="flat"
             ).pack(side="left", fill="x", expand=True, padx=8, ipady=3)

    tk.Label(frame, text="回车开始 · ESC 取消（称呼可留空）",
             font=("Microsoft YaHei", 9),
             bg="#101A33", fg="#5E6F9E").pack(pady=(12, 4))

    result = {"value": None}

    def confirm(event=None):
        result["value"] = (age_var.get().strip() or "18", name_var.get().strip())
        dlg.destroy()

    def cancel(event=None):
        dlg.destroy()

    dlg.bind("<Return>", confirm)
    dlg.bind("<Escape>", cancel)
    dlg.protocol("WM_DELETE_WINDOW", cancel)
    dlg.grab_set()
    root.wait_window(dlg)
    return result["value"]


# ================================================================== 入口
def parse_args():
    p = argparse.ArgumentParser(description="生日祝福 · 流星雨之夜")
    p.add_argument("-a", "--age", help="年龄；给了就跳过输入框")
    p.add_argument("-n", "--name", default="", help="名字/称呼（可选）")
    p.add_argument("-w", "--wish", default="",
                   help='自定义祝福语（终章打字机显示，用 "｜" 分隔多行）')
    p.add_argument("--font", default=DEFAULT_FONT, help="字体名")
    p.add_argument("--windowed", action="store_true", help="窗口模式（默认全屏）")
    return p.parse_args()


def main():
    args = parse_args()

    root = tk.Tk()
    root.withdraw()

    age, name = args.age, args.name
    if age is None:
        got = ask_age_name(root)
        if got is None:
            root.destroy()
            return
        age, name = got

    wish = args.wish.replace("｜", "|")
    lines = [s.strip() for s in wish.split("|") if s.strip()] if wish else []

    root.deiconify()
    show = MeteorShow(root, age, name, font=args.font, windowed=args.windowed)
    if lines:
        show.bless_lines = lines
    root.mainloop()


if __name__ == "__main__":
    main()
