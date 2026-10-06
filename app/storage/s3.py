import os
import io
import logging
from typing import Optional, Tuple
from app.config import settings

logger = logging.getLogger(__name__)

try:
    import boto3
    from botocore.exceptions import ClientError, BotoCoreError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    logger.info("boto3 is not available. S3 storage disabled; local fallback active.")

class S3StorageManager:
    """
    Manages cloud object storage via AWS S3 / Cloudflare R2 / MinIO / Supabase Storage.
    Falls back gracefully when S3 credentials are not configured.
    """

    def __init__(self):
        self.bucket_name = settings.S3_BUCKET_NAME if hasattr(settings, "S3_BUCKET_NAME") else os.getenv("S3_BUCKET_NAME")
        self.access_key = getattr(settings, "AWS_ACCESS_KEY_ID", None) or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_key = getattr(settings, "AWS_SECRET_ACCESS_KEY", None) or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region = getattr(settings, "AWS_REGION", "us-east-1") or os.getenv("AWS_REGION", "us-east-1")
        self.endpoint_url = getattr(settings, "AWS_ENDPOINT_URL", None) or os.getenv("AWS_ENDPOINT_URL")
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(BOTO3_AVAILABLE and self.bucket_name and ((self.access_key and self.secret_key) or os.getenv("AWS_EXECUTION_ENV")))

    def _get_client(self):
        if not self.is_configured:
            return None
        if self._client is None:
            try:
                kwargs = {"region_name": self.region}
                if self.access_key and self.secret_key:
                    kwargs["aws_access_key_id"] = self.access_key
                    kwargs["aws_secret_access_key"] = self.secret_key
                if self.endpoint_url:
                    kwargs["endpoint_url"] = self.endpoint_url

                self._client = boto3.client("s3", **kwargs)
            except Exception as e:
                logger.error(f"Failed to initialize S3 client: {e}")
                self._client = None
        return self._client

    def upload_file(self, file_bytes: bytes, storage_key: str, content_type: str = "application/pdf") -> bool:
        client = self._get_client()
        if not client:
            return False
        try:
            client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=file_bytes,
                ContentType=content_type,
            )
            logger.info(f"Uploaded file to S3: s3://{self.bucket_name}/{storage_key}")
            return True
        except (ClientError, BotoCoreError) as e:
            logger.error(f"Failed to upload to S3 ({storage_key}): {e}")
            return False

    def download_file(self, storage_key: str) -> Optional[bytes]:
        client = self._get_client()
        if not client:
            return None
        try:
            response = client.get_object(Bucket=self.bucket_name, Key=storage_key)
            return response["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                logger.warning(f"S3 key does not exist: {storage_key}")
            else:
                logger.error(f"Failed to download from S3 ({storage_key}): {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected S3 download error ({storage_key}): {e}")
            return None

    def delete_file(self, storage_key: str) -> bool:
        client = self._get_client()
        if not client:
            return False
        try:
            client.delete_object(Bucket=self.bucket_name, Key=storage_key)
            logger.info(f"Deleted S3 object: {storage_key}")
            return True
        except (ClientError, BotoCoreError) as e:
            logger.warning(f"Failed to delete S3 object ({storage_key}): {e}")
            return False

    def file_exists(self, storage_key: str) -> bool:
        client = self._get_client()
        if not client:
            return False
        try:
            client.head_object(Bucket=self.bucket_name, Key=storage_key)
            return True
        except ClientError:
            return False

    def generate_presigned_url(self, storage_key: str, expires_in: int = 3600) -> Optional[str]:
        client = self._get_client()
        if not client:
            return None
        try:
            return client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": storage_key},
                ExpiresIn=expires_in,
            )
        except Exception as e:
            logger.warning(f"Failed to generate presigned S3 URL: {e}")
            return None


s3_manager = S3StorageManager()


class PersistentDocumentStorage:
    """
    High-availability document storage service.
    Orchestrates S3 persistent cloud storage with local storage caching and
    resilient multi-environment path discovery.
    """

    def __init__(self):
        # Base upload directory determined deterministically
        backend_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        workspace_root = os.path.dirname(backend_root)
        self.candidate_upload_roots = [
            os.path.join(backend_root, "uploads", "business_docs"),
            os.path.join(workspace_root, "uploads", "business_docs"),
            os.path.join(os.getcwd(), "uploads", "business_docs"),
        ]
        self.primary_upload_dir = self.candidate_upload_roots[0]
        os.makedirs(self.primary_upload_dir, exist_ok=True)

    def get_storage_key(self, business_id: str, filename: str) -> str:
        return f"business_docs/{business_id}/{filename}"

    def save(self, business_id: str, filename: str, file_bytes: bytes, content_type: str = "application/pdf") -> Tuple[str, str]:
        """
        Saves document binary payload.
        Stores locally in primary upload directory and mirrors to S3 if configured.
        Returns: (storage_key, canonical_local_path)
        """
        storage_key = self.get_storage_key(business_id, filename)

        # 1. Save to primary local storage
        biz_dir = os.path.join(self.primary_upload_dir, str(business_id))
        os.makedirs(biz_dir, exist_ok=True)
        local_path = os.path.join(biz_dir, filename)

        with open(local_path, "wb") as f:
            f.write(file_bytes)

        # 2. Mirror to S3 if configured
        if s3_manager.is_configured:
            s3_manager.upload_file(file_bytes, storage_key, content_type)

        return storage_key, local_path

    def locate_or_fetch(self, doc, business_id: str) -> Tuple[Optional[str], Optional[bytes], str]:
        """
        Resiliently resolves a document's physical file:
        1. Checks S3 cloud storage first if configured.
        2. Checks recorded doc.file_path on local disk.
        3. Scans all candidate upload root folders using doc.filename and basename.
        Returns: (local_file_path, memory_bytes, mime_type)
        """
        mime_type = getattr(doc, "mime_type", None) or "application/pdf"
        storage_key = self.get_storage_key(str(business_id), doc.filename)

        # 1. If S3 is configured, check S3
        if s3_manager.is_configured:
            content = s3_manager.download_file(storage_key)
            if content:
                return None, content, mime_type

        # 2. Direct path check (if path in database exists on current disk)
        if doc.file_path and os.path.exists(doc.file_path) and os.path.isfile(doc.file_path):
            return doc.file_path, None, mime_type

        # 3. Search across all candidate local upload roots
        possible_filenames = [
            doc.filename,
            os.path.basename(doc.file_path) if doc.file_path else None,
            getattr(doc, "original_name", None),
        ]
        possible_filenames = [fn for fn in possible_filenames if fn]

        for root in self.candidate_upload_roots:
            # Check root/{business_id}/{filename}
            for fn in possible_filenames:
                biz_candidate = os.path.join(root, str(business_id), fn)
                if os.path.exists(biz_candidate) and os.path.isfile(biz_candidate):
                    return biz_candidate, None, mime_type

                # Check root/{filename}
                flat_candidate = os.path.join(root, fn)
                if os.path.exists(flat_candidate) and os.path.isfile(flat_candidate):
                    return flat_candidate, None, mime_type

        # 4. Search recursively inside candidate upload directories for matching filename
        for root in self.candidate_upload_roots:
            if not os.path.exists(root):
                continue
            for dirpath, _, filenames in os.walk(root):
                for fn in possible_filenames:
                    if fn in filenames:
                        matched = os.path.join(dirpath, fn)
                        return matched, None, mime_type

        # Document physical binary cannot be found on this host
        return None, None, mime_type

    def delete(self, doc, business_id: str) -> bool:
        """Removes document from S3 and local filesystem."""
        storage_key = self.get_storage_key(str(business_id), doc.filename)
        if s3_manager.is_configured:
            s3_manager.delete_file(storage_key)

        local_path, _, _ = self.locate_or_fetch(doc, business_id)
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
                return True
            except Exception as e:
                logger.warning(f"Failed to delete local file {local_path}: {e}")
        return False


document_storage = PersistentDocumentStorage()
