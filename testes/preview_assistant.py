"""Disposable local UI review. Never reads or modifies the owner's vault."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temporary = tempfile.TemporaryDirectory(prefix="condor-ui-review-")
os.environ["CONDOR_HOME"] = temporary.name

from condor.config import Config
from condor.paths import state_path
from condor.server import montar
import uvicorn

config = Config(
    servidor={"porta": 18777}, escuta={"ativa": False}, visualizacao_movel={"ativa": False},
    cerebro={"provedor_preferido": "local", "modelo_local": "qwen3:4b-instruct", "max_tokens": 400},
    seguranca={"simulacao": True}, sessao={"abrir_janela_ao_acordar": False, "fechar_janela_ao_dormir": False},
)
app, session = montar(config)

async def prepare():
    setup = next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/api/seguranca/configurar")
    await setup({"passphrase": "disposable-preview-passphrase", "owner": "Teste local"})
    token = state_path("security", "ui-token").read_text().strip()
    print(f"REVIEW_URL=http://127.0.0.1:18777/ui/index.html#t={token}", flush=True)

app.router.add_event_handler("startup", prepare)
try:
    uvicorn.run(app, host="127.0.0.1", port=18777, log_level="warning")
finally:
    temporary.cleanup()

