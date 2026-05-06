"""Aliyun OSS uploader.

Uses content-hashed filenames so that re-uploading the same image is a no-op,
which makes runs idempotent and keeps the bucket clean.
"""

from __future__ import annotations

import hashlib
import mimetypes

try:
    import oss2
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "oss2 is required to upload to Aliyun OSS. "
        "Install it with: pip install oss2"
    ) from e

from .config import Config


class OSSUploader:
    def __init__(self, config: Config):
        self.config = config
        auth = oss2.Auth(config.access_key_id, config.access_key_secret)
        self.bucket = oss2.Bucket(auth, config.endpoint, config.bucket)

    def upload(self, data: bytes, ext: str) -> str:
        """Upload bytes and return the public URL."""
        ext = ext.lower()
        if not ext.startswith("."):
            ext = "." + ext

        digest = hashlib.sha256(data).hexdigest()[:24]
        filename = f"{digest}{ext}"
        key = f"{self.config.prefix}/{filename}" if self.config.prefix else filename

        if not self.bucket.object_exists(key):
            content_type, _ = mimetypes.guess_type(filename)
            headers = {"Content-Type": content_type} if content_type else None
            self.bucket.put_object(key, data, headers=headers)

        return self._build_url(key)

    def _build_url(self, key: str) -> str:
        if self.config.custom_domain:
            domain = self.config.custom_domain
            if not domain.startswith(("http://", "https://")):
                domain = "https://" + domain
            return f"{domain}/{key}"

        endpoint = self.config.endpoint
        for prefix in ("https://", "http://"):
            if endpoint.startswith(prefix):
                endpoint = endpoint[len(prefix):]
                break
        return f"https://{self.config.bucket}.{endpoint}/{key}"

    def is_own_url(self, url: str) -> bool:
        """Return True if the URL is already on this bucket / custom domain."""
        if not url:
            return False
        if self.config.custom_domain and self.config.custom_domain in url:
            return True
        host_marker = f"{self.config.bucket}."
        endpoint = self.config.endpoint
        for prefix in ("https://", "http://"):
            if endpoint.startswith(prefix):
                endpoint = endpoint[len(prefix):]
                break
        return host_marker in url and endpoint in url
