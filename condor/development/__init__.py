"""Modelos técnicos usados pelo ambiente de desenvolvimento."""

from .programming import detect_language
from .arduino import ArduinoToolchain

__all__ = ["detect_language", "ArduinoToolchain"]
