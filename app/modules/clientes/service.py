from app.core.exceptions import ConflictoError, RecursoNoEncontradoError
from app.modules.clientes.models import Cliente, Vehiculo
from app.modules.clientes.schemas import ClienteCreate, VehiculoCreate
from app.modules.clientes.unit_of_work import ClientesUnitOfWork


class ClienteService:
    """Reglas de negocio para la gestión de clientes y sus vehículos."""

    def __init__(self, uow: ClientesUnitOfWork) -> None:
        self.uow = uow

    async def crear_cliente(self, datos: ClienteCreate) -> Cliente:
        """Crea un nuevo cliente garantizando unicidad de documento y usuario (RN-01)."""
        async with self.uow:
            existente_doc = await self.uow.clientes.get_by_documento(datos.documento)
            if existente_doc:
                raise ConflictoError(
                    f"El documento '{datos.documento}' ya se encuentra registrado."
                )

            if datos.usuario_id is not None:
                existente_usr = await self.uow.clientes.get_by_usuario_id(datos.usuario_id)
                if existente_usr:
                    raise ConflictoError("El usuario ya tiene un cliente asociado.")

            cliente = Cliente(
                usuario_id=datos.usuario_id,
                nombre=datos.nombre,
                documento=datos.documento,
                telefono=datos.telefono,
            )
            await self.uow.clientes.add(cliente)
            return cliente

    async def obtener_con_vehiculos(self, cliente_id: int) -> Cliente:
        """Obtiene un cliente y sus vehículos activos con carga anticipada (sin N+1)."""
        cliente = await self.uow.clientes.get_con_vehiculos_activos(cliente_id)
        if not cliente:
            raise RecursoNoEncontradoError(f"Cliente con id {cliente_id} no encontrado.")
        return cliente

    async def agregar_vehiculo(
        self,
        cliente_id: int,
        datos: VehiculoCreate,
    ) -> Vehiculo:
        """Agrega un vehículo activo asociado al cliente."""
        async with self.uow:
            cliente = await self.uow.clientes.get_by_id(cliente_id)
            if not cliente:
                raise RecursoNoEncontradoError(
                    f"Cliente con id {cliente_id} no encontrado."
                )

            existente = await self.uow.vehiculos.get_by_patente_activa(datos.patente)
            if existente:
                raise ConflictoError(
                    f"Ya existe un vehículo activo con la patente '{datos.patente}'."
                )

            vehiculo = Vehiculo(
                cliente_id=cliente_id,
                patente=datos.patente,
                marca=datos.marca,
                modelo=datos.modelo,
                anio=datos.anio,
            )
            await self.uow.vehiculos.add(vehiculo)
            return vehiculo

    async def dar_de_baja_vehiculo(self, vehiculo_id: int) -> None:
        """Aplica borrado lógico sobre el vehículo (RN-16).

        Rechaza con 409 si el vehículo posee órdenes en estado no final.
        """
        async with self.uow:
            vehiculo = await self.uow.vehiculos.get_active_by_id(vehiculo_id)
            if not vehiculo:
                raise RecursoNoEncontradoError(
                    f"Vehículo con id {vehiculo_id} no encontrado."
                )

            tiene_abiertas = await self.uow.vehiculos.tiene_ordenes_abiertas(vehiculo_id)
            if tiene_abiertas:
                raise ConflictoError(
                    "No se puede dar de baja el vehículo porque posee órdenes de trabajo abiertas."
                )

            await self.uow.vehiculos.soft_delete(vehiculo)
