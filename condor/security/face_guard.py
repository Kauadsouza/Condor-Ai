"""Autenticacao facial local e sob demanda do dono.

Nao guarda fotografias. YuNet detecta/mede pose, SFace produz um vetor e apenas
o centroide desse vetor e persistido dentro do snapshot cifrado da memoria.
Webcams RGB nao equivalem a Windows Hello: por isso o retorno exige um desafio
ativo de movimento e a frase do cofre continua sendo a recuperacao soberana.
"""

from __future__ import annotations

import base64
import importlib.util
import math
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from condor.paths import state_path


MODEL_NAME = "opencv-yunet-2023mar+sface-2021dec"
DEFAULT_THRESHOLD = 0.45
VIRTUAL_CAMERA_MARKERS = (
    "camo", "virtual", "obs", "manycam", "droidcam", "snap camera", "xsplit",
)


@dataclass
class _Challenge:
    token: str
    expires: float
    step: int = 0
    stable: int = 0
    first_side: int = 0
    attempts: int = 0
    steps: tuple[str, ...] = field(
        default_factory=lambda: ("center", "side", "opposite", "center")
    )


class FacePresenceGuard:
    """Decisao deterministica acima da IA e ligada diretamente a ``Guarda``."""

    CHALLENGE_TTL_SECONDS = 35.0

    def __init__(self, memory, guard) -> None:
        self.memory = memory
        self.guard = guard
        self.detector_path = state_path("models", "face", "face_detection_yunet_2023mar.onnx")
        self.recognizer_path = state_path("models", "face", "face_recognition_sface_2021dec.onnx")
        self._cv2 = None
        self._detector = None
        self._recognizer = None
        self._model_lock = threading.RLock()
        self._template: np.ndarray | None = None
        self._threshold = DEFAULT_THRESHOLD
        self._active = False
        self._locked = False
        self._reason = "disabled"
        self._challenge: _Challenge | None = None
        self._lock_callback = None

    @property
    def models_ready(self) -> bool:
        return (
            importlib.util.find_spec("cv2") is not None
            and self.detector_path.is_file()
            and self.recognizer_path.is_file()
        )

    @property
    def requires_face(self) -> bool:
        profile = self.memory.face_identity_profile() if self.memory.unlocked else None
        return bool(profile and profile.get("enabled"))

    @property
    def access_blocked(self) -> bool:
        return self._active and self._locked

    @staticmethod
    def physical_camera_label(label: str) -> bool:
        lowered = (label or "").strip().lower()
        return bool(lowered) and not any(marker in lowered for marker in VIRTUAL_CAMERA_MARKERS)

    def status(self) -> dict[str, Any]:
        profile = self.memory.face_identity_profile() if self.memory.unlocked else None
        return {
            "available": self.models_ready,
            "enrolled": bool(profile),
            "enabled": bool(profile and profile.get("enabled")),
            "active": self._active,
            "locked": self._locked,
            "reason": self._reason,
            "owner_session_active": self.guard.owner_session_active,
            "sample_count": int(profile.get("sample_count") or 0) if profile else 0,
            "model": MODEL_NAME if self.models_ready else None,
            "frame_storage": "disabled",
            "comparison": "local_only",
            "matching_policy": "owner_template_only",
            "identity_slots": 1,
            "camera_policy": "biometric_authentication_only",
            "continuous_monitoring": False,
            "background_capture": False,
            "rgb_limit": "active_motion_not_windows_hello",
        }

    def after_vault_unlock(self) -> bool:
        """Carrega o vetor em RAM; retorna se o rosto ainda precisa liberar a sessao."""
        profile = self.memory.face_identity_profile()
        if not profile or not profile.get("enabled"):
            self._active = False
            self._locked = False
            self._template = None
            self._reason = "disabled"
            return False
        if not self.models_ready:
            # Falha fechada. A frase pode desativar a biometria pela rota de recuperacao.
            self._active = True
            self._locked = True
            self._template = np.asarray(profile["template"], dtype=np.float32)
            self._threshold = float(profile.get("threshold") or DEFAULT_THRESHOLD)
            self.guard.lock_owner_session()
            self._reason = "models_unavailable"
            return True
        template = np.asarray(profile["template"], dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(template))
        if not math.isfinite(norm) or norm <= 0:
            self._active = True
            self._locked = True
            self.guard.lock_owner_session()
            self._reason = "invalid_template"
            return True
        self._template = template / norm
        self._threshold = float(profile.get("threshold") or DEFAULT_THRESHOLD)
        self._active = True
        self._locked = True
        self._reason = "owner_face_required"
        self.guard.lock_owner_session()
        return True

    def require_owner_face(self, reason: str = "window_open") -> bool:
        """Fecha a sessao do dono para uma nova janela exigir o desafio facial."""
        if not self.requires_face:
            return False
        if not self._active or self._template is None:
            return self.after_vault_unlock()
        self._locked = True
        self._reason = reason
        self._challenge = None
        self.guard.lock_owner_session()
        self.guard.auditar("security", "face_window_lock", "ROSTO NECESSARIO", True, False)
        return True

    def _ensure_models(self) -> None:
        if not self.models_ready:
            raise RuntimeError("modelos locais de reconhecimento facial indisponiveis")
        if self._detector is not None and self._recognizer is not None:
            return
        import cv2

        self._cv2 = cv2
        self._detector = cv2.FaceDetectorYN.create(
            str(self.detector_path), "", (320, 320), 0.88, 0.3, 1000
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(self.recognizer_path), "")

    def _decode(self, image_b64: str):
        if not image_b64 or len(image_b64) > 2_800_000:
            raise ValueError("quadro ausente ou grande demais")
        try:
            raw = base64.b64decode(image_b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("quadro invalido") from exc
        if len(raw) < 256 or len(raw) > 2_000_000:
            raise ValueError("quadro fora do limite seguro")
        image = self._cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), self._cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("imagem nao reconhecida")
        height, width = image.shape[:2]
        if width < 240 or height < 180 or width * height > 1_500_000:
            raise ValueError("resolucao de camera fora do limite")
        return image

    def _inspect(self, image_b64: str) -> list[dict[str, Any]]:
        with self._model_lock:
            self._ensure_models()
            image = self._decode(image_b64)
            height, width = image.shape[:2]
            self._detector.setInputSize((width, height))
            _, detected = self._detector.detect(image)
            if detected is None:
                return []
            results: list[dict[str, Any]] = []
            brightness = float(self._cv2.cvtColor(image, self._cv2.COLOR_BGR2GRAY).mean())
            for face in detected:
                x, y, box_w, box_h = (float(value) for value in face[:4])
                right_eye = np.asarray(face[4:6], dtype=np.float32)
                left_eye = np.asarray(face[6:8], dtype=np.float32)
                nose = np.asarray(face[8:10], dtype=np.float32)
                eye_span = max(1.0, float(abs(left_eye[0] - right_eye[0])))
                yaw = float((nose[0] - ((left_eye[0] + right_eye[0]) / 2.0)) / eye_span)
                aligned = self._recognizer.alignCrop(image, face)
                feature = self._recognizer.feature(aligned).reshape(-1).astype(np.float32)
                norm = float(np.linalg.norm(feature))
                if not math.isfinite(norm) or norm <= 0:
                    continue
                coverage = max(0.0, box_w * box_h / float(width * height))
                results.append({
                    "feature": feature / norm,
                    "yaw": yaw,
                    "score": float(face[14]),
                    "coverage": coverage,
                    "brightness": brightness,
                    "box": (x, y, box_w, box_h),
                })
            return results

    @staticmethod
    def _quality(face: dict[str, Any]) -> None:
        _, _, width, height = face["box"]
        if min(width, height) < 95 or face["coverage"] < 0.065:
            raise ValueError("aproxime o rosto da camera")
        if face["score"] < 0.90:
            raise ValueError("rosto pouco definido")
        if face["brightness"] < 35 or face["brightness"] > 225:
            raise ValueError("ajuste a iluminacao do rosto")

    @staticmethod
    def _pose_matches(expected: str, yaw: float, first_side: int) -> tuple[bool, int]:
        if expected == "center":
            return abs(yaw) <= 0.16, first_side
        sign = 1 if yaw > 0 else -1
        if expected == "side":
            return abs(yaw) >= 0.18, sign if abs(yaw) >= 0.18 else first_side
        return abs(yaw) >= 0.18 and first_side and sign == -first_side, first_side

    def check_enrollment_frame(
        self, image_b64: str, expected: str, first_side: int = 0
    ) -> dict[str, Any]:
        """Valida uma etapa sem persistir o quadro; o cadastro final revalida tudo."""
        if expected not in {"center", "side", "opposite"}:
            raise ValueError("etapa de prova de vida invalida")
        faces = self._inspect(image_b64)
        if len(faces) != 1:
            guidance = (
                "posicione somente o seu rosto dentro do oval"
                if faces else "posicione seu rosto dentro do oval"
            )
            return {
                "accepted": False, "detected": len(faces), "first_side": first_side,
                "guidance": guidance,
            }
        try:
            self._quality(faces[0])
        except ValueError as exc:
            return {
                "accepted": False, "detected": 1, "first_side": first_side,
                "guidance": str(exc),
            }
        accepted, detected_side = self._pose_matches(expected, faces[0]["yaw"], first_side)
        guidance = {
            "center": "mantenha o rosto reto e olhe para a camera",
            "side": "vire um pouco mais o rosto para um dos lados",
            "opposite": "vire o rosto para o outro lado",
        }[expected]
        return {
            "accepted": accepted,
            "detected": 1,
            "first_side": detected_side,
            "guidance": "posicao confirmada" if accepted else guidance,
        }

    def enroll(self, samples: list[dict[str, str]]) -> dict[str, Any]:
        if len(samples) < 8 or len(samples) > 12:
            raise ValueError("cadastro exige oito a doze quadros")
        expected_order = ("center", "side", "opposite", "center")
        inspected: list[tuple[str, dict[str, Any]]] = []
        for sample in samples:
            step = str(sample.get("step") or "")
            if step not in expected_order:
                raise ValueError("etapa de prova de vida invalida")
            faces = self._inspect(str(sample.get("image_b64") or ""))
            if len(faces) != 1:
                raise ValueError("mantenha somente o seu rosto no quadro")
            self._quality(faces[0])
            inspected.append((step, faces[0]))
        grouped = [step for step, _ in inspected]
        cursor = 0
        first_side = 0
        for expected in expected_order:
            current = []
            while cursor < len(grouped) and grouped[cursor] == expected:
                current.append(inspected[cursor][1])
                cursor += 1
            if len(current) < 2:
                raise ValueError(f"repita a etapa {expected}")
            for face in current:
                ok, first_side = self._pose_matches(expected, face["yaw"], first_side)
                if not ok:
                    raise ValueError("movimento de prova de vida nao confirmado")
        if cursor != len(inspected):
            raise ValueError("sequencia de prova de vida invalida")
        features = [face["feature"] for _, face in inspected]
        reference = features[0]
        if any(float(np.dot(reference, feature)) < 0.363 for feature in features[1:]):
            raise ValueError("os quadros nao parecem pertencer a mesma pessoa")
        centroid = np.mean(np.stack(features), axis=0)
        centroid /= max(float(np.linalg.norm(centroid)), 1e-9)
        profile = self.memory.save_face_identity_profile(
            centroid.astype(float).tolist(), len(features), DEFAULT_THRESHOLD, MODEL_NAME
        )
        self._template = centroid.astype(np.float32)
        self._threshold = DEFAULT_THRESHOLD
        self._active = True
        self._locked = False
        self._reason = "owner_present"
        self.guard.unlock_owner_session()
        self.guard.auditar("security", "face_enroll", "VETOR FACIAL CIFRADO", True, True)
        return {"ok": True, "sample_count": profile.get("sample_count", len(features))}

    def begin_challenge(self) -> dict[str, Any]:
        if not self._active or self._template is None:
            raise RuntimeError("identidade facial nao esta ativa")
        self._challenge = _Challenge(
            token=secrets.token_urlsafe(24),
            expires=time.monotonic() + self.CHALLENGE_TTL_SECONDS,
        )
        return self._challenge_payload()

    def _challenge_payload(self, *, verified: bool = False) -> dict[str, Any]:
        challenge = self._challenge
        if verified or challenge is None:
            return {"verified": True, "step": "complete", "instruction": "IDENTIDADE CONFIRMADA"}
        expected = challenge.steps[challenge.step]
        instructions = {
            "center": "OLHE DIRETAMENTE PARA A CAMERA",
            "side": "VIRE O ROSTO PARA UM DOS LADOS",
            "opposite": "AGORA VIRE PARA O OUTRO LADO",
        }
        return {
            "verified": False,
            "token": challenge.token,
            "step": expected,
            "step_index": challenge.step,
            "total_steps": len(challenge.steps),
            "instruction": instructions[expected],
            "expires_in": max(0, int(challenge.expires - time.monotonic())),
        }

    def challenge_frame(self, token: str, image_b64: str) -> dict[str, Any]:
        challenge = self._challenge
        if challenge is None or not secrets.compare_digest(token, challenge.token):
            raise ValueError("desafio facial invalido")
        if time.monotonic() > challenge.expires:
            self._challenge = None
            raise ValueError("desafio facial expirou")
        faces = self._inspect(image_b64)
        if len(faces) != 1:
            challenge.stable = 0
            challenge.attempts += 1
            return {**self._challenge_payload(), "detected": len(faces), "accepted": False}
        face = faces[0]
        self._quality(face)
        similarity = float(np.dot(self._template, face["feature"]))
        if similarity < self._threshold:
            challenge.attempts += 1
            challenge.stable = 0
            if challenge.attempts >= 5:
                self._lock("unknown_face")
                self._challenge = None
                raise PermissionError("rosto nao reconhecido")
            return {**self._challenge_payload(), "detected": 1, "accepted": False}
        expected = challenge.steps[challenge.step]
        pose_ok, side = self._pose_matches(expected, face["yaw"], challenge.first_side)
        if pose_ok:
            challenge.first_side = side
            challenge.stable += 1
        else:
            challenge.stable = 0
        if challenge.stable < 2:
            return {**self._challenge_payload(), "detected": 1, "accepted": pose_ok}
        challenge.step += 1
        challenge.stable = 0
        if challenge.step < len(challenge.steps):
            return {**self._challenge_payload(), "detected": 1, "accepted": True}
        self._challenge = None
        self._locked = False
        self._reason = "owner_present"
        self.guard.unlock_owner_session()
        self.guard.auditar("security", "face_unlock", "DONO PRESENTE", True, True)
        return self._challenge_payload(verified=True)

    def _lock(self, reason: str) -> None:
        changed = not self._locked or self._reason != reason
        self._locked = True
        self._reason = reason
        self.guard.lock_owner_session()
        if self._lock_callback is not None:
            try:
                self._lock_callback(reason)
            except Exception:
                pass
        if changed:
            # A trava ter bloqueado uma identidade ausente/desconhecida e uma
            # defesa bem-sucedida, nao uma pane operacional nem uma aprovacao
            # pendente. O motivo continua preservado na auditoria.
            self.guard.auditar("security", "face_presence", f"BLOQUEADO: {reason}", True, False)

    def set_lock_callback(self, callback) -> None:
        self._lock_callback = callback

    def disable_with_recovery(self) -> None:
        if self.memory.face_identity_profile():
            self.memory.set_face_identity_enabled(False)
        self._active = False
        self._locked = False
        self._reason = "disabled_by_owner"
        self._challenge = None
        self.guard.unlock_owner_session()
        self.guard.auditar("security", "face_disable", "DESATIVADO PELO DONO", True, True)

    def on_vault_lock(self) -> None:
        """Apaga do processo o vetor que veio do cofre."""
        self._template = None
        self._active = False
        self._locked = True
        self._reason = "vault_locked"
        self._challenge = None

    def remove_with_recovery(self) -> None:
        self.memory.delete_face_identity_profile()
        self._template = None
        self.disable_with_recovery()
