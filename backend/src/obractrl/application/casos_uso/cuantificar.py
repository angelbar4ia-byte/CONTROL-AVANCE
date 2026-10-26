"""Casos de uso del cuantificador: `plano → medida → cantidad` (cerebro
MODELO.md §1b).

Spec §12.11 (la aplicación orquesta el dominio por puertos).

Tres casos de uso:

- `RegistrarTrazoConEnlaces` — alta de un trazo (WKT) y uno o más enlaces
  vigentes; por cada nodo que resulta, recalcula la cantidad total medida
  y la aplica según a qué mitad del NODO de cerebro apunta (ver abajo).
- `ReemplazarEnlace` — marca un enlace existente `vigente=false` y,
  opcionalmente, crea el reemplazo en la misma llamada; acción EXPLÍCITA y
  manual siempre (MODELO.md §1b: "depende de que quien traza reemplace el
  enlace a mano, nunca de un emparejamiento automático por cercanía
  espacial").
- `RegistrarNotaPlano` — alta simple, sin cantidad.

**El patrón que ninguno de los dos primeros rompe (no autocorrección):**

- `actividad_id` (obra con presupuesto ya congelado): la cantidad medida
  se COMPARA contra `actividad.cant_base`, nunca la reemplaza (mismo
  criterio que `adapters/repos/actividades_sql.py` ~línea 373, "no toca
  cant_base ni cant_ejecutada"). Si se desvía más allá del umbral
  (`domain.presupuesto.rendimiento.desviacion_de`), nace una `Desviacion`
  candidata con `causa=None` — el mismo mecanismo exacto que
  `domain.ingenieria.desviacion.generar_desviaciones_candidatas` ya usa
  para la ingeniería del lote, aplicado aquí a una medida en vez de a una
  reversión por destajo.
- `prototipo_nodo_id` (prototipo "diseño_nuevo" de un solo uso, el que
  `AplicadorIngenieriaLote._aplicar_diseno_nuevo` crea,
  `application/casos_uso/aplicar_carga.py`): ahí SÍ se sobreescribe
  `prototipo_nodo.cantidad` directo, con `modo_cantidad='medida'` — mismo
  mecanismo que esa clase ya usa para `modo_cantidad='cargada'`, reusando
  `RepositorioPrototipoNodo.actualizar_cantidad` sin tocarlo.

**Decisión de diseño no dada 100% explícita por el encargo — gobierno del
camino `prototipo_nodo`:** la política RLS de `prototipo_nodo` (migración
0012) exige `app.es_config()` —Control de obra o Super intendente— para
cualquier `UPDATE`, porque es una tabla de catálogo compartida por muchas
obras, no una tabla operativa de una sola obra. Cerebro dice "trazar:
Costos·Control·Residente·Supervisor" sin distinguir a qué nodo apunta el
trazo; aquí un Residente o Supervisor SÍ puede trazar y enlazar contra una
`actividad` (su obra), pero NO contra un `prototipo_nodo` —la base
rechazaría el `UPDATE` de cualquier forma—. En vez de dejar que eso falle
como un error de permisos opaco a medio camino (el trazo y el enlace ya
insertados, la reclasificación silenciosamente sin efecto), este módulo lo
valida ANTES de escribir nada y lo nombra con un error de dominio claro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    ObraNoEncontrada,
)
from obractrl.application.puertos.cuantificacion import (
    RepositorioEnlacesCuantificacion,
    RepositorioNotasPlano,
    RepositorioPlanos,
    RepositorioTrazos,
)
from obractrl.application.puertos.repositorios import (
    RepositorioActividades,
    RepositorioDesviaciones,
    RepositorioPrototipoNodo,
    UnidadDeTrabajo,
)
from obractrl.domain.cuantificacion.reglas import (
    EnlaceCuantificacion,
    ErrorDeCuantificacion,
    MedidaDeEnlace,
    cantidad_medida,
)
from obractrl.domain.desviacion.desviacion import Desviacion
from obractrl.domain.presupuesto.rendimiento import UMBRAL_DESVIACION, desviacion_de
from obractrl.domain.shared.diccionario import (
    MedidaCuantificacion,
    Rol,
    TipoDesviacion,
    TipoNodoCuantificacion,
)

__all__ = [
    "ComandoReemplazarEnlace",
    "ComandoRegistrarNotaPlano",
    "ComandoRegistrarTrazo",
    "ConsultarCuantificacion",
    "EnlaceNoEncontrado",
    "ErrorDeCuantificacion",
    "GobiernoDeCuantificacionInvalido",
    "IntencionEnlace",
    "NodoCuantificado",
    "NotaPlanoRegistrada",
    "NuevoEnlace",
    "PlanoNoEncontrado",
    "ReemplazarEnlace",
    "RegistrarNotaPlano",
    "RegistrarPlano",
    "RegistrarTrazoConEnlaces",
    "ResultadoDeRecalculo",
    "TrazoRegistrado",
]

_ROLES_QUE_TOCAN_PROTOTIPO = (Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)
"""Quién puede enlazar contra un `prototipo_nodo` (ver docstring del
módulo): los mismos dos roles que `app.es_config()` ya exige para
escribir cualquier catálogo compartido (migración 0011/0012) — esta lista
no inventa un gobierno nuevo, solo lo hace explícito antes de que la base
lo rechace a medio camino."""


class GobiernoDeCuantificacionInvalido(ValueError):
    """Un rol sin permiso de catálogo intentó enlazar contra un
    `prototipo_nodo` (ver docstring del módulo, gobierno del camino
    `prototipo_nodo`)."""


class EnlaceNoEncontrado(LookupError):
    """El enlace a reemplazar no existe o salió del alcance (RLS)."""


class PlanoNoEncontrado(LookupError):
    """El plano no existe o salió del alcance (RLS): indistinguibles a
    propósito (§12.4)."""


@dataclass(frozen=True, slots=True)
class IntencionEnlace:
    """Un enlace querido por quien traza, antes de persistir — exactamente
    uno de `actividad_id`/`prototipo_nodo_id`, validado por
    `domain.cuantificacion.reglas.EnlaceCuantificacion` en cuanto el
    `trazo_id` existe."""

    medida: MedidaCuantificacion
    factor: Decimal
    actividad_id: UUID | None = None
    prototipo_nodo_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComandoRegistrarTrazo:
    plano_id: UUID
    version_plano: int
    capa: str | None
    fuente: str
    geometria_wkt: str
    autor_id: UUID
    rol: Rol
    enlaces: tuple[IntencionEnlace, ...] = ()


@dataclass(frozen=True, slots=True)
class ResultadoDeRecalculo:
    """Lo que `_recalcular_nodo` hizo con la cantidad total de un nodo —a
    lo sumo una de las dos, nunca las dos (ver docstring del módulo)."""

    cantidad_total: Decimal
    desviacion_id: UUID | None = None
    prototipo_nodo_actualizado: UUID | None = None


@dataclass(frozen=True, slots=True)
class TrazoRegistrado:
    trazo_id: UUID
    enlace_ids: tuple[UUID, ...]
    recalculos: tuple[ResultadoDeRecalculo, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class NuevoEnlace:
    """El reemplazo, cuando `ReemplazarEnlace` lo crea en la misma
    llamada. Apunta a un trazo YA registrado —nunca dibuja uno nuevo, eso
    es `RegistrarTrazoConEnlaces`— y hereda el nodo del enlace que
    reemplaza: reemplazar es sobre la MISMA instancia física (MODELO.md
    §1b), nunca una forma de mover la medida a otro nodo."""

    trazo_id: UUID
    medida: MedidaCuantificacion
    factor: Decimal


@dataclass(frozen=True, slots=True)
class ComandoReemplazarEnlace:
    enlace_id: UUID
    rol: Rol
    nuevo: NuevoEnlace | None = None


@dataclass(frozen=True, slots=True)
class ComandoRegistrarNotaPlano:
    plano_id: UUID
    version_plano: int
    ubicacion_wkt: str
    autor_id: UUID
    texto: str
    actividad_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class NotaPlanoRegistrada:
    nota_id: UUID


def _exigir_gobierno(rol: Rol, intenciones: tuple[IntencionEnlace, ...] | tuple[()]) -> None:
    apunta_a_prototipo = any(i.prototipo_nodo_id is not None for i in intenciones)
    if apunta_a_prototipo and rol not in _ROLES_QUE_TOCAN_PROTOTIPO:
        permitidos = ", ".join(r.value for r in _ROLES_QUE_TOCAN_PROTOTIPO)
        raise GobiernoDeCuantificacionInvalido(
            f"Enlazar contra un prototipo_nodo (camino 'diseño_nuevo') exige "
            f"{permitidos}: el rol {rol.value!r} no puede — "
            f"`prototipo_nodo` es un catálogo compartido y su UPDATE ya "
            f"exige ese mismo gobierno (migración 0011/0012)."
        )


def _desviacion_a_datos(d: Desviacion) -> dict[str, object]:
    return {
        "insumo_id": d.insumo_id,
        "concepto_id": d.concepto_id,
        "obra_id": d.obra_id,
        "tipo": str(d.tipo),
        "monto": d.monto,
        "cantidad_plan": d.cantidad_plan,
        "cantidad_real": d.cantidad_real,
        "precio_plan": d.precio_plan,
        "precio_real": d.precio_real,
        "detectada_en": d.detectada_en,
    }


async def _recalcular_nodo(
    *,
    tipo_nodo: TipoNodoCuantificacion,
    actividad_id: UUID | None,
    prototipo_nodo_id: UUID | None,
    enlaces: RepositorioEnlacesCuantificacion,
    actividades: RepositorioActividades,
    prototipo_nodos: RepositorioPrototipoNodo,
    desviaciones: RepositorioDesviaciones,
    detectada_en: datetime,
    umbral: Decimal = UMBRAL_DESVIACION,
) -> ResultadoDeRecalculo:
    """Suma la cantidad vigente del nodo y aplica la consecuencia que le
    toca (ver docstring del módulo) — compartido por
    `RegistrarTrazoConEnlaces` y `ReemplazarEnlace` para no duplicar esta
    secuencia en los dos."""
    filas = await enlaces.enlaces_de_nodo(
        tipo_nodo=tipo_nodo.value,
        actividad_id=actividad_id,
        prototipo_nodo_id=prototipo_nodo_id,
    )
    medidas = tuple(
        MedidaDeEnlace(
            medida_valor=Decimal(str(fila["medida_valor"])),
            factor=Decimal(str(fila["factor"])),
            vigente=bool(fila["vigente"]),
        )
        for fila in filas
    )
    cantidad_total = cantidad_medida(medidas)

    if tipo_nodo is TipoNodoCuantificacion.ACTIVIDAD:
        actividad = await actividades.obtener(actividad_id)  # type: ignore[arg-type]
        # Sin fila o sin concepto de catálogo (actividad extra-catálogo,
        # §5.1) no hay con qué construir una `Desviacion` válida —exige
        # `concepto_id`, §3.3 lo resuelve el borde— así que no se levanta
        # ningún error: simplemente no hay nada que proponer todavía.
        if actividad is None or actividad.get("concepto_id") is None:
            return ResultadoDeRecalculo(cantidad_total=cantidad_total)

        cant_base = Decimal(str(actividad["cant_base"]))
        precio = Decimal(str(actividad["precio_unitario"]))
        medida_desv = desviacion_de(
            importe_presupuestado=cant_base * precio,
            importe_ejecutado=cantidad_total * precio,
            umbral=umbral,
        )
        if not medida_desv.relevante:
            return ResultadoDeRecalculo(cantidad_total=cantidad_total)

        desviacion = Desviacion(
            insumo_id=None,
            concepto_id=str(actividad["concepto_id"]),
            obra_id=str(actividad["obra_id"]),
            tipo=TipoDesviacion.CONSUMO,
            monto=medida_desv.importe,
            cantidad_plan=cant_base,
            cantidad_real=cantidad_total,
            precio_plan=None,
            precio_real=None,
            detectada_en=detectada_en,
            causa=None,
        )
        desviacion_id = await desviaciones.crear(_desviacion_a_datos(desviacion))
        return ResultadoDeRecalculo(
            cantidad_total=cantidad_total, desviacion_id=desviacion_id
        )

    # prototipo_nodo: se sobreescribe directo (ver docstring del módulo).
    nodo = await prototipo_nodos.obtener(prototipo_nodo_id)  # type: ignore[arg-type]
    if nodo is None:
        return ResultadoDeRecalculo(cantidad_total=cantidad_total)

    actualizado = await prototipo_nodos.actualizar_cantidad(
        UUID(str(nodo["prototipo_id"])),
        parent_id=UUID(str(nodo["parent_id"])) if nodo.get("parent_id") else None,
        clave=str(nodo["clave"]),
        cantidad=cantidad_total,
        modo_cantidad="medida",
    )
    return ResultadoDeRecalculo(
        cantidad_total=cantidad_total,
        prototipo_nodo_actualizado=(
            UUID(str(nodo["id"])) if actualizado is not None else None
        ),
    )


class RegistrarTrazoConEnlaces:
    """Alta de un trazo (WKT) con uno o más enlaces vigentes (MODELO.md
    §1b: "un trazo, varios enlaces")."""

    def __init__(
        self,
        *,
        trazos: RepositorioTrazos,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._trazos = trazos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow

    async def ejecutar(
        self, cmd: ComandoRegistrarTrazo, *, detectada_en: datetime
    ) -> TrazoRegistrado:
        _exigir_gobierno(cmd.rol, cmd.enlaces)

        async with self._uow:
            trazo_id = await self._trazos.crear(
                plano_id=cmd.plano_id,
                version_plano=cmd.version_plano,
                capa=cmd.capa,
                geometria_wkt=cmd.geometria_wkt,
                fuente=cmd.fuente,
                autor_id=cmd.autor_id,
            )

            enlace_ids: list[UUID] = []
            nodos_tocados: dict[
                tuple[TipoNodoCuantificacion, UUID | None, UUID | None], None
            ] = {}
            for intencion in cmd.enlaces:
                # Valida exclusividad de nodo, factor positivo y la
                # coherencia de conteo ANTES de escribir — mismo criterio
                # que el resto del repo (§12.11: el dominio decide, el
                # repo solo ejecuta).
                validado = EnlaceCuantificacion(
                    trazo_id=str(trazo_id),
                    actividad_id=(
                        str(intencion.actividad_id) if intencion.actividad_id else None
                    ),
                    prototipo_nodo_id=(
                        str(intencion.prototipo_nodo_id)
                        if intencion.prototipo_nodo_id
                        else None
                    ),
                    medida=intencion.medida,
                    factor=intencion.factor,
                )
                enlace_id = await self._enlaces.crear(
                    trazo_id=trazo_id,
                    actividad_id=intencion.actividad_id,
                    prototipo_nodo_id=intencion.prototipo_nodo_id,
                    medida=validado.medida.value,
                    factor=validado.factor,
                )
                enlace_ids.append(enlace_id)
                nodos_tocados[
                    (validado.tipo_nodo, intencion.actividad_id, intencion.prototipo_nodo_id)
                ] = None

            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=tipo_nodo,
                        actividad_id=actividad_id,
                        prototipo_nodo_id=prototipo_nodo_id,
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                    )
                    for (tipo_nodo, actividad_id, prototipo_nodo_id) in nodos_tocados
                ]
            )

            await self._uow.commit()

        return TrazoRegistrado(
            trazo_id=trazo_id, enlace_ids=tuple(enlace_ids), recalculos=recalculos
        )


class ReemplazarEnlace:
    """Marca un enlace `vigente=false` y, opcionalmente, crea el
    reemplazo vigente en la misma llamada (MODELO.md §1b): acción
    EXPLÍCITA y manual, nunca un emparejamiento automático por cercanía
    espacial."""

    def __init__(
        self,
        *,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow

    async def ejecutar(
        self, cmd: ComandoReemplazarEnlace, *, detectada_en: datetime
    ) -> ResultadoDeRecalculo:
        anterior = await self._enlaces.obtener(cmd.enlace_id)
        if anterior is None:
            raise EnlaceNoEncontrado(
                f"El enlace {cmd.enlace_id} no existe o está fuera de tu alcance."
            )

        tipo_nodo = TipoNodoCuantificacion(str(anterior["tipo_nodo"]))
        actividad_id = anterior["actividad_id"]
        prototipo_nodo_id = anterior["prototipo_nodo_id"]

        if (
            tipo_nodo is TipoNodoCuantificacion.PROTOTIPO_NODO
            and cmd.rol not in _ROLES_QUE_TOCAN_PROTOTIPO
        ):
            permitidos = ", ".join(r.value for r in _ROLES_QUE_TOCAN_PROTOTIPO)
            raise GobiernoDeCuantificacionInvalido(
                f"Reemplazar un enlace de prototipo_nodo exige {permitidos}: "
                f"el rol {cmd.rol.value!r} no puede."
            )

        async with self._uow:
            await self._enlaces.marcar_no_vigente(cmd.enlace_id)

            if cmd.nuevo is not None:
                # Valida factor/medida del reemplazo — el nodo lo hereda
                # del enlace anterior, nunca lo re-declara (ver docstring
                # de `NuevoEnlace`).
                EnlaceCuantificacion(
                    trazo_id=str(cmd.nuevo.trazo_id),
                    actividad_id=str(actividad_id) if actividad_id else None,
                    prototipo_nodo_id=(
                        str(prototipo_nodo_id) if prototipo_nodo_id else None
                    ),
                    medida=cmd.nuevo.medida,
                    factor=cmd.nuevo.factor,
                )
                await self._enlaces.crear(
                    trazo_id=cmd.nuevo.trazo_id,
                    actividad_id=actividad_id,
                    prototipo_nodo_id=prototipo_nodo_id,
                    medida=cmd.nuevo.medida.value,
                    factor=cmd.nuevo.factor,
                )

            resultado = await _recalcular_nodo(
                tipo_nodo=tipo_nodo,
                actividad_id=actividad_id,
                prototipo_nodo_id=prototipo_nodo_id,
                enlaces=self._enlaces,
                actividades=self._actividades,
                prototipo_nodos=self._prototipo_nodos,
                desviaciones=self._desviaciones,
                detectada_en=detectada_en,
            )

            await self._uow.commit()

        return resultado


class RegistrarNotaPlano:
    """Alta simple de una anotación sobre el plano (MODELO.md §1b): nunca
    produce cantidad, nunca tiene enlace."""

    def __init__(self, *, notas: RepositorioNotasPlano, uow: UnidadDeTrabajo) -> None:
        self._notas = notas
        self._uow = uow

    async def ejecutar(self, cmd: ComandoRegistrarNotaPlano) -> NotaPlanoRegistrada:
        texto = cmd.texto.strip()
        if not texto:
            raise ErrorDeCuantificacion(
                "La nota necesita texto: nota_plano.texto es not null "
                "(MODELO.md §1b)."
            )

        async with self._uow:
            nota_id = await self._notas.crear(
                plano_id=cmd.plano_id,
                version_plano=cmd.version_plano,
                ubicacion_wkt=cmd.ubicacion_wkt,
                autor_id=cmd.autor_id,
                texto=texto,
                actividad_id=cmd.actividad_id,
            )
            await self._uow.commit()

        return NotaPlanoRegistrada(nota_id=nota_id)


class RegistrarPlano:
    """Alta de metadatos de un plano (MODELO.md §1b, hueco 1 de la
    cabecera de la migración 0057): el archivo ya está subido a R2 con
    `POST /evidencias/presigned`, mismo patrón que
    `application.casos_uso.gestionar_expediente.AgregarDocumento`."""

    def __init__(self, *, planos: RepositorioPlanos, uow: UnidadDeTrabajo) -> None:
        self._planos = planos
        self._uow = uow

    async def ejecutar(
        self,
        *,
        obra_id: UUID,
        nombre: str,
        archivo_url: str,
        version: int,
        capas: list[str] | None,
        subido_por: UUID,
    ) -> UUID:
        nombre_limpio = nombre.strip()
        if not nombre_limpio:
            raise ErrorDeCuantificacion(
                "El plano necesita un nombre: plano.nombre es not null "
                "(MODELO.md §1b)."
            )
        url_limpia = archivo_url.strip()
        if not url_limpia:
            raise ErrorDeCuantificacion(
                "El plano necesita la clave del objeto ya subido a R2; "
                "plano.archivo_url es not null (§12.2)."
            )
        if version <= 0:
            raise ErrorDeCuantificacion("La version de un plano debe ser positiva.")

        async with self._uow:
            plano_id = await self._planos.crear(
                obra_id=obra_id,
                nombre=nombre_limpio,
                archivo_url=url_limpia,
                version=version,
                capas=capas,
                subido_por=subido_por,
            )
            await self._uow.commit()

        return plano_id


@dataclass(frozen=True, slots=True)
class NodoCuantificado:
    """Cómo va la cuantificación de un nodo (`actividad` o `prototipo_nodo`).

    `cant_base` es lo que el presupuesto trae para ese nodo y `cantidad_medida`
    lo que suman sus enlaces vigentes; la diferencia **informa**, no corrige:
    sobre una actividad la medida se compara y nunca reemplaza a `cant_base`
    (migración 0057, hueco 2).
    """

    tipo_nodo: str
    nodo_id: UUID
    descripcion: str | None
    cant_base: Decimal | None
    cantidad_medida: Decimal
    enlaces_vigentes: int
    enlaces_reemplazados: int
    trazos_por_revisar: int
    """Enlaces vigentes cuyo trazo se hizo sobre una versión anterior del
    plano: su cantidad **no** se recalculó sola (MODELO.md §1b)."""

    @property
    def diferencia(self) -> Decimal | None:
        if self.cant_base is None:
            return None
        return self.cantidad_medida - self.cant_base


class ConsultarCuantificacion:
    """Lecturas del cuantificador: planos de una obra, los trazos de un plano
    como GeoJSON y cómo va la cuantificación nodo por nodo.

    **Lectura abierta a quien tiene acceso a la obra** (MODELO.md §1b: "ver
    cómo está cuantificada la obra ... es lectura, no un permiso aparte"): no
    hay guarda de rol; el alcance lo impone RLS (§12.4).
    """

    def __init__(
        self,
        *,
        planos: RepositorioPlanos,
        trazos: RepositorioTrazos,
        enlaces: RepositorioEnlacesCuantificacion,
        notas: RepositorioNotasPlano,
    ) -> None:
        self._planos = planos
        self._trazos = trazos
        self._enlaces = enlaces
        self._notas = notas

    async def planos_de_obra(self, obra_id: UUID) -> list[dict]:
        await self._exigir_obra(obra_id)
        return await self._planos.listar_de_obra(obra_id)

    async def trazos_de_plano(self, plano_id: UUID) -> tuple[dict, list[dict]]:
        """`(plano, trazos)`; cada trazo trae su geometría GeoJSON y sus
        enlaces con `medida_valor`."""
        plano = await self._planos.obtener(plano_id)
        if plano is None:
            raise PlanoNoEncontrado(
                f"El plano {plano_id} no existe o no está en tu alcance."
            )
        return plano, await self._trazos.de_plano(plano_id)

    async def notas_de_plano(self, plano_id: UUID) -> list[dict]:
        """Las notas del plano; leerlas no pide rol (solo anotar lo pide)."""
        if await self._planos.obtener(plano_id) is None:
            raise PlanoNoEncontrado(
                f"El plano {plano_id} no existe o no está en tu alcance."
            )
        return await self._notas.de_plano(plano_id)

    async def estado_de_obra(self, obra_id: UUID) -> list[NodoCuantificado]:
        await self._exigir_obra(obra_id)
        filas = await self._enlaces.de_obra(obra_id)

        por_nodo: dict[tuple[str, UUID], list[dict]] = {}
        for fila in filas:
            nodo_id = fila["actividad_id"] or fila["prototipo_nodo_id"]
            por_nodo.setdefault((str(fila["tipo_nodo"]), nodo_id), []).append(fila)

        nodos: list[NodoCuantificado] = []
        for (tipo_nodo, nodo_id), enlaces in por_nodo.items():
            vigentes = [e for e in enlaces if e["vigente"]]
            primero = enlaces[0]
            nodos.append(
                NodoCuantificado(
                    tipo_nodo=tipo_nodo,
                    nodo_id=nodo_id,
                    descripcion=primero["descripcion"],
                    cant_base=(
                        Decimal(str(primero["cant_base"]))
                        if primero["cant_base"] is not None
                        else None
                    ),
                    # El dominio suma; el SQL solo midió (§12.11).
                    cantidad_medida=cantidad_medida(
                        [
                            MedidaDeEnlace(
                                medida_valor=Decimal(str(e["medida_valor"])),
                                factor=Decimal(str(e["factor"])),
                                vigente=bool(e["vigente"]),
                            )
                            for e in enlaces
                        ]
                    ),
                    enlaces_vigentes=len(vigentes),
                    enlaces_reemplazados=len(enlaces) - len(vigentes),
                    trazos_por_revisar=sum(1 for e in vigentes if e["por_revisar"]),
                )
            )
        return nodos

    async def _exigir_obra(self, obra_id: UUID) -> None:
        if not await self._planos.obra_visible(obra_id):
            raise ObraNoEncontrada(
                f"La obra {obra_id} no existe o no está en tu alcance."
            )
