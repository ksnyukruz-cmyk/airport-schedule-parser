"""Небольшие GET-запросы к публичным табло."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
TIMEOUT = 25


class SourceError(RuntimeError):
    """Источник табло не ответил или отдал неожиданные данные."""


def get_bytes(url: str, accept: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "ru,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise SourceError(f"HTTP {error.code} от {url}") from error
    except urllib.error.URLError as error:
        raise SourceError(f"нет связи с {url}: {error.reason}") from error
    except TimeoutError as error:
        raise SourceError(f"таймаут запроса к {url}") from error


def get_json(url: str):
    raw = get_bytes(url, "application/json")
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise SourceError(f"источник вернул не JSON: {url}") from error


def get_text(url: str) -> str:
    return get_bytes(url, "text/html").decode("utf-8", "replace")
