"""Cloudflare R2 sync (S3-compatible API via boto3).

Config lives in config.json at the repo root (gitignored):
{
  "r2": {
    "account_id": "...",
    "access_key_id": "...",
    "secret_access_key": "...",
    "bucket": "slate-gravestones",
    "public_base_url": "https://pub-XXXX.r2.dev"
  },
  "photo_source_dir": "/Users/jvh/Library/CloudStorage/GoogleDrive-.../My Drive/Gravestones"
}
"""
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def r2_configured():
    cfg = load_config().get("r2", {})
    return all(cfg.get(k) for k in
               ("account_id", "access_key_id", "secret_access_key", "bucket"))


def client():
    import boto3
    cfg = load_config()["r2"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{cfg['account_id']}.r2.cloudflarestorage.com",
        aws_access_key_id=cfg["access_key_id"],
        aws_secret_access_key=cfg["secret_access_key"],
        region_name="auto",
    ), cfg["bucket"]


def upload_photo(photo_id, thumb_path, disp_path, enh_path=None,
                 depth_path=None):
    s3, bucket = client()
    files = [(thumb_path, "thumb.jpg"), (disp_path, "disp.jpg")]
    if enh_path and os.path.exists(enh_path):
        files.append((enh_path, "enh.jpg"))
    if depth_path and os.path.exists(depth_path):
        files.append((depth_path, "depth.jpg"))
    for path, name in files:
        s3.upload_file(path, bucket, f"img/{photo_id}/{name}",
                       ExtraArgs={"ContentType": "image/jpeg",
                                  "CacheControl": "public, max-age=31536000"})


def upload_object(key, path, content_type):
    s3, bucket = client()
    s3.upload_file(path, bucket, key,
                   ExtraArgs={"ContentType": content_type,
                              "CacheControl": "public, max-age=31536000"})


def public_base():
    return load_config().get("r2", {}).get("public_base_url", "").rstrip("/")
