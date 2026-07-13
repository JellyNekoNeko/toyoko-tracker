from __future__ import annotations

import threading
from typing import Any

import requests
from requests.adapters import HTTPAdapter


_LOCAL = threading.local()


def session() -> requests.Session:
    current = getattr(_LOCAL, "session", None)
    if current is None:
        current = requests.Session()
        adapter = HTTPAdapter(pool_connections=4, pool_maxsize=4, max_retries=0)
        current.mount("https://", adapter)
        current.mount("http://", adapter)
        _LOCAL.session = current
    return current


def get(url: str, **kwargs: Any) -> requests.Response:
    return session().get(url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response:
    return session().post(url, **kwargs)
