import os
import sys
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Windows UTF-8 stdout
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).parent.resolve()
GITV_ROOT = SCRIPT_DIR.parent.parent
OUTPUT_DEFAULT_DIR = GITV_ROOT / "workbench" / "candidates" / "article-images"

# Canvas parameters (16:9 standard)
CANVAS_W = 1920
CANVAS_H = 1080
MARGIN_X = 45
MARGIN_Y = 40
GUTTER_X = 35
GUTTER_Y = 30
BORDER_WIDTH = 5

PANEL_W = (CANVAS_W - (2 * MARGIN_X) - GUTTER_X) // 2
PANEL_H = (CANVAS_H - (2 * MARGIN_Y) - GUTTER_Y) // 2

# Font setup
def get_japanese_font(size=24, bold=False):
    font_candidates = [
        "C:/Windows/Fonts/meiryob.ttc" if bold else "C:/Windows/Fonts/meiryo.ttc",
        "C:/Windows/Fonts/msgothic.ttc",
        "C:/Windows/Fonts/YuGothB.ttc" if bold else "C:/Windows/Fonts/YuGothM.ttc",
    ]
    for font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return ImageFont.load_default()

def wrap_text(text, font, max_width, draw):
    if not text:
        return []
    NO_LINE_START = set("、。！？!?ッっゃゅょャュョ…」）)』")
    lines = []
    current_line = ""
    for char in text:
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line = test_line
        else:
            # Check kinsoku shori
            if char in NO_LINE_START and current_line:
                # If the forbidden char would start a new line, force it onto the current line if reasonably close
                current_line = test_line
                lines.append(current_line)
                current_line = ""
            else:
                if current_line:
                    lines.append(current_line)
                current_line = char
    if current_line:
        lines.append(current_line)
    return lines

def get_panel_box(panel_index):
    """0-indexed: 0=top-left, 1=top-right, 2=bottom-left, 3=bottom-right"""
    col = panel_index % 2
    row = panel_index // 2
    x0 = MARGIN_X + col * (PANEL_W + GUTTER_X)
    y0 = MARGIN_Y + row * (PANEL_H + GUTTER_Y)
    x1 = x0 + PANEL_W
    y1 = y0 + PANEL_H
    return x0, y0, x1, y1

def draw_captain(draw, cx, ground_y, scale=1.0, pose="default"):
    """
    Captain (Jameson-type cyborg):
    - Cylindrical steel barrel body (#94a3b8)
    - Glowing red cyclops lens eye (#ef4444)
    - Parabolic radar dish antenna on top (#475569)
    - Ceramic white coffee mug (#ffffff)
    - 6 spider walker legs (#334155) radiating from barrel base
    """
    body_w = int(120 * scale)
    body_h = int(140 * scale)
    barrel_top = ground_y - int(185 * scale)
    barrel_bottom = ground_y - int(45 * scale)
    mouth_pos = (cx, barrel_top + int(95 * scale))

    if pose == "sleeping":
        # Bed frame & pillow
        bed_w = int(220 * scale)
        bed_h = int(90 * scale)
        draw.rounded_rectangle([cx - bed_w // 2, ground_y - bed_h, cx + bed_w // 2, ground_y], radius=8, fill="#e2e8f0", outline="#94a3b8", width=2)
        # White pillow
        draw.rounded_rectangle([cx - int(100 * scale), ground_y - int(105 * scale), cx - int(30 * scale), ground_y - int(55 * scale)], radius=6, fill="#ffffff", outline="#cbd5e1", width=2)
        # Captain cylinder head resting on pillow
        draw.rounded_rectangle([cx - int(80 * scale), ground_y - int(95 * scale), cx + int(15 * scale), ground_y - int(35 * scale)], radius=12, fill="#94a3b8", outline="#334155", width=3)
        # Dim closed cyclops eye slit
        draw.ellipse([cx - int(55 * scale), ground_y - int(75 * scale), cx - int(25 * scale), ground_y - int(55 * scale)], fill="#1e293b")
        draw.line([(cx - int(50 * scale), ground_y - int(65 * scale)), (cx - int(30 * scale), ground_y - int(65 * scale))], fill="#ef4444", width=3)
        # Radar dish tilted back on pillow
        draw.arc([cx - int(100 * scale), ground_y - int(135 * scale), cx - int(50 * scale), ground_y - int(95 * scale)], start=160, end=330, fill="#334155", width=3)
        # Warm brown blanket covering lower body
        draw.rounded_rectangle([cx - int(30 * scale), ground_y - int(85 * scale), cx + int(105 * scale), ground_y], radius=8, fill="#b45309", outline="#78350f", width=2)
        # Zzz floating sleeping symbols
        draw.text((cx - int(10 * scale), ground_y - int(135 * scale)), "z", fill="#3b82f6", font=get_japanese_font(20, bold=True))
        draw.text((cx + int(12 * scale), ground_y - int(160 * scale)), "Z", fill="#3b82f6", font=get_japanese_font(28, bold=True))
        
        mouth_pos = (cx - int(40 * scale), ground_y - int(55 * scale))
        head_top_y = ground_y - int(120 * scale)
        return mouth_pos, head_top_y

    # 1. Spider legs (6 legs: 3 left, 3 right)
    leg_color = "#334155"
    leg_width = max(3, int(5 * scale))
    leg_base_y = barrel_bottom - int(10 * scale)

    # Left legs
    for i in range(3):
        knee_x = cx - int(body_w * 0.45) - int((50 + i * 15) * scale)
        knee_y = leg_base_y - int((10 - i * 15) * scale)
        foot_x = knee_x - int((20 + i * 10) * scale)
        foot_y = ground_y
        draw.line([(cx - int(body_w * 0.35), leg_base_y), (knee_x, knee_y), (foot_x, foot_y)], fill=leg_color, width=leg_width)
        draw.ellipse([foot_x - 3, foot_y - 3, foot_x + 3, foot_y + 3], fill="#1e293b")

    # Right legs
    for i in range(3):
        knee_x = cx + int(body_w * 0.45) + int((50 + i * 15) * scale)
        knee_y = leg_base_y - int((10 - i * 15) * scale)
        foot_x = knee_x + int((20 + i * 10) * scale)
        foot_y = ground_y
        draw.line([(cx + int(body_w * 0.35), leg_base_y), (knee_x, knee_y), (foot_x, foot_y)], fill=leg_color, width=leg_width)
        draw.ellipse([foot_x - 3, foot_y - 3, foot_x + 3, foot_y + 3], fill="#1e293b")

    # 2. Cylindrical barrel body
    barrel_rect = [cx - body_w // 2, barrel_top, cx + body_w // 2, barrel_bottom]
    draw.rounded_rectangle(barrel_rect, radius=int(16 * scale), fill="#94a3b8", outline="#334155", width=max(2, int(4 * scale)))

    # Subtle metallic vertical highlight
    draw.line([(cx - int(body_w * 0.25), barrel_top + 10), (cx - int(body_w * 0.25), barrel_bottom - 10)], fill="#cbd5e1", width=max(2, int(6 * scale)))

    # 3. Cyclops eye (single large glowing red eye)
    eye_r = int(22 * scale)
    eye_cy = barrel_top + int(60 * scale)
    draw.ellipse([cx - eye_r - 4, eye_cy - eye_r - 4, cx + eye_r + 4, eye_cy + eye_r + 4], fill="#1e293b")
    draw.ellipse([cx - eye_r, eye_cy - eye_r, cx + eye_r, eye_cy + eye_r], fill="#ef4444", outline="#b91c1c", width=2)
    # Eye highlight
    draw.ellipse([cx - int(8 * scale), eye_cy - int(10 * scale), cx - int(2 * scale), eye_cy - int(4 * scale)], fill="#ffffff")

    # 4. Parabolic antenna dish on top
    ant_base_y = barrel_top
    draw.rectangle([cx - int(6 * scale), ant_base_y - int(12 * scale), cx + int(6 * scale), ant_base_y], fill="#475569")
    draw.arc([cx - int(32 * scale), ant_base_y - int(38 * scale), cx + int(32 * scale), ant_base_y - int(8 * scale)], start=190, end=350, fill="#334155", width=max(2, int(4 * scale)))
    draw.line([(cx, ant_base_y - int(22 * scale)), (cx + int(12 * scale), ant_base_y - int(42 * scale))], fill="#334155", width=max(2, int(3 * scale)))
    draw.ellipse([cx + int(10 * scale), ant_base_y - int(45 * scale), cx + int(16 * scale), ant_base_y - int(39 * scale)], fill="#ef4444")

    # 5. Mechanical arm holding coffee mug (right side)
    mug_x = cx + int(body_w * 0.38)
    mug_y = barrel_top + int(90 * scale)
    draw.line([(cx + int(body_w * 0.3), barrel_top + int(80 * scale)), (mug_x, mug_y + int(10 * scale))], fill="#475569", width=max(2, int(4 * scale)))
    mug_w = int(24 * scale)
    mug_h = int(28 * scale)
    draw.rounded_rectangle([mug_x, mug_y, mug_x + mug_w, mug_y + mug_h], radius=3, fill="#ffffff", outline="#334155", width=2)
    draw.arc([mug_x + mug_w - 2, mug_y + 4, mug_x + mug_w + int(10 * scale), mug_y + mug_h - 4], start=270, end=90, fill="#334155", width=2)
    draw.line([(mug_x + mug_w // 2, mug_y - 3), (mug_x + mug_w // 2 - 2, mug_y - 12)], fill="#94a3b8", width=2)

    # 6. Optional smartphone in other hand (left side) if pose == "phone"
    if pose == "phone":
        phone_w = int(22 * scale)
        phone_h = int(36 * scale)
        phone_x = cx - int(body_w * 0.38) - phone_w
        phone_y = barrel_top + int(75 * scale)
        # Left arm
        draw.line([(cx - int(body_w * 0.3), barrel_top + int(80 * scale)), (phone_x + phone_w, phone_y + int(20 * scale))], fill="#475569", width=max(2, int(4 * scale)))
        # Phone body
        draw.rounded_rectangle([phone_x, phone_y, phone_x + phone_w, phone_y + phone_h], radius=4, fill="#0f172a", outline="#334155", width=2)
        # Glowing screen
        draw.rectangle([phone_x + 3, phone_y + 4, phone_x + phone_w - 3, phone_y + phone_h - 6], fill="#38bdf8")

    head_top_y = ant_base_y - int(45 * scale)
    return mouth_pos, head_top_y

def draw_nagi(draw, cx, ground_y, scale=1.0, pose="default"):
    """
    Nagi:
    - Long black twintails with vivid cyan blue (#00e5ff) inner highlights
    - Black hoodie (#1e293b)
    - Cute anime chibi face
    - Ear propeller spin effect lines if excited
    """
    head_r = int(45 * scale)
    head_cy = ground_y - int(190 * scale)
    mouth_pos = (cx, head_cy + int(20 * scale))

    # 1. Back hair / Twintails
    tail_len = int(140 * scale)
    # Left twintail
    lt_x0 = cx - int(42 * scale)
    lt_y0 = head_cy - int(10 * scale)
    # Outer black
    draw.polygon([
        (lt_x0, lt_y0),
        (lt_x0 - int(35 * scale), lt_y0 + tail_len * 0.5),
        (lt_x0 - int(25 * scale), lt_y0 + tail_len),
        (lt_x0 - int(5 * scale), lt_y0 + tail_len * 0.8),
        (lt_x0, lt_y0 + int(30 * scale))
    ], fill="#0f172a", outline="#020617")
    # Inner cyan mesh
    draw.polygon([
        (lt_x0 - int(8 * scale), lt_y0 + int(25 * scale)),
        (lt_x0 - int(22 * scale), lt_y0 + tail_len * 0.55),
        (lt_x0 - int(15 * scale), lt_y0 + tail_len * 0.95),
        (lt_x0 - int(4 * scale), lt_y0 + tail_len * 0.75)
    ], fill="#00e5ff")

    # Right twintail
    rt_x0 = cx + int(42 * scale)
    rt_y0 = head_cy - int(10 * scale)
    draw.polygon([
        (rt_x0, rt_y0),
        (rt_x0 + int(35 * scale), rt_y0 + tail_len * 0.5),
        (rt_x0 + int(25 * scale), rt_y0 + tail_len),
        (rt_x0 + int(5 * scale), rt_y0 + tail_len * 0.8),
        (rt_x0, rt_y0 + int(30 * scale))
    ], fill="#0f172a", outline="#020617")
    # Inner cyan mesh
    draw.polygon([
        (rt_x0 + int(8 * scale), rt_y0 + int(25 * scale)),
        (rt_x0 + int(22 * scale), rt_y0 + tail_len * 0.55),
        (rt_x0 + int(15 * scale), rt_y0 + tail_len * 0.95),
        (rt_x0 + int(4 * scale), rt_y0 + tail_len * 0.75)
    ], fill="#00e5ff")

    # Propeller spin effect lines (Ear propeller signature!)
    prop_color = "#00e5ff"
    draw.arc([lt_x0 - int(25 * scale), lt_y0 - int(25 * scale), lt_x0 + int(15 * scale), lt_y0 + int(15 * scale)], start=120, end=300, fill=prop_color, width=2)
    draw.arc([rt_x0 - int(15 * scale), rt_y0 - int(25 * scale), rt_x0 + int(25 * scale), rt_y0 + int(15 * scale)], start=240, end=60, fill=prop_color, width=2)

    # 2. Black hoodie body
    body_top = head_cy + int(35 * scale)
    body_bottom = ground_y - int(40 * scale)
    body_w = int(75 * scale)
    draw.polygon([
        (cx - body_w * 0.4, body_top),
        (cx + body_w * 0.4, body_top),
        (cx + body_w * 0.55, body_bottom),
        (cx - body_w * 0.55, body_bottom)
    ], fill="#1e293b", outline="#0f172a", width=2)

    # 3. Legs
    leg_w = int(12 * scale)
    draw.line([(cx - int(14 * scale), body_bottom), (cx - int(14 * scale), ground_y)], fill="#0f172a", width=leg_w)
    draw.line([(cx + int(14 * scale), body_bottom), (cx + int(14 * scale), ground_y)], fill="#0f172a", width=leg_w)
    # White sneakers
    draw.rounded_rectangle([cx - int(24 * scale), ground_y - int(10 * scale), cx - int(6 * scale), ground_y], radius=3, fill="#ffffff", outline="#64748b")
    draw.rounded_rectangle([cx + int(6 * scale), ground_y - int(10 * scale), cx + int(24 * scale), ground_y], radius=3, fill="#ffffff", outline="#64748b")

    # 4. Head & Face
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill="#fef08a", outline="#0f172a", width=2)
    # Front bangs
    draw.polygon([
        (cx - head_r, head_cy - int(15 * scale)),
        (cx - int(25 * scale), head_cy + int(5 * scale)),
        (cx, head_cy - int(5 * scale)),
        (cx + int(25 * scale), head_cy + int(5 * scale)),
        (cx + head_r, head_cy - int(15 * scale)),
        (cx + int(30 * scale), head_cy - head_r),
        (cx - int(30 * scale), head_cy - head_r)
    ], fill="#0f172a")

    # Big expressive anime eyes (vivid cyan/dark)
    eye_w = int(12 * scale)
    eye_h = int(16 * scale)
    draw.ellipse([cx - int(24 * scale), head_cy - int(2 * scale), cx - int(24 * scale) + eye_w, head_cy - int(2 * scale) + eye_h], fill="#00e5ff", outline="#0f172a", width=2)
    draw.ellipse([cx + int(12 * scale), head_cy - int(2 * scale), cx + int(12 * scale) + eye_w, head_cy - int(2 * scale) + eye_h], fill="#00e5ff", outline="#0f172a", width=2)
    # Open cheerful mouth
    draw.arc([cx - int(8 * scale), head_cy + int(14 * scale), cx + int(8 * scale), head_cy + int(26 * scale)], start=0, end=180, fill="#ef4444", width=2)

    # 5. Arms (Waving or excited!)
    if pose == "excited" or pose == "default":
        draw.line([(cx - body_w * 0.4, body_top + int(10 * scale)), (cx - int(55 * scale), body_top - int(15 * scale))], fill="#1e293b", width=int(10 * scale))
        draw.line([(cx + body_w * 0.4, body_top + int(10 * scale)), (cx + int(55 * scale), body_top - int(15 * scale))], fill="#1e293b", width=int(10 * scale))
        draw.ellipse([cx - int(62 * scale), body_top - int(22 * scale), cx - int(48 * scale), body_top - int(8 * scale)], fill="#fef08a")
        draw.ellipse([cx + int(48 * scale), body_top - int(22 * scale), cx + int(62 * scale), body_top - int(8 * scale)], fill="#fef08a")

    head_top_y = head_cy - head_r
    return mouth_pos, head_top_y

def draw_sumi(draw, cx, ground_y, scale=1.0, pose="default"):
    """
    Sumi:
    - Long dark brown hair (#451a03)
    - Gray hoodie (#64748b)
    - Yellow construction safety helmet (#eab308) with green cross (#22c55e) in Genba Neko style
    - Jito-me (cool deadpan cat-like slit eyes)
    """
    head_r = int(45 * scale)
    head_cy = ground_y - int(190 * scale)
    mouth_pos = (cx, head_cy + int(20 * scale))
    helmet_top = head_cy - head_r - int(12 * scale)

    # 1. Long dark brown hair (shoulders/back)
    draw.polygon([
        (cx - int(48 * scale), head_cy),
        (cx - int(55 * scale), ground_y - int(60 * scale)),
        (cx - int(30 * scale), ground_y - int(50 * scale)),
        (cx + int(30 * scale), ground_y - int(50 * scale)),
        (cx + int(55 * scale), ground_y - int(60 * scale)),
        (cx + int(48 * scale), head_cy)
    ], fill="#451a03", outline="#270e02", width=2)

    # 2. Gray hoodie body
    body_top = head_cy + int(35 * scale)
    body_bottom = ground_y - int(40 * scale)
    body_w = int(80 * scale)
    draw.rounded_rectangle([cx - body_w // 2, body_top, cx + body_w // 2, body_bottom], radius=int(10 * scale), fill="#64748b", outline="#334155", width=2)

    # 3. Legs
    draw.line([(cx - int(15 * scale), body_bottom), (cx - int(15 * scale), ground_y)], fill="#334155", width=int(12 * scale))
    draw.line([(cx + int(15 * scale), body_bottom), (cx + int(15 * scale), ground_y)], fill="#334155", width=int(12 * scale))

    # 4. Arms & Pose
    if pose == "shock":
        draw.line([(cx - int(35 * scale), body_top + int(20 * scale)), (cx - int(46 * scale), helmet_top + int(35 * scale))], fill="#64748b", width=int(10 * scale))
        draw.ellipse([cx - int(52 * scale), helmet_top + int(25 * scale), cx - int(40 * scale), helmet_top + int(40 * scale)], fill="#fef08a")
        draw.line([(cx + int(35 * scale), body_top + int(20 * scale)), (cx + int(46 * scale), helmet_top + int(35 * scale))], fill="#64748b", width=int(10 * scale))
        draw.ellipse([cx + int(40 * scale), helmet_top + int(25 * scale), cx + int(52 * scale), helmet_top + int(40 * scale)], fill="#fef08a")
    elif pose == "pointing":
        draw.line([(cx - body_w * 0.4, body_top + int(20 * scale)), (cx - int(65 * scale), body_top + int(12 * scale))], fill="#64748b", width=int(10 * scale))
        draw.ellipse([cx - int(72 * scale), body_top + int(6 * scale), cx - int(58 * scale), body_top + int(18 * scale)], fill="#fef08a")
        draw.line([(cx + body_w * 0.4, body_top + int(20 * scale)), (cx + int(35 * scale), body_bottom - int(5 * scale))], fill="#64748b", width=int(10 * scale))
    else:
        draw.line([(cx - int(35 * scale), body_top + int(25 * scale)), (cx + int(30 * scale), body_top + int(35 * scale))], fill="#475569", width=int(12 * scale))
        draw.line([(cx + int(35 * scale), body_top + int(25 * scale)), (cx - int(30 * scale), body_top + int(35 * scale))], fill="#64748b", width=int(10 * scale))

    # 5. Face & Helmet
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill="#fef08a", outline="#270e02", width=2)

    # Yellow Safety Helmet (covers top half)
    helmet_top = head_cy - head_r - int(12 * scale)
    helmet_bottom = head_cy + int(5 * scale)
    draw.pieslice([cx - head_r - int(8 * scale), helmet_top, cx + head_r + int(8 * scale), helmet_bottom + int(40 * scale)], start=180, end=360, fill="#eab308", outline="#854d0e", width=2)
    # Green Cross mark (現場安全緑十字)
    cross_cx = cx
    cross_cy = helmet_top + int(25 * scale)
    cw = int(6 * scale)
    cl = int(18 * scale)
    draw.ellipse([cross_cx - cl // 2 - 4, cross_cy - cl // 2 - 4, cross_cx + cl // 2 + 4, cross_cy + cl // 2 + 4], fill="#ffffff")
    draw.rectangle([cross_cx - cw // 2, cross_cy - cl // 2, cross_cx + cw // 2, cross_cy + cl // 2], fill="#22c55e")
    draw.rectangle([cross_cx - cl // 2, cross_cy - cw // 2, cross_cx + cl // 2, cross_cy + cw // 2], fill="#22c55e")

    # Jito-me (Deadpan / cool eyes)
    eye_y = head_cy + int(12 * scale)
    draw.line([(cx - int(28 * scale), eye_y), (cx - int(12 * scale), eye_y)], fill="#270e02", width=3)
    draw.ellipse([cx - int(22 * scale), eye_y, cx - int(18 * scale), eye_y + 4], fill="#ca8a04")
    draw.line([(cx + int(12 * scale), eye_y), (cx + int(28 * scale), eye_y)], fill="#270e02", width=3)
    draw.ellipse([cx + int(18 * scale), eye_y, cx + int(22 * scale), eye_y + 4], fill="#ca8a04")

    # Mouth & expression lines
    if pose == "shock":
        for sx in [-15, -7, 0, 7, 15]:
            draw.line([(cx + int(sx * scale), head_cy - int(10 * scale)), (cx + int(sx * scale), head_cy + int(18 * scale))], fill="#38bdf8", width=2)
        draw.rounded_rectangle([cx - int(12 * scale), head_cy + int(22 * scale), cx + int(12 * scale), head_cy + int(36 * scale)], radius=4, fill="#ef4444", outline="#7f1d1d", width=2)
    elif pose == "pointing":
        draw.arc([cx - int(10 * scale), head_cy + int(16 * scale), cx + int(10 * scale), head_cy + int(32 * scale)], start=0, end=180, fill="#ef4444", width=3)
    else:
        draw.line([(cx - int(6 * scale), head_cy + int(26 * scale)), (cx + int(6 * scale), head_cy + int(26 * scale))], fill="#270e02", width=2)

    return mouth_pos, helmet_top

def draw_yura(draw, cx, ground_y, scale=1.0, pose="default"):
    """
    Yura:
    - Shoulder-length layered hair (#18181b)
    - Black business suit (#09090b), white shirt, black tie
    - Calm closed slit eyes / gentle smile
    """
    head_r = int(45 * scale)
    head_cy = ground_y - int(190 * scale)
    mouth_pos = (cx, head_cy + int(20 * scale))

    # Hair back
    draw.polygon([
        (cx - int(45 * scale), head_cy),
        (cx - int(45 * scale), ground_y - int(80 * scale)),
        (cx + int(45 * scale), ground_y - int(80 * scale)),
        (cx + int(45 * scale), head_cy)
    ], fill="#18181b")

    # Suit body
    body_top = head_cy + int(35 * scale)
    body_bottom = ground_y - int(40 * scale)
    body_w = int(75 * scale)
    draw.rectangle([cx - body_w // 2, body_top, cx + body_w // 2, body_bottom], fill="#09090b", outline="#000000", width=2)
    # White V-shirt & Black Tie
    draw.polygon([(cx - int(12 * scale), body_top), (cx + int(12 * scale), body_top), (cx, body_top + int(28 * scale))], fill="#ffffff")
    draw.polygon([(cx - int(4 * scale), body_top + int(6 * scale)), (cx + int(4 * scale), body_top + int(6 * scale)), (cx, body_top + int(36 * scale))], fill="#09090b")

    # Slacks
    draw.line([(cx - int(14 * scale), body_bottom), (cx - int(14 * scale), ground_y)], fill="#09090b", width=int(12 * scale))
    draw.line([(cx + int(14 * scale), body_bottom), (cx + int(14 * scale), ground_y)], fill="#09090b", width=int(12 * scale))

    # Head & Bangs
    draw.ellipse([cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r], fill="#fef08a", outline="#18181b", width=2)
    draw.pieslice([cx - head_r, head_cy - head_r, cx + head_r, head_cy + int(10 * scale)], start=190, end=350, fill="#18181b")
    # Side bangs
    draw.line([(cx - int(38 * scale), head_cy - int(10 * scale)), (cx - int(32 * scale), head_cy + int(35 * scale))], fill="#18181b", width=int(8 * scale))
    draw.line([(cx + int(30 * scale), head_cy - int(10 * scale)), (cx + int(36 * scale), head_cy + int(35 * scale))], fill="#18181b", width=int(8 * scale))

    # Gentle closed smiling slit eyes (^^)
    eye_y = head_cy + int(10 * scale)
    draw.arc([cx - int(26 * scale), eye_y - 6, cx - int(10 * scale), eye_y + 8], start=180, end=360, fill="#09090b", width=3)
    draw.arc([cx + int(10 * scale), eye_y - 6, cx + int(26 * scale), eye_y + 8], start=180, end=360, fill="#09090b", width=3)
    # Gentle smile
    draw.arc([cx - int(8 * scale), head_cy + int(16 * scale), cx + int(8 * scale), head_cy + int(26 * scale)], start=0, end=180, fill="#ef4444", width=2)

    head_top_y = head_cy - head_r
    return mouth_pos, head_top_y

def draw_speech_bubble(draw, bubble_rect, mouth_pos, text, head_top_y=None):
    """
    Draws a clean white speech bubble with a crisp black outline,
    and a triangular pointer tail pointing directly towards the speaker.
    """
    bx0, by0, bx1, by1 = bubble_rect
    bcx = (bx0 + bx1) // 2
    bcy = (by0 + by1) // 2
    mx, my = mouth_pos

    # Target point for tail tip: stop slightly above head or towards mouth
    target_y = head_top_y - 8 if head_top_y is not None else my - 30
    target_x = mx

    # Tail connection base on bubble border:
    # If speaker is below vertical center of bubble, tail emerges from bottom (by1)
    if target_y >= bcy:
        tail_base_y = by1
        tail_base_x = min(max(bx0 + 40, target_x), bx1 - 40)
        p1 = (tail_base_x - 14, tail_base_y)
        p2 = (tail_base_x + 14, tail_base_y)
        tip_x = target_x
        tip_y = max(by1 + 12, min(target_y, by1 + 65))
    else:
        tail_base_y = by0
        tail_base_x = min(max(bx0 + 40, target_x), bx1 - 40)
        p1 = (tail_base_x - 14, tail_base_y)
        p2 = (tail_base_x + 14, tail_base_y)
        tip_x = target_x
        tip_y = min(by0 - 12, max(target_y, by0 - 65))

    # 1. Draw tail triangle (filled with white)
    draw.polygon([p1, p2, (tip_x, tip_y)], fill="#ffffff")

    # 2. Draw bubble rounded rectangle
    draw.rounded_rectangle(bubble_rect, radius=20, fill="#ffffff", outline="#000000", width=4)

    # 3. Draw tail triangle over bubble seam
    draw.polygon([p1, p2, (tip_x, tip_y)], fill="#ffffff")

    # 4. Redraw the two outer edges of the tail triangle
    draw.line([p1, (tip_x, tip_y)], fill="#000000", width=4)
    draw.line([p2, (tip_x, tip_y)], fill="#000000", width=4)

    # 5. Render wrapped text
    font = get_japanese_font(size=25, bold=True)
    max_text_w = (bx1 - bx0) - 40
    lines = wrap_text(text, font, max_text_w, draw)
    if lines:
        line_h = 32
        total_text_h = len(lines) * line_h
        start_y = bcy - (total_text_h // 2)
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            lw = bbox[2] - bbox[0]
            lx = bcx - (lw // 2)
            ly = start_y + i * line_h
            draw.text((lx, ly), line, fill="#000000", font=font)

def render_storyboard(panels_spec, output_path, bubbles_only=False):
    """
    panels_spec: list of 4 dicts
    bubbles_only: if True, do not draw character bodies or monitors;
                  only draw panel borders, speech bubbles, text, and tails.
    """
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), "#ffffff")
    draw = ImageDraw.Draw(img)

    tag_font = get_japanese_font(size=18, bold=True)

    for i in range(4):
        p_box = get_panel_box(i)
        px0, py0, px1, py1 = p_box
        pw = px1 - px0
        ph = py1 - py0
        ground_y = py1 - 35

        # 1. Subtle background inside panel (clean lab tone)
        draw.rectangle([px0, py0, px1, py1], fill="#f8fafc")

        # Floor line (only if full storyboard)
        if not bubbles_only:
            draw.line([(px0, ground_y), (px1, ground_y)], fill="#cbd5e1", width=2)

        spec = panels_spec[i] if i < len(panels_spec) else {}
        chars = spec.get("characters", [])
        speaker_mouths = {}

        # Optional Terminal Monitor (only if not bubbles_only)
        if not bubbles_only:
            mon_spec = spec.get("monitor")
            if mon_spec:
                mw = int(pw * 0.38)
                mh = int(ph * 0.42)
                my0 = py0 + int(ph * 0.25)
                if mon_spec.get("position") == "left":
                    mx0 = px0 + 35
                else:
                    mx0 = px1 - mw - 35
                # Monitor frame
                draw.rounded_rectangle([mx0, my0, mx0 + mw, my0 + mh], radius=8, fill="#1e293b", outline="#0f172a", width=3)
                # Screen
                draw.rectangle([mx0 + 8, my0 + 8, mx0 + mw - 8, my0 + mh - 14], fill="#020617")
                # Stand
                scx = mx0 + mw // 2
                draw.rectangle([scx - 14, my0 + mh, scx + 14, ground_y], fill="#475569")
                draw.rectangle([scx - 45, ground_y - 6, scx + 45, ground_y], fill="#334155")
                # Terminal text lines
                line_col = "#ef4444" if mon_spec.get("error") else "#22c55e"
                for lj in range(4):
                    ly = my0 + 18 + lj * 16
                    draw.line([(mx0 + 16, ly), (mx0 + mw - 25 - (lj * 20), ly)], fill=line_col, width=3)

        # 2. Characters / Speaker Anchor Positions
        for ch in chars:
            name = ch.get("name", "").lower()
            pos = ch.get("position", "center").lower()
            pose = ch.get("pose", "default")
            scale = ch.get("scale", 1.0)

            if pos == "left":
                cx = px0 + int(pw * 0.28)
            elif pos == "right":
                cx = px0 + int(pw * 0.72)
            elif pos == "center":
                cx = px0 + int(pw * 0.50)
            elif pos == "far_left":
                cx = px0 + int(pw * 0.18)
            elif pos == "far_right":
                cx = px0 + int(pw * 0.82)
            else:
                cx = px0 + int(pw * 0.50)

            if bubbles_only:
                # In bubbles_only mode, do not draw character body.
                # Just compute anchor position for bubble tail pointer.
                mouth_pos = (cx, ground_y - int(150 * scale))
                head_top_y = ground_y - int(190 * scale)
                speaker_mouths[name] = (mouth_pos, head_top_y)
            else:
                mouth_info = None
                if name == "captain":
                    mouth_info = draw_captain(draw, cx, ground_y, scale=scale, pose=pose)
                elif name == "nagi":
                    mouth_info = draw_nagi(draw, cx, ground_y, scale=scale, pose=pose)
                elif name == "sumi":
                    mouth_info = draw_sumi(draw, cx, ground_y, scale=scale, pose=pose)
                elif name == "yura":
                    mouth_info = draw_yura(draw, cx, ground_y, scale=scale, pose=pose)
                
                if mouth_info:
                    speaker_mouths[name] = mouth_info

        # 3. Speech Bubble
        dialogue = spec.get("dialogue")
        speaker = spec.get("bubble_speaker", "").lower()
        if dialogue:
            sp_data = speaker_mouths.get(speaker)
            if not sp_data and speaker_mouths:
                # Default to first available speaker
                sp_data = list(speaker_mouths.values())[0]

            if sp_data:
                mouth_pos, head_top_y = sp_data
                mx, my = mouth_pos
                bw = min(440, int(pw * 0.58))
                bh = 115
                by0 = py0 + 25
                by1 = by0 + bh

                if mx > px0 + pw * 0.5:
                    bx1 = px1 - 25
                    bx0 = bx1 - bw
                else:
                    bx0 = px0 + 25
                    bx1 = bx0 + bw

                draw_speech_bubble(draw, (bx0, by0, bx1, by1), mouth_pos, dialogue, head_top_y=head_top_y)

        # 4. Panel border (Crisp thick black rectangular border)
        draw.rectangle([px0, py0, px1, py1], outline="#000000", width=BORDER_WIDTH)

        # 5. Panel label tag
        tag_text = f"Panel {i + 1}"
        draw.rectangle([px0 + 8, py0 + 8, px0 + 85, py0 + 32], fill="#000000")
        draw.text((px0 + 14, py0 + 10), tag_text, fill="#ffffff", font=tag_font)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG")
    print(f"✓ Storyboard successfully rendered to: {output_path}")
    return output_path

def get_demo_spec():
    return [
        {
            "characters": [
                {"name": "captain", "position": "left"},
                {"name": "nagi", "position": "right", "pose": "excited"}
            ],
            "dialogue": "隊長！これ見て！ドラレコ動いたッ！",
            "bubble_speaker": "nagi",
            "action": "Captain holding coffee on left, Nagi on right excitedly pointing at monitor"
        },
        {
            "characters": [
                {"name": "nagi", "position": "center", "pose": "excited", "scale": 1.25}
            ],
            "dialogue": "お耳のプロペラがパタパタパタパタッ！！",
            "bubble_speaker": "nagi",
            "action": "Close-up of Nagi with cyan twintails and spinning propeller effect lines"
        },
        {
            "characters": [
                {"name": "sumi", "position": "center", "pose": "default", "scale": 1.15}
            ],
            "dialogue": "…いや、ただの原チャの手書き記録やろ。",
            "bubble_speaker": "sumi",
            "action": "Sumi in yellow safety helmet with green cross, deadpan eyes, arms crossed"
        },
        {
            "characters": [
                {"name": "captain", "position": "left"},
                {"name": "yura", "position": "right", "pose": "default"}
            ],
            "dialogue": "ふふ、でも現場が回ればヨシですね。",
            "bubble_speaker": "yura",
            "action": "Captain with glowing red eye and coffee, Yura smiling warmly in business suit"
        }
    ]

def get_oauth_spec():
    return [
        {
            "monitor": {"position": "left", "error": True},
            "characters": [
                {"name": "sumi", "position": "right", "pose": "default"}
            ],
            "dialogue": "認証切れで秒死したのに５分後に復活…自動リトライ偉いじゃん",
            "bubble_speaker": "sumi",
            "action": "Sumi in yellow safety helmet looking at PC monitor with authentication error on left, arms crossed, deadpan eyes"
        },
        {
            "characters": [
                {"name": "captain", "position": "left", "pose": "phone"},
                {"name": "sumi", "position": "right", "pose": "default"}
            ],
            "dialogue": "いや、俺がスマホから手動でポチっただけやで",
            "bubble_speaker": "captain",
            "action": "Captain holding smartphone in left hand and coffee mug in right, confessing to Sumi"
        },
        {
            "characters": [
                {"name": "sumi", "position": "center", "pose": "shock", "scale": 1.25}
            ],
            "dialogue": "じゃあ前夜の定期便が死んだまま放置されてたのは…",
            "bubble_speaker": "sumi",
            "action": "Close-up of Sumi holding yellow helmet with both hands in shock, face pale with blue lines, realizing the fatal truth"
        },
        {
            "characters": [
                {"name": "captain", "position": "left", "pose": "sleeping"},
                {"name": "sumi", "position": "right", "pose": "pointing"}
            ],
            "dialogue": "隊長の睡眠時間が最大のボトルネックじゃん！",
            "bubble_speaker": "sumi",
            "action": "Captain sleeping in bed with blanket and Zzz symbols, Sumi furiously pointing at him in yellow helmet and gray hoodie"
        }
    ]

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate 4-panel manga storyboard PNG")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DEFAULT_DIR / "sample_storyboard.png"))
    parser.add_argument("--sample", action="store_true", help="Generate default demo storyboard")
    parser.add_argument("--oauth", action="store_true", help="Generate OAuth episode storyboard")
    parser.add_argument("--bubbles-only", action="store_true", help="Render only panel borders, speech bubbles, and text (no character bodies)")
    args = parser.parse_args()

    if args.oauth:
        spec = get_oauth_spec()
    else:
        spec = get_demo_spec()

    out_path = render_storyboard(spec, args.output, bubbles_only=args.bubbles_only)
