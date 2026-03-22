import os
import io
import torch
from celery import Celery
import boto3
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration

# Celery 초기화
app = Celery('inference_tasks', broker=os.getenv('CELERY_BROKER_URL'))

# [AI 모델 로드] 서버 시작 시 한 번만 로드하여 GPU에 올립니다
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"현재 사용 장치: {device}")

# 모델을 로드합니다
processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base").to(device)

# S3 클라이언트 설정
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

@app.task(name="process_vision_inference")
def process_vision_inference(image_key, user_id):
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
    
    try:
        # [Step 1] S3에서 이미지 다운로드
        response = s3_client.get_object(Bucket=bucket_name, Key=image_key)
        image_data = response['Body'].read()
        raw_image = Image.open(io.BytesIO(image_data)).convert('RGB')
        
        # [Step 2] 실제 BLIP 모델 추론 [cite: 13, 14]
        # 이미지를 모델 형식에 맞게 변환하여 GPU로 전송합니다
        inputs = processor(raw_image, return_tensors="pt").to(device)
        
        # 캡션 생성
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