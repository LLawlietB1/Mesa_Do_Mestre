"""Cliente mínimo do Vercel Blob (privado), direto pela API HTTP — sem o SDK, que arrasta dezenas de dependências.

Protocolo (o mesmo do SDK oficial `vercel`/`@vercel/blob`):
  PUT  https://vercel.com/api/blob?pathname=<caminho>   corpo = bytes; cabeçalhos x-vercel-blob-access: private, ...
  POST https://vercel.com/api/blob/delete               JSON {"urls": [...]}
  GET  <url privada do blob>                            com Authorization: Bearer <token>
Os arquivos são privados: a URL do Blob NUNCA é enviada ao navegador. Toda leitura passa pela rota autenticada
/media/<id>, que confere o dono antes de buscar o conteúdo aqui."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import urlparse

from flask import current_app

API_URL = "https://vercel.com/api/blob"
API_VERSION = "11"
BLOB_HOST_SUFFIX = ".blob.vercel-storage.com"
TIMEOUT = 20
MAX_REDIRECTS = 3


class BlobError(Exception):
    pass


def token() -> str:
    return current_app.config.get("BLOB_READ_WRITE_TOKEN", "")


def enabled() -> bool:
    return bool(token())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):          # nunca segue sozinho: o token não pode vazar para outro host
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _http(req: urllib.request.Request):
    """Executa a requisição e devolve (status, cabeçalhos, corpo). Ponto único de rede (facilita os testes)."""
    try:
        with _opener.open(req, timeout=TIMEOUT) as resp:       # noqa: S310 (hosts validados abaixo)
            return resp.status, dict(resp.headers.items()), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        raise BlobError("Não foi possível falar com o armazenamento de arquivos.") from None


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {token()}"}


def _blob_host_ok(url: str) -> bool:
    p = urlparse(url)
    return p.scheme == "https" and bool(p.hostname) and p.hostname.endswith(BLOB_HOST_SUFFIX)


def put(pathname: str, data: bytes, content_type: str) -> str:
    """Grava um arquivo PRIVADO e devolve a URL do blob (guardada só no servidor)."""
    headers = {
        **_auth(), "x-api-version": API_VERSION, "x-content-type": content_type, "x-vercel-blob-access": "private",
        "x-add-random-suffix": "0", "x-allow-overwrite": "0", "x-cache-control-max-age": "31536000",
    }
    req = urllib.request.Request(f"{API_URL}?pathname={urllib.parse.quote(pathname)}", data=data, method="PUT", headers=headers)
    status, _h, body = _http(req)
    if not 200 <= status < 300:
        current_app.logger.error("[blob] PUT falhou: %s %s", status, body[:200])
        raise BlobError("O armazenamento de arquivos recusou o envio.")
    try:
        url = json.loads(body)["url"]
    except (ValueError, KeyError, TypeError):
        raise BlobError("Resposta inesperada do armazenamento de arquivos.") from None
    if not _blob_host_ok(url):
        raise BlobError("Resposta inesperada do armazenamento de arquivos.")
    return url


def fetch(url: str) -> tuple[bytes, str]:
    """Lê o conteúdo de um blob privado. Só aceita URLs do domínio do Blob (a URL vem do nosso banco)."""
    for _ in range(MAX_REDIRECTS + 1):
        if not _blob_host_ok(url):
            raise BlobError("URL de arquivo inválida.")
        status, headers, body = _http(urllib.request.Request(url, headers=_auth(), method="GET"))
        if status in (301, 302, 303, 307, 308) and headers.get("Location"):
            url = urllib.parse.urljoin(url, headers["Location"])
            continue
        if status == 404:
            raise BlobError("Arquivo não encontrado no armazenamento.")
        if not 200 <= status < 300:
            current_app.logger.error("[blob] GET falhou: %s", status)
            raise BlobError("Não foi possível ler o arquivo no armazenamento.")
        lower = {k.lower(): v for k, v in headers.items()}
        return body, lower.get("content-type", "application/octet-stream")
    raise BlobError("Redirecionamentos demais ao ler o arquivo.")


def delete(urls) -> None:
    """Remove blobs. Melhor esforço: falha vira log (um arquivo órfão não pode quebrar a página)."""
    urls = [u for u in urls if u and _blob_host_ok(u)]
    if not urls or not enabled():
        return
    req = urllib.request.Request(
        f"{API_URL}/delete", data=json.dumps({"urls": urls}).encode(), method="POST",
        headers={**_auth(), "x-api-version": API_VERSION, "content-type": "application/json"},
    )
    try:
        status, _h, body = _http(req)
        if not 200 <= status < 300:
            current_app.logger.error("[blob] DELETE falhou: %s %s", status, body[:200])
    except BlobError:
        current_app.logger.exception("[blob] falha de rede ao remover %d arquivo(s)", len(urls))
