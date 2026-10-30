"""Script de inicialización de datos para la base de datos (seed.py).

Vacía las tablas y carga el catálogo obligatorio de estados, los usuarios de prueba,
clientes, vehículos, repuestos con stock inicial y órdenes de referencia para los casos de prueba.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import bcrypt
from sqlalchemy import text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.modules.usuarios.models import Usuario, AsignacionRol, EventoSeguridad
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.repuestos.models import Repuesto, MovimientoStock, HistorialPrecioRepuesto
from app.modules.ordenes.models import EstadoOrden, OrdenTrabajo, ItemOrden, HistorialEstadoOrden


def _hash_password_seed(password: str) -> str:
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


async def seed() -> None:
    settings = get_settings()
    engine = create_db_engine(settings)
    session_factory = create_session_factory(engine)

    async with session_factory() as session:
        print("1. Limpiando tablas existentes...")
        # Truncate cascada vacía las tablas y reinicia secuencias
        await session.execute(
            text(
                """
                TRUNCATE TABLE 
                    historial_precio_repuesto,
                    movimiento_stock,
                    historial_estado_orden,
                    item_orden,
                    orden_trabajo,
                    estado_orden,
                    repuesto,
                    vehiculo,
                    cliente,
                    evento_seguridad,
                    intento_acceso,
                    asignacion_rol,
                    usuario
                RESTART IDENTITY CASCADE;
                """
            )
        )
        await session.commit()

        print("2. Cargando catálogo de estados de orden (RN-19)...")
        estados = [
            EstadoOrden(codigo="PENDIENTE", descripcion="Orden creada pendiente de revisión", posicion=1, es_final=False),
            EstadoOrden(codigo="EN_REPARACION", descripcion="Orden en proceso de reparación", posicion=2, es_final=False),
            EstadoOrden(codigo="TERMINADA", descripcion="Orden finalizada con repuestos descontados", posicion=3, es_final=True),
            EstadoOrden(codigo="CANCELADA", descripcion="Orden cancelada", posicion=4, es_final=True),
        ]
        session.add_all(estados)
        await session.commit()

        print("3. Cargando usuarios y roles...")
        ahora = datetime.now(timezone.utc)
        pwd_comun = _hash_password_seed("Password123!")

        usuarios_datos = [
            ("admin@example.com", "Administrador Principal", "ADMIN", False),
            ("admin2@example.com", "Segundo Administrador", "ADMIN", False),
            ("recepcion@example.com", "Recepcionista Taller", "RECEPCION", False),
            ("mecanico@example.com", "Mecánico Principal", "MECANICO", False),
            ("mecanico2@example.com", "Segundo Mecánico", "MECANICO", False),
            ("cliente@example.com", "Laura Gómez", "CLIENTE", False),
            ("nuevo@example.com", "Mecánico Nuevo (cambio req)", "MECANICO", True),
        ]

        usuarios_map = {}
        for email, nombre, rol, debe_cambiar in usuarios_datos:
            usr = Usuario(
                email=email,
                nombre=nombre,
                password_hash=pwd_comun,
                activo=True,
                debe_cambiar_password=debe_cambiar,
                password_cambiada_en=ahora,
            )
            session.add(usr)
            await session.flush()
            usuarios_map[email] = usr

            asig = AsignacionRol(
                usuario_id=usr.id,  # type: ignore[arg-type]
                rol=rol,
                desde=ahora,
                vence_en=None,
                revocada_en=None,
                otorgada_por=None,
            )
            session.add(asig)

        await session.commit()

        print("4. Cargando clientes y vehículos...")
        # Cliente 1: Laura con usuario asociado
        cliente_laura = Cliente(
            usuario_id=usuarios_map["cliente@example.com"].id,
            nombre="Laura Gómez",
            documento="30111222",
            telefono="1144556677",
        )
        session.add(cliente_laura)
        await session.flush()

        vehiculo_laura_1 = Vehiculo(
            cliente_id=cliente_laura.id,  # type: ignore[arg-type]
            patente="AB123CD",
            marca="Toyota",
            modelo="Corolla",
            anio=2020,
        )
        vehiculo_laura_2 = Vehiculo(
            cliente_id=cliente_laura.id,  # type: ignore[arg-type]
            patente="CD456EF",
            marca="Ford",
            modelo="Focus",
            anio=2018,
        )
        session.add_all([vehiculo_laura_1, vehiculo_laura_2])

        # Cliente 2: Jorge sin usuario
        cliente_jorge = Cliente(
            usuario_id=None,
            nombre="Jorge Pérez",
            documento="20333444",
            telefono="1199887766",
        )
        session.add(cliente_jorge)
        await session.flush()

        vehiculo_jorge = Vehiculo(
            cliente_id=cliente_jorge.id,  # type: ignore[arg-type]
            patente="EF789GH",
            marca="Volkswagen",
            modelo="Gol",
            anio=2015,
        )
        session.add(vehiculo_jorge)
        await session.commit()

        print("5. Cargando repuestos y stock inicial...")
        admin_usr = usuarios_map["admin@example.com"]
        repuestos_datos = [
            ("REP-01", "Filtro de aceite", Decimal("8500.00"), 10),
            ("REP-02", "Pastillas de freno", Decimal("22000.00"), 4),
            ("REP-03", "Bujía", Decimal("4500.00"), 2),
            ("REP-04", "Aceite por litro", Decimal("9500.00"), 20),
        ]

        repuestos_map = {}
        for codigo, desc, precio, stock in repuestos_datos:
            rep = Repuesto(
                codigo=codigo,
                descripcion=desc,
                precio=precio,
                stock=stock,
            )
            session.add(rep)
            await session.flush()
            repuestos_map[codigo] = rep

            mov = MovimientoStock(
                repuesto_id=rep.id,  # type: ignore[arg-type]
                orden_id=None,
                usuario_id=admin_usr.id,  # type: ignore[arg-type]
                cantidad=stock,
                motivo="Stock inicial",
                cuando=ahora,
            )
            session.add(mov)

        # Historial de precio inicial para el filtro de aceite (de 8000 a 8500)
        hist_precio = HistorialPrecioRepuesto(
            repuesto_id=repuestos_map["REP-01"].id,  # type: ignore[arg-type]
            usuario_id=admin_usr.id,  # type: ignore[arg-type]
            precio_anterior=Decimal("8000.00"),
            precio_nuevo=Decimal("8500.00"),
            cuando=ahora,
        )
        session.add(hist_precio)
        await session.commit()

        print("6. Cargando órdenes de trabajo de prueba...")
        # Orden 1: PENDIENTE, de Laura (primer auto)
        orden_1 = OrdenTrabajo(
            vehiculo_id=vehiculo_laura_1.id,  # type: ignore[arg-type]
            mecanico_id=None,
            estado="PENDIENTE",
            falla="Ruido en tren delantero y cambio de aceite",
            creada_en=ahora,
            total=Decimal("8500.00"),
        )
        session.add(orden_1)
        await session.flush()

        item_orden_1 = ItemOrden(
            orden_id=orden_1.id,  # type: ignore[arg-type]
            repuesto_id=repuestos_map["REP-01"].id,  # type: ignore[arg-type]
            cantidad=1,
            precio_unitario=Decimal("8500.00"),
        )
        session.add(item_orden_1)

        hist_orden_1 = HistorialEstadoOrden(
            orden_id=orden_1.id,  # type: ignore[arg-type]
            desde_estado=None,
            hasta_estado="PENDIENTE",
            usuario_id=usuarios_map["recepcion@example.com"].id,  # type: ignore[arg-type]
            cuando=ahora,
        )
        session.add(hist_orden_1)

        # Orden 2: EN_REPARACION, de Jorge, asignada a mecanico, con 4 bujías cuando hay 2 en stock
        orden_2 = OrdenTrabajo(
            vehiculo_id=vehiculo_jorge.id,  # type: ignore[arg-type]
            mecanico_id=usuarios_map["mecanico@example.com"].id,
            estado="EN_REPARACION",
            falla="Falla en encendido (pide 4 bujías, hay 2 en stock)",
            creada_en=ahora,
            total=Decimal("18000.00"),
        )
        session.add(orden_2)
        await session.flush()

        item_orden_2 = ItemOrden(
            orden_id=orden_2.id,  # type: ignore[arg-type]
            repuesto_id=repuestos_map["REP-03"].id,  # type: ignore[arg-type]
            cantidad=4,  # Intencional: 4 bujías cuando stock es 2 para el caso C-13
            precio_unitario=Decimal("4500.00"),
        )
        session.add(item_orden_2)

        hist_orden_2_creacion = HistorialEstadoOrden(
            orden_id=orden_2.id,  # type: ignore[arg-type]
            desde_estado=None,
            hasta_estado="PENDIENTE",
            usuario_id=usuarios_map["recepcion@example.com"].id,  # type: ignore[arg-type]
            cuando=ahora,
        )
        hist_orden_2_inicio = HistorialEstadoOrden(
            orden_id=orden_2.id,  # type: ignore[arg-type]
            desde_estado="PENDIENTE",
            hasta_estado="EN_REPARACION",
            usuario_id=usuarios_map["mecanico@example.com"].id,  # type: ignore[arg-type]
            cuando=ahora,
        )
        session.add_all([hist_orden_2_creacion, hist_orden_2_inicio])

        # 7. Historial de seguridad
        evento = EventoSeguridad(
            cuando=ahora,
            actor="SISTEMA",
            accion="Carga de los datos iniciales",
        )
        session.add(evento)

        await session.commit()
        print("¡Datos iniciales cargados con éxito!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
