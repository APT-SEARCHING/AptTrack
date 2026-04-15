"""Shared rate-limiter instance.

Imported by main.py (to mount on the app) and by every endpoint module
(to apply @limiter.limit() decorators). Keeping it here breaks the circular
import that would arise from endpoint modules importing from app.main.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
