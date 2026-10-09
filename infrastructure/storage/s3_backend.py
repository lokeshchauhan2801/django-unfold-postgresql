"""S3-compatible storage backend stub."""
from typing import BinaryIO
from .interfaces import StorageBackend


class S3StorageBackend(StorageBackend):
    """Future S3-compatible storage. Replace LocalStorageBackend with this when ready."""

    def __init__(self, bucket: str, prefix: str = ''):
        self.bucket = bucket
        self.prefix = prefix
        # boto3 client init goes here
        raise NotImplementedError('S3StorageBackend is not yet implemented.')

    def save(self, path: str, content: BinaryIO) -> str:
        raise NotImplementedError

    def delete(self, path: str) -> None:
        raise NotImplementedError

    def exists(self, path: str) -> bool:
        raise NotImplementedError

    def url(self, path: str) -> str:
        raise NotImplementedError

    def read(self, path: str) -> bytes:
        raise NotImplementedError
