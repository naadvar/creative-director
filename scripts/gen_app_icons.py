"""Generate the native app icon + splash SOURCE images for @capacitor/assets.
Writes frontend/resources/{icon.png, splash.png, splash-dark.png}. Then:
    cd frontend && npx @capacitor/assets generate --ios
regenerates every iOS size from these.

- icon.png   : 1024x1024, OPAQUE (no alpha), full-bleed brand gradient + play
               triangle. Apple requires a 1024 icon with no alpha and no rounded
               corners (iOS applies its own mask).
- splash.png : 2732x2732, dark ink background with a centered gradient logo tile,
               matching the app's dark theme.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path("frontend/resources")
OUT.mkdir(parents=True, exist_ok=True)
VIOLET = np.array([124, 92, 255], dtype=float)
CYAN = np.array([33, 200, 255], dtype=float)
INK = (7, 7, 10)


def gradient(size: int) -> Image.Image:
    y, x = np.mgrid[0:size, 0:size]
    t = (x + y) / (2 * (size - 1))
    rgb = VIOLET[None, None, :] * (1 - t)[..., None] + CYAN[None, None, :] * t[..., None]
    return Image.fromarray(rgb.astype(np.uint8), "RGB")


def play_triangle(draw: ImageDraw.ImageDraw, size: int, scale: float) -> None:
    c = size / 2
    h = size * scale
    w = h * 0.86
    left = c - w / 2 + size * 0.03  # optical centering
    top = c - h / 2
    draw.polygon([(left, top), (left, top + h), (left + w, c)], fill=(255, 255, 255))


# --- App icon: 1024, opaque, full-bleed ---
icon = gradient(1024)
play_triangle(ImageDraw.Draw(icon), 1024, 0.42)
icon.save(OUT / "icon.png")
print("wrote", OUT / "icon.png", icon.size, icon.mode)

# --- Splash: 2732, dark with a centered logo tile ---
SP = 2732
splash = Image.new("RGB", (SP, SP), INK)
tile = gradient(820)
play_triangle(ImageDraw.Draw(tile), 820, 0.42)
# round the tile corners for a nice centered logo
mask = Image.new("L", (820, 820), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, 819, 819], radius=int(820 * 0.22), fill=255)
splash.paste(tile, ((SP - 820) // 2, (SP - 820) // 2), mask)
splash.save(OUT / "splash.png")
splash.save(OUT / "splash-dark.png")
print("wrote", OUT / "splash.png", splash.size, splash.mode)
