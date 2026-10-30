from functools import lru_cache
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación cargada desde variables de entorno o archivo .env.

    Los secretos críticos como POSTGRES_PASSWORD y JWT_SECRET_KEY no poseen valor por
    defecto en el código; si faltan en el entorno, la aplicación fallará al inicializarse.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Variables de PostgreSQL
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str  # Obligatoria: sin valor por defecto
    POSTGRES_DB: str = "taller_mecanico"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    SQL_ECHO: bool = False

    # Seguridad y firma de tokens
    JWT_SECRET_KEY: str  # Obligatoria: sin valor por defecto
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    COOKIE_SECURE: bool = False

    # Costo de hash para contraseñas
    BCRYPT_ROUNDS: int = 12

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """Arma la URL asincrónica de conexión para PostgreSQL usando asyncpg."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache
def get_settings() -> Settings:
    """Retorna una instancia cacheada de Settings."""
    return Settings()
