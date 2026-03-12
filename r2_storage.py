import os
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


def upload_fileobj_to_r2(fileobj, original_filename: str, content_type: str | None = None) -> tuple[str, str]:
    ext = original_filename.rsplit(".", 1)[1].lower()
    key = f"{uuid.uuid4()}.{ext}"

    client = get_r2_client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    client.upload_fileobj(fileobj, Config.R2_BUCKET, key, ExtraArgs=extra_args)

    public_url = f"{Config.R2_PUBLIC_URL.rstrip('/')}/{key}"
    return key, public_url


def delete_from_r2(key: str) -> None:
    if not key:
        return
    client = get_r2_client()
    client.delete_object(Bucket=Config.R2_BUCKET, Key=key)
