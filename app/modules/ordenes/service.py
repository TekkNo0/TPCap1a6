import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import logging
from typing import Optional

from app.core.dependencies import obtener_roles_vigentes_usuario
from app.core.exceptions import (
    ConflictoError,
    PermisoDenegadoError,
    RecursoNoEncontradoError,
)
from app.modules.ordenes.models import (
    EstadoOrden,
    HistorialEstadoOrden,
    ItemOrden,
    OrdenTrabajo,
)
from app.modules.ordenes.schemas import OrdenCreate
from app.modules.ordenes.unit_of_work import OrdenesUnitOfWork
from app.modules.repuestos.models import MovimientoStock
from app.modules.usuarios.models import Usuario

logger = logging.getLogger("taller.ordenes")


async def simular_notificacion_cliente(orden_id: int, cliente_email: str) -> None:
    """Tarea en segundo plano (BackgroundTasks) para notificar al cliente al terminar la orden (sección 3.9)."""
    await asyncio.sleep(0.5)
    logger.info(f"Notificación enviada con éxito a {cliente_email} para la orden #{orden_id}.")


class OrdenService:
    """Reglas de negocio para órdenes de trabajo, transiciones y stock."""

    def __init__(self, uow: OrdenesUnitOfWork) -> None:
        self.uow = uow

    async def listar_catalogo(self) -> list[EstadoOrden]:
        """Retorna las filas del catálogo de estados por posición (RN-19)."""
        return await self.uow.catalogo.listar_por_posicion()

    async def crear_orden(
        self,
        datos: OrdenCreate,
        usuario_id: int,
    ) -> OrdenTrabajo:
        """Crea una orden de trabajo en estado PENDIENTE (RN-10).

        Copia el precio unitario vigente de cada repuesto y calcula el total.
        Inserta la primera línea en historial_estado_orden.
        """
        async with self.uow:
            # RN-19: Si el catálogo está vacío responde 409
            cant_estados = await self.uow.catalogo.count()
            if cant_estados == 0:
                raise ConflictoError(
                    "El catálogo de estados se encuentra vacío. No se pueden crear órdenes."
                )

            # Validar vehículo activo
            vehiculo = await self.uow.vehiculos.get_active_by_id(datos.vehiculo_id)
            if not vehiculo:
                raise ConflictoError(
                    f"Vehículo con id {datos.vehiculo_id} no encontrado o dado de baja."
                )

            # Validar y calcular precios de repuestos
            total = Decimal("0.00")
            items_preparados = []
            for item in datos.items:
                repuesto = await self.uow.repuestos.get_active_by_id(item.repuesto_id)
                if not repuesto:
                    # Caso C-10: Con repuesto inexistente o borrado responde 409
                    raise ConflictoError(
                        f"Repuesto con id {item.repuesto_id} no disponible o inexistente."
                    )
                subtotal = repuesto.precio * item.cantidad
                total += subtotal
                items_preparados.append((repuesto.id, item.cantidad, repuesto.precio))

            ahora = datetime.now(timezone.utc)
            orden = OrdenTrabajo(
                vehiculo_id=datos.vehiculo_id,
                mecanico_id=None,
                estado="PENDIENTE",
                falla=datos.falla,
                creada_en=ahora,
                total=total,
            )
            await self.uow.ordenes.add(orden)

            for rep_id, cantidad, precio in items_preparados:
                item_orden = ItemOrden(
                    orden_id=orden.id,  # type: ignore[arg-type]
                    repuesto_id=rep_id,
                    cantidad=cantidad,
                    precio_unitario=precio,
                )
                await self.uow.items.add(item_orden)

            # Primera línea de historial inmutable
            historial = HistorialEstadoOrden(
                orden_id=orden.id,  # type: ignore[arg-type]
                desde_estado=None,
                hasta_estado="PENDIENTE",
                usuario_id=usuario_id,
                cuando=ahora,
            )
            await self.uow.historial.add(historial)

            return await self.uow.ordenes.get_detalle_completo(orden.id)  # type: ignore[return-value]

    async def obtener_por_id(
        self,
        orden_id: int,
        usuario_actual: Usuario,
    ) -> OrdenTrabajo:
        """Obtiene el detalle completo de una orden sin N+1.

        Accesible por el personal del taller o el dueño del vehículo (RN-17).
        """
        orden = await self.uow.ordenes.get_detalle_completo(orden_id)
        if not orden:
            raise RecursoNoEncontradoError(f"Orden con id {orden_id} no encontrada.")

        roles = await obtener_roles_vigentes_usuario(
            usuario_actual.id,  # type: ignore[arg-type]
            self.uow.session,
        )
        es_personal = any(r in roles for r in ["ADMIN", "RECEPCION", "MECANICO"])
        es_duenio = bool(
            orden.vehiculo
            and orden.vehiculo.cliente
            and orden.vehiculo.cliente.usuario_id == usuario_actual.id
        )

        if not (es_personal or es_duenio):
            raise PermisoDenegadoError(
                "Acceso denegado: esta orden pertenece a otro cliente."
            )

        return orden

    async def iniciar(
        self,
        orden_id: int,
        mecanico_id: int,
    ) -> OrdenTrabajo:
        """Transición PENDIENTE -> EN_REPARACION por un mecánico asignado (RN-11)."""
        async with self.uow:
            orden = await self.uow.ordenes.get_by_id(orden_id)
            if not orden:
                raise RecursoNoEncontradoError(f"Orden con id {orden_id} no encontrada.")

            if orden.estado != "PENDIENTE":
                raise ConflictoError(
                    f"No se puede iniciar una orden en estado '{orden.estado}'. Debe estar PENDIENTE."
                )

            ahora = datetime.now(timezone.utc)
            orden.estado = "EN_REPARACION"
            orden.mecanico_id = mecanico_id
            await self.uow.ordenes.update(orden)

            historial = HistorialEstadoOrden(
                orden_id=orden.id,  # type: ignore[arg-type]
                desde_estado="PENDIENTE",
                hasta_estado="EN_REPARACION",
                usuario_id=mecanico_id,
                cuando=ahora,
            )
            await self.uow.historial.add(historial)
            if hasattr(orden, "historial_estados"):
                orden.historial_estados.append(historial)

            return await self.uow.ordenes.get_detalle_completo(orden.id)  # type: ignore[return-value]

    async def terminar(
        self,
        orden_id: int,
        usuario_actual: Usuario,
    ) -> tuple[OrdenTrabajo, str]:
        """Transición EN_REPARACION -> TERMINADA con descuento atómico de stock (RN-11 / RN-13).

        Si algún repuesto no alcanza, la transacción entera hace rollback (Caso C-11).
        """
        async with self.uow:
            orden = await self.uow.ordenes.get_detalle_completo(orden_id)
            if not orden:
                raise RecursoNoEncontradoError(f"Orden con id {orden_id} no encontrada.")

            roles = await obtener_roles_vigentes_usuario(
                usuario_actual.id,  # type: ignore[arg-type]
                self.uow.session,
            )
            es_admin = "ADMIN" in roles
            es_mecanico_asignado = orden.mecanico_id == usuario_actual.id

            if not (es_admin or es_mecanico_asignado):
                raise PermisoDenegadoError(
                    "Sólo el mecánico asignado a la orden o un administrador pueden terminarla."
                )

            if orden.estado != "EN_REPARACION":
                raise ConflictoError(
                    f"No se puede terminar una orden en estado '{orden.estado}'. Debe estar EN_REPARACION."
                )

            # RN-13: Verificar que alcance el stock de TODOS los ítems antes de aplicar cambios
            for item in orden.items:
                rep = await self.uow.repuestos.get_by_id_including_deleted(item.repuesto_id)
                if not rep or rep.stock < item.cantidad:
                    raise ConflictoError(
                        f"Stock insuficiente para el repuesto '{rep.codigo if rep else item.repuesto_id}'. "
                        f"Requerido: {item.cantidad}, Disponible: {rep.stock if rep else 0}."
                    )

            # Descontar stock y registrar movimientos de salida
            ahora = datetime.now(timezone.utc)
            for item in orden.items:
                rep = await self.uow.repuestos.get_by_id_including_deleted(item.repuesto_id)
                if rep:
                    rep.stock -= item.cantidad
                    await self.uow.repuestos.update(rep)

                    mov = MovimientoStock(
                        repuesto_id=rep.id,  # type: ignore[arg-type]
                        orden_id=orden.id,
                        usuario_id=usuario_actual.id,  # type: ignore[arg-type]
                        cantidad=-item.cantidad,  # Salida
                        motivo=f"Salida por terminación de orden #{orden.id}",
                        cuando=ahora,
                    )
                    await self.uow.movimientos.add(mov)

            orden.estado = "TERMINADA"
            await self.uow.ordenes.update(orden)

            historial = HistorialEstadoOrden(
                orden_id=orden.id,  # type: ignore[arg-type]
                desde_estado="EN_REPARACION",
                hasta_estado="TERMINADA",
                usuario_id=usuario_actual.id,  # type: ignore[arg-type]
                cuando=ahora,
            )
            await self.uow.historial.add(historial)
            if hasattr(orden, "historial_estados"):
                orden.historial_estados.append(historial)

            cliente_email = (
                orden.vehiculo.cliente.usuario.email
                if (orden.vehiculo and orden.vehiculo.cliente and orden.vehiculo.cliente.usuario)
                else "cliente@example.com"
            )

            return orden, cliente_email

    async def cancelar(
        self,
        orden_id: int,
        usuario_actual: Usuario,
    ) -> OrdenTrabajo:
        """Transición PENDIENTE -> CANCELADA.

        RN-12: El permiso se evalúa antes que el estado (403 antes que 409).
        """
        async with self.uow:
            orden = await self.uow.ordenes.get_detalle_completo(orden_id)
            if not orden:
                raise RecursoNoEncontradoError(f"Orden con id {orden_id} no encontrada.")

            # 1. Permiso: RECEPCION, ADMIN o el dueño del vehículo
            roles = await obtener_roles_vigentes_usuario(
                usuario_actual.id,  # type: ignore[arg-type]
                self.uow.session,
            )
            es_personal = any(r in roles for r in ["ADMIN", "RECEPCION"])
            es_duenio = bool(
                orden.vehiculo
                and orden.vehiculo.cliente
                and orden.vehiculo.cliente.usuario_id == usuario_actual.id
            )

            if not (es_personal or es_duenio):
                raise PermisoDenegadoError(
                    "No posee autorización para cancelar esta orden de trabajo."
                )

            # 2. Estado (evaluado tras confirmar el permiso)
            if orden.estado != "PENDIENTE":
                raise ConflictoError(
                    f"No se puede cancelar una orden en estado '{orden.estado}'. Solo se pueden cancelar órdenes PENDIENTE."
                )

            ahora = datetime.now(timezone.utc)
            orden.estado = "CANCELADA"
            await self.uow.ordenes.update(orden)

            historial = HistorialEstadoOrden(
                orden_id=orden.id,  # type: ignore[arg-type]
                desde_estado="PENDIENTE",
                hasta_estado="CANCELADA",
                usuario_id=usuario_actual.id,  # type: ignore[arg-type]
                cuando=ahora,
            )
            await self.uow.historial.add(historial)
            if hasattr(orden, "historial_estados"):
                orden.historial_estados.append(historial)

            return orden

    async def listar(
        self,
        estado: Optional[str],
        page: int,
        size: int,
    ) -> tuple[list[OrdenTrabajo], int, int]:
        """Lista órdenes de trabajo filtradas opcionalmente por estado."""
        return await self.uow.ordenes.listar_paginado(estado=estado, page=page, size=size)

    async def listar_mis_ordenes(
        self,
        usuario_id: int,
        page: int,
        size: int,
    ) -> tuple[list[OrdenTrabajo], int, int]:
        """Lista las órdenes de los vehículos del cliente autenticado (RN-17)."""
        cliente = await self.uow.clientes.get_by_usuario_id(usuario_id)
        if not cliente:
            return [], 0, 1
        return await self.uow.ordenes.listar_por_cliente_paginado(
            cliente_id=cliente.id,  # type: ignore[arg-type]
            page=page,
            size=size,
        )
