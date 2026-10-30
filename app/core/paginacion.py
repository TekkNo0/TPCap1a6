import math
from typing import Generic, Sequence, TypeVar
from fastapi import HTTPException, status
from pydantic import BaseModel, Field

T = TypeVar("T")


class Pagina(BaseModel, Generic[T]):
    """Envoltorio estándar de paginación según la sección 2.9 de la consigna.

    Formato: {items, total, page, size, pages}
    """

    items: list[T]
    total: int
    page: int
    size: int
    pages: int


def validar_y_calcular_paginacion(total: int, page: int, size: int) -> tuple[int, int]:
    """Calcula la cantidad total de páginas y el offset SQL.

    Lanza HTTP 422 si:
    - size no está en el rango [1, 100]
    - page es menor a 1
    - page supera la última página existente (o si con total 0 se pide page > 1).
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="El número de página debe ser mayor o igual a 1.",
        )

    if size < 1 or size > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"El tamaño de página ({size}) debe estar entre 1 y 100.",
        )

    if total == 0:
        pages = 1
        if page > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"La página {page} no existe: hay 1",
            )
        return pages, 0

    pages = math.ceil(total / size)
    if page > pages:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"La página {page} no existe: hay {pages}",
        )

    offset = (page - 1) * size
    return pages, offset
