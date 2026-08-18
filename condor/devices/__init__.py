"""Ponte modular e segura para dispositivos físicos."""

from .bridge import DeviceBridge
from .camera import CameraBridge
from .safety import ActionSafetyLayer, RiskLevel

__all__ = ["ActionSafetyLayer", "CameraBridge", "DeviceBridge", "RiskLevel"]
