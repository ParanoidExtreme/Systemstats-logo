from PIL import Image
import os
import math
import subprocess
import zipfile

os.makedirs("frames/part0", exist_ok=True)
os.makedirs("frames/part1", exist_ok=True)

size_ref = Image.open("logo_full.png").convert("RGBA")
overlay  = Image.open("cog.png").convert("RGBA")
stats    = Image.open("stats.png").convert("RGBA")
system   = Image.open("system.png").convert("RGBA")
lst      = Image.open("list.png").convert("RGBA")

FPS = 30
SECONDS_PER_ROTATION = 10
TOTAL_ROTATIONS = 1
ANIM_SECONDS = 1.5

CANVAS_WIDTH  = 1280
CANVAS_HEIGHT = 800
COG_LIST_WIDTH = 183
CENTER_OFFSET  = COG_LIST_WIDTH // 2

PAD = 800
PADDED_W = size_ref.width  + PAD * 2
PADDED_H = size_ref.height + PAD * 2

# part0: full intro animation (once)
part0_frames = FPS * SECONDS_PER_ROTATION * TOTAL_ROTATIONS
# part1: one seamless rotation loop
part1_frames = FPS * SECONDS_PER_ROTATION

degrees_per_frame = 360 / (FPS * SECONDS_PER_ROTATION)
anim_frames       = int(FPS * ANIM_SECONDS)

cog_x, cog_y = 0, 4

logo_x = (CANVAS_WIDTH  - size_ref.width)  // 2
logo_y = (CANVAS_HEIGHT - size_ref.height) // 2

STATS_DELAY  = 0
SYSTEM_DELAY = 8
COG_DELAY    = 15
LIST_DELAY   = 20
CANVAS_DELAY = 5

def ease_out_bounce(t):
    if t < 1 / 2.75:
        return 7.5625 * t * t
    elif t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    elif t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    else:
        t -= 2.625 / 2.75
        return 7.5625 * t * t + 0.984375

def ease_out_elastic(t):
    if t == 0 or t == 1:
        return t
    return (2 ** (-10 * t)) * math.sin((t - 0.075) * (2 * math.pi) / 0.3) + 1

def ease_out_back(t, overshoot=2.5):
    t -= 1
    return t * t * ((overshoot + 1) * t + overshoot) + 1

def clamp01(v):
    return max(0.0, min(1.0, v))

def apply_alpha(img, a):
    a = max(0, min(255, int(a)))
    r, g, b, a_ch = img.split()
    a_ch = a_ch.point(lambda p: int(p * a / 255))
    return Image.merge("RGBA", (r, g, b, a_ch))

def composite_onto(base, img, x, y):
    bw, bh = base.size
    iw, ih = img.size
    dx0, dy0 = x, y
    dx1, dy1 = x + iw, y + ih
    cx0 = max(dx0, 0)
    cy0 = max(dy0, 0)
    cx1 = min(dx1, bw)
    cy1 = min(dy1, bh)
    if cx0 >= cx1 or cy0 >= cy1:
        return
    sx0 = cx0 - dx0
    sy0 = cy0 - dy0
    sx1 = sx0 + (cx1 - cx0)
    sy1 = sy0 + (cy1 - cy0)
    src_crop = img.crop((sx0, sy0, sx1, sy1))
    base.alpha_composite(src_crop, dest=(cx0, cy0))

def scale_centered(img, scale):
    if scale <= 0:
        return Image.new("RGBA", img.size, (0, 0, 0, 0))
    new_w = max(1, int(img.width  * scale))
    new_h = max(1, int(img.height * scale))
    scaled = img.resize((new_w, new_h), Image.LANCZOS)
    canvas_w = max(img.width,  new_w)
    canvas_h = max(img.height, new_h)
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    ox = (canvas_w - new_w) // 2
    oy = (canvas_h - new_h) // 2
    canvas.alpha_composite(scaled, dest=(ox, oy))
    return canvas

def build_frame(i, angle_offset=0):
    angle = -((i + angle_offset) * degrees_per_frame)

    # stats: bounce in from left
    t_stats     = clamp01((i - STATS_DELAY) / anim_frames)
    e_stats     = ease_out_bounce(t_stats)
    stats_slide = int((1 - e_stats) * 400)
    stats_frame = apply_alpha(stats, clamp01(t_stats * 3) * 255)

    # system: elastic snap from right
    t_sys        = clamp01((i - SYSTEM_DELAY) / anim_frames)
    e_sys        = ease_out_elastic(t_sys)
    sys_slide    = int((1 - e_sys) * 400)
    system_frame = apply_alpha(system, clamp01(t_sys * 3) * 255)

    # cog: blast spin entry
    t_cog         = clamp01((i - COG_DELAY) / anim_frames)
    e_cog         = ease_out_back(t_cog)
    entry_spin    = (1 - e_cog) * 720
    rotated       = overlay.rotate(angle - entry_spin, resample=Image.BICUBIC, expand=True)
    pulse         = 1.0 + math.sin(i * 0.3) * 0.015 if t_cog >= 1.0 else e_cog
    rotated       = scale_centered(rotated, pulse)
    orig_cx       = overlay.width  // 2 + cog_x
    orig_cy       = overlay.height // 2 + cog_y
    new_x         = orig_cx - rotated.width  // 2
    new_y         = orig_cy - rotated.height // 2
    rotated_frame = apply_alpha(rotated, clamp01(t_cog * 2) * 255)

    # list: drop from top + scale 50->100% + slow fade
    t_lst      = clamp01((i - LIST_DELAY) / anim_frames)
    e_lst      = ease_out_bounce(t_lst)
    lst_drop   = int((1 - e_lst) * 300)
    lst_frame  = apply_alpha(scale_centered(lst, 0.5 + e_lst * 0.5), clamp01(t_lst * 1.5) * 255)

    # whole canvas elastic slide
    t_canvas        = clamp01((i - CANVAS_DELAY) / anim_frames)
    e_canvas        = ease_out_elastic(t_canvas)
    canvas_offset_x = int((1 - e_canvas) * -CENTER_OFFSET)

    padded = Image.new("RGBA", (PADDED_W, PADDED_H), (0, 0, 0, 0))
    composite_onto(padded, rotated_frame, PAD + new_x,       PAD + new_y)
    composite_onto(padded, stats_frame,   PAD - stats_slide, PAD)
    composite_onto(padded, system_frame,  PAD + sys_slide,   PAD)
    composite_onto(padded, lst_frame,     PAD,               PAD - lst_drop)

    main_canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    composite_onto(main_canvas, padded, logo_x + canvas_offset_x - PAD, logo_y - PAD)
    return main_canvas

# --- Part 0: intro animation, plays once ---
print("Rendering part0 (intro)...")
for i in range(part0_frames):
    frame = build_frame(i)
    frame.save(f"frames/part0/frame_{i:04d}.png", compress_level=6)
    print(f"  part0 frame {i+1}/{part0_frames}")

# --- Part 1: seamless loop, everything fully in, just cog spinning + pulse ---
print("Rendering part1 (loop)...")
# Use a large i so all animations are fully complete (t=1 for everything)
SETTLED = part0_frames  # all easing is done by now

for j in range(part1_frames):
    i = SETTLED + j  # keeps angle continuous from part0
    angle = -(i * degrees_per_frame)
    pulse = 1.0 + math.sin(i * 0.3) * 0.015

    rotated = overlay.rotate(angle, resample=Image.BICUBIC, expand=True)
    rotated = scale_centered(rotated, pulse)
    orig_cx = overlay.width  // 2 + cog_x
    orig_cy = overlay.height // 2 + cog_y
    new_x   = orig_cx - rotated.width  // 2
    new_y   = orig_cy - rotated.height // 2

    padded = Image.new("RGBA", (PADDED_W, PADDED_H), (0, 0, 0, 0))
    composite_onto(padded, rotated,  PAD + new_x, PAD + new_y)
    composite_onto(padded, stats,    PAD,          PAD)
    composite_onto(padded, system,   PAD,          PAD)
    composite_onto(padded, lst,      PAD,          PAD)

    main_canvas = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    composite_onto(main_canvas, padded, logo_x - PAD, logo_y - PAD)

    main_canvas.save(f"frames/part1/frame_{j:04d}.png", compress_level=6)
    print(f"  part1 frame {j+1}/{part1_frames}")

# --- MP4 preview (part0 only for sanity check) ---
print("Compiling preview MP4...")
subprocess.run([
    "ffmpeg", "-y",
    "-framerate", str(FPS),
    "-i", "frames/part0/frame_%04d.png",
    "-filter_complex", "color=c=black:s=1280x800[bg];[bg][0:v]overlay=format=auto",
    "-frames:v", str(part0_frames),
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "-crf", "18",
    "preview.mp4"
])

# --- bootanimation.zip ---
print("Building bootanimation.zip...")

desc = f"{CANVAS_WIDTH} {CANVAS_HEIGHT} 60\np 1 0 part0\np 0 0 part1\n"

with zipfile.ZipFile("bootanimation.zip", "w", compression=zipfile.ZIP_STORED) as zf:
    zf.writestr("desc.txt", desc)

    # audio in part0 folder
    zf.write("audio.wav", "part0/audio.wav")

    for i in range(part0_frames):
        zf.write(f"frames/part0/frame_{i:04d}.png", f"part0/frame_{i:04d}.png")
        print(f"  zipping part0 {i+1}/{part0_frames}")

    for j in range(part1_frames):
        zf.write(f"frames/part1/frame_{j:04d}.png", f"part1/frame_{j:04d}.png")
        print(f"  zipping part1 {j+1}/{part1_frames}")

print("Done!")
print("Push with:")
print("  adb root && adb push bootanimation.zip /system/media/bootanimation.zip")