"""!
@file __init__.py
@brief HTTP API платформы (роутеры FastAPI).
"""
from . import health, inventory, stands, vms

__all__ = ["health", "inventory", "stands", "vms"]
