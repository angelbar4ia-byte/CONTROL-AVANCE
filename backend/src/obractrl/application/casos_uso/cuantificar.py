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

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.capturar_avance import ActividadNoEncontrada
from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    ObraNoEncontrada,
)
from obractrl.application.eventos import PartesCambiaronDeEstado, PublicadorEventos
from obractrl.application.puertos.cuantificacion import (
    RepositorioEnlacesCuantificacion,
    RepositorioMatrices,
    RepositorioMediciones,
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
from obractrl.domain.cuantificacion.conversion import (
    CAMPOS_POR_MODO,
    MODOS_POR_TIPO,
    coincide_la_unidad,
    conversion_por_defecto,
    formula_en_texto,
    medida_natural,
    normalizar_conversion,
)
from obractrl.domain.cuantificacion.escala import escala_desde_referencia
from obractrl.domain.cuantificacion.matriz import NodoDeMatriz, ajuste_por_medicion
from obractrl.domain.cuantificacion.medicion import motivo_de_incompatibilidad
from obractrl.domain.cuantificacion.muro import (
    ParteDeAltura,
    altura_efectiva,
    factor_de_muro,
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
    "AgregarHuecoATrazo",
    "CalibrarEscalaDePlano",
    "ComandoAgregarHueco",
    "ComandoAgregarVano",
    "ComandoCalibrarEscala",
    "ComandoEliminarTrazo",
    "ComandoFijarVistaDePlano",
    "ComandoReemplazarEnlace",
    "ComandoRegistrarNotaPlano",
    "ComandoRegistrarTrazo",
    "ComandoTransformarTrazos",
    "ConsultarCuantificacion",
    "ConversionDelEnlace",
    "EliminarTrazo",
    "EnlaceNoEncontrado",
    "ErrorDeCuantificacion",
    "EscalaCalibrada",
    "FijarVistaDePlano",
    "GestionarVanos",
    "GobiernoDeCuantificacionInvalido",
    "HuecoAgregado",
    "IntencionEnlace",
    "NodoCuantificado",
    "NotaPlanoRegistrada",
    "NuevoEnlace",
    "PlanoNoEncontrado",
    "QuitarHueco",
    "ReemplazarEnlace",
    "RegistrarNotaPlano",
    "RegistrarPlano",
    "RegistrarTrazoConEnlaces",
    "ResultadoDeRecalculo",
    "TransformarTrazos",
    "TrazoEliminado",
    "TrazoRegistrado",
    "TrazoTransformado",
    "VanoCambiado",
]

RADIO_DE_UNION_M = Decimal("0.5")
"""A cuántos metros de un extremo se considera que otro muro se encuentra con él."""

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


class TrazoNoEncontrado(LookupError):
    """El trazo no existe o salió del alcance (RLS): indistinguibles a propósito
    (§12.4)."""


class MedicionNoEncontrada(LookupError):
    """La medición no existe o salió del alcance (RLS): indistinguibles a propósito (§12.4)."""


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
    matriz_concepto_id: UUID | None = None
    """Si se mide una matriz interna de la actividad (nervaduras, trabes…) y no la actividad
    entera (D-583). Solo con `actividad_id`."""


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
    grosor_m: Decimal | None = None
    """Grosor en metros de una **línea** (un muro): su área es largo × grosor (0086)."""
    alineacion: str | None = None
    """De qué lado del eje queda el cuerpo de la línea: centro, izquierda o derecha."""
    forma: dict[str, Any] | None = None
    """Plantilla con la que se estampó un **polígono** que nació de un punto con forma."""
    medicion_id: UUID | None = None
    """La medición a la que entra el trazo (0088): hereda los enlaces de su medición y de las que la contienen."""
    pendiente_pct: Decimal | None = None
    """Pendiente en % de una **línea** inclinada: su longitud real es la de la planta × √(1 + p²) (0087)."""


@dataclass(frozen=True, slots=True)
class ComandoAgregarHueco:
    trazo_id: UUID
    geometria_wkt: str
    autor_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoAgregarVano:
    trazo_id: UUID
    clave: str
    tipo: str
    ancho_m: Decimal
    alto_m: Decimal
    antepecho_m: Decimal
    piezas: int
    posicion_m: Decimal | None
    autor_id: UUID
    rol: Rol
    lado_muro: int = 0


@dataclass(frozen=True, slots=True)
class VanoCambiado:
    vano_id: UUID
    recalculos: tuple[Any, ...]


@dataclass(frozen=True, slots=True)
class ComandoEliminarTrazo:
    trazo_id: UUID
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class ComandoTransformarTrazos:
    """Mover `(dx, dy)` o girar `grados` (positivo de +x hacia +y, en el sistema del plano)."""

    trazo_ids: tuple[UUID, ...]
    usuario_id: UUID
    rol: Rol
    dx: Decimal = Decimal(0)
    dy: Decimal = Decimal(0)
    grados: Decimal = Decimal(0)
    pivote: tuple[Decimal, Decimal] | None = None


@dataclass(frozen=True, slots=True)
class TrazoTransformado:
    trazo_id: UUID
    pivote: tuple[Decimal, Decimal] | None


@dataclass(frozen=True, slots=True)
class TrazoEliminado:
    trazo_id: UUID
    recalculos: tuple[ResultadoDeRecalculo, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class HuecoAgregado:
    hueco_id: UUID
    recalculos: tuple[ResultadoDeRecalculo, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ResultadoDeRecalculo:
    """Lo que `_recalcular_nodo` hizo con la cantidad total de un nodo —a
    lo sumo una de las dos, nunca las dos (ver docstring del módulo)."""

    cantidad_total: Decimal
    desviacion_id: UUID | None = None
    prototipo_nodo_actualizado: UUID | None = None
    reapertura: tuple[UUID, str, bool] | None = None
    """`(obra, parte, tenía_programa)`: medir devolvió a cuantificarse una parte ya validada."""


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
    conversion: dict[str, Any] | None = None
    """Cómo cuenta el trazo para el concepto (D-633): con ella el factor es 1 y la cantidad la calcula la base."""


@dataclass(frozen=True, slots=True)
class ComandoReemplazarEnlace:
    enlace_id: UUID
    rol: Rol
    nuevo: NuevoEnlace | None = None
    usuario_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComandoRegistrarNotaPlano:
    plano_id: UUID
    version_plano: int
    ubicacion_wkt: str
    autor_id: UUID
    texto: str
    actividad_id: UUID | None = None
    tipo: str = "nota"
    """`nota`, `texto`, `flecha` o `llamada` (0087)."""
    destino_wkt: str | None = None
    """A dónde apunta una `flecha` o una `llamada`."""


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


async def _avisar_reaperturas(
    eventos: PublicadorEventos | None,
    recalculos: Sequence[ResultadoDeRecalculo],
    usuario_id: UUID | None,
) -> None:
    """Medir puede devolver a cuantificarse una parte ya validada: se avisa igual que cuando la
    devuelve una modificación (D-571), a quien lleva el programa."""
    if eventos is None:
        return
    for r in recalculos:
        if r.reapertura is None:
            continue
        obra_id, clave, tenia_programa = r.reapertura
        await eventos.publicar(
            PartesCambiaronDeEstado(
                obra_id=obra_id,
                accion="devolver",
                claves=(clave,),
                estados=("cuantificando",),
                usuario_id=usuario_id,
                programa_por_revisar=(clave,) if tenia_programa else (),
            )
        )


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
    matriz_concepto_id: UUID | None = None,
    matrices: RepositorioMatrices | None = None,
    proponer_desviacion: bool = True,
) -> ResultadoDeRecalculo:
    """Suma la cantidad vigente del nodo y aplica la consecuencia que le
    toca (ver docstring del módulo) — compartido por
    `RegistrarTrazoConEnlaces` y `ReemplazarEnlace` para no duplicar esta
    secuencia en los dos."""
    filas = await enlaces.enlaces_de_nodo(
        tipo_nodo=tipo_nodo.value,
        actividad_id=actividad_id,
        prototipo_nodo_id=prototipo_nodo_id,
        matriz_concepto_id=matriz_concepto_id,
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

    if matriz_concepto_id is not None:
        # Una matriz interna de la actividad (nervaduras, trabes…, D-583): su cantidad es de esta
        # obra y no reescribe ni la cantidad de la actividad ni el catálogo. Se guarda derivada.
        if matrices is not None:
            # Sin ningún enlace vigente la matriz vuelve a estar sin medir (no «medida en cero»).
            await matrices.fijar_cantidad(
                actividad_id=actividad_id,  # type: ignore[arg-type]
                concepto_id=matriz_concepto_id,
                cantidad=cantidad_total if any(m.vigente for m in medidas) else None,
            )
        return ResultadoDeRecalculo(cantidad_total=cantidad_total)

    if tipo_nodo is TipoNodoCuantificacion.ACTIVIDAD:
        actividad = await actividades.obtener(actividad_id)  # type: ignore[arg-type]
        # En una obra «Nueva» lo que se mide es el presupuesto: sustituye a la cantidad base
        # (0081). En las demás solo se compara.
        sustituida = (
            await actividades.fijar_cantidad_medida(
                actividad_id,  # type: ignore[arg-type]
                cantidad_total,
            )
            if actividad is not None
            else None
        )
        if sustituida is not None:
            return ResultadoDeRecalculo(
                cantidad_total=cantidad_total,
                reapertura=(
                    (UUID(str(sustituida["obra_id"])), sustituida["clave"], sustituida["tenia_programa"])
                    if sustituida["reabierta"]
                    else None
                ),
            )
        # Sin fila o sin concepto de catálogo (actividad extra-catálogo,
        # §5.1) no hay con qué construir una `Desviacion` válida —exige
        # `concepto_id`, §3.3 lo resuelve el borde— así que no se levanta
        # ningún error: simplemente no hay nada que proponer todavía.
        if actividad is None or actividad.get("concepto_id") is None:
            return ResultadoDeRecalculo(cantidad_total=cantidad_total)

        # Al borrar el último trazo del nodo la cantidad vuelve a «sin medir»: eso no es una
        # desviación de -100 %, es que ya no hay medida con qué comparar.
        if not proponer_desviacion:
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


#: Un nodo que hay que recalcular: (actividad, matriz).
NodoActividad = tuple[UUID, UUID | None]


async def aplicar_asignaciones_a_trazo(
    *,
    trazo_id: UUID,
    medicion_id: UUID,
    mediciones: RepositorioMediciones,
    enlaces: RepositorioEnlacesCuantificacion,
) -> set[NodoActividad]:
    """Crea los enlaces que le tocan a un trazo por estar en una medición: los de ella y los de las
    que la contienen. No repite un enlace que el trazo ya tiene. Devuelve los nodos que tocó."""
    tocados: set[NodoActividad] = set()
    asignaciones = await mediciones.asignaciones_de(await mediciones.con_ancestros(medicion_id))
    for a in asignaciones:
        if await mediciones.enlace_vigente_equivalente(
            trazo_id=trazo_id,
            actividad_id=a["actividad_id"],
            matriz_concepto_id=a["matriz_concepto_id"],
            medida=a["medida"],
        ):
            continue
        validado = EnlaceCuantificacion(
            trazo_id=str(trazo_id),
            actividad_id=str(a["actividad_id"]),
            prototipo_nodo_id=None,
            medida=MedidaCuantificacion(a["medida"]),
            factor=Decimal(str(a["factor"])),
            matriz_concepto_id=str(a["matriz_concepto_id"]) if a["matriz_concepto_id"] else None,
            derivado=bool(a.get("usa_peso")),
        )
        await enlaces.crear(
            trazo_id=trazo_id,
            actividad_id=a["actividad_id"],
            prototipo_nodo_id=None,
            matriz_concepto_id=a["matriz_concepto_id"],
            medida=validado.medida.value,
            factor=validado.factor,
            asignacion_id=a["id"],
        )
        tocados.add((a["actividad_id"], a["matriz_concepto_id"]))
    return tocados


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
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
        mediciones: RepositorioMediciones | None = None,
    ) -> None:
        self._trazos = trazos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices
        self._mediciones = mediciones

    async def ejecutar(
        self, cmd: ComandoRegistrarTrazo, *, detectada_en: datetime
    ) -> TrazoRegistrado:
        _exigir_gobierno(cmd.rol, cmd.enlaces)

        # Antes de abrir la transacción: una geometría inválida se rechaza con un
        # motivo legible, no se acepta para medir cero ni revienta como un 500.
        motivo = await self._trazos.motivo_de_geometria_invalida(cmd.geometria_wkt)
        if motivo is not None:
            raise ErrorDeCuantificacion(f"El trazo no se puede medir. {motivo}")

        # El grosor es de una línea y la forma de un polígono: en otra geometría no
        # significan nada y se rechazan en vez de guardarse callados.
        tipo = await self._trazos.tipo_de_geometria(cmd.geometria_wkt)
        if (cmd.grosor_m is not None or cmd.alineacion is not None) and tipo != "ST_LineString":
            raise ErrorDeCuantificacion("El grosor y la alineación son de una línea (un muro).")
        if (cmd.grosor_m is None) != (cmd.alineacion is None):
            raise ErrorDeCuantificacion("El grosor y la alineación van juntos.")
        if cmd.forma is not None and tipo != "ST_Polygon":
            raise ErrorDeCuantificacion("La forma es de un trazo cerrado (un polígono).")
        if cmd.pendiente_pct is not None:
            if tipo != "ST_LineString":
                raise ErrorDeCuantificacion("La pendiente es de una línea (un tramo inclinado).")
            if cmd.pendiente_pct <= 0:
                raise ErrorDeCuantificacion("La pendiente debe ser mayor que cero.")
        if cmd.medicion_id is not None:
            if self._mediciones is None:
                raise ErrorDeCuantificacion("Las mediciones no están disponibles.")
            medicion = await self._mediciones.obtener(cmd.medicion_id)
            if medicion is None:
                raise MedicionNoEncontrada(f"La medición {cmd.medicion_id} no existe o está fuera de tu alcance.")
            if medicion["plano_id"] != cmd.plano_id:
                raise ErrorDeCuantificacion("La medición es de otro plano.")
            motivo_medicion = motivo_de_incompatibilidad(medicion["tipo"], tipo, cmd.forma is not None)
            if motivo_medicion is not None:
                raise ErrorDeCuantificacion(motivo_medicion)

        async with self._uow:
            trazo_id = await self._trazos.crear(
                plano_id=cmd.plano_id,
                version_plano=cmd.version_plano,
                capa=cmd.capa,
                geometria_wkt=cmd.geometria_wkt,
                fuente=cmd.fuente,
                autor_id=cmd.autor_id,
                grosor_m=cmd.grosor_m,
                alineacion=cmd.alineacion,
                forma=cmd.forma,
                pendiente_pct=cmd.pendiente_pct,
            )

            enlace_ids: list[UUID] = []
            nodos_tocados: dict[
                tuple[TipoNodoCuantificacion, UUID | None, UUID | None, UUID | None], None
            ] = {}
            for intencion in cmd.enlaces:
                # Valida exclusividad de nodo, factor positivo y la
                # coherencia de conteo ANTES de escribir — mismo criterio
                # que el resto del repo (§12.11: el dominio decide, el
                # repo solo ejecuta).
                if intencion.matriz_concepto_id is not None and self._matrices is not None:
                    arbol = await self._matrices.arbol_de_actividad(intencion.actividad_id)  # type: ignore[arg-type]
                    if arbol is None or intencion.matriz_concepto_id not in {
                        m["concepto_id"] for m in arbol["matrices"]
                    }:
                        raise ErrorDeCuantificacion(
                            "Esa no es una matriz interna del concepto de la actividad: solo se "
                            "miden las que su receta contiene (D-583)."
                        )
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
                    matriz_concepto_id=(
                        str(intencion.matriz_concepto_id) if intencion.matriz_concepto_id else None
                    ),
                )
                enlace_id = await self._enlaces.crear(
                    trazo_id=trazo_id,
                    actividad_id=intencion.actividad_id,
                    prototipo_nodo_id=intencion.prototipo_nodo_id,
                    matriz_concepto_id=intencion.matriz_concepto_id,
                    medida=validado.medida.value,
                    factor=validado.factor,
                )
                enlace_ids.append(enlace_id)
                nodos_tocados[
                    (
                        validado.tipo_nodo,
                        intencion.actividad_id,
                        intencion.prototipo_nodo_id,
                        intencion.matriz_concepto_id,
                    )
                ] = None

            if cmd.medicion_id is not None and self._mediciones is not None:
                await self._mediciones.poner_trazo(trazo_id, cmd.medicion_id)
                for actividad_id, matriz_id in await aplicar_asignaciones_a_trazo(
                    trazo_id=trazo_id,
                    medicion_id=cmd.medicion_id,
                    mediciones=self._mediciones,
                    enlaces=self._enlaces,
                ):
                    nodos_tocados[(TipoNodoCuantificacion.ACTIVIDAD, actividad_id, None, matriz_id)] = None

            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=tipo_nodo,
                        actividad_id=actividad_id,
                        prototipo_nodo_id=prototipo_nodo_id,
                        matriz_concepto_id=matriz_concepto_id,
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                    )
                    for (
                        tipo_nodo,
                        actividad_id,
                        prototipo_nodo_id,
                        matriz_concepto_id,
                    ) in nodos_tocados
                ]
            )

            await self._uow.commit()

        await _avisar_reaperturas(self._eventos, recalculos, cmd.autor_id)
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
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
    ) -> None:
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

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
        matriz_concepto_id = anterior.get("matriz_concepto_id")

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
                    matriz_concepto_id=str(matriz_concepto_id) if matriz_concepto_id else None,
                )
                await self._enlaces.crear(
                    trazo_id=cmd.nuevo.trazo_id,
                    actividad_id=actividad_id,
                    prototipo_nodo_id=prototipo_nodo_id,
                    matriz_concepto_id=matriz_concepto_id,
                    medida=cmd.nuevo.medida.value,
                    factor=cmd.nuevo.factor,
                    **({"conversion": cmd.nuevo.conversion} if cmd.nuevo.conversion is not None else {}),
                )

            resultado = await _recalcular_nodo(
                tipo_nodo=tipo_nodo,
                actividad_id=actividad_id,
                prototipo_nodo_id=prototipo_nodo_id,
                matriz_concepto_id=matriz_concepto_id,
                enlaces=self._enlaces,
                actividades=self._actividades,
                prototipo_nodos=self._prototipo_nodos,
                desviaciones=self._desviaciones,
                detectada_en=detectada_en,
                matrices=self._matrices,
            )

            await self._uow.commit()

        await _avisar_reaperturas(self._eventos, (resultado,), cmd.usuario_id)
        return resultado


@dataclass(frozen=True, slots=True)
class ComandoTraerTrazo:
    trazo_id: UUID
    plano_destino_id: UUID
    usuario_id: UUID
    rol: Rol
    dx: Decimal = Decimal(0)
    dy: Decimal = Decimal(0)
    """Cuánto se corre el trazo al pasarlo (unidades de plano): el alineado de una versión con otra."""


@dataclass(frozen=True, slots=True)
class TrazoTraido:
    trazo_id: UUID
    enlace_ids: tuple[UUID, ...]
    huecos: int
    recalculos: tuple[ResultadoDeRecalculo, ...] = field(default_factory=tuple)


class TraerTrazoAOtraVersion:
    """Pasa un trazo de una versión anterior del plano a la versión nueva (empalme de versiones).

    Es la acción **explícita y manual** de siempre (MODELO.md §1b, «Si el plano cambia»): nunca se
    empareja solo por cercanía. El trazo se repite en la versión nueva —corrido lo que se diga, con
    sus huecos y sus enlaces vigentes— y los enlaces del trazo viejo dejan de ser vigentes (el trazo y
    sus enlaces se quedan como evidencia), de modo que **lo medido no se cuenta dos veces**. No se
    traen las pertenencias a una medición: la capa sombra es de cada plano.
    """

    def __init__(
        self,
        *,
        trazos: RepositorioTrazos,
        planos: RepositorioPlanos,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
    ) -> None:
        self._trazos = trazos
        self._planos = planos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

    async def ejecutar(self, cmd: ComandoTraerTrazo, *, detectada_en: datetime) -> TrazoTraido:
        origen = await self._trazos.para_traer(cmd.trazo_id)
        if origen is None:
            raise TrazoNoEncontrado(f"El trazo {cmd.trazo_id} no existe o está fuera de tu alcance.")
        if origen["hueco_de"] is not None:
            raise ErrorDeCuantificacion("Un hueco viaja con su trazo: trae el trazo, no el hueco.")
        plano_origen = await self._planos.obtener(origen["plano_id"])
        destino = await self._planos.obtener(cmd.plano_destino_id)
        if plano_origen is None or destino is None:
            raise PlanoNoEncontrado("El plano no existe o está fuera de tu alcance.")
        if plano_origen["obra_id"] != destino["obra_id"] or plano_origen["nombre"] != destino["nombre"]:
            raise ErrorDeCuantificacion("Solo se trae de una versión a otra del mismo plano de la obra.")
        if int(destino["version"]) <= int(plano_origen["version"]):
            raise ErrorDeCuantificacion("Se trae de una versión anterior a una más nueva, no al revés.")

        vigentes = await self._enlaces.vigentes_de_trazo(cmd.trazo_id)
        intenciones = tuple(
            IntencionEnlace(
                medida=MedidaCuantificacion(str(e["medida"])),
                factor=Decimal(str(e["factor"])),
                actividad_id=e["actividad_id"],
                prototipo_nodo_id=e["prototipo_nodo_id"],
                matriz_concepto_id=e["matriz_concepto_id"],
            )
            for e in vigentes
        )
        _exigir_gobierno(cmd.rol, intenciones)

        geometria = await self._trazos.trasladar(origen["geometria_wkt"], cmd.dx, cmd.dy)
        huecos = [await self._trazos.trasladar(h, cmd.dx, cmd.dy) for h in await self._trazos.huecos_de(cmd.trazo_id)]

        async with self._uow:
            nuevo_id = await self._trazos.crear(
                plano_id=cmd.plano_destino_id,
                version_plano=int(destino["version"]),
                capa=origen["capa"],
                geometria_wkt=geometria,
                fuente=str(origen["fuente"]),
                autor_id=cmd.usuario_id,
                grosor_m=origen["grosor_m"],
                alineacion=origen["alineacion"],
                forma=origen["forma"],
                pendiente_pct=origen["pendiente_pct"],
            )
            for hueco in huecos:
                await self._trazos.crear_hueco(trazo_id=nuevo_id, geometria_wkt=hueco, autor_id=cmd.usuario_id)

            enlace_ids: list[UUID] = []
            nodos: dict[tuple[TipoNodoCuantificacion, UUID | None, UUID | None, UUID | None], None] = {}
            for viejo, intencion in zip(vigentes, intenciones, strict=True):
                validado = EnlaceCuantificacion(
                    trazo_id=str(nuevo_id),
                    actividad_id=str(intencion.actividad_id) if intencion.actividad_id else None,
                    prototipo_nodo_id=str(intencion.prototipo_nodo_id) if intencion.prototipo_nodo_id else None,
                    medida=intencion.medida,
                    factor=intencion.factor,
                    matriz_concepto_id=str(intencion.matriz_concepto_id) if intencion.matriz_concepto_id else None,
                )
                enlace_ids.append(
                    await self._enlaces.crear(
                        trazo_id=nuevo_id,
                        actividad_id=intencion.actividad_id,
                        prototipo_nodo_id=intencion.prototipo_nodo_id,
                        matriz_concepto_id=intencion.matriz_concepto_id,
                        medida=validado.medida.value,
                        factor=validado.factor,
                    )
                )
                await self._enlaces.marcar_no_vigente(viejo["id"])
                nodos[
                    (validado.tipo_nodo, intencion.actividad_id, intencion.prototipo_nodo_id, intencion.matriz_concepto_id)
                ] = None

            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=tipo_nodo,
                        actividad_id=actividad_id,
                        prototipo_nodo_id=prototipo_nodo_id,
                        matriz_concepto_id=matriz_concepto_id,
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                    )
                    for (tipo_nodo, actividad_id, prototipo_nodo_id, matriz_concepto_id) in nodos
                ]
            )
            await self._uow.commit()

        await _avisar_reaperturas(self._eventos, recalculos, cmd.usuario_id)
        return TrazoTraido(
            trazo_id=nuevo_id, enlace_ids=tuple(enlace_ids), huecos=len(huecos), recalculos=recalculos
        )


@dataclass(frozen=True, slots=True)
class ComandoCalibrarEscala:
    plano_id: UUID
    punto_a: tuple[float, float]
    punto_b: tuple[float, float]
    distancia_m: Decimal
    usuario_id: UUID
    rol: Rol


@dataclass(frozen=True, slots=True)
class EscalaCalibrada:
    escala_m_por_unidad: Decimal
    recalculos: tuple[ResultadoDeRecalculo, ...] = field(default_factory=tuple)


class CalibrarEscalaDePlano:
    """`PUT /planos/{id}/escala`: dos puntos de una distancia conocida y los
    metros que son (migración 0069).

    Sin escala, la cantidad que se mide es un número en unidades de plano —píxeles
    del visor, o lo que el CAD traiga— y compararla contra la `cant_base` del
    presupuesto (m², ml) no significa nada. La medida se lee ya escalada, así que
    calibrar corrige de golpe todos los trazos del plano; lo que hay que hacer
    aquí es **recalcular** cada nodo que esos trazos alimentan, porque su cantidad
    total cambió: la actividad se vuelve a comparar contra su `cant_base` (y puede
    levantar una desviación nueva; las anteriores, medidas con la escala vieja,
    quedan como historia) y el `prototipo_nodo` se vuelve a sobreescribir.

    Recalibrar sobre un plano con enlaces a `prototipo_nodo` toca un catálogo
    compartido, así que tiene el mismo gobierno que enlazarlos: Control de obra o
    Super intendente. Se valida **antes** de escribir.
    """

    def __init__(
        self,
        *,
        planos: RepositorioPlanos,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
    ) -> None:
        self._planos = planos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

    async def ejecutar(
        self, cmd: ComandoCalibrarEscala, *, detectada_en: datetime
    ) -> EscalaCalibrada:
        if await self._planos.obtener(cmd.plano_id) is None:
            raise PlanoNoEncontrado(
                f"El plano {cmd.plano_id} no existe o está fuera de tu alcance."
            )

        escala = escala_desde_referencia(cmd.punto_a, cmd.punto_b, cmd.distancia_m)

        nodos = await self._enlaces.nodos_vigentes_de_plano(cmd.plano_id)
        if (
            any(n["tipo_nodo"] == TipoNodoCuantificacion.PROTOTIPO_NODO.value for n in nodos)
            and cmd.rol not in _ROLES_QUE_TOCAN_PROTOTIPO
        ):
            permitidos = ", ".join(r.value for r in _ROLES_QUE_TOCAN_PROTOTIPO)
            raise GobiernoDeCuantificacionInvalido(
                f"Este plano alimenta cantidades de un prototipo_nodo: recalibrarlo "
                f"las cambia, y eso exige {permitidos}; el rol {cmd.rol.value!r} no puede."
            )

        async with self._uow:
            await self._planos.fijar_escala(
                cmd.plano_id,
                escala_m_por_unidad=escala,
                referencia={
                    "punto_a": list(cmd.punto_a),
                    "punto_b": list(cmd.punto_b),
                    "distancia_m": str(cmd.distancia_m),
                },
                usuario_id=cmd.usuario_id,
            )
            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=TipoNodoCuantificacion(str(n["tipo_nodo"])),
                        actividad_id=n["actividad_id"],
                        prototipo_nodo_id=n["prototipo_nodo_id"],
                        matriz_concepto_id=n.get("matriz_concepto_id"),
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                    )
                    for n in nodos
                ]
            )
            await self._uow.commit()

        await _avisar_reaperturas(self._eventos, recalculos, cmd.usuario_id)
        return EscalaCalibrada(escala_m_por_unidad=escala, recalculos=recalculos)


@dataclass(frozen=True, slots=True)
class ComandoAprobarTrazo:
    trazo_id: UUID
    aprobador_id: UUID


@dataclass(frozen=True, slots=True)
class TrazoAprobado:
    trazo_id: UUID
    aprobado_por: UUID
    aprobado_en: datetime
    ya_estaba_aprobado: bool


class AprobarTrazo:
    """`aprobar_trazo`: Control de obra marca un trazo como revisado (cerebro
    MODELO.md §1b). El rol lo impone el endpoint; aquí vive el hecho.

    Es una **marca de revisión, no una compuerta**: un trazo cuenta en la
    cantidad desde que se guarda, aprobado o no (ver migración 0065 — el
    cerebro no define lo contrario). Por eso aprobar no recalcula nada.

    Idempotente: aprobar de nuevo no pisa quién ni cuándo aprobó primero.
    """

    def __init__(self, *, trazos: RepositorioTrazos, uow: UnidadDeTrabajo) -> None:
        self._trazos = trazos
        self._uow = uow

    async def ejecutar(self, cmd: ComandoAprobarTrazo) -> TrazoAprobado:
        if await self._trazos.obtener(cmd.trazo_id) is None:
            raise TrazoNoEncontrado(
                f"El trazo {cmd.trazo_id} no existe o no está en tu alcance."
            )

        async with self._uow:
            aprobado_ahora = await self._trazos.aprobar(
                trazo_id=cmd.trazo_id, aprobador_id=cmd.aprobador_id
            )
            await self._uow.commit()

        trazo = await self._trazos.obtener(cmd.trazo_id)
        assert trazo is not None and trazo["aprobado_por"] is not None
        return TrazoAprobado(
            trazo_id=cmd.trazo_id,
            aprobado_por=trazo["aprobado_por"],
            aprobado_en=trazo["aprobado_en"],
            ya_estaba_aprobado=not aprobado_ahora,
        )


class AgregarHuecoATrazo:
    """Abre un hueco en un área ya trazada (la ventana de un muro, el cubo de una escalera).

    La geometría de un trazo no se toca (0057): el hueco es un trazo hijo y lo que se mide
    es la geometría efectiva, la del área menos sus huecos (0086). Como cambia lo que el
    área mide, cada nodo que alimenta se **recalcula**: la actividad se vuelve a comparar
    contra su `cant_base` (y puede levantar una desviación) y el `prototipo_nodo` se vuelve
    a sobreescribir. Si el área alimenta un `prototipo_nodo`, tiene el mismo gobierno que
    enlazarlo: Control de obra o Super intendente.
    """

    def __init__(
        self,
        *,
        trazos: RepositorioTrazos,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
    ) -> None:
        self._trazos = trazos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

    async def ejecutar(
        self, cmd: ComandoAgregarHueco, *, detectada_en: datetime
    ) -> HuecoAgregado:
        if await self._trazos.obtener(cmd.trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {cmd.trazo_id} no existe o no está en tu alcance.")

        motivo = await self._trazos.motivo_de_geometria_invalida(cmd.geometria_wkt)
        if motivo is not None:
            raise ErrorDeCuantificacion(f"El hueco no se puede medir. {motivo}")
        motivo = await self._trazos.motivo_de_hueco_invalido(cmd.trazo_id, cmd.geometria_wkt)
        if motivo is not None:
            raise ErrorDeCuantificacion(motivo)

        nodos = await self._enlaces.nodos_vigentes_de_trazo(cmd.trazo_id)
        if (
            any(n["tipo_nodo"] == TipoNodoCuantificacion.PROTOTIPO_NODO.value for n in nodos)
            and cmd.rol not in _ROLES_QUE_TOCAN_PROTOTIPO
        ):
            permitidos = ", ".join(r.value for r in _ROLES_QUE_TOCAN_PROTOTIPO)
            raise GobiernoDeCuantificacionInvalido(
                f"Esta área alimenta la cantidad de un prototipo_nodo: abrirle un hueco la "
                f"cambia, y eso exige {permitidos}; el rol {cmd.rol.value!r} no puede."
            )

        async with self._uow:
            hueco_id = await self._trazos.crear_hueco(
                trazo_id=cmd.trazo_id, geometria_wkt=cmd.geometria_wkt, autor_id=cmd.autor_id
            )
            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=TipoNodoCuantificacion(str(n["tipo_nodo"])),
                        actividad_id=n["actividad_id"],
                        prototipo_nodo_id=n["prototipo_nodo_id"],
                        matriz_concepto_id=n.get("matriz_concepto_id"),
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                    )
                    for n in nodos
                ]
            )
            await self._uow.commit()

        await _avisar_reaperturas(self._eventos, recalculos, cmd.autor_id)
        return HuecoAgregado(hueco_id=hueco_id, recalculos=recalculos)


class GestionarVanos(AgregarHuecoATrazo):
    """Coloca o quita un vano (puerta, ventana, paso) sobre una línea.

    Cambia lo que la línea mide (el servidor lo descuenta al medir, 0103), así que cada nodo que la línea
    alimenta se **recalcula**, igual que con un hueco; y si alimenta un `prototipo_nodo` tiene el mismo gobierno.
    """

    async def _cambiar(
        self, trazo_id: UUID, rol: Rol, autor_id: UUID, detectada_en: datetime, accion: Any
    ) -> VanoCambiado:
        nodos = await self._enlaces.nodos_vigentes_de_trazo(trazo_id)
        if (
            any(n["tipo_nodo"] == TipoNodoCuantificacion.PROTOTIPO_NODO.value for n in nodos)
            and rol not in _ROLES_QUE_TOCAN_PROTOTIPO
        ):
            permitidos = ", ".join(r.value for r in _ROLES_QUE_TOCAN_PROTOTIPO)
            raise GobiernoDeCuantificacionInvalido(
                f"Esta línea alimenta la cantidad de un prototipo_nodo: cambiarle un vano la cambia, y eso exige "
                f"{permitidos}; el rol {rol.value!r} no puede."
            )
        async with self._uow:
            vano_id = await accion()
            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=TipoNodoCuantificacion(str(n["tipo_nodo"])),
                        actividad_id=n["actividad_id"],
                        prototipo_nodo_id=n["prototipo_nodo_id"],
                        matriz_concepto_id=n.get("matriz_concepto_id"),
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                    )
                    for n in nodos
                ]
            )
            await self._uow.commit()
        await _avisar_reaperturas(self._eventos, recalculos, autor_id)
        return VanoCambiado(vano_id=vano_id, recalculos=recalculos)

    async def agregar(self, cmd: ComandoAgregarVano, *, detectada_en: datetime) -> VanoCambiado:
        if await self._trazos.obtener(cmd.trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {cmd.trazo_id} no existe o no está en tu alcance.")
        if not await self._trazos.admite_vano(cmd.trazo_id):
            raise ErrorDeCuantificacion("Un vano se coloca sobre una línea (un muro) o sobre un área.")

        async def crear() -> UUID:
            return await self._trazos.crear_vano(
                trazo_id=cmd.trazo_id,
                clave=cmd.clave.strip(),
                tipo=cmd.tipo,
                ancho_m=cmd.ancho_m,
                alto_m=cmd.alto_m,
                antepecho_m=cmd.antepecho_m,
                piezas=cmd.piezas,
                posicion_m=cmd.posicion_m,
                autor_id=cmd.autor_id,
                lado_muro=cmd.lado_muro,
            )

        return await self._cambiar(cmd.trazo_id, cmd.rol, cmd.autor_id, detectada_en, crear)

    async def quitar(
        self, vano_id: UUID, *, autor_id: UUID, rol: Rol, detectada_en: datetime
    ) -> VanoCambiado:
        trazo_id = await self._trazos.trazo_del_vano(vano_id)
        if trazo_id is None:
            raise TrazoNoEncontrado(f"El vano {vano_id} no existe o está fuera de tu alcance.")

        async def borrar() -> UUID:
            await self._trazos.quitar_vano(vano_id)
            return vano_id

        return await self._cambiar(trazo_id, rol, autor_id, detectada_en, borrar)

    async def cambiar_ancho(
        self, vano_id: UUID, ancho_m: Decimal, *, autor_id: UUID, rol: Rol, detectada_en: datetime
    ) -> VanoCambiado:
        """Ensancha o angosta un vano: cambia lo que descuenta, así que recalcula lo que alimenta la línea."""
        trazo_id = await self._trazos.trazo_del_vano(vano_id)
        if trazo_id is None:
            raise TrazoNoEncontrado(f"El vano {vano_id} no existe o está fuera de tu alcance.")
        if ancho_m <= 0:
            raise ErrorDeCuantificacion("El ancho del vano debe ser mayor que cero.")

        async def guardar() -> UUID:
            await self._trazos.fijar_ancho_vano(vano_id, ancho_m)
            return vano_id

        return await self._cambiar(trazo_id, rol, autor_id, detectada_en, guardar)

    async def del_plano(self, plano_id: UUID) -> list[dict[str, Any]]:
        return await self._trazos.vanos_del_plano(plano_id)

    async def muro(self, trazo_id: UUID) -> dict[str, Any]:
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        return await self._trazos.muro_de_trazo(trazo_id)

    async def uniones(self, trazo_id: UUID) -> dict[str, Any]:
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        return {
            "extremos": await self._trazos.uniones_de_trazo(trazo_id),
            "candidatos": await self._trazos.candidatos_de_union(trazo_id, RADIO_DE_UNION_M),
        }

    async def fijar_union(
        self,
        trazo_id: UUID,
        *,
        extremo: str,
        op: str | None,
        con_trazo_id: UUID | None,
        autor_id: UUID,
        rol: Rol,
        detectada_en: datetime,
    ) -> VanoCambiado:
        """Qué pasa en un extremo del muro cuando llega a otro (D-629): conexión, unión a tope o empalme. `op=None` la
        quita. Cambia lo que mide el largo del muro, así que se recalcula lo que alimenta, como con un vano."""
        if extremo not in ("ini", "fin"):
            raise ErrorDeCuantificacion("El extremo es el inicio o el final del muro.")
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if not await self._trazos.es_linea(trazo_id):
            raise ErrorDeCuantificacion("Las uniones se fijan sobre una línea (un muro).")
        if op is not None:
            if op not in ("conexion", "union", "empalme"):
                raise ErrorDeCuantificacion("La unión es conexión, unión a tope o empalme (la fusión es otra acción).")
            if con_trazo_id is None or con_trazo_id == trazo_id:
                raise ErrorDeCuantificacion("Elige el otro muro con el que se encuentra.")
            if not any(
                c["extremo"] == extremo and UUID(str(c["trazo_id"])) == con_trazo_id
                for c in await self._trazos.candidatos_de_union(trazo_id, RADIO_DE_UNION_M)
            ):
                raise ErrorDeCuantificacion("Ese muro no se encuentra con este extremo.")

        async def guardar() -> UUID:
            if op is None:
                await self._trazos.quitar_union(trazo_id=trazo_id, extremo=extremo)
            else:
                await self._trazos.fijar_union(
                    trazo_id=trazo_id, extremo=extremo, op=op, con_trazo_id=con_trazo_id, autor_id=autor_id  # type: ignore[arg-type]
                )
            return trazo_id

        return await self._cambiar(trazo_id, rol, autor_id, detectada_en, guardar)

    async def fusionar(
        self, trazo_id: UUID, con_trazo_id: UUID, *, autor_id: UUID, rol: Rol, detectada_en: datetime
    ) -> VanoCambiado:
        """Los dos muros pasan a ser uno (D-629): el primero conserva su identidad y absorbe al segundo."""
        for t in (trazo_id, con_trazo_id):
            if await self._trazos.obtener(t) is None:
                raise TrazoNoEncontrado(f"El trazo {t} no existe o no está en tu alcance.")
        if trazo_id == con_trazo_id:
            raise ErrorDeCuantificacion("Elige otro muro para fusionar.")

        async def juntar() -> UUID:
            motivo = await self._trazos.fusionar(
                trazo_id=trazo_id, con_trazo_id=con_trazo_id, tolerancia_m=RADIO_DE_UNION_M
            )
            if motivo is not None:
                raise ErrorDeCuantificacion(motivo)
            return trazo_id

        return await self._cambiar(trazo_id, rol, autor_id, detectada_en, juntar)

    async def fijar_muro(
        self,
        trazo_id: UUID,
        *,
        altura_m: Decimal | None,
        caras: int,
        cara: str | None,
        partes: Sequence[ParteDeAltura] | None,
        autor_id: UUID,
        rol: Rol,
        detectada_en: datetime,
    ) -> VanoCambiado:
        """Cómo cuenta un muro (D-627): altura única o por partes y una o dos caras. Rehace el factor de sus enlaces de
        largo en m² y recalcula los nodos que alimenta, igual que un vano."""
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if not await self._trazos.es_linea(trazo_id):
            raise ErrorDeCuantificacion("Cómo cuenta el muro se fija sobre una línea.")
        factor = factor_de_muro(altura_efectiva(altura_m, partes), caras)
        guardar_partes = (
            [{"nombre": p.nombre, "desde_m": str(p.desde_m), "hasta_m": str(p.hasta_m), "suma": p.suma} for p in partes]
            if partes
            else None
        )

        async def guardar() -> UUID:
            await self._trazos.fijar_muro(
                trazo_id=trazo_id,
                altura_m=None if partes else altura_m,
                caras=caras,
                cara=cara if caras == 1 else None,
                partes=guardar_partes,
                factor=factor,
            )
            return trazo_id

        return await self._cambiar(trazo_id, rol, autor_id, detectada_en, guardar)

    async def fijar_hoja(self, vano_id: UUID, *, bisagra: int, lado_hoja: int, apertura_grados: int) -> None:
        """La hoja de una puerta (D-632): bisagra, lado y apertura. Es dibujo y especificación: no cambia lo que descuenta."""
        if await self._trazos.trazo_del_vano(vano_id) is None:
            raise TrazoNoEncontrado(f"El vano {vano_id} no existe o está fuera de tu alcance.")
        if bisagra not in (-1, 1) or lado_hoja not in (-1, 1):
            raise ErrorDeCuantificacion("La bisagra y el lado de la hoja son 1 o -1.")
        if not 0 <= apertura_grados <= 180:
            raise ErrorDeCuantificacion("La apertura va de 0° a 180°.")
        async with self._uow:
            await self._trazos.fijar_hoja(vano_id, bisagra=bisagra, lado_hoja=lado_hoja, apertura_grados=apertura_grados)
            await self._uow.commit()

    async def mover(self, vano_id: UUID, posicion_m: Decimal) -> None:
        """Corre un vano por su muro. Dónde está no cambia lo que mide, así que no recalcula nada."""
        if await self._trazos.trazo_del_vano(vano_id) is None:
            raise TrazoNoEncontrado(f"El vano {vano_id} no existe o está fuera de tu alcance.")
        if posicion_m < 0:
            raise ErrorDeCuantificacion("La posición del vano no puede ser negativa.")
        async with self._uow:
            await self._trazos.mover_vano(vano_id, posicion_m)
            await self._uow.commit()

    async def listar(self, trazo_id: UUID) -> list[dict[str, Any]]:
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        return await self._trazos.vanos_de_trazo(trazo_id)


class EliminarTrazo:
    """Borra un trazo (un punto, una línea, un área) con sus enlaces y sus huecos.

    Quien lo borra: Control de obra y Super intendente cualquiera; los demás roles, solo uno
    suyo que aún no esté aprobado (aprobar deja constancia de una revisión que no se desharía
    en silencio). Si el trazo alimenta un `prototipo_nodo`, tiene el mismo gobierno que
    enlazarlo. Cada nodo que alimentaba se **recalcula**; si era su último trazo vuelve a «sin
    medir» y no levanta una desviación.
    """

    def __init__(
        self,
        *,
        trazos: RepositorioTrazos,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
    ) -> None:
        self._trazos = trazos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

    async def ejecutar(
        self, cmd: ComandoEliminarTrazo, *, detectada_en: datetime
    ) -> TrazoEliminado:
        trazo = await self._trazos.obtener(cmd.trazo_id)
        if trazo is None or trazo.get("hueco_de") is not None:
            raise TrazoNoEncontrado(f"El trazo {cmd.trazo_id} no existe o no está en tu alcance.")

        if cmd.rol not in _ROLES_QUE_TOCAN_PROTOTIPO and (
            trazo.get("autor_id") != cmd.usuario_id or trazo.get("aprobado_por") is not None
        ):
            raise GobiernoDeCuantificacionInvalido(
                "Solo puedes borrar un trazo tuyo que todavía no esté aprobado; "
                "Control de obra y Super intendente borran cualquiera."
            )

        nodos = await self._enlaces.nodos_vigentes_de_trazo(cmd.trazo_id)
        if (
            any(n["tipo_nodo"] == TipoNodoCuantificacion.PROTOTIPO_NODO.value for n in nodos)
            and cmd.rol not in _ROLES_QUE_TOCAN_PROTOTIPO
        ):
            permitidos = ", ".join(r.value for r in _ROLES_QUE_TOCAN_PROTOTIPO)
            raise GobiernoDeCuantificacionInvalido(
                f"Este trazo alimenta la cantidad de un prototipo_nodo: borrarlo la cambia, "
                f"y eso exige {permitidos}; el rol {cmd.rol.value!r} no puede."
            )

        async with self._uow:
            await self._trazos.eliminar(cmd.trazo_id)
            recalculos: list[ResultadoDeRecalculo] = []
            for n in nodos:
                tipo = TipoNodoCuantificacion(str(n["tipo_nodo"]))
                quedan = await self._enlaces.enlaces_de_nodo(
                    tipo_nodo=tipo.value,
                    actividad_id=n["actividad_id"],
                    prototipo_nodo_id=n["prototipo_nodo_id"],
                    matriz_concepto_id=n.get("matriz_concepto_id"),
                )
                recalculos.append(
                    await _recalcular_nodo(
                        tipo_nodo=tipo,
                        actividad_id=n["actividad_id"],
                        prototipo_nodo_id=n["prototipo_nodo_id"],
                        matriz_concepto_id=n.get("matriz_concepto_id"),
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                        proponer_desviacion=any(bool(f["vigente"]) for f in quedan),
                    )
                )
            await self._uow.commit()

        resultado = tuple(recalculos)
        await _avisar_reaperturas(self._eventos, resultado, cmd.usuario_id)
        return TrazoEliminado(trazo_id=cmd.trazo_id, recalculos=resultado)


class QuitarHueco:
    """Quita un hueco de un área (deshacer abrirlo, o corregirlo): el área vuelve a medir lo que medía.
    Mismo gobierno que borrar el trazo, y los nodos que el área alimenta se recalculan."""

    def __init__(
        self,
        *,
        trazos: RepositorioTrazos,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
    ) -> None:
        self._trazos = trazos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

    async def ejecutar(
        self, *, trazo_id: UUID, hueco_id: UUID, usuario_id: UUID, rol: Rol, detectada_en: datetime
    ) -> TrazoEliminado:
        padre = await self._trazos.obtener(trazo_id)
        hueco = await self._trazos.obtener(hueco_id)
        if padre is None or hueco is None or hueco.get("hueco_de") != trazo_id:
            raise TrazoNoEncontrado(f"El hueco {hueco_id} no existe en el trazo {trazo_id}.")
        if rol not in _ROLES_QUE_TOCAN_PROTOTIPO and (
            padre.get("autor_id") != usuario_id or padre.get("aprobado_por") is not None
        ):
            raise GobiernoDeCuantificacionInvalido(
                "Solo puedes cambiar un trazo tuyo que todavía no esté aprobado; "
                "Control de obra y Super intendente cambian cualquiera."
            )
        nodos = await self._enlaces.nodos_vigentes_de_trazo(trazo_id)
        if (
            any(n["tipo_nodo"] == TipoNodoCuantificacion.PROTOTIPO_NODO.value for n in nodos)
            and rol not in _ROLES_QUE_TOCAN_PROTOTIPO
        ):
            permitidos = ", ".join(r.value for r in _ROLES_QUE_TOCAN_PROTOTIPO)
            raise GobiernoDeCuantificacionInvalido(
                f"Esta área alimenta la cantidad de un prototipo_nodo: cambiarla exige "
                f"{permitidos}; el rol {rol.value!r} no puede."
            )
        async with self._uow:
            await self._trazos.eliminar(hueco_id)
            recalculos = tuple(
                [
                    await _recalcular_nodo(
                        tipo_nodo=TipoNodoCuantificacion(str(n["tipo_nodo"])),
                        actividad_id=n["actividad_id"],
                        prototipo_nodo_id=n["prototipo_nodo_id"],
                        matriz_concepto_id=n.get("matriz_concepto_id"),
                        enlaces=self._enlaces,
                        actividades=self._actividades,
                        prototipo_nodos=self._prototipo_nodos,
                        desviaciones=self._desviaciones,
                        detectada_en=detectada_en,
                        matrices=self._matrices,
                    )
                    for n in nodos
                ]
            )
            await self._uow.commit()
        await _avisar_reaperturas(self._eventos, recalculos, usuario_id)
        return TrazoEliminado(trazo_id=trazo_id, recalculos=recalculos)


_TIPOS_DE_ANOTACION = ("nota", "texto", "flecha", "llamada")


@dataclass(frozen=True, slots=True)
class ComandoFijarVistaDePlano:
    plano_id: UUID
    rotacion_grados: int
    volteo_horizontal: bool
    volteo_vertical: bool


class FijarVistaDePlano:
    """`PUT /planos/{id}/vista`: cómo se ve el plano —girado y/o en espejo— (migración 0087).

    Es presentación: no toca la geometría de los trazos ni ninguna cantidad, así que no recalcula
    nada y no pide más gobierno que poder trazar sobre el plano."""

    def __init__(self, *, planos: RepositorioPlanos, uow: UnidadDeTrabajo) -> None:
        self._planos = planos
        self._uow = uow

    async def ejecutar(self, cmd: ComandoFijarVistaDePlano) -> None:
        if cmd.rotacion_grados not in (0, 90, 180, 270):
            raise ErrorDeCuantificacion("El plano solo gira de 90 en 90 grados.")
        if await self._planos.obtener(cmd.plano_id) is None:
            raise PlanoNoEncontrado(
                f"El plano {cmd.plano_id} no existe o está fuera de tu alcance."
            )
        async with self._uow:
            await self._planos.fijar_vista(
                cmd.plano_id,
                rotacion_grados=cmd.rotacion_grados,
                volteo_horizontal=cmd.volteo_horizontal,
                volteo_vertical=cmd.volteo_vertical,
            )
            await self._uow.commit()


class RegistrarNotaPlano:
    """Alta simple de una anotación sobre el plano (MODELO.md §1b): nunca
    produce cantidad, nunca tiene enlace."""

    def __init__(self, *, notas: RepositorioNotasPlano, uow: UnidadDeTrabajo) -> None:
        self._notas = notas
        self._uow = uow

    async def ejecutar(self, cmd: ComandoRegistrarNotaPlano) -> NotaPlanoRegistrada:
        texto = cmd.texto.strip()
        if cmd.tipo not in _TIPOS_DE_ANOTACION:
            raise ErrorDeCuantificacion(f"Tipo de anotación desconocido: {cmd.tipo!r}.")
        # Una flecha puede ir sin palabras; todo lo demás necesita texto.
        if not texto and cmd.tipo != "flecha":
            raise ErrorDeCuantificacion(
                "La anotación necesita texto: nota_plano.texto es not null "
                "(MODELO.md §1b)."
            )
        if (cmd.tipo in ("flecha", "llamada")) != (cmd.destino_wkt is not None):
            raise ErrorDeCuantificacion(
                "Solo una flecha o una llamada apuntan a un destino, y las dos lo necesitan."
            )

        async with self._uow:
            nota_id = await self._notas.crear(
                plano_id=cmd.plano_id,
                version_plano=cmd.version_plano,
                ubicacion_wkt=cmd.ubicacion_wkt,
                autor_id=cmd.autor_id,
                texto=texto,
                actividad_id=cmd.actividad_id,
                tipo=cmd.tipo,
                destino_wkt=cmd.destino_wkt,
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
            if fila.get("matriz_concepto_id") is not None:
                continue  # las matrices internas se leen aparte (`ConsultarMatrices`, D-583)
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


class ConsultarMatrices:
    """`GET /actividades/{id}/matrices`: las matrices internas de una actividad (D-583).

    El concepto es la matriz madre y un insumo puede ser otra matriz (nervaduras, trabes,
    bastones), a cualquier profundidad. Cada una trae lo que el catálogo implicaba para esta
    actividad, lo que se midió y la diferencia; y el importe de la actividad **ajustado** por lo
    medido, sin tocar su cantidad base.
    """

    def __init__(self, *, matrices: RepositorioMatrices) -> None:
        self._matrices = matrices

    async def ejecutar(self, actividad_id: UUID) -> dict:
        arbol = await self._matrices.arbol_de_actividad(actividad_id)
        if arbol is None:
            raise ActividadNoEncontrada(
                f"La actividad {actividad_id} no existe o está fuera de tu alcance."
            )
        cant_base = Decimal(str(arbol["cant_base"]))
        precio = Decimal(str(arbol["precio_unitario"] or 0))
        filas = arbol["matrices"]
        nodos = [
            NodoDeMatriz(
                concepto_id=str(f["concepto_id"]),
                ruta=tuple(str(x) for x in f["ruta"]),
                acumulada=Decimal(str(f["acumulada"])),
                precio_unitario=Decimal(str(f["precio_unitario"])),
                cantidad_medida=(
                    Decimal(str(f["cantidad_medida"])) if f["cantidad_medida"] is not None else None
                ),
            )
            for f in filas
        ]
        ajuste = ajuste_por_medicion(nodos, cant_base=cant_base)
        importe = cant_base * precio
        matrices = []
        for f, n in zip(filas, nodos, strict=True):
            catalogo = n.catalogo(cant_base)
            matrices.append(
                {
                    "concepto_id": f["concepto_id"],
                    "padre_id": f["padre_id"],
                    "nivel": f["nivel"],
                    "clave": f["clave"],
                    "descripcion": f["descripcion"],
                    "unidad": f["unidad"],
                    "cantidad_unitaria": f["unitaria"],
                    "formula": f.get("formula"),
                    "cantidad_catalogo": catalogo,
                    "precio_unitario": f["precio_unitario"],
                    "cantidad_medida": n.cantidad_medida,
                    "diferencia": (
                        n.cantidad_medida - catalogo if n.cantidad_medida is not None else None
                    ),
                }
            )
        return {
            "actividad_id": actividad_id,
            "concepto_id": arbol["concepto_id"],
            "concepto_clave": arbol["concepto_clave"],
            "descripcion": arbol["descripcion"],
            "cant_base": cant_base,
            "importe": importe,
            "importe_ajuste": ajuste.importe_ajuste,
            "importe_ajustado": importe + ajuste.importe_ajuste,
            "medidas": ajuste.medidas,
            "matrices": matrices,
        }


class TransformarTrazos:
    """Mueve o gira trazos, con sus huecos, sin cambiar su cantidad.

    Mismo gobierno que borrar: Control de obra y Super intendente cualquiera; los demás roles,
    solo un trazo suyo que aún no esté aprobado (aprobar deja constancia de una revisión). Un trazo
    que alimenta un `prototipo_nodo` exige Control de obra o Super intendente. Todo o nada: si
    uno de los trazos no se puede tocar, no se mueve ninguno. Un largo o un área no cambian al
    mover ni al girar, así que no hay nada que recalcular.
    """

    def __init__(
        self,
        *,
        trazos: RepositorioTrazos,
        enlaces: RepositorioEnlacesCuantificacion,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._trazos = trazos
        self._enlaces = enlaces
        self._uow = uow

    async def ejecutar(self, cmd: ComandoTransformarTrazos) -> list[TrazoTransformado]:
        for trazo_id in cmd.trazo_ids:
            trazo = await self._trazos.obtener(trazo_id)
            if trazo is None or trazo.get("hueco_de") is not None:
                raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
            if cmd.rol not in _ROLES_QUE_TOCAN_PROTOTIPO and (
                trazo.get("autor_id") != cmd.usuario_id or trazo.get("aprobado_por") is not None
            ):
                raise GobiernoDeCuantificacionInvalido(
                    "Solo puedes mover o girar un trazo tuyo que todavía no esté aprobado; "
                    "Control de obra y Super intendente tocan cualquiera."
                )
            nodos = await self._enlaces.nodos_vigentes_de_trazo(trazo_id)
            if (
                any(n["tipo_nodo"] == TipoNodoCuantificacion.PROTOTIPO_NODO.value for n in nodos)
                and cmd.rol not in _ROLES_QUE_TOCAN_PROTOTIPO
            ):
                permitidos = ", ".join(r.value for r in _ROLES_QUE_TOCAN_PROTOTIPO)
                raise GobiernoDeCuantificacionInvalido(
                    f"Este trazo alimenta la cantidad de un prototipo_nodo: tocarlo exige "
                    f"{permitidos}; el rol {cmd.rol.value!r} no puede."
                )

        resultado: list[TrazoTransformado] = []
        async with self._uow:
            for trazo_id in cmd.trazo_ids:
                pivote = await self._trazos.transformar(
                    trazo_id, dx=cmd.dx, dy=cmd.dy, grados=cmd.grados, pivote=cmd.pivote
                )
                resultado.append(TrazoTransformado(trazo_id=trazo_id, pivote=pivote))
            await self._uow.commit()
        return resultado


class ConversionDelEnlace:
    """Cómo cuenta un trazo para su concepto (D-633): ver, calcular y aplicar la conversión de un enlace.

    **Aplicar** es un reemplazo explícito: crea un enlace nuevo con la conversión y el anterior queda como evidencia
    (`vigente=false`) y deja de sumar. Con `a_todos`, lo mismo para los demás trazos del mismo tipo del concepto.
    """

    def __init__(self, *, enlaces: RepositorioEnlacesCuantificacion, reemplazar: ReemplazarEnlace) -> None:
        self._enlaces = enlaces
        self._reemplazar = reemplazar

    async def _enlace_vigente(self, enlace_id: UUID) -> dict[str, Any]:
        e = await self._enlaces.obtener(enlace_id)
        if e is None:
            raise EnlaceNoEncontrado(f"El enlace {enlace_id} no existe o está fuera de tu alcance.")
        if not e["vigente"]:
            raise ErrorDeCuantificacion("Ese enlace ya fue reemplazado: elige el vigente.")
        return e

    async def _tipo(self, e: dict[str, Any]) -> str:
        return str((await self._enlaces.calcular_conversion(e["trazo_id"], {"modo": "largo"}))["tipo"])

    async def ver(self, enlace_id: UUID) -> dict[str, Any]:
        e = await self._enlace_vigente(enlace_id)
        unidad = await self._enlaces.unidad_del_concepto(e)
        tipo = await self._tipo(e)
        actual = e.get("conversion") or conversion_por_defecto(tipo, unidad)
        con_modos = tipo in MODOS_POR_TIPO
        return {
            "enlace_id": enlace_id,
            "tipo": tipo,
            "unidad_del_concepto": unidad,
            "conversion": normalizar_conversion(tipo, actual) if con_modos else None,
            "es_la_de_hoy": e.get("conversion") is not None,
            "modos": [{"clave": k, "nombre": n} for k, n in MODOS_POR_TIPO.get(tipo, ())],
            "campos": {
                m: [{"clave": c, "etiqueta": et, "unidad": u} for c, et, u in CAMPOS_POR_MODO.get(f"{tipo}/{m}", ())]
                for m, _ in MODOS_POR_TIPO.get(tipo, ())
            },
        }

    async def calcular(self, enlace_id: UUID, conversion: dict[str, Any]) -> dict[str, Any]:
        e = await self._enlace_vigente(enlace_id)
        tipo = await self._tipo(e)
        limpia = normalizar_conversion(tipo, conversion)
        c = await self._enlaces.calcular_conversion(e["trazo_id"], limpia)
        unidad = await self._enlaces.unidad_del_concepto(e)
        return {
            "valor": float(c["valor"]),
            "unidad": str(c["unidad"]),
            "formula": formula_en_texto(c, limpia),
            "unidad_del_concepto": unidad,
            "coincide": coincide_la_unidad(str(c["unidad"]), unidad),
            "conversion": limpia,
            "componentes": c,
        }

    async def aplicar(
        self, enlace_id: UUID, conversion: dict[str, Any], *, a_todos: bool, rol: Rol, usuario_id: UUID | None, detectada_en: datetime
    ) -> dict[str, Any]:
        e = await self._enlace_vigente(enlace_id)
        tipo = await self._tipo(e)
        limpia = normalizar_conversion(tipo, conversion)
        objetivos = [e]
        if a_todos:
            for h in await self._enlaces.hermanos_del_mismo_tipo(e):
                objetivos.append(await self._enlace_vigente(h["id"]))
        resultado = None
        for o in objetivos:
            resultado = await self._reemplazar.ejecutar(
                ComandoReemplazarEnlace(
                    enlace_id=o["id"],
                    rol=rol,
                    usuario_id=usuario_id,
                    nuevo=NuevoEnlace(
                        trazo_id=o["trazo_id"],
                        medida=MedidaCuantificacion(medida_natural(tipo)),
                        factor=Decimal(1),
                        conversion=limpia,
                    ),
                ),
                detectada_en=detectada_en,
            )
        assert resultado is not None
        return {"aplicados": len(objetivos), "resultado": resultado}
