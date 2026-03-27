import os

import boto3


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is not None:
        return _s3_client

    aws_access_key_id = _require_env("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = _require_env("AWS_SECRET_ACCESS_KEY")
    region_name = os.getenv("AWS_REGION", "ap-northeast-2").strip() or "ap-northeast-2"

    _s3_client = boto3.client(
        "s3",
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name,
    )
    return _s3_client


class _LazyS3Client:
    def __getattr__(self, item):
        return getattr(get_s3_client(), item)


# Backward-compatible import for existing call sites.
s3_client = _LazyS3Client()
