#!/usr/bin/env python3
"""خريطة النبض — المعالجة الآلية للمقاطع المعتمدة.

لكل ملف مهمة في tools/jobs/*.json:
  1. ينزّل المقطع الأصلي (أو يولّد مقطعاً توضيحياً للعرض التجريبي).
  2. يطبع على المقطع: اسم المستشفى المصحّح، المنطقة، شعار الجمعية والحملة.
  3. يضغطه للويب (720×1280، H.264) ويستخرج صورة غلاف.
  4. ينزّل صور المنشأة والمتحدث (أو يولّد صوراً توضيحية).
  5. يضيف المشاركة إلى data/entries.json (أو data/demo-entries.json للتجريبي) ثم يحذف ملف المهمة.

يعمل محلياً أو في GitHub Actions. يحتاج: ffmpeg، rsvg-convert، Pillow مع raqm، وخطوط Tajawal في FONT_DIR.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

ROOT = Path(__file__).resolve().parent.parent
JOBS = ROOT / "tools" / "jobs"
FONT_DIR = Path(os.environ.get("FONT_DIR", ROOT / "tools" / "fonts"))
W, H = 720, 1280
NAVY = (27, 42, 92)
NAVY_DEEP = (17, 27, 64)
AMBER = (242, 163, 58)
GOLD = (212, 175, 55)
SLOGAN = "نبض واحد.. لأطفال الوطن"

if not features.check("raqm"):
    sys.exit("Pillow without raqm: Arabic text would render incorrectly. Install libraqm / libfribidi.")


def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / f"Tajawal-{weight}.ttf"), size, layout_engine=ImageFont.Layout.RAQM)


def text_rtl(d: ImageDraw.ImageDraw, xy, s: str, f, fill, anchor="ra"):
    d.text(xy, s, font=f, fill=fill, anchor=anchor, direction="rtl", language="ar")


def wrap(d: ImageDraw.ImageDraw, s: str, f, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in s.split():
        t = f"{cur} {w}".strip()
        if d.textlength(t, font=f, direction="rtl", language="ar") > max_w and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


def logo_png(width: int) -> Image.Image:
    out = Path(tempfile.gettempdir()) / f"pulse-logo-{width}.png"
    if not out.exists():
        subprocess.run(["rsvg-convert", "-w", str(width), "-o", str(out), str(ROOT / "assets" / "logo-gold.svg")], check=True)
    return Image.open(out).convert("RGBA")


def overlay(entry: dict) -> Image.Image:
    """الشريط المطبوع على المقطع: الشعار أعلى، واسم المستشفى والمنطقة والحملة أسفل."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    # تدرّج علوي خفيف خلف الشعار
    for y in range(0, 190):
        a = int(150 * (1 - y / 190))
        d.line([(0, y), (W, y)], fill=(*NAVY_DEEP, a))
    lg = logo_png(150)
    im.alpha_composite(lg, (W - lg.width - 28, 24))
    # تدرّج سفلي يحمل النصوص
    top = 900
    for y in range(top, H):
        a = int(235 * min(1, (y - top) / 160))
        d.line([(0, y), (W, y)], fill=(*NAVY_DEEP, a))
    x = W - 40
    f_name = font("ExtraBold", 46)
    lines = wrap(d, entry["hospital"], f_name, W - 80)[:2]
    y = H - 330 - (len(lines) - 1) * 54
    for ln in lines:
        text_rtl(d, (x, y), ln, f_name, (255, 255, 255))
        y += 56
    text_rtl(d, (x, y + 6), entry["region"], font("Bold", 32), AMBER)
    # خط النبض
    py = y + 76
    pts = [(40, py), (430, py), (450, py - 26), (472, py + 26), (494, py - 12), (508, py), (W - 40, py)]
    d.line(pts, fill=(*AMBER, 255), width=4, joint="curve")
    text_rtl(d, (x, py + 42), f"«{SLOGAN}»", font("Bold", 30), GOLD)
    text_rtl(d, (x, py + 90), "الجمعية السعودية لطب طوارئ الأطفال", font("Medium", 24), (255, 255, 255, 220))
    return im


def download(url: str, dest: Path):
    req = urllib.request.Request(url, headers={"User-Agent": "pulse-map-processor"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)


def demo_clip(entry: dict, dest: Path):
    """مقطع توضيحي: يعرض أجزاء النصيحة كما سيقولها الطبيب (يُستبدل بالمقطع الحقيقي)."""
    parts = entry["tip"]["parts"]
    fps, secs = 10, 12
    frames_dir = Path(tempfile.mkdtemp())
    f_part = font("Bold", 40)
    f_small = font("Medium", 26)
    for i in range(fps * secs):
        t = i / fps
        im = Image.new("RGB", (W, H), NAVY)
        d = ImageDraw.Draw(im)
        for y in range(H):
            k = y / H
            d.line([(0, y), (W, y)], fill=(int(27 + 20 * k), int(42 + 12 * k), int(92 - 30 * k)))
        # شخص توضيحي
        d.ellipse([W / 2 - 110, 300, W / 2 + 110, 520], fill=(58, 74, 128))
        d.rounded_rectangle([W / 2 - 190, 540, W / 2 + 190, 900], radius=120, fill=(58, 74, 128))
        text_rtl(d, (W / 2, 250), "مقطع توضيحي — يُستبدل بمقطع الطبيب", f_small, (255, 255, 255), anchor="ma")
        seg = min(len(parts) - 1, int(t / (secs / len(parts))))
        y = 560
        for ln in wrap(d, parts[seg], f_part, W - 140):
            text_rtl(d, (W / 2, y), ln, f_part, (255, 255, 255), anchor="ma")
            y += 54
        im.save(frames_dir / f"f{i:04d}.png")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames_dir / "f%04d.png"),
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", str(dest)],
        check=True,
    )


def demo_photo(label: str, dest: Path, tone=(58, 74, 128)):
    im = Image.new("RGB", (900, 1200), tone)
    d = ImageDraw.Draw(im)
    for y in range(1200):
        k = y / 1200
        d.line([(0, y), (900, y)], fill=(int(tone[0] * (1 - .3 * k)), int(tone[1] * (1 - .3 * k)), int(tone[2] * (1 - .2 * k))))
    for ln_i, ln in enumerate(wrap(d, label, font("Bold", 52), 760)):
        text_rtl(d, (450, 540 + ln_i * 66), ln, font("Bold", 52), (255, 255, 255), anchor="ma")
    text_rtl(d, (450, 1120), "صورة توضيحية", font("Medium", 30), (255, 255, 255, 200), anchor="ma")
    im.save(dest, quality=82)


def demo_speaker(dest: Path):
    im = Image.new("RGBA", (900, 1200), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([310, 170, 590, 470], fill=(236, 214, 141, 255))
    d.rounded_rectangle([190, 500, 710, 1200], radius=220, fill=(255, 255, 255, 255))
    d.polygon([(450, 520), (400, 700), (450, 760), (500, 700)], fill=(27, 42, 92, 255))
    im.filter(ImageFilter.SMOOTH).save(dest)


def process(job_path: Path) -> dict:
    job = json.loads(job_path.read_text(encoding="utf-8"))
    entry = job["entry"]
    eid = entry["id"]
    out = ROOT / "media" / eid
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp())

    raw = tmp / "raw.mp4"
    if job.get("demo") and not job.get("video_url"):
        demo_clip(entry, raw)
    else:
        download(job["video_url"], raw)
    ov = tmp / "overlay.png"
    overlay(entry).save(ov)
    video = out / "video.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-i", str(ov), "-filter_complex",
         f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30[v];[v][1:v]overlay=0:0[o]",
         "-map", "[o]", "-map", "0:a?", "-t", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(video)],
        check=True,
    )
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1", "-i", str(video), "-frames:v", "1", "-q:v", "4",
                    str(out / "poster.jpg")], check=True)

    photos = job.get("photos") or {}
    media = {"video": f"media/{eid}/video.mp4", "poster": f"media/{eid}/poster.jpg", "ed": []}
    if job.get("demo"):
        demo_speaker(out / "speaker.png")
        demo_photo("قسم طوارئ الأطفال", out / "ed1.jpg", (42, 104, 120))
        demo_photo("واجهة المستشفى", out / "facade.jpg", (120, 92, 52))
        media.update(speaker=f"media/{eid}/speaker.png", ed=[f"media/{eid}/ed1.jpg"], facade=f"media/{eid}/facade.jpg")
    else:
        for key in ("speaker", "facade"):
            if photos.get(key):
                ext = photos[key].split("?")[0].rsplit(".", 1)[-1].lower()
                ext = ext if ext in ("jpg", "jpeg", "png", "webp") else "jpg"
                download(photos[key], out / f"{key}.{ext}")
                media[key] = f"media/{eid}/{key}.{ext}"
        for i, url in enumerate(photos.get("ed") or [], start=1):
            download(url, out / f"ed{i}.jpg")
            media["ed"].append(f"media/{eid}/ed{i}.jpg")

    entry = {**entry, "media": media, "processed": True}
    target = ROOT / "data" / ("demo-entries.json" if job.get("demo") else "entries.json")
    entries = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    entries = [e for e in entries if e.get("id") != eid] + [entry]
    entries.sort(key=lambda e: e.get("published_at") or "")
    target.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    job_path.unlink()
    return entry


def main():
    jobs = sorted(JOBS.glob("*.json"))
    if not jobs:
        print("no jobs")
        return
    failed = 0
    for j in jobs:
        try:
            e = process(j)
            print("processed", e["id"], e["hospital"])
        except Exception as ex:  # keep the job file so it can be retried
            failed += 1
            print("FAILED", j.name, ex, file=sys.stderr)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
