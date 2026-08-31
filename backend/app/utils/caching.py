from functools import wraps

from flask import make_response


def cache_control(value: str):
    """Sets a Cache-Control header on a GET route's response.

    Only ever apply this to endpoints with no auth and no per-user data —
    Cloud CDN (and any other shared cache) doesn't vary its cache by the
    Authorization header by default, so caching an authenticated endpoint's
    response risks serving one user's data to another.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            resp = make_response(fn(*args, **kwargs))
            resp.headers["Cache-Control"] = value
            return resp

        return wrapper

    return decorator
