from io import BytesIO
from PIL import Image

from config import Config


def get_extension(filename):
    return filename.rsplit(".", 1)[1].lower()


def allowed_file(filename):
    return "." in filename and get_extension(filename) in Config.ALLOWED_EXTENSIONS


def get_media_type(filename):
    ext = get_extension(filename)
    if ext in Config.IMAGE_EXTENSIONS:
        return "image"
    if ext in Config.VIDEO_EXTENSIONS:
        return "video"
    return None


def prepare_upload(file):
    media_type = get_media_type(file.filename)

    if media_type == "image":
        image = Image.open(file)
        image.verify()

        file.seek(0)
        image = Image.open(file)

        output = BytesIO()
        save_format = image.format if image.format else "PNG"
        image.save(output, format=save_format)
        output.seek(0)
        return output, media_type

    if media_type == "video":
        file.seek(0)
        data = BytesIO(file.read())
        data.seek(0)
        return data, media_type

    raise ValueError("Unsupported media type")