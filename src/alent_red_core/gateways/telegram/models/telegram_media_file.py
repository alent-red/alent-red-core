from pydantic import BaseModel


class TelegramMediaFile(BaseModel):
    """A downloadable file attached to a message (document, audio, video, etc.).

    Only the fields needed to download and name the file are modeled; every
    Telegram media object exposes a file_id, and most expose an optional file_name.
    """

    file_id: str
    file_name: str | None = None
