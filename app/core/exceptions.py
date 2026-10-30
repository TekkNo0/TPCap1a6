from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError


class DominioError(Exception):
    """Excepción base del dominio."""

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


class RecursoNoEncontradoError(DominioError):
    """Lanzada cuando una entidad solicitada no existe (HTTP 404)."""
    pass


class ConflictoError(DominioError):
    """Lanzada cuando una operación viola una restricción de unicidad o estado (HTTP 409)."""
    pass


class PermisoDenegadoError(DominioError):
    """Lanzada cuando un actor no tiene autorización para operar sobre un recurso (HTTP 403)."""
    pass


class NoAutenticadoError(DominioError):
    """Lanzada cuando falta autenticación o el token es inválido/expirado (HTTP 401)."""
    pass


class ValidacionDominioError(DominioError):
    """Lanzada cuando los datos no cumplen reglas de dominio o paginación (HTTP 422)."""
    pass


def traducir_error_integridad(exc: IntegrityError) -> HTTPException:
    """Traduce excepciones de base de datos IntegrityError a HTTP 409 con mensaje propio.

    Evita exponer trazas internas del motor de base de datos (RN-18).
    """
    orig_msg = str(exc.orig).lower() if exc.orig else str(exc).lower()

    if "unique" in orig_msg or "duplicate key" in orig_msg:
        if "uq_usuario_email" in orig_msg or "usuario_email" in orig_msg:
            detalle = "El correo electrónico ya se encuentra registrado."
        elif "uq_cliente_documento" in orig_msg or "cliente_documento" in orig_msg:
            detalle = "El documento ya pertenece a otro cliente registrado."
        elif "ix_vehiculo_patente_activa" in orig_msg:
            detalle = "Ya existe un vehículo activo con la misma patente."
        elif "ix_repuesto_codigo_activo" in orig_msg:
            detalle = "Ya existe un repuesto activo con ese código."
        elif "uq_item_orden_orden_repuesto" in orig_msg:
            detalle = "El repuesto ya está cargado en esta orden."
        elif "ix_asignacion_rol_usuario_rol_activa" in orig_msg:
            detalle = "El usuario ya posee ese rol activo."
        else:
            detalle = "Conflicto: ya existe un registro con esos datos únicos."
    elif "foreign key" in orig_msg or "fk_" in orig_msg:
        detalle = "Operación rechazada: se hace referencia a un registro inexistente o catálogo incompatible."
    elif "check constraint" in orig_msg or "ck_" in orig_msg:
        detalle = "Operación rechazada: los valores no satisfacen las restricciones de negocio de la base de datos."
    else:
        detalle = "Conflicto de integridad de datos al procesar la solicitud."

    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)
