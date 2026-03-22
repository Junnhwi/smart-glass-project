import os
from celery import Celery
import boto3
from PIL import Image
import io

# Celery 초기화 
app = Celery('inference_tasks', broker=os.getenv('CELERY_BROKER_URL'))

# S3 클라이언트 설정
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
)

@app.task(name="process_vision_inference")
def process_vision_inference(image_key, user_id):
    """
    1. S3에서 이미지 다운로드
    2. VLM 모델 추론 (캡셔닝)
    3. 결과 저장 (RDB/Vector DB)
    """
    bucket_name = os.getenv('AWS_S3_BUCKET_NAME')
    
    try:
        # [Step 1] S3에서 이미지 가져오기
        response = s3_client.get_object(Bucket=bucket_name, Key=image_key)
        image_data = response['Body'].read()
        image = Image.open(io.BytesIO(image_data))
        
        print(f"User {user_id}: 이미지 {image_key} 다운로드 완료 ({image.size})")

        # [Step 2] VLM 추론 (현재는 플레이스홀더, 이후 팀원이 채울 부분)
        # caption = vlm_model.generate_caption(image) 
        caption = "검은색 지갑이 소파 위에 리모컨 옆에 있습니다." 
        
        # [Step 3] 결과 저장 (RDB 및 Vector DB 연동 예정)
        print(f"추론 결과: {caption}")
        
        return {"status": "success", "caption": caption}

    except Exception as e:
        print(f"추론 실패: {str(e)}")
        return {"status": "error", "message": str(e)}