import asyncio
from typing import Mapping

import httpx

from ...common import Logger
from ...models import Error, ErrorCode
from .models import TelegramFile, TelegramUpdate, TelegramUserProfilePhotos

_BASE_URL = "https://api.telegram.org"
_LONG_POLL_TIMEOUT_SECONDS = 30
_LONG_POLL_LIMIT = 100
_REQUEST_TIMEOUT_MARGIN_SECONDS = 10
_PHOTO_FIELD_NAME = "photo"


class TelegramClient:
    """HTTP transport for the Telegram Bot API.

    Performs single Telegram requests, parses responses into Telegram models, and
    maps failures to Error with an appropriate ErrorCode. Rate-limit backoff is
    honored internally as a protocol rule; all other retry policy is the caller's.
    """

    def __init__(self, token: str):
        """Initialize the Telegram client.

        Args:
            token: Bot token from BotFather.
        """
        self._base_url = f"{_BASE_URL}/bot{token}"
        self._file_base_url = f"{_BASE_URL}/file/bot{token}"
        self._client = httpx.AsyncClient(
            timeout=_LONG_POLL_TIMEOUT_SECONDS + _REQUEST_TIMEOUT_MARGIN_SECONDS
        )
        self._logger = Logger.get_logger("gateways.telegram.telegram_client")

    async def get_updates(self, offset: int | None) -> list[TelegramUpdate]:
        """Long-poll for new updates.

        Args:
            offset: Identifier of the first update to return, or None to fetch the
                earliest unconfirmed updates.

        Returns:
            List of updates in increasing update_id order.

        Raises:
            Error: If the request fails or Telegram returns an error.
        """
        parameters: dict[str, int] = {
            "timeout": _LONG_POLL_TIMEOUT_SECONDS,
            "limit": _LONG_POLL_LIMIT,
        }
        if offset is not None:
            parameters["offset"] = offset

        result = await self._request("getUpdates", parameters)

        if not isinstance(result, list):
            raise Error(ErrorCode.INVALID_RESPONSE, "getUpdates result is not a list")

        return [TelegramUpdate.model_validate(item) for item in result]

    async def send_message(self, chat_id: int, text: str) -> None:
        """Send a text message to a chat.

        Args:
            chat_id: Target chat identifier.
            text: Message text.

        Raises:
            Error: If the request fails or Telegram returns an error.
        """
        await self._request("sendMessage", {"chat_id": chat_id, "text": text})

    async def send_chat_action(self, chat_id: int, action: str) -> None:
        """Send a chat action (such as a typing indicator) to a chat.

        Args:
            chat_id: Target chat identifier.
            action: Chat action to display.

        Raises:
            Error: If the request fails or Telegram returns an error.
        """
        await self._request("sendChatAction", {"chat_id": chat_id, "action": action})

    async def send_photo(self, chat_id: int, file_name: str, content: bytes) -> None:
        """Send a photo to a chat by uploading its bytes.

        Args:
            chat_id: Target chat identifier.
            file_name: Name to upload the photo under.
            content: Raw photo bytes.

        Raises:
            Error: If the request fails or Telegram returns an error.
        """
        await self._request(
            "sendPhoto",
            {"chat_id": chat_id},
            files={_PHOTO_FIELD_NAME: (file_name, content)},
        )

    async def get_user_profile_photos(self, user_id: int) -> TelegramUserProfilePhotos:
        """Get a user's profile photos.

        Args:
            user_id: Target user identifier.

        Returns:
            The user's profile photos.

        Raises:
            Error: If the request fails or Telegram returns an error.
        """
        result = await self._request("getUserProfilePhotos", {"user_id": user_id, "limit": 1})
        return TelegramUserProfilePhotos.model_validate(result)

    async def get_file(self, file_id: str) -> TelegramFile:
        """Resolve a file id into a downloadable file.

        Args:
            file_id: Identifier of the file to resolve.

        Returns:
            The resolved file, including its download path when available.

        Raises:
            Error: If the request fails or Telegram returns an error.
        """
        result = await self._request("getFile", {"file_id": file_id})
        return TelegramFile.model_validate(result)

    async def download_file(self, file_path: str) -> bytes:
        """Download a file's content by its Telegram file path.

        Args:
            file_path: File path returned by get_file.

        Returns:
            Raw file content.

        Raises:
            Error: If the download fails or Telegram returns an error status.
        """
        url = f"{self._file_base_url}/{file_path}"

        try:
            response = await self._client.get(url)
        except httpx.TimeoutException as exception:
            raise Error(ErrorCode.TIMEOUT, f"Telegram download timed out: {exception}")
        except httpx.HTTPError as exception:
            raise Error(ErrorCode.TIMEOUT, f"Telegram download failed: {exception}")

        if response.status_code >= 500:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Telegram download server error: {response.status_code}",
            )
        if response.status_code != 200:
            raise Error(
                self._error_code(response.status_code),
                f"Telegram download failed with status {response.status_code}",
            )

        return response.content

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        parameters: Mapping[str, object],
        files: Mapping[str, tuple[str, bytes]] | None = None,
    ) -> object:
        """Perform a Telegram request, honoring rate-limit backoff.

        Args:
            method: Telegram Bot API method name.
            parameters: Request parameters.
            files: Optional multipart file uploads keyed by field name.

        Returns:
            The "result" field of a successful Telegram response.

        Raises:
            Error: If the request fails or Telegram returns a non-rate-limit error.
        """
        url = f"{self._base_url}/{method}"

        while True:
            try:
                if files is not None:
                    response = await self._client.post(url, data=parameters, files=files)
                else:
                    response = await self._client.post(url, json=parameters)
            except httpx.TimeoutException as exception:
                raise Error(ErrorCode.TIMEOUT, f"Telegram request timed out: {exception}")
            except httpx.HTTPError as exception:
                raise Error(ErrorCode.TIMEOUT, f"Telegram request failed: {exception}")

            retry_after = self._retry_after_seconds(response)
            if retry_after is not None:
                self._logger.debug("rate_limited", method=method, retry_after=retry_after)
                await asyncio.sleep(retry_after)
                continue

            return self._parse_response(method, response)

    def _retry_after_seconds(self, response: httpx.Response) -> int | None:
        """Extract the rate-limit retry delay from a response, if rate-limited.

        Args:
            response: HTTP response from Telegram.

        Returns:
            Seconds to wait before retrying, or None if not rate-limited.
        """
        if response.status_code != 429:
            return None

        body = response.json()
        retry_after = body.get("parameters", {}).get("retry_after")
        if isinstance(retry_after, int):
            return retry_after
        return 1

    def _parse_response(self, method: str, response: httpx.Response) -> object:
        """Parse a Telegram response, raising on failure.

        Args:
            method: Telegram Bot API method name (for error context).
            response: HTTP response from Telegram.

        Returns:
            The "result" field of a successful response.

        Raises:
            Error: If the response indicates failure.
        """
        if response.status_code >= 500:
            raise Error(
                ErrorCode.INVALID_RESPONSE,
                f"Telegram {method} server error: {response.status_code}",
            )

        body = response.json()

        if not body.get("ok", False):
            description = body.get("description", "unknown error")
            raise Error(self._error_code(response.status_code), f"Telegram {method}: {description}")

        return body["result"]

    def _error_code(self, status_code: int) -> ErrorCode:
        """Map a Telegram HTTP status code to an ErrorCode.

        Args:
            status_code: HTTP status code from Telegram.

        Returns:
            Corresponding ErrorCode.
        """
        if status_code in (401, 403):
            return ErrorCode.NOT_ALLOWED
        if status_code == 400:
            return ErrorCode.INVALID_ARGUMENT
        return ErrorCode.UNKNOWN
