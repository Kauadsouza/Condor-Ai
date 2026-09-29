"""Ponte modular e segura para dispositivos físicos."""

from .bridge import DeviceBridge
from .gestures import GestureEngine, GesturePCControl
from .safety import ActionSafetyLayer, RiskLevel

__all__ = ["ActionSafetyLayer", "DeviceBridge", "GestureEngine", "GesturePCControl", "RiskLevel"]
