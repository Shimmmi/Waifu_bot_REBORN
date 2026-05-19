__all__ = ["create_app"]


def __getattr__(name: str):
    if name == "create_app":
        from .main import create_app as _create_app

        return _create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
