import os
import uuid
from PIL import Image
from config import Config


def get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower()


def allowed_file(filename: str) -> bool:
    return "." in filename and get_extension(filename) in Config.ALLOWED_EXTENSIONS


def get_media_type(filename: str) -> str | None:
    ext = get_extension(filename)
    if ext in Config.IMAGE_EXTENSIONS:
        return "image"
    if ext in Config.VIDEO_EXTENSIONS:
        return "video"
    return None


def save_upload(file_storage):
    ext = get_extension(file_storage.filename)
    filename = f"{uuid.uuid4()}.{ext}"
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    path = os.path.join(Config.UPLOAD_FOLDER, filename)

    media_type = get_media_type(file_storage.filename)

    if media_type == "image":
        image = Image.open(file_storage)
        image.verify()

        file_storage.seek(0)
        image = Image.open(file_storage)
        image.save(path)
    elif media_type == "video":
        file_storage.seek(0)
        file_storage.save(path)
    else:
        raise ValueError("Unsupported media type")

    return filename, media_type
