"""Ponto de entrada da Vercel (função serverless Python). Expõe o objeto WSGI `app`.

Se a configuração estiver errada (ex.: SECRET_KEY ausente), em vez de um "500" mudo a função responde
com uma página explicando o que falta, e o erro completo vai para os logs da Vercel."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from app import create_app

    app = create_app()
except Exception as exc:  # noqa: BLE001
    logging.exception("Falha ao iniciar a aplicação")
    from flask import Flask

    # Só mostramos a mensagem quando é um erro de configuração NOSSO (RuntimeError com texto próprio).
    detail = str(exc) if isinstance(exc, RuntimeError) else "Falha ao iniciar a aplicação. Veja os logs da função na Vercel."
    app = Flask(__name__)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def startup_error(path):
        return (f"<!doctype html><meta charset=utf-8><title>Erro de configuração</title>"
                f"<h1>Mesa do Mestre — erro de configuração</h1><p>{detail}</p>"
                f"<p>Corrija as variáveis de ambiente na Vercel (Settings → Environment Variables) e faça um novo deploy.</p>"), 500
