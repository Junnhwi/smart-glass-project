import argparse
import mimetypes
from pathlib import Path

from src.storage.s3 import get_s3_client


def _require_env(name: str) -> str:
    import os

    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _guess_content_type(image_path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(image_path))
    return guessed or "image/jpeg"


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload a local image to S3.")
    parser.add_argument("--image", required=True, help="Path to image inside container")
    parser.add_argument("--image-key", required=True, help="Destination S3 object key")
    args = parser.parse_args()

    image_path = Path(args.image)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    bucket_name = _require_env("AWS_S3_BUCKET_NAME")
    client = get_s3_client()
    with image_path.open("rb") as file_obj:
        client.put_object(
            Bucket=bucket_name,
            Key=args.image_key,
            Body=file_obj.read(),
            ContentType=_guess_content_type(image_path),
        )
    print(args.image_key)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
