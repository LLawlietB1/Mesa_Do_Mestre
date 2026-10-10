"""Remove file_assets.storage_url (as imagens ficam sempre no banco)

Revision ID: b7c1d2e3f4a5
Revises: 0aed6c58175a
Create Date: 2026-10-10 10:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c1d2e3f4a5'
down_revision = '0aed6c58175a'
branch_labels = None
depends_on = None


def upgrade():
    # Linhas que só tinham o arquivo no Blob não têm conteúdo: não existem em bancos locais.
    op.execute("DELETE FROM file_assets WHERE data IS NULL")
    with op.batch_alter_table('file_assets', schema=None) as batch_op:
        batch_op.drop_column('storage_url')
        batch_op.alter_column('data', existing_type=sa.LargeBinary(), nullable=False)


def downgrade():
    with op.batch_alter_table('file_assets', schema=None) as batch_op:
        batch_op.alter_column('data', existing_type=sa.LargeBinary(), nullable=True)
        batch_op.add_column(sa.Column('storage_url', sa.String(length=600), nullable=True))
