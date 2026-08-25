"""
S3 artifact storage — uploads / downloads datasets, model pickles,
evidence JSONL, and experiment logs to S3.

Falls back to local filesystem when S3_BUCKET is not configured.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from .config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client singleton
# ---------------------------------------------------------------------------
_client = None


def _get_s3_client():
    """Return a cached boto3 S3 client (or None if S3 is not configured)."""
    global _client
    settings = get_settings()
    if not settings.s3_bucket:
        return None
    if _client is None:
        session_kwargs: Dict[str, Any] = {"region_name": settings.aws_region}
        if settings.aws_profile:
            session_kwargs["profile_name"] = settings.aws_profile
        session = boto3.Session(**session_kwargs)
        _client = session.client("s3")
    return _client


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _key(prefix: str, filename: str) -> str:
    """Build a full S3 key: <s3_prefix>/<prefix>/<filename>."""
    settings = get_settings()
    ts = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    return f"{settings.s3_prefix}/{prefix}/{ts}/{filename}"


def upload_file(local_path: str, s3_prefix: str, filename: str | None = None) -> str | None:
    """Upload a local file to S3. Returns the S3 key, or None if S3 is off."""
    client = _get_s3_client()
    if client is None:
        logger.debug("S3 not configured — skipping upload of %s", local_path)
        return None

    settings = get_settings()
    filename = filename or os.path.basename(local_path)
    key = _key(s3_prefix, filename)

    try:
        client.upload_file(local_path, settings.s3_bucket, key)
        logger.info("Uploaded %s → s3://%s/%s", local_path, settings.s3_bucket, key)
        return key
    except ClientError as exc:
        logger.error("S3 upload failed: %s", exc)
        return None


def download_file(s3_key: str, local_path: str) -> bool:
    """Download a file from S3 to local disk. Returns True on success."""
    client = _get_s3_client()
    if client is None:
        logger.debug("S3 not configured — cannot download %s", s3_key)
        return False

    settings = get_settings()
    try:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        client.download_file(settings.s3_bucket, s3_key, local_path)
        logger.info("Downloaded s3://%s/%s → %s", settings.s3_bucket, s3_key, local_path)
        return True
    except ClientError as exc:
        logger.error("S3 download failed: %s", exc)
        return False


def upload_json(prefix: str, filename: str, data: Any) -> str | None:
    """Serialize *data* to JSON and upload to S3. Returns the S3 key."""
    client = _get_s3_client()
    if client is None:
        return None

    settings = get_settings()
    key = _key(prefix, filename)
    body = json.dumps(data, default=str, indent=2).encode("utf-8")

    try:
        client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        logger.info("Uploaded JSON → s3://%s/%s", settings.s3_bucket, key)
        return key
    except ClientError as exc:
        logger.error("S3 put_object failed: %s", exc)
        return None


def upload_bytes(prefix: str, filename: str, data: bytes, content_type: str = "application/octet-stream") -> str | None:
    """Upload raw bytes to S3."""
    client = _get_s3_client()
    if client is None:
        return None

    settings = get_settings()
    key = _key(prefix, filename)

    try:
        client.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        logger.info("Uploaded bytes → s3://%s/%s", settings.s3_bucket, key)
        return key
    except ClientError as exc:
        logger.error("S3 put_object failed: %s", exc)
        return None


def download_json(s3_key: str) -> Any | None:
    """Download and parse a JSON object from S3."""
    client = _get_s3_client()
    if client is None:
        return None

    settings = get_settings()
    try:
        resp = client.get_object(Bucket=settings.s3_bucket, Key=s3_key)
        body = resp["Body"].read().decode("utf-8")
        return json.loads(body)
    except ClientError as exc:
        logger.error("S3 get_object failed: %s", exc)
        return None


def list_keys(prefix: str) -> List[str]:
    """List all S3 keys under the given prefix."""
    client = _get_s3_client()
    if client is None:
        return []

    settings = get_settings()
    full_prefix = f"{settings.s3_prefix}/{prefix}/"
    keys: List[str] = []

    try:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=settings.s3_bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
    except ClientError as exc:
        logger.error("S3 list_objects failed: %s", exc)

    return keys


def delete_key(s3_key: str) -> bool:
    """Delete a single object from S3."""
    client = _get_s3_client()
    if client is None:
        return False

    settings = get_settings()
    try:
        client.delete_object(Bucket=settings.s3_bucket, Key=s3_key)
        return True
    except ClientError as exc:
        logger.error("S3 delete_object failed: %s", exc)
        return False


def is_configured() -> bool:
    """Return True if S3 bucket is set."""
    return get_settings().s3_bucket is not None


# ---------------------------------------------------------------------------
# Convenience wrappers for common artifact types
# ---------------------------------------------------------------------------

def upload_model(local_path: str, model_name: str) -> str | None:
    """Upload a trained model pickle."""
    return upload_file(local_path, "models", filename=f"{model_name}.pkl")


def upload_dataset(local_path: str, dataset_name: str) -> str | None:
    """Upload a dataset CSV."""
    return upload_file(local_path, "datasets", filename=f"{dataset_name}.csv")


def upload_evidence(local_path: str, run_id: str) -> str | None:
    """Upload the evidence JSONL buffer after a loop run."""
    return upload_file(local_path, "evidence", filename=f"evidence_{run_id}.jsonl")


def upload_experiment_log(experiment_id: str, data: Dict[str, Any]) -> str | None:
    """Upload experiment log as JSON."""
    return upload_json("experiments", f"{experiment_id}.json", data)
