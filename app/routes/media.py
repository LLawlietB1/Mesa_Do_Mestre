from flask import Blueprint, Response, abort

from app.extensions import db
from app.models import FileAsset
from app.services.ownership import is_owned
from app.services.uploads import SAFE_NAME

bp = Blueprint("media", __name__, url_prefix="/media")


@bp.get("/<string:filename>")
def serve(filename):
    """Serve a imagem somente ao dono (id aleatório + checagem de posse; nunca caminhos de arquivo)."""
    if not SAFE_NAME.match(filename):
        abort(404)
    asset = db.session.get(FileAsset, filename)
    if asset is None or not is_owned(asset):
        abort(404)
    resp = Response(asset.data, mimetype=asset.content_type)
    resp.headers["Cache-Control"] = "private, max-age=3600"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
