"""Letterform extraction: find individual carved characters in the enhanced
photos and save a crop per letter, for the specimen-sheet ("Letters") view
and carver-attribution work.

Requires: brew install tesseract   and   pip3 install pytesseract
"""
import os
import re

from PIL import Image, ImageOps

LETTER_DIR = os.path.join(os.path.dirname(__file__), "media", "letters")
KEEP = re.compile(r"[A-Za-z0-9&]")
MIN_PX = 18        # minimum box side in pixels
MIN_WORD_CONF = 50
PAD = 0.18         # crop padding as fraction of box size
CROP_EDGE = 96     # saved crop long edge


def extract_letters(enh_path):
    """Returns list of (ch, box) with boxes in top-left-origin pixel coords."""
    import pytesseract
    img = Image.open(enh_path).convert("L")
    W, H = img.size
    # word-level confidence gates the character boxes
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(data["text"])):
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf >= MIN_WORD_CONF and data["text"][i].strip():
            words.append((data["left"][i], data["top"][i],
                          data["left"][i] + data["width"][i],
                          data["top"][i] + data["height"][i], conf))
    out = []
    for line in pytesseract.image_to_boxes(img).splitlines():
        parts = line.split()
        if len(parts) < 5 or not KEEP.fullmatch(parts[0]):
            continue
        ch = parts[0].upper()
        x0, y0b, x1, y1b = map(int, parts[1:5])
        y0, y1 = H - y1b, H - y0b          # tesseract boxes are bottom-origin
        if x1 - x0 < MIN_PX or y1 - y0 < MIN_PX:
            continue
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        conf = next((c for (wx0, wy0, wx1, wy1, c) in words
                     if wx0 <= cx <= wx1 and wy0 <= cy <= wy1), None)
        if conf is None:
            continue
        out.append((ch, (x0, y0, x1, y1), conf))
    return out, img


def save_crop(img, box, letter_id):
    x0, y0, x1, y1 = box
    pw, ph = int((x1 - x0) * PAD), int((y1 - y0) * PAD)
    crop = img.crop((max(0, x0 - pw), max(0, y0 - ph),
                     min(img.width, x1 + pw), min(img.height, y1 + ph)))
    crop = ImageOps.autocontrast(crop, cutoff=1)
    crop.thumbnail((CROP_EDGE, CROP_EDGE), Image.LANCZOS)
    os.makedirs(LETTER_DIR, exist_ok=True)
    path = os.path.join(LETTER_DIR, f"{letter_id}.jpg")
    crop.save(path, "JPEG", quality=85)
    return path


def crop_vector(letter_id, size=32):
    """32x32 grayscale vector of a saved crop, for shape clustering."""
    import numpy as np
    p = os.path.join(LETTER_DIR, f"{letter_id}.jpg")
    img = Image.open(p).convert("L").resize((size, size), Image.LANCZOS)
    v = np.asarray(img, dtype=float).flatten()
    v = v - v.mean()
    n = np.linalg.norm(v)
    return v / n if n > 0 else v
