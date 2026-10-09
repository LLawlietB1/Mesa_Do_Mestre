"""Upload seguro de imagens. As imagens são validadas, recodificadas (Pillow: remove EXIF/metadados,
limita o tamanho) e guardadas NO BANCO (tabela file_assets), servidas só ao dono em /media/<id>.
Guardar no banco evita disco (inexistente na Vercel), entra no backup e herda o isolamento por usuário."""
from __future__ import annotations

import io
import re
import uuid

from flask import current_app, g
from sqlalchemy import delete, func

from app.extensions import db
from app.models import FileAsset
from app.services import blobstore

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_FORMATS = {"PNG", "JPEG", "GIF", "WEBP"}
SAFE_NAME = re.compile(r"^[0-9a-f]{32}$")
MAX_DIMENSION = 800


class UploadError(ValueError):
    pass


def process_image(data: bytes) -> tuple[bytes, str]:
    """Confere que é uma imagem de verdade e a recodifica em WEBP (sem EXIF, até 800 px)."""
    from PIL import Image, ImageOps, UnidentifiedImageError   # import preguiçoso: acelera o início a frio

    Image.MAX_IMAGE_PIXELS = 25_000_000      # protege contra "bombas de descompressão"
    try:
        probe = Image.open(io.BytesIO(data))
        if probe.format not in ALLOWED_FORMATS:
            raise UploadError("O conteúdo do arquivo não corresponde a uma imagem válida.")
        probe.verify()
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION))
        img = img.convert("RGBA" if "A" in img.getbands() or img.mode == "P" else "RGB")
        out = io.BytesIO()
        img.save(out, "WEBP", quality=82, method=4)
    except UploadError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise UploadError("O conteúdo do arquivo não corresponde a uma imagem válida.") from None
    return out.getvalue(), "image/webp"


def validate_image(storage) -> tuple[bytes, str]:
    """Valida um FileStorage (extensão, tamanho, conteúdo) e devolve (bytes processados, content-type)."""
    filename = storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise UploadError("Formato não permitido. Use PNG, JPG, GIF ou WEBP.")
    max_bytes = current_app.config["MAX_IMAGE_BYTES"]
    raw = storage.stream.read(max_bytes + 1)
    storage.stream.seek(0)
    if not raw:
        raise UploadError("O arquivo está vazio.")
    if len(raw) > max_bytes:
        raise UploadError(f"Imagem muito grande (máximo {max_bytes // (1024 * 1024)} MB).")
    return process_image(raw)


def used_bytes(owner_id: int) -> int:
    return db.session.query(func.coalesce(func.sum(FileAsset.size), 0)).filter(FileAsset.owner_id == owner_id).scalar() or 0


NOT_ENABLED = "O envio de imagens ainda não foi liberado para a sua conta. Solicite a liberação em «Minha conta»."


def uploads_allowed() -> bool:
    user = getattr(g, "user", None)
    return bool(user and user.can_upload_images)


def save_image(storage) -> str:
    """Valida, recodifica e adiciona a imagem à sessão do banco (o commit é de quem chama)."""
    if not uploads_allowed():                      # defesa em profundidade: o formulário já desabilita o campo
        raise UploadError(NOT_ENABLED)
    data, ctype = validate_image(storage)
    quota = current_app.config["USER_IMAGE_QUOTA_BYTES"]
    if used_bytes(g.user.id) + len(data) > quota:
        raise UploadError(f"Limite de armazenamento de imagens atingido ({quota // (1024 * 1024)} MB). Remova imagens antigas.")
    asset_id = uuid.uuid4().hex
    asset = FileAsset(id=asset_id, owner_id=g.user.id, content_type=ctype, size=len(data))
    if blobstore.enabled():
        try:
            asset.storage_url = blobstore.put(f"img/{asset_id}.webp", data, ctype)
        except blobstore.BlobError as exc:
            raise UploadError(f"Não foi possível salvar a imagem: {exc} Tente novamente.") from None
        g.setdefault("pending_blob", []).append(asset.storage_url)   # removido no fim da requisição se não for confirmado
    else:
        asset.data = data
    db.session.add(asset)
    return asset.id


def delete_image(asset_id: str | None) -> None:
    """Remove a imagem do usuário atual (usado depois do commit da troca/exclusão)."""
    if not asset_id or not SAFE_NAME.match(asset_id):
        return
    url = db.session.query(FileAsset.storage_url).filter(FileAsset.id == asset_id, FileAsset.owner_id == g.user.id).scalar()
    db.session.execute(delete(FileAsset).where(FileAsset.id == asset_id, FileAsset.owner_id == g.user.id))
    db.session.commit()
    blobstore.delete([url])                       # só depois do commit: se falhar, no máximo sobra um arquivo órfão


def read_asset(asset: FileAsset) -> tuple[bytes, str]:
    """Conteúdo + content-type de uma imagem, venha do Blob ou do banco."""
    if asset.storage_url:
        body, _ = blobstore.fetch(asset.storage_url)
        return body, asset.content_type
    return asset.data or b"", asset.content_type


def apply_image(storage, current: str | None) -> tuple[str | None, str | None]:
    """Salva a nova imagem (se enviada). Devolve (id_novo_ou_atual, id_antigo_a_remover_após_commit)."""
    if storage is None or not getattr(storage, "filename", ""):
        return current, None
    new = save_image(storage)
    return new, current
