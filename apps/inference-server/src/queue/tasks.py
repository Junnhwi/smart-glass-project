import os
import io
from celery import Celery
from PIL import Image

from src.models.blip import get_blip_components
from src.storage.s3 import get_s3_client

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
app = Celery("inference_tasks", broker=broker_url)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


@app.task(name="process_vision_inference")
def process_vision_inference(image_key, user_id):
    bucket_name = _require_env("AWS_S3_BUCKET_NAME")

    try:
        device, model, processor = get_blip_components()
        print(f"현재 사용 장치: {device}")

        s3_client = get_s3_client()
        response = s3_client.get_object(Bucket=bucket_name, Key=image_key)
        image_data = response["Body"].read()
        raw_image = Image.open(io.BytesIO(image_data)).convert("RGB")
        inputs = processor(raw_image, return_tensors="pt").to(device)

        out = model.generate(**inputs)
        caption = processor.decode(out[0], skip_special_tokens=True)

        print(f"--- [추론 성공] ---")
        print(f"User: {user_id} / File: {image_key}")
        print(f"Result: {caption}")
        print(f"-------------------")

        return {"status": "success", "caption": caption}
    except Exception as e:
        print(f"추론 실패: {str(e)}")
        return {"status": "error", "message": str(e)}
