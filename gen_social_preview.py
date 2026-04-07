"""Generate the yamlwav GitHub social preview image (1280x640)."""
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H = 1280, 640
BG = (11, 14, 20)          # near-black with blue tint

LATO_BLACK   = "/usr/share/fonts/lato-fonts/Lato-Black.ttf"
LATO_BOLD    = "/usr/share/fonts/lato-fonts/Lato-Bold.ttf"
LATO_REGULAR = "/usr/share/fonts/lato-fonts/Lato-Regular.ttf"
FIRA_BOLD    = "/usr/share/fonts/fira-code/FiraCode-Bold.ttf"

# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------
img = Image.new("RGB", (W, H), BG)

# Subtle radial-ish vignette via a soft circle glow at center
glow = Image.new("RGB", (W, H), (0, 0, 0))
glow_draw = ImageDraw.Draw(glow)
for r in range(500, 0, -10):
    alpha = int(18 * (1 - r / 500))
    c = (alpha, alpha + 2, alpha + 6)
    glow_draw.ellipse(
        (W // 2 - r, H // 2 - r, W // 2 + r, H // 2 + r),
        fill=c,
    )
img = Image.blend(img, glow, 0.6)

# ---------------------------------------------------------------------------
# Sine wave visualization — 7 channels, representing encoded YAML keys
# Drawn in a 240px-tall band centred vertically at y=370
# ---------------------------------------------------------------------------
WAVE_Y_CENTER = 390
WAVE_BAND_H = 230

# channel colours (r, g, b) and wave parameters
channels = [
    {"color": (56,  189, 248), "amp": 48, "freq": 2.1, "phase": 0.00, "lw": 3},  # sky
    {"color": (52,  211, 153), "amp": 38, "freq": 1.4, "phase": 0.85, "lw": 2},  # emerald
    {"color": (250, 189,  53), "amp": 30, "freq": 3.0, "phase": 1.60, "lw": 2},  # amber
    {"color": (167, 139, 250), "amp": 42, "freq": 1.8, "phase": 2.30, "lw": 2},  # violet
    {"color": (251, 113, 133), "amp": 26, "freq": 2.6, "phase": 3.10, "lw": 2},  # rose
    {"color": (34,  211, 238), "amp": 36, "freq": 1.1, "phase": 3.80, "lw": 2},  # cyan
    {"color": (253, 186, 116), "amp": 22, "freq": 3.5, "phase": 4.50, "lw": 2},  # peach
]

# --- glow pass (blurred, semi-transparent) ---
glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
glow_wave_draw = ImageDraw.Draw(glow_layer)

for ch in channels:
    r, g, b = ch["color"]
    for x in range(W):
        y = WAVE_Y_CENTER + ch["amp"] * math.sin(
            2 * math.pi * ch["freq"] * x / W + ch["phase"]
        )
        glow_wave_draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(r, g, b, 60))

blurred_glow = glow_layer.filter(ImageFilter.GaussianBlur(radius=14))
img = img.convert("RGBA")
img = Image.alpha_composite(img, blurred_glow)

# --- crisp wave pass ---
wave_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
wave_draw = ImageDraw.Draw(wave_layer)

for ch in channels:
    r, g, b = ch["color"]
    lw = ch["lw"]
    pts = []
    for x in range(W + 1):
        # fade alpha near left/right edges (first/last 120px)
        edge_fade = min(x / 120, 1, (W - x) / 120)
        y = WAVE_Y_CENTER + ch["amp"] * math.sin(
            2 * math.pi * ch["freq"] * x / W + ch["phase"]
        )
        pts.append((x, y, int(200 * edge_fade)))

    for i in range(len(pts) - 1):
        alpha = (pts[i][2] + pts[i + 1][2]) // 2
        wave_draw.line(
            [(pts[i][0], pts[i][1]), (pts[i + 1][0], pts[i + 1][1])],
            fill=(r, g, b, alpha),
            width=lw,
        )

img = Image.alpha_composite(img, wave_layer)
img = img.convert("RGB")
draw = ImageDraw.Draw(img)

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
def centered_text(draw, y, text, font, fill):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    x = (W - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]  # line height

# "yamlwav" — monospaced, large
font_title = ImageFont.truetype(FIRA_BOLD, 118)
font_sub   = ImageFont.truetype(LATO_BOLD, 36)
font_meta  = ImageFont.truetype(LATO_REGULAR, 26)

TITLE = "yamlwav"
TAGLINE = "Configuration via .wav? Sounds good to me."
META = "Pure Python  ·  stdlib only  ·  no dependencies"

# Title — draw faint shadow first for depth
title_bbox = font_title.getbbox(TITLE)
title_w = title_bbox[2] - title_bbox[0]
title_x = (W - title_w) // 2
title_y = 108

draw.text((title_x + 3, title_y + 4), TITLE, font=font_title, fill=(20, 30, 45))
draw.text((title_x, title_y), TITLE, font=font_title, fill=(240, 246, 255))

# Tagline
sub_bbox = font_sub.getbbox(TAGLINE)
sub_w = sub_bbox[2] - sub_bbox[0]
sub_x = (W - sub_w) // 2
sub_y = title_y + (title_bbox[3] - title_bbox[1]) + 18
draw.text((sub_x, sub_y), TAGLINE, font=font_sub, fill=(130, 150, 175))

# Thin accent line between tagline and waves
line_y = sub_y + (sub_bbox[3] - sub_bbox[1]) + 28
accent_color = (56, 189, 248)   # sky blue — matches first wave
line_w = 60
draw.rectangle(
    [(W // 2 - line_w // 2, line_y), (W // 2 + line_w // 2, line_y + 2)],
    fill=accent_color,
)

# Bottom meta line
meta_bbox = font_meta.getbbox(META)
meta_w = meta_bbox[2] - meta_bbox[0]
meta_x = (W - meta_w) // 2
meta_y = H - 72
draw.text((meta_x, meta_y), META, font=font_meta, fill=(65, 85, 110))

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
out = "social_preview.png"
img.save(out, "PNG")
print(f"Saved {out} ({W}x{H})")
