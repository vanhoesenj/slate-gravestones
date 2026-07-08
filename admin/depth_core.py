"""Monocular depth estimation for the virtual raking-light viewer.
Requires (one-time, ~2GB): pip3 install torch transformers
First build downloads the Depth-Anything-V2-Small model (~100MB)."""
import os

MAX_EDGE = 1200  # long edge of the published depth map

_pipe = None


def get_pipe():
    global _pipe
    if _pipe is None:
        import torch
        from transformers import pipeline
        device = 0 if torch.cuda.is_available() else (
            "mps" if getattr(torch.backends, "mps", None)
            and torch.backends.mps.is_available() else -1)
        _pipe = pipeline("depth-estimation",
                         model="depth-anything/Depth-Anything-V2-Small-hf",
                         device=device)
    return _pipe


def build_depth(disp_path, out_path):
    """Estimate depth for one display image; save 8-bit grayscale JPEG."""
    import numpy as np
    from PIL import Image

    img = Image.open(disp_path).convert("RGB")
    depth = get_pipe()(img)["depth"]          # PIL image, arbitrary range
    arr = np.array(depth, dtype=np.float32)
    lo, hi = float(arr.min()), float(arr.max())
    arr = (arr - lo) / max(1e-6, hi - lo)
    dep = Image.fromarray((arr * 255).astype("uint8"))
    if max(dep.size) > MAX_EDGE:
        dep.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    dep.save(out_path, "JPEG", quality=90, optimize=True)
