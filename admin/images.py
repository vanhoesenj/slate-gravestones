"""Derivative generation. Originals stay where they are (Google Drive);
we generate a thumbnail and a display-size JPEG per photo into admin/media/,
which the admin UI serves locally and the R2 sync uploads."""
import os
from PIL import Image, ImageOps

MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media")
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
    return os.path.join(d, "thumb.jpg"), os.path.join(d, "disp.jpg")


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
    return w, h
