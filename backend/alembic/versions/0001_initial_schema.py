"""initial schema

Revision ID: 0001
Revises: -
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('app_settings',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_app_settings'))
    )
    op.create_table('vendors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('vat_id', sa.String(length=32), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_vendors')),
    sa.UniqueConstraint('vat_id', name=op.f('uq_vendors_vat_id'))
    )
    op.create_table('webhook_endpoints',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('url', sa.String(length=2048), nullable=False),
    sa.Column('secret', sa.String(length=255), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_endpoints'))
    )
    op.create_table('documents',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('storage_key', sa.String(length=255), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('ocr_method', sa.String(length=20), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('vendor_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], name=op.f('fk_documents_vendor_id_vendors')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_documents'))
    )
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documents_sha256'), ['sha256'], unique=False)
        batch_op.create_index('ix_documents_status_created', ['status', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_documents_vendor_id'), ['vendor_id'], unique=False)

    op.create_table('webhook_deliveries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('endpoint_id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=True),
    sa.Column('event', sa.String(length=50), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_status_code', sa.Integer(), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['endpoint_id'], ['webhook_endpoints.id'], name=op.f('fk_webhook_deliveries_endpoint_id_webhook_endpoints'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_webhook_deliveries'))
    )
    with op.batch_alter_table('webhook_deliveries', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_webhook_deliveries_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_webhook_deliveries_endpoint_id'), ['endpoint_id'], unique=False)

    op.create_table('extractions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('raw', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('overrides', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('data', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('needs_review', sa.Boolean(), nullable=False),
    sa.Column('min_confidence', sa.Double(), nullable=False),
    sa.Column('vendor_name', sa.String(length=255), nullable=True),
    sa.Column('invoice_number', sa.String(length=100), nullable=True),
    sa.Column('total', sa.Double(), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_extractions_document_id_documents'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_extractions')),
    sa.UniqueConstraint('document_id', name=op.f('uq_extractions_document_id'))
    )
    with op.batch_alter_table('extractions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_extractions_needs_review'), ['needs_review'], unique=False)

    op.create_table('field_corrections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=False),
    sa.Column('vendor_id', sa.Integer(), nullable=True),
    sa.Column('field_path', sa.String(length=64), nullable=False),
    sa.Column('old_value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('new_value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], name=op.f('fk_field_corrections_document_id_documents'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], name=op.f('fk_field_corrections_vendor_id_vendors')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_field_corrections'))
    )
    with op.batch_alter_table('field_corrections', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_field_corrections_document_id'), ['document_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_field_corrections_vendor_id'), ['vendor_id'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('field_corrections', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_field_corrections_vendor_id'))
        batch_op.drop_index(batch_op.f('ix_field_corrections_document_id'))

    op.drop_table('field_corrections')
    with op.batch_alter_table('extractions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_extractions_needs_review'))

    op.drop_table('extractions')
    with op.batch_alter_table('webhook_deliveries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_webhook_deliveries_endpoint_id'))
        batch_op.drop_index(batch_op.f('ix_webhook_deliveries_document_id'))

    op.drop_table('webhook_deliveries')
    with op.batch_alter_table('documents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documents_vendor_id'))
        batch_op.drop_index('ix_documents_status_created')
        batch_op.drop_index(batch_op.f('ix_documents_sha256'))

    op.drop_table('documents')
    op.drop_table('webhook_endpoints')
    op.drop_table('vendors')
    op.drop_table('app_settings')
