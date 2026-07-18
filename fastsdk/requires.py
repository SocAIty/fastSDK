"""Optional-dependency guard (same contract as ``socaity_cli.requires``)."""
import functools
from importlib.util import find_spec
from typing import Optional

_available: set = set()


def requires(package: str, pip_name: Optional[str] = None, cli: bool = False):
    """Run the decorated function only when ``package`` is installed.

    Defaults to library mode (``cli=False``): raises ``ImportError``.
    """
    install_name = pip_name or package

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if package not in _available:
                try:
                    spec = find_spec(package)
                except (ImportError, ValueError):
                    spec = None
                if spec is None:
                    message = (
                        f"This {'command' if cli else 'feature'} needs the '{package}' package. "
                        f"Please install it with: pip install {install_name}"
                    )
                    if cli:
                        print(message)
                        raise SystemExit(1)
                    raise ImportError(message)
                _available.add(package)
            return func(*args, **kwargs)
        return wrapper
    return decorator
