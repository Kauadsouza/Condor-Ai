"""Gestos reais: MediaPipe local, lista fixa de ações no PC e permissões."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Nada de ~/.condor: a raiz temporária precisa existir antes dos imports.
_ORIGINAL_HOME = os.environ.get("CONDOR_HOME")
_STATE = tempfile.TemporaryDirectory(prefix="condor-gestos-")
os.environ["CONDOR_HOME"] = _STATE.name

from condor.devices.gestures import (  # noqa: E402
    GESTURE_PC_ACTIONS, MEDIAPIPE_DIR, GestureEngine, GesturePCControl,
)

UI = ROOT / "condor" / "ui"
PASS = "uma frase secreta longa e exclusiva"


def tearDownModule():
    if _ORIGINAL_HOME is None:
        os.environ.pop("CONDOR_HOME", None)
    else:
        os.environ["CONDOR_HOME"] = _ORIGINAL_HOME
    _STATE.cleanup()


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def atalho(self, teclas):
        self.calls.append(("atalho", teclas))
        return {"ok": True, "saida": f"Teclas: {teclas}"}

    def rolar(self, passos):
        self.calls.append(("rolar", passos))
        return {"ok": True, "saida": f"Rolagem: {passos:+d}"}


class GesturePCControlTests(unittest.TestCase):
    def test_allowlist_is_fixed_and_maps_to_media_keys(self):
        self.assertEqual(set(GESTURE_PC_ACTIONS), {
            "playpause", "proximo", "anterior", "rolar_cima", "rolar_baixo",
            "volume_mais", "volume_menos",
        })
        fake = FakeExecutor()
        control = GesturePCControl(fake)
        for action in GESTURE_PC_ACTIONS:
            self.assertTrue(control.run(action)["ok"])
        self.assertEqual(fake.calls, [
            ("atalho", "playpause"), ("atalho", "nexttrack"), ("atalho", "prevtrack"),
            ("rolar", 3), ("rolar", -3), ("atalho", "volumeup"), ("atalho", "volumedown"),
        ])

    def test_unknown_or_raw_key_actions_are_rejected(self):
        control = GesturePCControl(FakeExecutor())
        for action in ("win+r", "alt+f4", "enter", "PLAYPAUSE", "", None, 3, ["playpause"]):
            self.assertFalse(control.valid(action))
        with self.assertRaises(ValueError):
            control.run("win+r")

    def test_rate_limit_is_eight_per_second(self):
        now = [100.0]
        control = GesturePCControl(FakeExecutor(), clock=lambda: now[0])
        self.assertTrue(all(control.rate_allowed() for _ in range(8)))
        self.assertFalse(control.rate_allowed())
        now[0] += 1.01
        self.assertTrue(control.rate_allowed())


class VendoredMediaPipeTests(unittest.TestCase):
    def test_every_vendored_file_matches_manifest(self):
        manifest = json.loads((MEDIAPIPE_DIR / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")
        self.assertEqual(manifest["license"], "Apache-2.0")
        on_disk = {
            path.relative_to(MEDIAPIPE_DIR).as_posix()
            for path in MEDIAPIPE_DIR.rglob("*") if path.is_file()
        } - {"MANIFEST.json"}
        self.assertEqual(on_disk, set(manifest["files"]))
        for name, meta in manifest["files"].items():
            data = (MEDIAPIPE_DIR / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta["sha256"], name)
            self.assertEqual(len(data), meta["bytes"], name)
        for required in (
            "vision_bundle.js", "gesture_recognizer.task", "LICENSE.txt",
            "wasm/vision_wasm_internal.wasm", "wasm/vision_wasm_nosimd_internal.wasm",
        ):
            self.assertIn(required, manifest["files"])
        self.assertIn("Apache License", (MEDIAPIPE_DIR / "LICENSE.txt").read_text(encoding="utf-8"))

    def test_engine_reports_mediapipe_and_detects_tampering(self):
        status = GestureEngine().status()
        self.assertEqual(status["engine"], "mediapipe")
        self.assertTrue(status["mediapipe"]["available"])
        self.assertFalse(status["frame_storage"])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.js").write_text("ok", encoding="utf-8")
            (root / "MANIFEST.json").write_text(json.dumps({"version": "1.0.0", "files": {
                "a.js": {"sha256": hashlib.sha256(b"ok").hexdigest()},
            }}), encoding="utf-8")
            self.assertTrue(GestureEngine(root).status()["mediapipe"]["available"])
            (root / "a.js").write_text("adulterado", encoding="utf-8")
            tampered = GestureEngine(root).status()
            self.assertFalse(tampered["mediapipe"]["available"])
            self.assertNotEqual(tampered["engine"], "mediapipe")
            with self.assertRaises(RuntimeError):
                GestureEngine(root).start("mediapipe")

    def test_mediapipe_session_never_accepts_frames(self):
        engine = GestureEngine()
        session = engine.start("mediapipe")
        self.assertEqual(engine.status()["active_engine"], "mediapipe")
        with self.assertRaises(PermissionError):
            engine.analyze(session["token"], "AAAA")


class GesturesScriptTests(unittest.TestCase):
    def test_gestures_js_has_no_remote_urls_and_never_posts_frames(self):
        script = (UI / "scripts" / "gestures.js").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"https?:", script, re.IGNORECASE))
        self.assertNotIn("/api/gestures/frame", script)
        self.assertNotIn("toDataURL", script)
        self.assertNotIn("toBlob", script)
        self.assertIn("vendor/mediapipe", script)
        self.assertIn("recognizeForVideo", script)
        self.assertIn("requestAnimationFrame", script)
        self.assertIn("/api/gestures/action", script)
        self.assertIn("CondorVoz.toggleLocalVoice()", script)
        self.assertIn("CondorVoz.calar()", script)
        self.assertIn("'seguranca.bloqueado'", script)
        self.assertIn("PERMISSION_REVOKED", script)
        self.assertIn("document.hidden", script)

    def test_index_loads_fallback_and_short_card(self):
        index = (UI / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="gestureFeedback"', index)
        self.assertIn("<small>GESTOS</small>", index)
        self.assertLess(index.index("gestures-fallback.js"), index.index("scripts/gestures.js"))


class GestureServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from condor.config import Config
        from condor.paths import state_path
        from condor.server import montar

        cls.app, cls.session = montar(Config())
        cls.client = TestClient(cls.app, base_url="http://127.0.0.1:7777")
        segredo = state_path("security", "ui-token").read_text(encoding="utf-8").strip()
        response = cls.client.post("/api/session", headers={
            "Origin": "http://127.0.0.1:7777", "X-Condor-Client": "desktop-ui", "X-Condor-Token": segredo,
        })
        assert response.status_code == 200, response.text
        cls.client.headers.update({"Origin": "http://127.0.0.1:7777"})
        setup = cls.client.post("/api/seguranca/configurar", json={"owner": "Kaua", "passphrase": PASS})
        assert setup.status_code == 200, setup.text
        cls.memoria = cls.session.memoria
        cls.fake = FakeExecutor()
        cls.app.state.gesture_pc._executor = cls.fake

    def setUp(self):
        self.memoria.set_permission_decision("gesture_camera", "allow_always")
        self.memoria.set_permission_decision("gesture_pc_control", "block")
        self.fake.calls.clear()
        self.app.state.gesture_pc._recent.clear()

    def _token(self, label=""):
        response = self.client.post("/api/gestures/session", json={"camera_label": label, "engine": "mediapipe"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["token"]

    def test_csp_allows_wasm_but_not_eval(self):
        headers = self.client.get("/api/gestures/status").headers
        csp = headers["content-security-policy"]
        script_src = re.search(r"script-src ([^;]+);", csp).group(1).split()
        self.assertEqual(script_src, ["'self'", "'wasm-unsafe-eval'"])
        self.assertNotIn("'unsafe-eval'", csp)
        self.assertNotIn("googleapis", csp)

    def test_wasm_and_model_are_served_locally(self):
        wasm = self.client.get("/ui/vendor/mediapipe/wasm/vision_wasm_internal.wasm")
        self.assertEqual(wasm.status_code, 200)
        self.assertEqual(wasm.headers["content-type"], "application/wasm")
        model = self.client.get("/ui/vendor/mediapipe/gesture_recognizer.task")
        self.assertEqual(model.status_code, 200)
        self.assertGreater(len(model.content), 1_000_000)

    def test_status_reports_active_engine(self):
        status = self.client.get("/api/gestures/status").json()
        self.assertEqual(status["engine"], "mediapipe")
        self.assertIn("active_engine", status)

    def test_session_accepts_empty_label_but_rejects_virtual_camera(self):
        self._token("")
        virtual = self.client.post("/api/gestures/session", json={"camera_label": "OBS Virtual Camera"})
        self.assertEqual(virtual.status_code, 400)

    def test_action_rejects_unknown_before_anything_else(self):
        token = self._token()
        for action in ("win+r", "alt+f4", None, {"key": "enter"}):
            response = self.client.post("/api/gestures/action", json={"token": token, "action": action})
            self.assertEqual(response.status_code, 400, action)
        self.assertEqual(self.fake.calls, [])

    def test_action_requires_session_token(self):
        self.memoria.set_permission_decision("gesture_pc_control", "allow_always")
        response = self.client.post("/api/gestures/action", json={"token": "x", "action": "playpause"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.fake.calls, [])

    def test_action_permission_gating_creates_request(self):
        token = self._token()
        self.memoria.set_permission_decision("gesture_pc_control", "block")
        with patch.object(self.memoria, "request_permission", wraps=self.memoria.request_permission) as asked:
            denied = self.client.post("/api/gestures/action", json={"token": token, "action": "playpause"})
        self.assertEqual(denied.status_code, 403)
        self.assertIn("permission_request", denied.json())
        asked.assert_called_once()
        self.assertEqual(asked.call_args.args[0], "gesture_pc_control")
        self.assertEqual(self.fake.calls, [])
        self.memoria.set_permission_decision("gesture_pc_control", "allow_always")
        allowed = self.client.post("/api/gestures/action", json={"token": token, "action": "rolar_baixo"})
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(self.fake.calls, [("rolar", -3)])

    def test_action_is_rate_limited(self):
        token = self._token()
        self.memoria.set_permission_decision("gesture_pc_control", "allow_always")
        codes = [
            self.client.post("/api/gestures/action", json={"token": token, "action": "volume_mais"}).status_code
            for _ in range(10)
        ]
        self.assertEqual(codes[:8], [200] * 8)
        self.assertIn(429, codes[8:])
        self.assertEqual(len(self.fake.calls), 8)

    def test_ping_reports_revoked_camera(self):
        token = self._token()
        self.assertEqual(self.client.post("/api/gestures/ping", json={"token": token}).status_code, 200)
        self.memoria.set_permission_decision("gesture_camera", "block")
        self.assertEqual(self.client.post("/api/gestures/ping", json={"token": token}).status_code, 403)

    def test_permission_is_off_by_default(self):
        from condor.memory.db import DEFAULT_PERMISSIONS
        self.assertIn(("gesture_pc_control", 0, "local"), DEFAULT_PERMISSIONS)


if __name__ == "__main__":
    unittest.main()
