import logging
from contextvars import ContextVar
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")
_private_request = ContextVar("private_http_request", default=False)


class _PrivateRequestFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not _private_request.get()


logging.getLogger("httpx").addFilter(_PrivateRequestFilter())


def private_http(function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        token = _private_request.set(True)
        try:
            return function(*args, **kwargs)
        finally:
            _private_request.reset(token)
    return wrapped
