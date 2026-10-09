"""Ponto de entrada: `python run.py` (desenvolvimento local)."""
import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402

app = create_app()

if __name__ == "__main__":
    # Aplicação para uso individual em computador confiável: escuta só em 127.0.0.1 por padrão.
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=app.config["DEBUG"],
    )
