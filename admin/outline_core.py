"""Silhouette extraction core, shared by the admin app's "Trace new outlines"
button and scripts/extract_outlines.py. Requires: pip3 install rembg onnxruntime
(first use downloads a ~170MB segmentation model)."""

MIN_AREA_FRAC = 0.12   # reject masks smaller than this fraction of the image
SIMPLIFY = 0.002       # contour simplification (fraction of perimeter)

_session = None


def get_session():
    """Load the segmentation model once per process."""
    global _session
    if _session is None:
        from rembg import new_session
        _session = new_session("u2net")
    return _session


def extract(disp_path):
    """Returns (svg_path_d, viewbox_h) on success or (None, reason)."""
    import cv2
    import numpy as np
    from PIL import Image
    from rembg import remove

    img = Image.open(disp_path)
    mask = remove(img, only_mask=True, session=get_session())
    m = np.array(mask)
    _, m = cv2.threshold(m, 127, 255, cv2.THRESH_BINARY)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, "no foreground found"
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < MIN_AREA_FRAC * m.shape[0] * m.shape[1]:
        return None, "foreground too small (stone not dominant in frame?)"
    c = cv2.approxPolyDP(c, SIMPLIFY * cv2.arcLength(c, True), True)
    pts = c.reshape(-1, 2).astype(float)
    x0, y0 = pts.min(axis=0)
    w, h = pts.max(axis=0) - (x0, y0)
    if w < 10 or h < 10:
        return None, "degenerate contour"
    scale = 100.0 / w
    pts = (pts - (x0, y0)) * scale
    d = "M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z"
    return d, round(h * scale, 1)
