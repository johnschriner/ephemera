import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB

    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif", "mp4", "webm"}
    IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
    VIDEO_EXTENSIONS = {"mp4", "webm"}

    MAX_APPROVED_IMAGES = 50
    FADING_COUNT = 5
