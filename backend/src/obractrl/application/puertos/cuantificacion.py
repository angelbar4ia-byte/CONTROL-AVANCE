"""Puertos del cuantificador (`plano`, `trazo`, `enlace_cuantificacion`,
`nota_plano`, migración 0057).

Spec §12.11 (inversión de dependencias: los puertos se declaran en la
aplicación y se implementan en el borde) · cerebro MODELO.md §1b.

Separados de `repositorios.py` por el mismo criterio que ya usa
`cargadores.py`: es un contexto propio (Cuantificación), con sus cuatro
tablas nuevas, y no una extensión de un puerto ya existente.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

__all__ = [
    "RepositorioEnlacesCuantificacion",
    "RepositorioNotasPlano",
    "RepositorioPlanos",
    "RepositorioTrazos",
]


@runtime_checkable
class RepositorioPlanos(Protocol):
    """Metadatos del plano ejecutivo (`plano`, migración 0057).

    El archivo ya está subido a R2 por `POST /evidencias/presigned`
    (mismo patrón que `expediente_doc`): `archivo_url` es la clave del
    objeto, nunca el binario.
    """

    async def crear(
        self,
        *,
        obra_id: UUID,
        nombre: str,
        archivo_url: str,
        version: int,
        capas: list[str] | None,
        subido_por: UUID,
    ) -> UUID: ...

    async def obtener(self, plano_id: UUID) -> dict[str, Any] | None: ...

    async def fijar_escala(
        self,
        plano_id: UUID,
        *,
        escala_m_por_unidad: Decimal,
        referencia: dict[str, Any],
        usuario_id: UUID,
    ) -> None:
        """Calibra (o recalibra) el plano (migración 0069). La geometría de los
        trazos no se toca: la escala se aplica al leer la medida."""
        ...

    async def obra_visible(self, obra_id: UUID) -> bool:
        """¿La obra existe y entra en el alcance de quien consulta (RLS)?
        Para responder 404 en vez de una lista vacía que se confunde con "esta
        obra no tiene planos"."""
        ...

    async def listar_de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Planos de una obra con `n_trazos` y `n_trazos_por_revisar` (los
        trazados sobre una versión anterior del plano, MODELO.md §1b "Si el
        plano cambia")."""
        ...


@runtime_checkable
class RepositorioTrazos(Protocol):
    """Geometrías trazadas sobre un plano (`trazo`, migración 0057).

    `crear` recibe la geometría como **WKT** (MODELO.md §1b, Decisión 3 de
    3: "la secuencia de puntos se arma directo como texto WKT ... y
    `ST_GeomFromText` la convierte a geometría nativa de un solo golpe") y
    persiste el tipo nativo de PostGIS — el texto se descarta, nunca es una
    copia paralela de la fuente de verdad.
    """

    async def crear(
        self,
        *,
        plano_id: UUID,
        version_plano: int,
        capa: str | None,
        geometria_wkt: str,
        fuente: str,
        autor_id: UUID,
        grosor_m: Decimal | None = None,
        alineacion: str | None = None,
        forma: dict[str, Any] | None = None,
    ) -> UUID: ...

    async def tipo_de_geometria(self, geometria_wkt: str) -> str:
        """`ST_GeometryType` del WKT: `ST_Polygon`, `ST_LineString`, `ST_Point`..."""
        ...

    async def motivo_de_hueco_invalido(self, trazo_id: UUID, geometria_wkt: str) -> str | None:
        """Por qué ese WKT no puede ser un hueco del trazo, o `None` si puede."""
        ...

    async def crear_hueco(self, *, trazo_id: UUID, geometria_wkt: str, autor_id: UUID) -> UUID:
        """Un hueco es un trazo hijo (`hueco_de`) que resta del área del padre; sin enlaces."""
        ...

    async def motivo_de_geometria_invalida(self, geometria_wkt: str) -> str | None:
        """Por qué el WKT no sirve para medir (no es WKT, está vacío o es
        inválido —bordes que se cruzan—), o `None` si sirve. PostGIS acepta un
        polígono con bordes cruzados y mide 0: sin esta guarda el trazo sumaría
        cero en silencio."""
        ...

    async def obtener(self, trazo_id: UUID) -> dict[str, Any] | None:
        """El trazo (sin geometría) o `None` si no existe o RLS no lo deja ver."""
        ...

    async def aprobar(self, *, trazo_id: UUID, aprobador_id: UUID) -> bool:
        """Marca el trazo como aprobado **solo si aún no lo estaba**. `True` si
        esta llamada lo aprobó, `False` si ya tenía aprobación (que no se pisa:
        quién y cuándo aprobó primero es un hecho)."""
        ...

    async def de_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Trazos de un plano con su geometría ya en **GeoJSON** (dict) y
        todos sus enlaces —vigentes y reemplazados— con `medida_valor`
        calculado (MODELO.md §1b, "Cómo viaja la geometría hacia el
        frontend"). GeoJSON se genera al leer; nunca se guarda."""
        ...


@runtime_checkable
class RepositorioEnlacesCuantificacion(Protocol):
    """`enlace_cuantificacion` (migración 0057): qué nodo alimenta cada
    trazo, con qué medida y qué factor, y si sigue vigente.
    """

    async def crear(
        self,
        *,
        trazo_id: UUID,
        actividad_id: UUID | None,
        prototipo_nodo_id: UUID | None,
        medida: str,
        factor: Decimal,
        vigente: bool = True,
        matriz_concepto_id: UUID | None = None,
    ) -> UUID: ...

    async def obtener(self, enlace_id: UUID) -> dict[str, Any] | None: ...

    async def nodos_vigentes_de_trazo(self, trazo_id: UUID) -> list[dict[str, Any]]:
        """Los nodos distintos a los que enlaza, vigentes, un trazo."""
        ...

    async def marcar_no_vigente(self, enlace_id: UUID) -> None:
        """`ReemplazarEnlace`: acción explícita y manual (MODELO.md §1b,
        "depende de que quien traza reemplace el enlace a mano, nunca de
        un emparejamiento automático por cercanía espacial"). El enlace
        queda como evidencia, nunca se borra."""
        ...

    async def enlaces_de_nodo(
        self,
        *,
        tipo_nodo: str,
        actividad_id: UUID | None,
        prototipo_nodo_id: UUID | None,
        matriz_concepto_id: UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Todos los enlaces —vigentes y no vigentes— de un mismo nodo (con `matriz_concepto_id`,
        solo los de esa matriz interna de la actividad; sin él, solo los de la actividad entera), con
        su `medida_valor` ya calculado (`ST_Area`/`ST_Perimeter`/
        `ST_Length` sobre `trazo.geometria`, o `1` si `medida == 'conteo'`)
        y su `factor`, para que
        `domain.cuantificacion.reglas.cantidad_medida` sume los vigentes
        (§12.11: el cálculo con PostGIS y el filtro de vigencia están
        separados a propósito — esta consulta solo calcula, el dominio
        decide qué sumar)."""
        ...

    async def nodos_vigentes_de_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        """Los nodos distintos (`tipo_nodo`, `actividad_id`, `prototipo_nodo_id`)
        a los que enlazan, vigentes, los trazos de un plano: lo que hay que
        recalcular cuando cambia su escala (migración 0069)."""
        ...

    async def de_obra(self, obra_id: UUID) -> list[dict[str, Any]]:
        """Todos los enlaces de los planos de una obra, con la descripción y la
        cantidad base de su nodo (`actividad` o `prototipo_nodo`) y si el
        trazo quedó sobre una versión anterior del plano. Misma separación que
        `enlaces_de_nodo`: aquí solo se calcula, el dominio decide qué sumar."""
        ...


@runtime_checkable
class RepositorioNotasPlano(Protocol):
    """`nota_plano` (migración 0057): anotación sin cantidad."""

    async def crear(
        self,
        *,
        plano_id: UUID,
        version_plano: int,
        ubicacion_wkt: str,
        autor_id: UUID,
        texto: str,
        actividad_id: UUID | None,
    ) -> UUID: ...

    async def de_plano(self, plano_id: UUID) -> list[dict[str, Any]]: ...


@runtime_checkable
class RepositorioMatrices(Protocol):
    """Las matrices internas de una actividad —un insumo de la receta que es otra matriz— y su
    cantidad medida en esa obra (migración 0085; cerebro D-583)."""

    async def fijar_cantidad(
        self, *, actividad_id: UUID, concepto_id: UUID, cantidad: Decimal | None
    ) -> None:
        """Escribe la cantidad medida (derivada de los enlaces vigentes) de una matriz; `None`
        la deja sin medir."""
        ...

    async def arbol_de_actividad(self, actividad_id: UUID) -> dict[str, Any] | None:
        """`{actividad_id, concepto_clave, cant_base, precio_unitario, matrices: [...]}` con las
        matrices internas del concepto de la actividad, a cualquier profundidad, o `None` si no se
        ve. Cada matriz: `{concepto_id, padre_id, nivel, clave, descripcion, unidad, ruta,
        cantidad_unitaria, acumulada, precio_unitario, cantidad_medida}`."""
        ...
