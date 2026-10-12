import os
import json
import base64
from pathlib import Path
from uuid import uuid4
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from ..common import Logger
from ..models import Blob, Error, ErrorCode


class BlobStorage:
    """Manages encrypted blob storage using AES-256-GCM."""

    def __init__(self, encryption_key: str, folder_path: str):
        """Initialize blob storage.

        Args:
            encryption_key_b64: Base64-encoded AES-256 encryption key (32 bytes).
            folder_path: Directory path for blob storage.
        """
        self._folder = Path(folder_path)
        self._logger = Logger.get_logger("blob.blob_storage")

        try:
            key_bytes = base64.b64decode(encryption_key)
            if len(key_bytes) != 32:
                raise Error(
                    ErrorCode.INVALID_ARGUMENT,
                    f"Encryption key must be 32 bytes for AES-256, got {len(key_bytes)} bytes",
                )
            self._aesgcm = AESGCM(key_bytes)
        except Exception as e:
            if isinstance(e, Error):
                raise
            raise Error(ErrorCode.INVALID_ARGUMENT, f"Invalid encryption key: {str(e)}")

        try:
            self._folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise Error(ErrorCode.INTERNAL, f"Failed to create blob storage folder: {str(e)}")

    async def save(self, blob: Blob) -> str:
        """Save blob to encrypted storage.

        Args:
            blob: Blob object containing content and metadata.

        Returns:
            Unique blob key.

        Raises:
            Error: If blob cannot be saved.
        """
        self._logger.debug(
            "save_started",
            content_type=blob.content_type,
            file_name=blob.file_name,
        )

        key = str(uuid4())

        try:
            content = blob.content

            # Prepare metadata
            metadata = {
                "content_type": blob.content_type,
                "file_name": blob.file_name,
                "size": len(content),
            }
            metadata_bytes = json.dumps(metadata).encode("utf-8")
            metadata_length = len(metadata_bytes).to_bytes(4, "big")

            # Encrypt content
            nonce = os.urandom(12)
            encrypted_content = self._aesgcm.encrypt(nonce, content, None)

            # Write blob file: [metadata_length][metadata][nonce][encrypted_content]
            blob_path = self._folder / f"{key}.blob"
            with open(blob_path, "wb") as f:
                f.write(metadata_length)
                f.write(metadata_bytes)
                f.write(nonce)
                f.write(encrypted_content)

            self._logger.debug("save_completed", key=key, size=len(content))

            return key

        except Error:
            raise
        except Exception as e:
            raise Error(ErrorCode.INTERNAL, f"Failed to save blob: {str(e)}")

    async def read(self, key: str) -> Blob | None:
        """Read and decrypt blob.

        Args:
            key: Blob key to read.

        Returns:
            Blob with decrypted content and metadata, or None if not found.

        Raises:
            Error: If blob format is invalid or cannot be decrypted.
        """
        self._logger.debug("read_started", key=key)

        try:
            blob_path = self._folder / f"{key}.blob"
            if not blob_path.exists():
                self._logger.debug("read_completed", key=key, found=False)
                return None

            with open(blob_path, "rb") as f:
                # Read metadata length
                metadata_length_bytes = f.read(4)
                if len(metadata_length_bytes) != 4:
                    raise Error(
                        ErrorCode.INVALID_RESPONSE, "Invalid blob format: missing metadata length"
                    )

                metadata_length = int.from_bytes(metadata_length_bytes, "big")

                # Read metadata
                metadata_bytes = f.read(metadata_length)
                if len(metadata_bytes) != metadata_length:
                    raise Error(
                        ErrorCode.INVALID_RESPONSE, "Invalid blob format: incomplete metadata"
                    )

                metadata = json.loads(metadata_bytes.decode("utf-8"))

                # Read nonce
                nonce = f.read(12)
                if len(nonce) != 12:
                    raise Error(ErrorCode.INVALID_RESPONSE, "Invalid blob format: missing nonce")

                # Read encrypted content
                encrypted_content = f.read()
                if not encrypted_content:
                    raise Error(
                        ErrorCode.INVALID_RESPONSE, "Invalid blob format: missing encrypted content"
                    )

            # Decrypt content
            try:
                content = self._aesgcm.decrypt(nonce, encrypted_content, None)
            except InvalidTag:
                raise Error(
                    ErrorCode.INVALID_RESPONSE,
                    "Blob decryption failed: data was tampered with or corrupted",
                )

            blob = Blob(
                content=content,
                content_type=metadata["content_type"],
                file_name=metadata.get("file_name"),
            )

            self._logger.debug("read_completed", key=key, size=len(content))

            return blob

        except Error:
            raise
        except Exception as e:
            raise Error(ErrorCode.INTERNAL, f"Failed to read blob: {str(e)}")

    async def delete(self, key: str) -> None:
        """Delete blob.

        Args:
            key: Blob key to delete.

        Raises:
            Error: If blob not found or cannot be deleted.
        """
        self._logger.debug("delete_started", key=key)

        try:
            blob_path = self._folder / f"{key}.blob"
            if not blob_path.exists():
                raise Error(ErrorCode.NOT_FOUND, f"Blob not found: {key}")

            blob_path.unlink()

            self._logger.debug("delete_completed", key=key)

        except Error:
            raise
        except Exception as e:
            raise Error(ErrorCode.INTERNAL, f"Failed to delete blob: {str(e)}")
