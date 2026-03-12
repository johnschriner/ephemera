import uuid
import boto3
from botocore.config import Config as BotoConfig

from config import Config


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=Config.R2_ENDPOINT,
        aws_access_key_id=Config.R2_ACCESS_KEY,
        aws_secret_access_key=Config.R2_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def get_public_url(key: str) -> str:
    return f"{Config.R2_PUBLIC_URL.rstrip('/')}/{key}"


def infer_media_type_from_key(key: str) -> str | None:
    ext = key.rsplit(".", 1)[-1].lower() if "." in key else ""
    if ext in Config.IMAGE_EXTENSIONS:
        return "image"
    if ext in Config.VIDEO_EXTENSIONS:
        return "video"
    return None


def upload_fileobj_to_r2(
    fileobj,
    original_filename: str,
    content_type: str | None = None,
    caption: str = "",
    status: str = "pending",
    media_type: str = "image",
    uploaded_at: str = "",
) -> tuple[str, str]:
    ext = original_filename.rsplit(".", 1)[1].lower()
    key = f"{uuid.uuid4()}.{ext}"

    client = get_r2_client()

    metadata = {
        "caption": caption or "",
        "status": status or "pending",
        "media_type": media_type or infer_media_type_from_key(key) or "image",
        "uploaded_at": uploaded_at or "",
    }

    extra_args = {"Metadata": metadata}
    if content_type:
        extra_args["ContentType"] = content_type

    client.upload_fileobj(fileobj, Config.R2_BUCKET, key, ExtraArgs=extra_args)

    return key, get_public_url(key)


def list_r2_objects() -> list[dict]:
    client = get_r2_client()
    paginator = client.get_paginator("list_objects_v2")

    objects = []
    for page in paginator.paginate(Bucket=Config.R2_BUCKET):
        for obj in page.get("Contents", []):
            objects.append(
                {
                    "key": obj["Key"],
                    "last_modified": obj.get("LastModified"),
                    "size": obj.get("Size"),
                }
            )

    return objects


def get_object_metadata(key: str) -> dict:
    client = get_r2_client()
    response = client.head_object(Bucket=Config.R2_BUCKET, Key=key)
    return response.get("Metadata", {})


def update_object_metadata(
    key: str,
    caption: str = "",
    status: str = "approved",
    media_type: str = "image",
    uploaded_at: str = "",
):
    client = get_r2_client()
    head = client.head_object(Bucket=Config.R2_BUCKET, Key=key)

    metadata = {
        "caption": caption or "",
        "status": status or "approved",
        "media_type": media_type or infer_media_type_from_key(key) or "image",
        "uploaded_at": uploaded_at or "",
    }

    copy_source = {"Bucket": Config.R2_BUCKET, "Key": key}

    extra_args = {
        "Bucket": Config.R2_BUCKET,
        "Key": key,
        "CopySource": copy_source,
        "Metadata": metadata,
        "MetadataDirective": "REPLACE",
    }

    content_type = head.get("ContentType")
    if content_type:
        extra_args["ContentType"] = content_type

    cache_control = head.get("CacheControl")
    if cache_control:
        extra_args["CacheControl"] = cache_control

    client.copy_object(**extra_args)


def delete_from_r2(key: str) -> None:
    if not key:
        return
    client = get_r2_client()
    client.delete_object(Bucket=Config.R2_BUCKET, Key=key)