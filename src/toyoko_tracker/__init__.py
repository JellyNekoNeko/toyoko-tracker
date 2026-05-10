"""
toyoko-tracker。
"""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("toyoko-tracker")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

__all__ = ["__version__"]