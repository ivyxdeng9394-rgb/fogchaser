"""
Upload a file to Cloudflare R2 (S3-compatible).

Required env vars:
  R2_ACCOUNT_ID        — Cloudflare account ID
  R2_ACCESS_KEY_ID     — R2 API token access key
  R2_SECRET_ACCESS_KEY — R2 API token secret
  R2_BUCKET_NAME       — bucket name (e.g. fogchaser-maps)
  R2_PUBLIC_URL        — public base URL (e.g. https://pub-XXXX.r2.dev)
"""
import os
import boto3
from botocore.config import Config
from pathlib import Path


def get_r2_client():
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
    )


def upload_tif(local_path: str, bucket: str = None, client=None) -> str:
    """
    Upload a GeoTIFF to R2. Returns the public URL.

    Pass a pre-built client to avoid recreating it for every upload in a batch.
    Raises on upload failure — caller should catch and log.
    """
    if bucket is None:
        bucket = os.environ["R2_BUCKET_NAME"]
    public_url_base = os.environ["R2_PUBLIC_URL"].rstrip("/")
    if client is None:
        client = get_r2_client()

    fname = Path(local_path).name
    client.upload_file(
        local_path, bucket, fname,
        ExtraArgs={"ContentType": "image/tiff"},
    )
    return f"{public_url_base}/{fname}"


def upload_manifest(local_path: str, bucket: str = None, client=None) -> str:
    """
    Upload manifest.json to R2. Returns the public URL.
    Uses no-cache so the app always gets the latest version.
    """
    if bucket is None:
        bucket = os.environ["R2_BUCKET_NAME"]
    public_url_base = os.environ["R2_PUBLIC_URL"].rstrip("/")
    if client is None:
        client = get_r2_client()

    client.upload_file(
        local_path, bucket, "manifest.json",
        ExtraArgs={"ContentType": "application/json", "CacheControl": "no-cache, no-store"},
    )
    return f"{public_url_base}/manifest.json"
