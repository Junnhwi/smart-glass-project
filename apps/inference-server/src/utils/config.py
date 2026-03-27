import os


class Settings:
    celery_broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    aws_region = os.getenv("AWS_REGION", "ap-northeast-2")
