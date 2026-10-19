"""Caso de uso: Extracción de un ensamble paramétrico (skill `erp-parametrico`
§6, dirección presupuesto → ensamble).

Spec §5.7-§5.10 · §12.11 (capa de aplicación).

Extracción arma la **plantilla** (ensamble) a partir de lo ya construido: el
llamador decide, renglón por renglón, qué concepto o sub-ensamble entra, con
qué cantidad y con qué origen (§2, "heredada del concepto / heredada de un
destajo / manual") — este caso de uso no camina el árbol del presupuesto ni
inventa esa clasificación por sí solo. Esa es la misma disciplina que el
usuario fijó para `modo_cantidad`: "el sistema interpreta, el usuario decide,
y que sea reversible" — aquí la propuesta de qué renglones extraer y con qué
origen vive aguas arriba (quien llama a `ExtraerEnsamble`), y nada queda
escrito hasta que ese renglón se confirma.

El caso de uso solo **traduce y persiste**: valida cada renglón con el
dominio (`RenglonEnsamble`, que exige concepto XOR sub-ensamble), resuelve
clave→id contra los catálogos, y guarda. La aritmética de la explosión y de
la tasa/dispersión es de `domain.catalogos.ensamble`; aquí no hay ninguna
regla de negocio nueva.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.calcular_cpu import (
    ConceptoNoEncontrado,
    componentes_por_clave,
)
from obractrl.application.puertos.repositorios import (
    RepositorioConceptos,
    RepositorioEnsambles,
    RepositorioGeneracionDePresupuesto,
    UnidadDeTrabajo,
)
from obractrl.domain.catalogos.apu import ErrorDeAPU, explotar
from obractrl.domain.catalogos.ensamble import (
    EstadoRenglonGenerado,
    ExplosionEnsambleCalculada,
    PartidaExistente,
    RenglonEnsamble,
    RenglonGenerado,
    ValorPartida,
    explotar_ensamble,
    receta_por_concepto,
    reconciliar_generacion,
)
from obractrl.domain.shared.diccionario import OrigenCantidadEnsamble, TipoHijoEnsamble
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = [
    "ClaveDeEnsambleEnUso",
    "ComandoExtraerEnsamble",
    "ComandoGenerarDesdeEnsamble",
    "ConceptoNoEncontrado",
    "EnsambleCreado",
    "EnsambleNoCoincideConInstancia",
    "EnsambleNoEncontrado",
    "ExplotarEnsamble",
    "ExtraerEnsamble",
    "GenerarDesdeEnsamble",
    "InstanciaNoEncontrada",
    "ReporteGeneracion",
    "SubEnsambleNoEncontrado",
]


class ClaveDeEnsambleEnUso(ErrorDeAPU):
    """Ya existe un ensamble con esta clave (§3.3: la clave es la identidad)."""

    def __init__(self, clave: str) -> None:
        super().__init__(f"Ya existe un ensamble con la clave {clave!r}.")
        self.clave = clave


class SubEnsambleNoEncontrado(LookupError):
    """El sub-ensamble referido por un renglón no existe (o no es visible,
    §12.4 — RLS hace indistinguibles los dos casos a propósito)."""

    def __init__(self, clave: str) -> None:
        super().__init__(f"No existe el ensamble {clave!r} o está fuera de tu alcance.")
        self.clave = clave


class EnsambleNoEncontrado(LookupError):
    """El ensamble que se quiere generar no existe (o no es visible)."""

    def __init__(self, clave: str) -> None:
        super().__init__(f"No existe el ensamble {clave!r} o está fuera de tu alcance.")
        self.clave = clave


class InstanciaNoEncontrada(LookupError):
    """El nodo que se quiere regenerar no existe, no es visible, o no es
    una instancia generada por un ensamble (`ensamble_id` nulo, migración
    0062) — regenerarlo no tiene sentido."""

    def __init__(self, prototipo_nodo_id: UUID) -> None:
        super().__init__(
            f"El nodo {prototipo_nodo_id} no existe, no es visible, o no es "
            "una instancia generada por un ensamble."
        )
        self.prototipo_nodo_id = prototipo_nodo_id


class EnsambleNoCoincideConInstancia(ErrorDeAPU):
    """La instancia ya fue generada por OTRO ensamble: regenerarla con uno
    distinto mezclaría dos recetas en el mismo nodo."""

    def __init__(self, prototipo_nodo_id: UUID, clave: str) -> None:
        super().__init__(
            f"El nodo {prototipo_nodo_id} fue generado por otro ensamble, no "
            f"por {clave!r}: no se puede regenerar con una plantilla distinta "
            "a la que ya tiene."
        )
        self.prototipo_nodo_id = prototipo_nodo_id
        self.clave = clave


@dataclass(frozen=True, slots=True)
class ComandoExtraerEnsamble:
    clave: str
    nombre: str
    renglones: Sequence[RenglonEnsamble]
    divisor_concepto_clave: str | None = None
    divisor_nombre: str | None = None
    presupuesto_origen_id: UUID | None = None
    """El presupuesto del que se extrajeron estos renglones (§3: referencia
    informativa, nunca liga estructural — se guarda en cada renglón, no en
    el ensamble, y sobrevive aunque esa partida se borre o reordene)."""
    cohorte_prototipo_ids: Sequence[UUID] = ()
    """Los prototipos que declaran, a mano, pertenecer a la cohorte de este
    ensamble (§5.7: la cohorte nunca se deriva, siempre se declara)."""


@dataclass(frozen=True, slots=True)
class EnsambleCreado:
    id: UUID
    clave: str
    nombre: str
    renglones: int
    cohorte: tuple[UUID, ...]


class ExtraerEnsamble:
    """`POST /ensambles` vía extracción (Control de obra y Super intendente,
    §11.2 — mismo rol que puede escribir presupuesto y catálogo de APU)."""

    def __init__(
        self,
        *,
        ensambles: RepositorioEnsambles,
        conceptos: RepositorioConceptos,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._ensambles = ensambles
        self._conceptos = conceptos
        self._uow = uow

    async def ejecutar(self, cmd: ComandoExtraerEnsamble) -> EnsambleCreado:
        if await self._ensambles.obtener_por_clave(cmd.clave) is not None:
            raise ClaveDeEnsambleEnUso(cmd.clave)

        divisor_concepto_id: UUID | None = None
        if cmd.divisor_concepto_clave is not None:
            divisor = await self._conceptos.obtener_por_clave(cmd.divisor_concepto_clave)
            if divisor is None:
                raise ConceptoNoEncontrado(
                    f"No existe el concepto {cmd.divisor_concepto_clave!r} o está "
                    "fuera de tu alcance (divisor del ensamble)."
                )
            divisor_concepto_id = UUID(str(divisor["id"]))

        renglones_a_guardar = [
            await self._resolver_renglon(renglon, cmd.presupuesto_origen_id)
            for renglon in cmd.renglones
        ]

        async with self._uow:
            ensamble_id = await self._ensambles.crear(
                {
                    "clave": cmd.clave,
                    "nombre": cmd.nombre,
                    "divisor_concepto_id": divisor_concepto_id,
                    "divisor_nombre": cmd.divisor_nombre,
                }
            )
            if renglones_a_guardar:
                await self._ensambles.agregar_renglones(ensamble_id, renglones_a_guardar)
            if cmd.cohorte_prototipo_ids:
                await self._ensambles.agregar_cohorte(
                    ensamble_id, cmd.cohorte_prototipo_ids
                )
            await self._uow.commit()

        return EnsambleCreado(
            id=ensamble_id,
            clave=cmd.clave,
            nombre=cmd.nombre,
            renglones=len(renglones_a_guardar),
            cohorte=tuple(cmd.cohorte_prototipo_ids),
        )

    async def _resolver_renglon(
        self, renglon: RenglonEnsamble, presupuesto_origen_id: UUID | None
    ) -> dict:
        concepto_id: UUID | None = None
        sub_ensamble_id: UUID | None = None

        if renglon.tipo_hijo is TipoHijoEnsamble.CONCEPTO:
            concepto = await self._conceptos.obtener_por_clave(renglon.clave_concepto or "")
            if concepto is None:
                raise ConceptoNoEncontrado(
                    f"No existe el concepto {renglon.clave_concepto!r} o está "
                    "fuera de tu alcance."
                )
            concepto_id = UUID(str(concepto["id"]))
        else:
            sub_ensamble = await self._ensambles.obtener_por_clave(
                renglon.clave_sub_ensamble or ""
            )
            if sub_ensamble is None:
                raise SubEnsambleNoEncontrado(renglon.clave_sub_ensamble or "")
            sub_ensamble_id = UUID(str(sub_ensamble["id"]))

        return {
            "concepto_id": concepto_id,
            "sub_ensamble_id": sub_ensamble_id,
            "cantidad": Decimal(renglon.cantidad),
            "origen": str(renglon.origen),
            "presupuesto_origen_id": presupuesto_origen_id,
            "orden": renglon.orden,
        }


# --- Generación: ensamble → presupuesto (skill §6) -----------------------


def _renglones_por_clave(filas: Sequence[dict]) -> dict[str, list[RenglonEnsamble]]:
    """Traduce filas de `RepositorioEnsambles.renglones_recursivos` al
    lenguaje del dominio (claves, §3.3) — mismo papel que
    `calcular_cpu.componentes_por_clave` para APU."""
    composiciones: dict[str, list[RenglonEnsamble]] = {}
    for fila in filas:
        clave_concepto = fila.get("concepto_clave")
        clave_sub_ensamble = fila.get("sub_ensamble_clave")
        composiciones.setdefault(str(fila["ensamble_clave"]), []).append(
            RenglonEnsamble(
                cantidad=Decimal(str(fila["cantidad"])),
                origen=OrigenCantidadEnsamble(str(fila["origen"])),
                clave_concepto=str(clave_concepto) if clave_concepto else None,
                clave_sub_ensamble=str(clave_sub_ensamble) if clave_sub_ensamble else None,
                orden=int(fila.get("orden") or 0),
            )
        )
    return composiciones


def _concepto_info_por_clave(filas: Sequence[dict]) -> dict[str, tuple[UUID, str]]:
    """``clave de concepto → (id, descripcion)`` — lo que hace falta para
    crear el nodo hoja (`nombre = concepto.descripcion`, mismo criterio que
    cada cargador de presupuesto)."""
    info: dict[str, tuple[UUID, str]] = {}
    for fila in filas:
        clave = fila.get("concepto_clave")
        if clave:
            info[str(clave)] = (
                UUID(str(fila["concepto_id"])),
                str(fila["concepto_descripcion"]),
            )
    return info


async def _precios_concepto(
    conceptos: RepositorioConceptos, filas: Sequence[dict]
) -> dict[str, PrecioUnitario]:
    """CPU vigente de cada concepto hoja alcanzable desde un ensamble: el
    de su propia explosión de APU si la tiene, o su CPU capturado si no
    (un `SUB-` cotizado a tanto alzado, §10.1 — mismo criterio que
    `PublicarVersionCPU`). La usan tanto `ExplotarEnsamble` (preview) como
    `GenerarDesdeEnsamble` (escritura) sobre las mismas filas de
    `renglones_recursivos`."""
    ids = sorted({UUID(str(f["concepto_id"])) for f in filas if f.get("concepto_id")})
    if not ids:
        return {}
    claves = sorted({str(f["concepto_clave"]) for f in filas if f.get("concepto_clave")})
    id_por_clave = {
        str(f["concepto_clave"]): UUID(str(f["concepto_id"]))
        for f in filas
        if f.get("concepto_clave")
    }

    crudas = await conceptos.composicion_recursiva_de(ids)
    composiciones, costos_insumo = componentes_por_clave(crudas)

    precios: dict[str, PrecioUnitario] = {}
    for clave in claves:
        if clave in composiciones:
            precios[clave] = explotar(
                clave, composiciones=composiciones, costos_insumo=costos_insumo
            ).precio
            continue
        capturado = await _precio_capturado(conceptos, id_por_clave[clave])
        if capturado is not None:
            precios[clave] = capturado
    return precios


async def _precio_capturado(
    conceptos: RepositorioConceptos, concepto_id: UUID
) -> PrecioUnitario | None:
    versiones = await conceptos.versiones_cpu(concepto_id)
    vigente = next(
        (v for v in versiones if bool(v.get("vigente")) and v.get("variante") is None),
        None,
    )
    if vigente is None:
        return None
    return PrecioUnitario(
        total=Dinero(Decimal(str(vigente["precio_unitario"]))),
        destajo=Dinero(Decimal(str(vigente["precio_destajo"]))),
    )


class ExplotarEnsamble:
    """`GET /ensambles/{clave}/explosion` (Control de obra y Super
    intendente, §11.2 — mismo alcance que `/conceptos/{id}/explosion`).

    Solo lectura: previsualiza costo y composición de un ensamble —con el
    `factor` de una instancia hipotética, si se da— sin crear ni tocar
    nada. Comparte la resolución de precios con `GenerarDesdeEnsamble`
    para que "lo que ves antes de generar" y "lo que se escribe al
    generar" nunca se calculen con dos caminos distintos.
    """

    def __init__(
        self, *, ensambles: RepositorioEnsambles, conceptos: RepositorioConceptos
    ) -> None:
        self._ensambles = ensambles
        self._conceptos = conceptos

    async def ejecutar(
        self, clave: str, *, factor: Decimal = Decimal(1)
    ) -> ExplosionEnsambleCalculada:
        ensamble = await self._ensambles.obtener_por_clave(clave)
        if ensamble is None:
            raise EnsambleNoEncontrado(clave)

        filas = await self._ensambles.renglones_recursivos(UUID(str(ensamble["id"])))
        composiciones = _renglones_por_clave(filas)
        precios_concepto = await _precios_concepto(self._conceptos, filas)

        return explotar_ensamble(
            clave,
            composiciones=composiciones,
            precios_concepto=precios_concepto,
            factor=factor,
        )


def _existentes_por_clave(
    filas: Sequence[dict],
) -> tuple[dict[str, PartidaExistente], dict[str, UUID]]:
    """Traduce filas de `RepositorioGeneracionDePresupuesto.
    partidas_de_instancia` a lo que pide `reconciliar_generacion`.

    Una fila sin `partida_id` es un concepto de la receta que todavía no
    tiene partida en esta instancia — no es "existente", así que no entra
    al mapa (`reconciliar_generacion` lo clasifica como NUEVO por su sola
    ausencia)."""
    existentes: dict[str, PartidaExistente] = {}
    partida_id_por_clave: dict[str, UUID] = {}
    for fila in filas:
        if fila.get("partida_id") is None:
            continue
        clave = str(fila["concepto_clave"])
        actual = ValorPartida(
            cantidad=Decimal(str(fila["cantidad"])),
            precio_unitario=Decimal(str(fila["precio_unitario"])),
        )
        snapshot = None
        if fila.get("cantidad_generada") is not None:
            snapshot = ValorPartida(
                cantidad=Decimal(str(fila["cantidad_generada"])),
                precio_unitario=Decimal(str(fila["precio_unitario_generado"])),
            )
        existentes[clave] = PartidaExistente(actual=actual, snapshot=snapshot)
        partida_id_por_clave[clave] = UUID(str(fila["partida_id"]))
    return existentes, partida_id_por_clave


@dataclass(frozen=True, slots=True)
class ComandoGenerarDesdeEnsamble:
    presupuesto_id: UUID
    prototipo_id: UUID
    ensamble_clave: str
    factor: Decimal
    nombre: str
    prototipo_nodo_id: UUID | None = None
    """El nodo de la instancia a regenerar. `None`: se crea una instancia
    nueva (§6 — Generación y regeneración son el mismo caso de uso; sin
    nodo previo todo concepto de la receta sale NUEVO)."""
    parent_id: UUID | None = None
    """Dónde colgar la instancia nueva en el árbol. Ignorado si
    `prototipo_nodo_id` ya apunta a una instancia existente."""
    orden: int = 0


@dataclass(frozen=True, slots=True)
class ReporteGeneracion:
    prototipo_nodo_id: UUID
    nuevos: tuple[str, ...]
    actualizados: tuple[str, ...]
    pendientes: tuple[RenglonGenerado, ...]
    """DESVINCULADO/CONFLICTO/SOBRA (skill §6, §8 regla 11): ninguno se
    escribió solo — aquí solo para que quien llama decida."""


class GenerarDesdeEnsamble:
    """Botón explícito "Generar"/"Regenerar" (Control de obra y Super
    intendente, §11.2 — mismo rol que Extracción).

    Solo NUEVO y ACTUALIZADO se escriben sin preguntar
    (`domain.catalogos.ensamble.EstadoRenglonGenerado`): lo demás se
    reporta en `pendientes` y nunca se aplica solo — "nada sale del
    presupuesto sin que el usuario lo decida".
    """

    def __init__(
        self,
        *,
        ensambles: RepositorioEnsambles,
        conceptos: RepositorioConceptos,
        generacion: RepositorioGeneracionDePresupuesto,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._ensambles = ensambles
        self._conceptos = conceptos
        self._generacion = generacion
        self._uow = uow

    async def ejecutar(self, cmd: ComandoGenerarDesdeEnsamble) -> ReporteGeneracion:
        ensamble = await self._ensambles.obtener_por_clave(cmd.ensamble_clave)
        if ensamble is None:
            raise EnsambleNoEncontrado(cmd.ensamble_clave)
        ensamble_id = UUID(str(ensamble["id"]))

        filas = await self._ensambles.renglones_recursivos(ensamble_id)
        composiciones = _renglones_por_clave(filas)
        precios_concepto = await _precios_concepto(self._conceptos, filas)

        calculada = explotar_ensamble(
            cmd.ensamble_clave,
            composiciones=composiciones,
            precios_concepto=precios_concepto,
            factor=cmd.factor,
        )
        receta = receta_por_concepto(calculada.lineas)
        concepto_info = _concepto_info_por_clave(filas)

        async with self._uow:
            instancia_id = await self._resolver_instancia(cmd, ensamble_id)

            filas_existentes = await self._generacion.partidas_de_instancia(
                presupuesto_id=cmd.presupuesto_id, instancia_id=instancia_id
            )
            existentes, partida_id_por_clave = _existentes_por_clave(filas_existentes)
            clasificados = reconciliar_generacion(receta=receta, existentes=existentes)

            nuevos: list[str] = []
            actualizados: list[str] = []
            pendientes: list[RenglonGenerado] = []

            for renglon in clasificados:
                if renglon.estado is EstadoRenglonGenerado.NUEVO:
                    assert renglon.receta is not None
                    concepto_id, nombre_concepto = concepto_info[renglon.clave_concepto]
                    await self._generacion.crear_partida_generada(
                        presupuesto_id=cmd.presupuesto_id,
                        prototipo_id=cmd.prototipo_id,
                        instancia_id=instancia_id,
                        concepto_id=concepto_id,
                        nombre=nombre_concepto,
                        cantidad=renglon.receta.cantidad,
                        precio_unitario=renglon.receta.precio_unitario,
                        importe=renglon.receta.cantidad * renglon.receta.precio_unitario,
                    )
                    nuevos.append(renglon.clave_concepto)
                elif renglon.estado is EstadoRenglonGenerado.ACTUALIZADO:
                    assert renglon.receta is not None
                    await self._generacion.actualizar_partida_generada(
                        partida_id_por_clave[renglon.clave_concepto],
                        cantidad=renglon.receta.cantidad,
                        precio_unitario=renglon.receta.precio_unitario,
                        importe=renglon.receta.cantidad * renglon.receta.precio_unitario,
                    )
                    actualizados.append(renglon.clave_concepto)
                else:
                    pendientes.append(renglon)

            await self._uow.commit()

        return ReporteGeneracion(
            prototipo_nodo_id=instancia_id,
            nuevos=tuple(nuevos),
            actualizados=tuple(actualizados),
            pendientes=tuple(pendientes),
        )

    async def _resolver_instancia(
        self, cmd: ComandoGenerarDesdeEnsamble, ensamble_id: UUID
    ) -> UUID:
        if cmd.prototipo_nodo_id is None:
            nodo = await self._generacion.crear_instancia(
                prototipo_id=cmd.prototipo_id,
                parent_id=cmd.parent_id,
                nombre=cmd.nombre,
                ensamble_id=ensamble_id,
                factor=cmd.factor,
                orden=cmd.orden,
            )
            return UUID(str(nodo["id"]))

        instancia = await self._generacion.obtener_instancia(cmd.prototipo_nodo_id)
        if instancia is None:
            raise InstanciaNoEncontrada(cmd.prototipo_nodo_id)
        if UUID(str(instancia["ensamble_id"])) != ensamble_id:
            raise EnsambleNoCoincideConInstancia(cmd.prototipo_nodo_id, cmd.ensamble_clave)

        instancia_id = UUID(str(instancia["id"]))
        if Decimal(str(instancia["ensamble_factor"])) != cmd.factor:
            await self._generacion.actualizar_factor(instancia_id, cmd.factor)
        return instancia_id
