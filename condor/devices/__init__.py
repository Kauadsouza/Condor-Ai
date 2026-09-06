"""Ponte modular e segura para dispositivos físicos."""

from .bridge import DeviceBridge
from .camera import CameraBridge
from .gestures import GestureEngine
from .safety import ActionSafetyLayer, RiskLevel

__all__ = ["ActionSafetyLayer", "CameraBridge", "DeviceBridge", "GestureEngine", "RiskLevel"]
