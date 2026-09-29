"""Controle gestual local e efêmero; nenhum quadro é persistido.

O motor principal é o MediaPipe GestureRecognizer rodando dentro da página
(WebAssembly vendorizado em condor/ui/vendor/mediapipe): os quadros nunca saem
do navegador. O detector por cor de pele em OpenCV fica só como reserva quando
o MediaPipe não carrega — ele confunde rosto e parede e só sabe "point"/"grab".
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MEDIAPIPE_DIR = Path(__file__).resolve().parents[1] / "ui" / "vendor" / "mediapipe"
ENGINES = ("mediapipe", "opencv")

# Lista FIXA: o cliente só escolhe o nome da ação, nunca a tecla. Assim nem uma
# página adulterada consegue usar este canal para digitar ou abrir atalhos.
GESTURE_PC_ACTIONS: dict[str, tuple[str, Any]] = {
    "playpause": ("tecla", "playpause"),
    "proximo": ("tecla", "nexttrack"),
    "anterior": ("tecla", "prevtrack"),
    "rolar_cima": ("rolar", 3),
    "rolar_baixo": ("rolar", -3),
    "volume_mais": ("tecla", "volumeup"),
    "volume_menos": ("tecla", "volumedown"),
}


class _MediaPipeCheck:
    """Confere os arquivos vendorizados contra MANIFEST.json uma vez por versão.

    Hash de ~32 MB custa algumas dezenas de ms e o status é consultado em laço
    pela interface; por isso só refaz quando tamanho ou mtime mudam.
    """

    def __init__(self, root: Path = MEDIAPIPE_DIR) -> None:
        self.root = root
        self._lock = threading.Lock()
        self._marca: tuple | None = None
        self._resultado: dict[str, Any] = {}

    def _marca_atual(self) -> tuple:
        if not self.root.exists():
            return ()
        return tuple(
            (path.as_posix(), path.stat().st_mtime_ns, path.stat().st_size)
            for path in sorted(self.root.rglob("*")) if path.is_file()
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            marca = self._marca_atual()
            if marca != self._marca:
                self._resultado = self._verificar()
                self._marca = marca
            return dict(self._resultado)

    def _verificar(self) -> dict[str, Any]:
        try:
            manifest = json.loads((self.root / "MANIFEST.json").read_text(encoding="utf-8"))
            files = dict(manifest["files"])
        except (OSError, ValueError, KeyError, TypeError):
            return {"available": False, "version": None, "reason": "manifesto ausente"}
        raiz = self.root.resolve()
        for name, meta in files.items():
            path = (raiz / name).resolve()
            if raiz not in path.parents:
                return {"available": False, "version": None, "reason": "manifesto inválido"}
            try:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                return {"available": False, "version": None, "reason": f"faltando {name}"}
            if digest != str((meta or {}).get("sha256", "")):
                return {"available": False, "version": None, "reason": f"hash divergente em {name}"}
        return {"available": True, "version": str(manifest.get("version") or ""), "reason": ""}


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
    engine: str = "mediapipe"


class GestureEngine:
    SESSION_TTL = 15 * 60
    MAX_FRAME_BYTES = 1_200_000

    def __init__(self, mediapipe_root: Path = MEDIAPIPE_DIR) -> None:
        self._sessions: dict[str, GestureSession] = {}
        self._lock = threading.Lock()
        self._mediapipe = _MediaPipeCheck(mediapipe_root)
        try:
            import cv2  # noqa: F401
            import numpy  # noqa: F401
            self.opencv_available = True
        except ImportError:
            self.opencv_available = False

    @property
    def available(self) -> bool:
        return self.opencv_available or bool(self._mediapipe.status()["available"])

    def status(self) -> dict[str, Any]:
        self._expire()
        mediapipe = self._mediapipe.status()
        with self._lock:
            engines = sorted({session.engine for session in self._sessions.values()})
        preferred = "mediapipe" if mediapipe["available"] else ("opencv" if self.opencv_available else "none")
        return {
            "state": "ready" if preferred != "none" else "model_unavailable",
            "engine": preferred,
            # Quem escolhe o motor de fato é a página: se o WebAssembly não
            # carregar, ela abre a sessão em "opencv" e isto passa a dizer.
            "active_engine": engines[0] if len(engines) == 1 else ("mixed" if engines else "none"),
            "mediapipe": mediapipe,
            "opencv_fallback": self.opencv_available,
            "active_sessions": len(self._sessions),
            "gestures": (
                ["Open_Palm", "Closed_Fist", "Thumb_Up", "swipe", "Pointing_Up", "Victory"]
                if mediapipe["available"] else ["point", "grab", "release"]
            ),
            "pc_actions": sorted(GESTURE_PC_ACTIONS),
            "scope": "condor_and_pc_allowlist",
            "frame_storage": False,
            "background_capture": False,
        }

    def start(self, engine: str = "mediapipe") -> dict[str, Any]:
        engine = engine if engine in ENGINES else "mediapipe"
        if engine == "mediapipe" and not self._mediapipe.status()["available"]:
            raise RuntimeError("MediaPipe local ausente ou adulterado")
        if engine == "opencv" and not self.opencv_available:
            raise RuntimeError("OpenCV local não está disponível")
        now = time.monotonic()
        session = GestureSession(secrets.token_urlsafe(24), now, now, engine=engine)
        with self._lock:
            self._sessions[session.token] = session
        return {
            "token": session.token, "expires_in": self.SESSION_TTL,
            **self.status(), "session_engine": engine,
        }

    def touch(self, token: str) -> GestureSession:
        """Valida a sessão (e renova o prazo) sem analisar quadro algum."""
        return self._session(token)

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
        # No MediaPipe o reconhecimento é todo no navegador: uma sessão dessas
        # nunca tem motivo para mandar quadros, então nem aceitamos.
        if session.engine != "opencv":
            raise PermissionError("esta sessão não envia quadros")
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


class GesturePCControl:
    """Traduz o nome de uma ação gestual para o executor, com limite de ritmo.

    Não passa pela política de ferramentas do LLM: quem gesticula é o dono,
    diante da câmera física, com a sessão local já provada. O limite existe
    para uma mão tremendo (ou uma página adulterada) não metralhar o PC.
    """

    MAX_PER_SECOND = 8

    def __init__(self, executor_module=None, clock: Callable[[], float] = time.monotonic) -> None:
        self._executor = executor_module
        self._clock = clock
        self._lock = threading.Lock()
        self._recent: deque[float] = deque()

    @staticmethod
    def valid(action: Any) -> bool:
        return isinstance(action, str) and action in GESTURE_PC_ACTIONS

    def rate_allowed(self) -> bool:
        now = self._clock()
        with self._lock:
            while self._recent and self._recent[0] <= now - 1.0:
                self._recent.popleft()
            if len(self._recent) >= self.MAX_PER_SECOND:
                return False
            self._recent.append(now)
            return True

    def run(self, action: str) -> dict:
        if not self.valid(action):
            raise ValueError("ação gestual desconhecida")
        executor = self._executor
        if executor is None:
            from condor.actions import executor
        kind, value = GESTURE_PC_ACTIONS[action]
        if kind == "rolar":
            return executor.rolar(int(value))
        return executor.atalho(str(value))
