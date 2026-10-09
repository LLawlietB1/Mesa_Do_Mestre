"""E-mail transacional via Resend (API HTTPS, plano gratuito). Usado para avisar o administrador."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from flask import current_app


def send_admin_email(subject: str, html: str) -> bool:
    """True só se o Resend aceitou o envio. Nunca levanta: falha de e-mail não pode quebrar a página."""
    c = current_app.config
    if not c["RESEND_API_KEY"] or not c["ADMIN_EMAIL"]:
        current_app.logger.error("[email] RESEND_API_KEY/ADMIN_EMAIL não configurados — e-mail não enviado: %r", subject)
        return False
    body = json.dumps({"from": c["RESEND_FROM"], "to": [c["ADMIN_EMAIL"]], "subject": subject, "html": html}).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=body, method="POST",
        headers={"Authorization": f"Bearer {c['RESEND_API_KEY']}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:      # noqa: S310 (URL fixa https)
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        current_app.logger.error("[email] Resend recusou o envio: %s %s", exc.code, exc.read()[:200])
    except (urllib.error.URLError, TimeoutError, OSError):
        current_app.logger.exception("[email] falha de rede ao enviar")
    return False
