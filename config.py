import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static/uploads")
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB

    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "mp4", "webm"}
    IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
    VIDEO_EXTENSIONS = {"mp4", "webm"}

    MAX_APPROVED_IMAGES = 50

    R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
    R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
    R2_BUCKET = os.getenv("R2_BUCKET")
    R2_ENDPOINT = os.getenv("R2_ENDPOINT")
    R2_PUBLIC_URL = os.getenv("R2_PUBLIC_URL")