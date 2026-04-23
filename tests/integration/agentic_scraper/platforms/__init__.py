"""Platform adapter registry for the agentic scraper."""
from .base import PlatformAdapter
from .registry import get_registry, try_platforms

__all__ = ["PlatformAdapter", "get_registry", "try_platforms"]
