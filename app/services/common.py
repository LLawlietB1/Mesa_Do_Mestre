from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db


def safe_commit() -> bool:
    """Confirma a transação; em caso de erro faz rollback, registra o log e devolve False."""
    try:
        db.session.commit()
        return True
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Falha ao gravar no banco de dados")
        return False
