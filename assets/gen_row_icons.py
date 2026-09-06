"""Genera los PNG base64 de los iconos de fila (grip / trash / calendar) que
van embebidos en `_ICON_B64` dentro de task_widget.py.

Rasteriza las formas de los SVG de al lado con anti-alias por campo de distancia
(SDF) — sin depender de Pillow ni de un navegador. Corré:

    python assets/gen_row_icons.py

y pegá la salida en el dict `_ICON_B64`.
"""
import base64, math, struct, zlib


def _png(w, h, rgba):
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data +
                struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(rgba[y * w * 4:(y + 1) * w * 4]) for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _rgb(s):
    s = s.lstrip("#")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _seg(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _render(w, h, color, sdf, ss=5):
    r, g, b = _rgb(color)
    buf = bytearray(w * h * 4)
    for y in range(h):
        for x in range(w):
            cov = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    d = sdf(x + (sx + .5) / ss, y + (sy + .5) / ss)
                    cov += max(0.0, min(1.0, 0.5 - d))
            i = (y * w + x) * 4
            buf[i:i + 4] = bytes((r, g, b, int(round(255 * cov / (ss * ss)))))
    return buf


def _grip(w, h):
    pts = [(w * cx, h * cy) for cx in (.34, .66) for cy in (.22, .50, .78)]
    return lambda x, y: min(math.hypot(x - px, y - py) - 1.9 for px, py in pts)


def _strokes(w, h, paths, hw=1.05):
    sx, sy = w / 24.0, h / 24.0

    def sdf(x, y):
        ux, uy = x / sx, y / sy
        best = min(_seg(ux, uy, *p[i], *p[i + 1])
                   for p in paths for i in range(len(p) - 1))
        return (best - hw) * min(sx, sy)
    return sdf


TRASH = [[(3, 6), (21, 6)],
         [(5, 6.5), (5, 20), (6.2, 21.6), (7.5, 22), (16.5, 22), (17.8, 21.6), (19, 20), (19, 6.5)],
         [(8, 6), (8, 4), (8.6, 2.6), (10, 2), (14, 2), (15.4, 2.6), (16, 4), (16, 6)],
         [(10, 10.5), (10, 17.5)], [(14, 10.5), (14, 17.5)]]
CAL = [[(5, 4), (19, 4), (20, 4.4), (20.5, 5.4), (20.5, 19), (20, 20),
        (19, 20.5), (5, 20.5), (4, 20), (3.5, 19), (3.5, 5.4), (4, 4.4), (5, 4)],
       [(8, 2), (8, 6)], [(16, 2), (16, 6)], [(3.5, 10), (20.5, 10)]]

COLORS = {"dark":  dict(dim="#8c8a7f", fg="#f3f1e7", over="#ff5a52", acc="#ffd23f"),
          "light": dict(dim="#71717a", fg="#1d1d1f", over="#d70015", acc="#0a84ff")}
GW, GH, TW, TH = 16, 26, 16, 16

if __name__ == "__main__":
    for theme, c in COLORS.items():
        specs = [
            (f"{theme}_grip_idle",  GW, GH, c["dim"],  _grip(GW, GH)),
            (f"{theme}_grip_hot",   GW, GH, c["fg"],   _grip(GW, GH)),
            (f"{theme}_trash_idle", TW, TH, c["dim"],  _strokes(TW, TH, TRASH)),
            (f"{theme}_trash_hot",  TW, TH, c["over"], _strokes(TW, TH, TRASH)),
            (f"{theme}_cal_idle",   TW, TH, c["dim"],  _strokes(TW, TH, CAL)),
            (f"{theme}_cal_hot",    TW, TH, c["acc"],  _strokes(TW, TH, CAL)),
        ]
        for key, w, h, color, sdf in specs:
            b64 = base64.b64encode(_png(w, h, _render(w, h, color, sdf))).decode()
            parts = [b64[i:i + 96] for i in range(0, len(b64), 96)]
            body = "\n        ".join(f"'{p}'" for p in parts)
            print(f"    '{key}': (\n        {body}\n    ),")
