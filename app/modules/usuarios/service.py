from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import obtener_roles_vigentes_usuario
from app.core.exceptions import (
    ConflictoError,
    RecursoNoEncontradoError,
)
from app.core.security import (
    crear_token_jwt,
    hash_password,
    verify_password,
)
from app.modules.clientes.models import Cliente
from app.modules.usuarios.models import (
    AsignacionRol,
    EventoSeguridad,
    IntentoAcceso,
    Usuario,
)
from app.modules.usuarios.schemas import (
    AsignarRolRequest,
    CambiarPasswordRequest,
    LoginRequest,
    RegistroRequest,
    UsuarioPersonalCreate,
)
from app.modules.usuarios.unit_of_work import UsuariosUnitOfWork


class UsuarioService:
    """Reglas de negocio para usuarios, roles, login y auditoría."""

    def __init__(self, uow: UsuariosUnitOfWork) -> None:
        self.uow = uow

    async def registrar_cliente(self, datos: RegistroRequest) -> Usuario:
        """Autorregistro público de clientes con rol CLIENTE (RN-02).

        El hash de la contraseña se realiza antes de abrir la transacción (sección 5.6).
        """
        settings = get_settings()
        # 1. Bcrypt fuera de la transacción para no retener la conexión
        pwd_hash = await hash_password(datos.password, rounds=settings.BCRYPT_ROUNDS)

        async with self.uow:
            # Validar unicidad de correo y documento
            existente_usr = await self.uow.usuarios.get_by_email(datos.email)
            if existente_usr:
                raise ConflictoError(f"El correo '{datos.email}' ya se encuentra registrado.")

            existente_doc = await self.uow.clientes.get_by_documento(datos.documento)
            if existente_doc:
                raise ConflictoError(f"El documento '{datos.documento}' ya se encuentra registrado.")

            ahora = datetime.now(timezone.utc)
            usuario = Usuario(
                email=datos.email,
                nombre=datos.nombre,
                password_hash=pwd_hash,
                activo=True,
                debe_cambiar_password=False,
                password_cambiada_en=ahora,
            )
            await self.uow.usuarios.add(usuario)

            cliente = Cliente(
                usuario_id=usuario.id,
                nombre=datos.nombre,
                documento=datos.documento,
                telefono=datos.telefono,
            )
            await self.uow.clientes.add(cliente)

            # Rol CLIENTE asignado por defecto
            rol = AsignacionRol(
                usuario_id=usuario.id,  # type: ignore[arg-type]
                rol="CLIENTE",
                desde=ahora,
                vence_en=None,
                revocada_en=None,
                otorgada_por=None,
            )
            await self.uow.roles.add(rol)

            evento = EventoSeguridad(
                cuando=ahora,
                actor="USUARIO",
                accion=f"Autorregistro de cliente {usuario.email}",
            )
            await self.uow.eventos.add(evento)

            return usuario

    async def login(
        self,
        datos: LoginRequest,
        ip: str,
        dummy_hash: str,
        session_factory,
    ) -> tuple[Usuario, str, int]:
        """Flujo de autenticación según orden estricto de la sección 5.5.

        1. Límite de intentos (RN-08): responde 429 sin calcular hash.
        2. Verificación de hash (real o ficticio para mitigar temporización RN-09).
        3. Registro del intento en su propia sesión independiente.
        4. Emisión de JWT en caso de éxito.
        """
        # Paso 1: Límite de intentos en 60 segundos
        supero = await self.uow.intentos.supero_limite_intentos(datos.email, ip)
        if supero:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demasiados intentos fallidos. Intente nuevamente en unos instantes.",
                headers={"Retry-After": "60"},
            )

        # Paso 2: Buscar usuario
        usuario = await self.uow.usuarios.get_by_email(datos.email)
        pwd_hash = (
            usuario.password_hash
            if (usuario and usuario.activo)
            else dummy_hash
        )

        # Paso 3: Verificar contraseña bajo semáforo
        valido = await verify_password(datos.password, pwd_hash)
        exito_final = bool(valido and usuario and usuario.activo)

        # Paso 4: Guardar intento en su propia sesión dedicada (sobrevive a fallos)
        ahora = datetime.now(timezone.utc)
        async with session_factory() as attempt_session:
            intento = IntentoAcceso(
                cuando=ahora,
                email=datos.email,
                ip=ip,
                exito=exito_final,
            )
            attempt_session.add(intento)
            await attempt_session.commit()

        # Si falló, responder 401 con mensaje genérico
        if not exito_final or usuario is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Credenciales inválidas.",
            )

        # Paso 5: Consultar roles vigentes y emitir token
        roles_vigentes = await obtener_roles_vigentes_usuario(
            usuario.id,  # type: ignore[arg-type]
            self.uow.session,
        )
        settings = get_settings()
        token, _, exp_seg = crear_token_jwt(
            usuario_id=usuario.id,  # type: ignore[arg-type]
            email=usuario.email,
            roles=roles_vigentes,
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expira_minutos=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        return usuario, token, exp_seg

    async def cambiar_password(
        self,
        usuario_id: int,
        datos: CambiarPasswordRequest,
    ) -> tuple[Usuario, str, int]:
        """Cambia la contraseña, actualiza password_cambiada_en y emite un nuevo token (RN-07)."""
        usuario = await self.uow.usuarios.get_by_id(usuario_id)
        if not usuario or not usuario.activo:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario inexistente o inactivo.",
            )

        # Verificar contraseña actual
        valido = await verify_password(datos.password_actual, usuario.password_hash)
        if not valido:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="La contraseña actual no es correcta.",
            )

        settings = get_settings()
        nuevo_hash = await hash_password(datos.password_nueva, rounds=settings.BCRYPT_ROUNDS)

        async with self.uow:
            ahora = datetime.now(timezone.utc)
            usuario.password_hash = nuevo_hash
            usuario.password_cambiada_en = ahora
            usuario.debe_cambiar_password = False
            await self.uow.usuarios.update(usuario)

            evento = EventoSeguridad(
                cuando=ahora,
                actor=usuario.email,
                accion="Cambio de contraseña",
            )
            await self.uow.eventos.add(evento)

        # Emitir token con iat posterior a password_cambiada_en
        roles_vigentes = await obtener_roles_vigentes_usuario(
            usuario.id,  # type: ignore[arg-type]
            self.uow.session,
        )
        token, _, exp_seg = crear_token_jwt(
            usuario_id=usuario.id,  # type: ignore[arg-type]
            email=usuario.email,
            roles=roles_vigentes,
            secret_key=settings.JWT_SECRET_KEY,
            algorithm=settings.JWT_ALGORITHM,
            expira_minutos=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )

        return usuario, token, exp_seg

    async def crear_personal(
        self,
        datos: UsuarioPersonalCreate,
        admin_actor: str,
    ) -> Usuario:
        """Alta de personal por un administrador (con cambio de contraseña obligatorio)."""
        settings = get_settings()
        pwd_hash = await hash_password(
            datos.password_provisoria, rounds=settings.BCRYPT_ROUNDS
        )

        async with self.uow:
            existente = await self.uow.usuarios.get_by_email(datos.email)
            if existente:
                raise ConflictoError(f"El correo '{datos.email}' ya existe.")

            ahora = datetime.now(timezone.utc)
            usuario = Usuario(
                email=datos.email,
                nombre=datos.nombre,
                password_hash=pwd_hash,
                activo=True,
                debe_cambiar_password=True,  # Obligatorio cambiar en primer login
                password_cambiada_en=ahora,
            )
            await self.uow.usuarios.add(usuario)

            rol = AsignacionRol(
                usuario_id=usuario.id,  # type: ignore[arg-type]
                rol=datos.rol,
                desde=ahora,
                vence_en=None,
                revocada_en=None,
                otorgada_por=None,
            )
            await self.uow.roles.add(rol)

            evento = EventoSeguridad(
                cuando=ahora,
                actor=admin_actor,
                accion=f"Alta de personal {usuario.email} con rol {datos.rol}",
            )
            await self.uow.eventos.add(evento)

            return usuario

    async def listar_roles_usuario(self, usuario_id: int) -> list[AsignacionRol]:
        """Retorna el historial completo de roles de un usuario."""
        usuario = await self.uow.usuarios.get_by_id(usuario_id)
        if not usuario:
            raise RecursoNoEncontradoError(f"Usuario con id {usuario_id} no encontrado.")
        return await self.uow.roles.listar_por_usuario(usuario_id)

    async def asignar_rol(
        self,
        usuario_id: int,
        datos: AsignarRolRequest,
        admin_usuario: Usuario,
    ) -> AsignacionRol:
        """Asigna un rol con vencimiento opcional.

        Si ya tenía el rol vencido, cierra la fila anterior y abre una nueva (sección 5.9).
        """
        async with self.uow:
            usuario = await self.uow.usuarios.get_by_id(usuario_id)
            if not usuario:
                raise RecursoNoEncontradoError(
                    f"Usuario con id {usuario_id} no encontrado."
                )

            ahora = datetime.now(timezone.utc)
            rol_activo = await self.uow.roles.get_rol_activo(usuario_id, datos.rol)

            if rol_activo:
                if rol_activo.vence_en is None or rol_activo.vence_en > ahora:
                    raise ConflictoError(
                        f"El usuario ya posee el rol activo y vigente '{datos.rol}'."
                    )
                # Cerrar fila del rol vencido
                rol_activo.revocada_en = ahora
                await self.uow.roles.update(rol_activo)

            nueva_asignacion = AsignacionRol(
                usuario_id=usuario_id,
                rol=datos.rol,
                desde=ahora,
                vence_en=datos.vence_en,
                revocada_en=None,
                otorgada_por=admin_usuario.id,
            )
            await self.uow.roles.add(nueva_asignacion)

            evento = EventoSeguridad(
                cuando=ahora,
                actor=admin_usuario.email,
                accion=f"Asignación de rol {datos.rol} a usuario {usuario_id}",
            )
            await self.uow.eventos.add(evento)

            return nueva_asignacion

    async def revocar_rol(
        self,
        usuario_id: int,
        rol: str,
        admin_usuario: Usuario,
    ) -> AsignacionRol:
        """Revoca un rol estableciendo revocada_en.

        Aplica reglas de autoprotección (RN-05):
        - Un administrador no puede revocarse a sí mismo el rol ADMIN.
        - No se puede revocar el último ADMIN activo del sistema.
        """
        # RN-05: Autoprotección
        if usuario_id == admin_usuario.id and rol == "ADMIN":
            raise ConflictoError(
                "Operación rechazada: un administrador no puede revocarse a sí mismo el rol ADMIN."
            )

        async with self.uow:
            usuario = await self.uow.usuarios.get_by_id(usuario_id)
            if not usuario:
                raise RecursoNoEncontradoError(
                    f"Usuario con id {usuario_id} no encontrado."
                )

            if rol == "ADMIN":
                admins_activos = await self.uow.roles.contar_admins_activos()
                if admins_activos <= 1:
                    raise ConflictoError(
                        "Operación rechazada: no se puede revocar al único administrador activo del sistema."
                    )

            rol_activo = await self.uow.roles.get_rol_activo(usuario_id, rol)
            if not rol_activo:
                raise RecursoNoEncontradoError(
                    f"El usuario no tiene una asignación activa del rol '{rol}'."
                )

            ahora = datetime.now(timezone.utc)
            rol_activo.revocada_en = ahora
            await self.uow.roles.update(rol_activo)

            evento = EventoSeguridad(
                cuando=ahora,
                actor=admin_usuario.email,
                accion=f"Revocación de rol {rol} a usuario {usuario_id}",
            )
            await self.uow.eventos.add(evento)

            return rol_activo

    async def listar_eventos_seguridad(
        self,
        page: int,
        size: int,
    ) -> tuple[list[EventoSeguridad], int, int]:
        """Lista los eventos de seguridad paginados."""
        return await self.uow.eventos.listar_paginado(page=page, size=size)
