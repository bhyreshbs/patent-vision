from fastapi import Response

from app.core.errors import ApiError
from app.core.storage import storage


def file_response(key: str | None, media_type: str, filename: str | None, missing_action: str) -> Response:
    """Serve a stored file through the API (ownership is checked by the caller), never by URL."""
    try:
        data = storage.read_bytes(key) if key else None
    except FileNotFoundError:
        data = None
    if not data:
        raise ApiError(404, "file_missing", "The requested file is missing from storage.", missing_action)
    headers = {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"}
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return Response(content=data, media_type=media_type, headers=headers)
