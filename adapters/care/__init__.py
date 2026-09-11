"""Adapter 1: kernel.contracts.Store over CARE's REST API.

adapters/care/map.py holds every field name, each marked with how it was
established; adapters/care/store.py holds the machinery and no field name.
"""
from adapters.care.store import CareError, CareStore, http_transport

__all__ = ["CareStore", "CareError", "http_transport"]
