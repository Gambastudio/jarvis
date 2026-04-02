"""Generate Jarvis app icon — Iron Man helmet design.

Stylized Iron Man helmet with glowing eyes and arc reactor aesthetic.
"""

import math
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
OUT_DIR = Path(__file__).parent.parent / "resources" / "AppIcon.iconset"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def lerp_color(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(len(c1)))


def make_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size

    # ── Background: rounded rect with dark metallic gradient ─────────
    bg_arr = np.zeros((s, s, 4), dtype=np.uint8)
    cx, cy = s / 2, s / 2
    max_r = s * 0.5 * math.sqrt(2)
    ys, xs = np.mgrid[0:s, 0:s]
    dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / max_r

    # Dark red-black gradient
    c_inner = np.array([35, 8, 8])
    c_outer = np.array([12, 4, 4])
    t = np.clip(dist, 0, 1)
    bg_arr[:, :, 0] = (c_inner[0] * (1 - t) + c_outer[0] * t).astype(np.uint8)
    bg_arr[:, :, 1] = (c_inner[1] * (1 - t) + c_outer[1] * t).astype(np.uint8)
    bg_arr[:, :, 2] = (c_inner[2] * (1 - t) + c_outer[2] * t).astype(np.uint8)
    bg_arr[:, :, 3] = 255
    bg = Image.fromarray(bg_arr, "RGBA")

    # Rounded rect mask
    radius = int(s * 0.22)
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    img.paste(bg, mask=mask)
    draw = ImageDraw.Draw(img)

    # ── Helmet shape (main face plate) ───────────────────────────────
    helmet = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    hd = ImageDraw.Draw(helmet)

    # Main helmet outline — rounded trapezoid shape
    hw = int(s * 0.38)  # half-width at widest
    hw_top = int(s * 0.30)  # narrower at top
    top_y = int(s * 0.16)
    mid_y = int(s * 0.42)
    chin_y = int(s * 0.82)
    chin_w = int(s * 0.18)

    # Iron Man red (#8B0000 to #CC2200)
    helmet_points = [
        (cx - hw_top, top_y),       # top-left
        (cx + hw_top, top_y),       # top-right
        (cx + hw, mid_y),           # widest right
        (cx + hw * 0.92, chin_y - s * 0.12),  # lower right
        (cx + chin_w, chin_y),      # chin right
        (cx, chin_y + s * 0.03),    # chin bottom
        (cx - chin_w, chin_y),      # chin left
        (cx - hw * 0.92, chin_y - s * 0.12),  # lower left
        (cx - hw, mid_y),           # widest left
    ]
    hd.polygon(helmet_points, fill=(180, 25, 25, 255))

    # Darker shade on edges for depth
    edge_layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge_layer)
    # Left shadow
    left_shade = [
        (cx - hw_top, top_y),
        (cx - hw, mid_y),
        (cx - hw * 0.92, chin_y - s * 0.12),
        (cx - chin_w, chin_y),
        (cx - hw_top * 0.6, top_y + s * 0.15),
        (cx - hw * 0.65, mid_y),
        (cx - hw * 0.55, chin_y - s * 0.12),
        (cx - chin_w * 0.3, chin_y - s * 0.05),
    ]
    ed.polygon(left_shade[:4], fill=(130, 15, 15, 100))
    helmet = Image.alpha_composite(helmet, edge_layer)
    hd = ImageDraw.Draw(helmet)

    # ── Gold face plate / forehead band ──────────────────────────────
    gold = (210, 170, 50, 255)
    gold_dark = (160, 120, 30, 255)

    # Forehead band
    band_y1 = int(s * 0.28)
    band_y2 = int(s * 0.35)
    band_w = int(s * 0.34)
    band_points = [
        (cx - band_w, band_y1),
        (cx + band_w, band_y1),
        (cx + band_w * 0.95, band_y2),
        (cx - band_w * 0.95, band_y2),
    ]
    hd.polygon(band_points, fill=gold)

    # Center line / nose ridge
    nose_w = int(s * 0.018)
    nose_top = band_y2
    nose_bot = int(s * 0.68)
    hd.polygon([
        (cx - nose_w, nose_top),
        (cx + nose_w, nose_top),
        (cx + nose_w * 0.6, nose_bot),
        (cx, nose_bot + s * 0.015),
        (cx - nose_w * 0.6, nose_bot),
    ], fill=gold_dark)

    # Mouth plate
    mouth_y = int(s * 0.62)
    mouth_w = int(s * 0.20)
    mouth_h = int(s * 0.12)
    # Horizontal slits
    for i in range(4):
        slit_y = mouth_y + i * int(mouth_h * 0.28)
        slit_w = mouth_w - i * int(s * 0.015)
        hd.line(
            [(cx - slit_w, slit_y), (cx + slit_w, slit_y)],
            fill=gold_dark,
            width=max(int(s * 0.006), 2),
        )

    # ── Eyes — glowing white-cyan, angular Iron Man style ──────────
    eye_y = int(s * 0.41)
    eye_h = int(s * 0.06)

    # Eye glow layer (behind eyes)
    glow_layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    for side in (-1, 1):
        # Trapezoid: wide at inner edge, narrow and angled down at outer
        inner_x = int(cx + side * s * 0.04)   # near nose
        outer_x = int(cx + side * s * 0.26)   # far edge

        eye_points = [
            (inner_x, eye_y - eye_h),                       # inner top
            (outer_x, eye_y - int(eye_h * 0.3)),            # outer top (lower)
            (outer_x, eye_y + int(eye_h * 0.4)),            # outer bottom
            (inner_x, eye_y + int(eye_h * 0.7)),            # inner bottom
        ]

        # Glow behind eye
        glow_pts_expanded = [
            (eye_points[0][0] - side * int(s * 0.02), eye_points[0][1] - int(s * 0.02)),
            (eye_points[1][0] + side * int(s * 0.02), eye_points[1][1] - int(s * 0.02)),
            (eye_points[2][0] + side * int(s * 0.02), eye_points[2][1] + int(s * 0.02)),
            (eye_points[3][0] - side * int(s * 0.02), eye_points[3][1] + int(s * 0.02)),
        ]
        glow_draw.polygon(glow_pts_expanded, fill=(100, 180, 255, 100))

        # Main eye
        hd.polygon(eye_points, fill=(200, 235, 255, 255))

        # Bright inner highlight
        highlight_points = [
            (inner_x + side * int(s * 0.02), eye_y - int(eye_h * 0.7)),
            (int((inner_x + outer_x) / 2), eye_y - int(eye_h * 0.5)),
            (int((inner_x + outer_x) / 2), eye_y + int(eye_h * 0.3)),
            (inner_x + side * int(s * 0.02), eye_y + int(eye_h * 0.4)),
        ]
        hd.polygon(highlight_points, fill=(240, 250, 255, 255))

    # Apply eye glow
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=int(s * 0.025)))
    helmet = Image.alpha_composite(helmet, glow_layer)

    # ── Outer glow (arc reactor blue) ────────────────────────────────
    arc_glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ag_draw = ImageDraw.Draw(arc_glow)
    glow_r = int(s * 0.08)
    # Small arc reactor on forehead
    arc_cx, arc_cy = int(cx), int(s * 0.22)
    for i in range(glow_r, 0, -1):
        t = 1 - (i / glow_r)
        alpha = int(t * 80)
        ag_draw.ellipse(
            [arc_cx - i, arc_cy - i, arc_cx + i, arc_cy + i],
            fill=(80, 180, 255, alpha),
        )
    # Bright center dot
    dot_r = int(glow_r * 0.3)
    ag_draw.ellipse(
        [arc_cx - dot_r, arc_cy - dot_r, arc_cx + dot_r, arc_cy + dot_r],
        fill=(200, 230, 255, 220),
    )
    arc_glow = arc_glow.filter(ImageFilter.GaussianBlur(radius=int(s * 0.01)))
    helmet = Image.alpha_composite(helmet, arc_glow)

    # ── Helmet outline / edge highlight ──────────────────────────────
    hd = ImageDraw.Draw(helmet)
    hd.line(
        helmet_points + [helmet_points[0]],
        fill=(100, 15, 15, 180),
        width=max(int(s * 0.008), 2),
    )

    # Compose helmet onto background
    img = Image.alpha_composite(img, helmet)

    # ── Subtle ambient glow around helmet ────────────────────────────
    ambient = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ad = ImageDraw.Draw(ambient)
    for i in range(3):
        r = int(s * (0.46 + i * 0.02))
        ad.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            outline=(180, 30, 30, 15 - i * 4),
            width=max(int(s * 0.005), 1),
        )
    ambient = ambient.filter(ImageFilter.GaussianBlur(radius=int(s * 0.01)))
    img = Image.alpha_composite(img, ambient)

    # Apply rounded rect mask to final image
    final_mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(final_mask).rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=255)
    img.putalpha(final_mask)

    return img


# ── Generate all iconset sizes ────────────────────────────────────────────────
SIZES = {
    "icon_16x16.png":      16,
    "icon_16x16@2x.png":   32,
    "icon_32x32.png":      32,
    "icon_32x32@2x.png":   64,
    "icon_64x64.png":      64,
    "icon_64x64@2x.png":   128,
    "icon_128x128.png":    128,
    "icon_128x128@2x.png": 256,
    "icon_256x256.png":    256,
    "icon_256x256@2x.png": 512,
    "icon_512x512.png":    512,
    "icon_512x512@2x.png": 1024,
    "icon_1024x1024.png":  1024,
}

print("Generating Iron Man icon at 1024px...")
base = make_icon(SIZE)

for filename, px in SIZES.items():
    if px == SIZE:
        out_img = base
    else:
        out_img = base.resize((px, px), Image.LANCZOS)
    out_path = OUT_DIR / filename
    out_img.save(out_path, "PNG")
    print(f"  {filename} ({px}px)")

print("Done.")
