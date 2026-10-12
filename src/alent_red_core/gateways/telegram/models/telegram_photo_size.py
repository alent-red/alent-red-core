from pydantic import BaseModel


class TelegramPhotoSize(BaseModel):
    """One size of a photo or a file/sticker thumbnail."""

    file_id: str
    width: int
    height: int
