from pydantic import BaseModel

from .telegram_photo_size import TelegramPhotoSize


class TelegramUserProfilePhotos(BaseModel):
    """A user's profile photos.

    Each entry of photos is one photo in several sizes, largest last.
    """

    total_count: int
    photos: list[list[TelegramPhotoSize]] = []
