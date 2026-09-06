"""Controle gestual local e efêmero; nenhum quadro é persistido."""

from __future__ import annotations

import base64
import math
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GestureSession:
    token: str
    created_at: float
    last_seen: float
    x: float = 0.5
    y: float = 0.5
    candidate: str = "none"
    candidate_frames: int = 0
    stable: str = "none"


class GestureEngine:
    SESSION_TTL = 15 * 60
    MAX_FRAME_BYTES = 1_200_000

    def __init__(self) -> None:
        self._sessions: dict[str, GestureSession] = {}
        self._lock = threading.Lock()
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False

    def status(self) -> dict[str, Any]:
        self._expire()
        return {
            "state": "ready" if self.available else "model_unavailable",
            "active_sessions": len(self._sessions),
            "gestures": ["point", "grab", "release"],
            "scope": "condor_window_only",
            "frame_storage": False,
            "background_capture": False,
        }

    def start(self) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError("OpenCV local não está disponível")
        now = time.monotonic()
        session = GestureSession(secrets.token_urlsafe(24), now, now)
        with self._lock:
            self._sessions[session.token] = session
        return {"token": session.token, "expires_in": self.SESSION_TTL, **self.status()}

    def stop(self, token: str) -> bool:
        with self._lock:
            return self._sessions.pop(str(token or ""), None) is not None

    def _expire(self) -> None:
        cutoff = time.monotonic() - self.SESSION_TTL
        with self._lock:
            for token, session in list(self._sessions.items()):
                if session.last_seen < cutoff:
                    self._sessions.pop(token, None)

    def _session(self, token: str) -> GestureSession:
        self._expire()
        with self._lock:
            session = self._sessions.get(str(token or ""))
            if session is None:
                raise PermissionError("sessão gestual inválida ou expirada")
            session.last_seen = time.monotonic()
            return session

    @staticmethod
    def _decode_frame(image_b64: str, max_bytes: int):
        import cv2
        import numpy as np

        encoded = str(image_b64 or "")
        if "," in encoded:
            encoded = encoded.split(",", 1)[1]
        if len(encoded) > max_bytes * 2:
            raise ValueError("quadro gestual excede o limite")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("quadro gestual inválido") from exc
        if not raw or len(raw) > max_bytes:
            raise ValueError("quadro gestual vazio ou muito grande")
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("imagem gestual não pôde ser decodificada")
        return frame

    @staticmethod
    def _raw_detection(frame) -> dict[str, Any]:
        import cv2
        import numpy as np

        height, width = frame.shape[:2]
        scale = 360 / max(1, width)
        frame = cv2.resize(frame, (360, max(180, int(height * scale))))
        frame = cv2.flip(frame, 1)
        height, width = frame.shape[:2]
        ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
        mask = cv2.inRange(ycrcb, np.array([0, 128, 68], dtype=np.uint8), np.array([255, 180, 135], dtype=np.uint8))
        mask = cv2.GaussianBlur(mask, (7, 7), 0)
        kernel = np.ones((5, 5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return {"present": False, "gesture": "none", "confidence": 0.0}
        contour = max(contours, key=cv2.contourArea)
        area = float(cv2.contourArea(contour))
        frame_area = float(width * height)
        if area / frame_area < 0.025:
            return {"present": False, "gesture": "none", "confidence": 0.0}
        hull_points = cv2.convexHull(contour)
        hull_area = max(1.0, float(cv2.contourArea(hull_points)))
        solidity = max(0.0, min(1.0, area / hull_area))
        x, y, box_w, box_h = cv2.boundingRect(contour)
        extent = area / max(1.0, float(box_w * box_h))
        defects_count = 0
        hull_indices = cv2.convexHull(contour, returnPoints=False)
        if hull_indices is not None and len(hull_indices) >= 4 and len(contour) >= 5:
            defects = cv2.convexityDefects(contour, hull_indices)
            if defects is not None:
                for start_i, end_i, far_i, depth in defects[:, 0]:
                    start = contour[start_i][0].astype(float)
                    end = contour[end_i][0].astype(float)
                    far = contour[far_i][0].astype(float)
                    a = np.linalg.norm(end - start)
                    b = np.linalg.norm(far - start)
                    c = np.linalg.norm(end - far)
                    denominator = max(1e-6, 2 * b * c)
                    angle = math.degrees(math.acos(max(-1.0, min(1.0, (b * b + c * c - a * a) / denominator))))
                    if angle < 92 and depth / 256.0 > box_h * 0.035:
                        defects_count += 1
        top = contour[contour[:, :, 1].argmin()][0]
        gesture = "point" if defects_count >= 1 or solidity < 0.76 else "grab"
        pointer_x = float(top[0] if gesture == "point" else x + box_w / 2) / width
        pointer_y = float(top[1] if gesture == "point" else y + box_h / 2) / height
        confidence = min(0.99, 0.42 + min(0.35, area / frame_area) + abs(solidity - 0.76))
        return {
            "present": True, "gesture": gesture,
            "x": max(0.0, min(1.0, pointer_x)), "y": max(0.0, min(1.0, pointer_y)),
            "confidence": round(confidence, 3), "hand_area": round(area / frame_area, 4),
            "diagnostics": {"solidity": round(solidity, 3), "defects": defects_count, "extent": round(extent, 3)},
        }

    def analyze(self, token: str, image_b64: str) -> dict[str, Any]:
        session = self._session(token)
        frame = self._decode_frame(image_b64, self.MAX_FRAME_BYTES)
        result = self._raw_detection(frame)
        if not result.get("present"):
            session.candidate = "none"
            session.candidate_frames = min(4, session.candidate_frames + 1)
            if session.candidate_frames >= 3:
                session.stable = "none"
            return {**result, "stable_gesture": session.stable, "frame_stored": False}
        session.x = session.x * 0.58 + float(result["x"]) * 0.42
        session.y = session.y * 0.58 + float(result["y"]) * 0.42
        candidate = str(result["gesture"])
        if candidate == session.candidate:
            session.candidate_frames += 1
        else:
            session.candidate = candidate
            session.candidate_frames = 1
        if session.candidate_frames >= 2:
            session.stable = candidate
        return {
            **result, "x": round(session.x, 4), "y": round(session.y, 4),
            "stable_gesture": session.stable, "frame_stored": False,
        }
