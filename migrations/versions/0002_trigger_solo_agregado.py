"""Disparador de sólo agregado (append-only) para tablas inmutables (RN-15).

Esta migración fue escrita a mano y revisada/auditada manualmente antes de su aplicación
porque Alembic autogenerate no detecta funciones ni triggers de PostgreSQL.
Garantiza que nadie pueda realizar UPDATE ni DELETE sobre:
- historial_estado_orden
- movimiento_stock
- historial_precio_repuesto

Revision ID: 0002_trigger_solo_agregado
Revises: 0001_tablas_iniciales
Create Date: 2026-10-28 09:35:00.000000
"""

from typing import Sequence, Union
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0002_trigger_solo_agregado"
down_revision: Union[str, None] = "0001_tablas_iniciales"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Función en PL/pgSQL que rechaza UPDATE o DELETE
    op.execute(
        """
        CREATE OR REPLACE FUNCTION rechazar_modificacion_solo_agregado()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Operación rechazada: la tabla % es de sólo agregado (append-only). Prohibido modificar o borrar filas.', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # 2. Trigger sobre historial_estado_orden
    op.execute(
        """
        CREATE TRIGGER tr_historial_estado_orden_solo_agregado
        BEFORE UPDATE OR DELETE ON historial_estado_orden
        FOR EACH ROW EXECUTE FUNCTION rechazar_modificacion_solo_agregado();
        """
    )

    # 3. Trigger sobre movimiento_stock
    op.execute(
        """
        CREATE TRIGGER tr_movimiento_stock_solo_agregado
        BEFORE UPDATE OR DELETE ON movimiento_stock
        FOR EACH ROW EXECUTE FUNCTION rechazar_modificacion_solo_agregado();
        """
    )

    # 4. Trigger sobre historial_precio_repuesto
    op.execute(
        """
        CREATE TRIGGER tr_historial_precio_repuesto_solo_agregado
        BEFORE UPDATE OR DELETE ON historial_precio_repuesto
        FOR EACH ROW EXECUTE FUNCTION rechazar_modificacion_solo_agregado();
        """
    )


def downgrade() -> None:
    # Eliminar triggers
    op.execute("DROP TRIGGER IF EXISTS tr_historial_precio_repuesto_solo_agregado ON historial_precio_repuesto;")
    op.execute("DROP TRIGGER IF EXISTS tr_movimiento_stock_solo_agregado ON movimiento_stock;")
    op.execute("DROP TRIGGER IF EXISTS tr_historial_estado_orden_solo_agregado ON historial_estado_orden;")

    # Eliminar función
    op.execute("DROP FUNCTION IF EXISTS rechazar_modificacion_solo_agregado();")
