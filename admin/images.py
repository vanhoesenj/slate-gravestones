"""Derivative generation. Originals stay where they are (Google Drive);
we generate a thumbnail and a display-size JPEG per photo into admin/media/,
which the admin UI serves locally and the R2 sync uploads."""
import os
from PIL import Image, ImageOps

# Override with SG_MEDIA env var (used by tests so they never touch real media)
MEDIA_DIR = os.environ.get("SG_MEDIA") or os.path.join(
    os.path.dirname(__file__), "media")
THUMB_EDGE = 480     # long edge, px
DISPLAY_EDGE = 2000  # long edge, px

RASTER_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".webp"}


def _open(path):
    try:
        img = Image.open(path)
    except Exception:
        # HEIC needs pillow-heif if photos come from an iPhone unconverted
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
            img = Image.open(path)
        except Exception as e:
            raise RuntimeError(f"Cannot open {path}: {e}")
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def exif_taken(path):
    try:
        img = Image.open(path)
        exif = img._getexif() or {}
        return str(exif.get(36867, ""))  # DateTimeOriginal
    except Exception:
        return ""


def photo_dir(photo_id):
    return os.path.join(MEDIA_DIR, str(photo_id))


def derivative_paths(photo_id):
    d = photo_dir(photo_id)
    return (os.path.join(d, "thumb.jpg"), os.path.join(d, "disp.jpg"),
            os.path.join(d, "enh.jpg"))


def _enhance(pil_img):
    """CLAHE on the lightness channel + unsharp mask: pulls shallow carving
    and worn inscriptions out of flat lighting while keeping the slate color."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        raise RuntimeError(
            "OpenCV is required for enhanced derivatives — run: "
            "pip3 install opencv-python-headless")
    bgr = cv2.cvtColor(np.array(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(l)
    bgr = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    blur = cv2.GaussianBlur(bgr, (0, 0), 3)
    sharp = cv2.addWeighted(bgr, 1.6, blur, -0.6, 0)
    return Image.fromarray(cv2.cvtColor(sharp, cv2.COLOR_BGR2RGB))


def make_derivatives(src_path, photo_id):
    """Returns (width, height) of the original."""
    img = _open(src_path)
    w, h = img.size
    d = photo_dir(photo_id)
    os.makedirs(d, exist_ok=True)
    for edge, name, q in ((THUMB_EDGE, "thumb.jpg", 80), (DISPLAY_EDGE, "disp.jpg", 85)):
        copy = img.copy()
        copy.thumbnail((edge, edge), Image.LANCZOS)
        copy.save(os.path.join(d, name), "JPEG", quality=q, optimize=True,
                  progressive=True)
    disp = Image.open(os.path.join(d, "disp.jpg"))
    _enhance(disp).save(os.path.join(d, "enh.jpg"), "JPEG", quality=85,
                        optimize=True, progressive=True)
    return w, h
