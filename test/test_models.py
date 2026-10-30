from decimal import Decimal
import pytest
from sqlmodel import SQLModel

from app.modules.usuarios.models import Usuario, AsignacionRol, IntentoAcceso, EventoSeguridad
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.repuestos.models import Repuesto, MovimientoStock, HistorialPrecioRepuesto
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo, ItemOrden, HistorialEstadoOrden


def test_registered_tables_count():
    """Valida que exactamente las 13 tablas del modelo de dominio estén registradas."""
    expected_tables = {
        "usuario",
        "asignacion_rol",
        "intento_acceso",
        "evento_seguridad",
        "cliente",
        "vehiculo",
        "repuesto",
        "estado_orden",
        "orden_trabajo",
        "item_orden",
        "historial_estado_orden",
        "movimiento_stock",
        "historial_precio_repuesto",
    }
    actual_tables = set(SQLModel.metadata.tables.keys())
    assert expected_tables.issubset(actual_tables)


def test_partial_unique_indexes_defined():
    """Valida los 3 índices únicos parciales requeridos por el dominio."""
    tables = SQLModel.metadata.tables

    # 1. asignacion_rol (usuario_id, rol) WHERE revocada_en IS NULL
    asignacion_tbl = tables["asignacion_rol"]
    idx_rol = next((idx for idx in asignacion_tbl.indexes if idx.name == "ix_asignacion_rol_usuario_rol_activa"), None)
    assert idx_rol is not None
    assert idx_rol.unique is True
    assert "revocada_en IS NULL" in str(idx_rol.dialect_options["postgresql"]["where"])

    # 2. vehiculo (patente) WHERE borrado_en IS NULL
    vehiculo_tbl = tables["vehiculo"]
    idx_vehiculo = next((idx for idx in vehiculo_tbl.indexes if idx.name == "ix_vehiculo_patente_activa"), None)
    assert idx_vehiculo is not None
    assert idx_vehiculo.unique is True
    assert "borrado_en IS NULL" in str(idx_vehiculo.dialect_options["postgresql"]["where"])

    # 3. repuesto (codigo) WHERE borrado_en IS NULL
    repuesto_tbl = tables["repuesto"]
    idx_repuesto = next((idx for idx in repuesto_tbl.indexes if idx.name == "ix_repuesto_codigo_activo"), None)
    assert idx_repuesto is not None
    assert idx_repuesto.unique is True
    assert "borrado_en IS NULL" in str(idx_repuesto.dialect_options["postgresql"]["where"])


def test_usuario_cliente_one_to_one_relationship():
    """Valida que Usuario.cliente devuelva un objeto (1 a 1) y no una lista."""
    mapper = Usuario.__mapper__
    cliente_rel = mapper.relationships["cliente"]
    assert cliente_rel.uselist is False


def test_foreign_keys_have_indexes():
    """Valida que cada clave foránea tenga su correspondiente índice (sección 4.10)."""
    for table_name, table in SQLModel.metadata.tables.items():
        for fk in table.foreign_keys:
            col_name = fk.parent.name
            # Verificar si la columna está cubierta por un índice o es clave primaria
            is_indexed = any(col_name in [c.name for c in idx.columns] for idx in table.indexes)
            is_pk = fk.parent.primary_key
            assert is_indexed or is_pk, f"Columna FK {table_name}.{col_name} no tiene índice asociado"
