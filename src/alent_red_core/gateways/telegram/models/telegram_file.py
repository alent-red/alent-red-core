from pydantic import BaseModel


class TelegramFile(BaseModel):
    """A file ready to be downloaded.

    The file can be downloaded from the file path; the path is valid for at least
    one hour, after which a new one must be requested.
    """

    file_id: str
    file_path: str | None = None
