"""Reglas del contexto Programación (§7.5, §11.2 "Programación · CPM").

Spec §6 (ruta crítica) · §7.5 (ProgramaBase · ProgramaBaseItem · ProgramaObra) ·
§7.6 (campos de programación de la Actividad) · §11.2 · §12.11.

Este módulo decide **qué cronograma debe existir**; escribirlo es del caso de
uso. Dos operaciones, las dos puras:

* `instanciar_programa` — baja la plantilla de duraciones del prototipo
  (`ProgramaBaseItem`, §7.5) a las actividades ya generadas de una obra
  (§11.2 `POST /obras/{id}/programa`). Aquí es donde se **resuelven las
  dependencias**: el programa base habla en `prototipo_nodo_id` y el
  cronograma de la obra habla en ids de actividad, así que cada `ref` se
  traduce por el nodo del prototipo que originó cada actividad
  (`actividad.prototipo_nodo_id`, migración 0018).
* `editar_programacion` — el ajuste manual de una actividad (§11.2
  `PATCH /actividades/{id}/programacion`).

El motor CPM vive al lado, en `cpm.py`, y es quien decide holgura, criticidad
y ciclos; aquí no se reimplementa nada de eso — se reutiliza `Dependencia`
tal cual para no tener dos formas de la misma precedencia.

**El calendario de trabajo no pasa por aquí, y es a propósito** (`calendario.py`,
migración 0040). Semana laboral o natural es una propiedad del cronograma
completo —vive en `programa_base` y baja a `programa_obra`—, no de cada
renglón: si el muro se calculara con sábados y el aplanado sin ellos, la
dependencia entre los dos no querría decir nada. Este módulo decide *cuántos
días* dura cada cosa y *qué depende de qué*, y esas cifras no cambian de valor
al cambiar de calendario: cambia a qué fecha las traduce el motor. Por eso
`validar_tramos` y `validar_item_base` valen igual bajo los dos —traslape,
orden y suma son aritmética de índices— y el caso de uso pasa el calendario
directo de la plantilla a `calcular_cpm` sin pasar por estas funciones.

Lo que sí cambia de significado es la **unidad**: con semana laboral,
`duracion_dias`, `lag_dias` y `offset_dias` son días hábiles.

Módulo puro: recibe y devuelve dataclasses, no toca la BD (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from obractrl.domain.programacion.cpm import Dependencia, NodoCPM, Tramo, trabajo_de

__all__ = [
    "DURACION_POR_DEFECTO",
    "ActividadProgramable",
    "ErrorDeProgramacion",
    "ItemProgramaBase",
    "ProgramaInstanciado",
    "ProgramacionDeActividad",
    "editar_programacion",
    "instanciar_programa",
    "item_aplicable",
    "nodos_cpm",
    "normalizar_tramos",
    "validar_item_base",
    "validar_tramos",
]

DURACION_POR_DEFECTO = Decimal(1)
"""Default de `programa_base_item.duracion_dias` y `actividad.duracion_dias`
(§7.5, §7.6). Una actividad sin plantilla nace con un día y se ajusta con
`PATCH /actividades/{id}/programacion` (§11.2)."""


class ErrorDeProgramacion(ValueError):
    """El cronograma pedido no es válido (§7.5, §6).

    No cubre el ciclo de dependencias: eso lo detecta el motor y lo reporta
    como `CicloEnGrafoError` con las actividades involucradas (`cpm.py`).
    """


@dataclass(frozen=True, slots=True)
class ItemProgramaBase:
    """Renglón de la plantilla de duraciones del prototipo (§7.5).

    Un item apunta a un `prototipo_nodo_id` concreto o —plantilla gruesa— a
    una `etapa_id` completa. Sus `dependencias` traen `ref` en el lenguaje
    del prototipo, no en ids de actividad: `instanciar_programa` las traduce.
    """

    duracion_dias: Decimal = DURACION_POR_DEFECTO
    prototipo_nodo_id: str | None = None
    etapa_id: str | None = None
    frente_id: str | None = None
    dependencias: tuple[Dependencia, ...] = ()
    orden: int = 0
    tramos: tuple[Tramo, ...] = ()
    """Interrupción de la actividad (§7.6). Vive en la plantilla y no solo en
    la obra porque partir el muro para colar la losa es de la **secuencia
    constructiva del prototipo**, no un ajuste de una obra concreta: si solo
    viviera en `actividad`, cada obra generada tendría que volver a partirlo a
    mano."""
    inicio_dias: Decimal | None = None
    """Ancla de arranque: el día del programa en que la actividad empieza
    **pase lo que pase con sus predecesoras** (§7.5, §6). `None` es el
    comportamiento de siempre —lo deriva el CPM—. Es el "Debe comenzar el" de
    MS Project y no el "No comenzar antes del": no es un piso que la
    predecesora pueda empujar, es un clavo. Vive en la plantilla por la misma
    razón que `tramos`: "la urbanización de esta manzana no arranca hasta el
    día 30" es del prototipo, no de una obra."""


@dataclass(frozen=True, slots=True)
class ActividadProgramable:
    """Lo que el cronograma necesita saber de una actividad ya existente (§7.6).

    `avance_pct` y `fecha_real_termino` no programan nada: alimentan el
    **desfase** del motor (§6), que mide una actividad concluida contra su
    fecha real y una en curso contra la fecha de corte.
    """

    id: str
    prototipo_nodo_id: str | None = None
    etapa_id: str | None = None
    frente_id: str | None = None
    duracion_dias: Decimal = DURACION_POR_DEFECTO
    dependencias: tuple[Dependencia, ...] = ()
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    avance_pct: Decimal = Decimal(0)
    bloqueada: bool = False
    tramos: tuple[Tramo, ...] = ()
    inicio_dias: Decimal | None = None
    """Ancla de arranque ya instanciada; ver `ItemProgramaBase.inicio_dias`."""


@dataclass(frozen=True, slots=True)
class ProgramacionDeActividad:
    """La programación que debe quedar escrita en una actividad (§7.6)."""

    actividad_id: str
    duracion_dias: Decimal
    dependencias: tuple[Dependencia, ...] = ()
    frente_id: str | None = None
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    tramos: tuple[Tramo, ...] = ()
    inicio_dias: Decimal | None = None
    """Ancla de arranque; ver `ItemProgramaBase.inicio_dias`."""


@dataclass(frozen=True, slots=True)
class ProgramaInstanciado:
    """Resultado de bajar el programa base a una obra (§11.2).

    `sin_item` y `refs_no_resueltas` no son errores: un prototipo puede
    tener plantilla solo para parte de su árbol, y el motor CPM ignora las
    dependencias cuyo `ref` no está en el grafo (`cpm.calcular_cpm`). Se
    devuelven para que el endpoint lo reporte y Control de obra complete la
    plantilla, en vez de que el hueco pase inadvertido.
    """

    actividades: tuple[ProgramacionDeActividad, ...]
    sin_item: tuple[str, ...] = ()
    refs_no_resueltas: tuple[str, ...] = ()


def normalizar_tramos(tramos: Sequence[Tramo]) -> tuple[Tramo, ...]:
    """Forma canónica de una lista de tramos (§7.6).

    Un solo tramo **es** una actividad sin interrupción, así que colapsa a la
    lista vacía: si no, el mismo cronograma tendría dos representaciones —una
    con `tramos: []` y otra con un tramo que cubre toda la duración— y el
    Gantt dibujaría un split de un solo pedazo.

    No ordena ni corrige nada más: los tramos desordenados son un error del
    cliente, no algo que el dominio deba adivinar (`validar_tramos`).
    """
    if len(tramos) <= 1:
        return ()
    return tuple(tramos)


def validar_tramos(
    tramos: Sequence[Tramo], duracion_dias: Decimal, *, sujeto: str
) -> tuple[Tramo, ...]:
    """Invariantes de la interrupción de una actividad (§7.6).

    Un tramo trabaja días positivos, arranca en un desplazamiento no negativo,
    y los tramos vienen ordenados y sin traslape: dos tramos que se pisan no
    son una interrupción, son un error de captura que dejaría un span mentiroso
    (`span_de` toma el máximo, así que el traslape pasaría inadvertido).

    El primero arranca en `offset_dias = 0`. Un hueco por delante no es una
    interrupción —es que la actividad empieza más tarde—, y eso se expresa con
    un lag en su dependencia, donde el CPM lo puede razonar.

    `duracion_dias` es la suma de los tramos: los días de **trabajo** son la
    cifra que consumen costo, recursos y destajo, y tenerla como un segundo
    número capturable a mano garantizaba que tarde o temprano discrepara del
    detalle. Devuelve los tramos normalizados.

    Raises:
        ErrorDeProgramacion: cualquiera de las invariantes anteriores.
    """
    normalizados = normalizar_tramos(tramos)
    if not normalizados:
        return ()

    anterior: Tramo | None = None
    for tramo in normalizados:
        if tramo.duracion_dias <= 0:
            raise ErrorDeProgramacion(
                f"Un tramo de {sujeto} dura {tramo.duracion_dias} días: la "
                f"duración de un tramo debe ser positiva (§7.6)."
            )
        if tramo.offset_dias < 0:
            raise ErrorDeProgramacion(
                f"Un tramo de {sujeto} arranca en el día {tramo.offset_dias}: "
                f"el desplazamiento de un tramo se mide desde el inicio de la "
                f"actividad y no puede ser negativo (§7.6)."
            )
        if anterior is None:
            if tramo.offset_dias != 0:
                raise ErrorDeProgramacion(
                    f"El primer tramo de {sujeto} arranca en el día "
                    f"{tramo.offset_dias} y no en el 0: un hueco por delante no "
                    f"es una interrupción, es una fecha de inicio más tarde — "
                    f"exprésala con el lag de su dependencia (§6)."
                )
        elif tramo.offset_dias < anterior.fin_dias:
            raise ErrorDeProgramacion(
                f"Dos tramos de {sujeto} se traslapan: el que arranca en el día "
                f"{tramo.offset_dias} pisa al que cierra en el "
                f"{anterior.fin_dias}. Los tramos van ordenados y sin "
                f"encimarse (§7.6)."
            )
        anterior = tramo

    trabajo = trabajo_de(0.0, normalizados)
    # Comparación con tolerancia y no exacta: los tramos viajan como float en
    # el jsonb y `duracion_dias` es un `numeric(8,2)`, así que 4.1 + 4.2 no da
    # exactamente 8.3 por ningún lado. La tolerancia es más fina que los dos
    # decimales que la columna guarda.
    if abs(trabajo - float(duracion_dias)) > 1e-6:
        raise ErrorDeProgramacion(
            f"Los tramos de {sujeto} suman {trabajo} días de trabajo pero su "
            f"duración dice {duracion_dias}: la duración de una actividad "
            f"interrumpida es la suma de sus tramos, no el calendario que "
            f"ocupan (§7.6)."
        )

    return normalizados


def validar_item_base(item: ItemProgramaBase) -> ItemProgramaBase:
    """Invariantes de un renglón de plantilla (§7.5).

    Espeja el `check (duracion_dias > 0)` de
    `database/migrations/20260814000006`: la regla se define aquí y la base la
    repite (§12.11, invariante 2 del roadmap).

    Devuelve el item con sus `tramos` normalizados (`normalizar_tramos`), que
    es lo que debe persistirse.
    """
    if item.duracion_dias <= 0:
        raise ErrorDeProgramacion(
            f"La duración de un renglón del programa base debe ser positiva; "
            f"llegó {item.duracion_dias} (§7.5)."
        )

    if item.prototipo_nodo_id is None and item.etapa_id is None:
        raise ErrorDeProgramacion(
            "Un renglón del programa base debe apuntar a un nodo del prototipo "
            "o a una etapa; sin ninguno de los dos no se puede aplicar a "
            "ninguna actividad (§7.5)."
        )

    for dep in item.dependencias:
        if item.prototipo_nodo_id and dep.ref == item.prototipo_nodo_id:
            raise ErrorDeProgramacion(
                f"El renglón {item.prototipo_nodo_id!r} depende de sí mismo: "
                f"eso es un ciclo de longitud 1 (§6)."
            )

    tramos = validar_tramos(
        item.tramos,
        item.duracion_dias,
        sujeto=f"el renglón {item.prototipo_nodo_id or item.etapa_id!r}",
    )
    if tramos == item.tramos:
        return item
    return replace(item, tramos=tramos)


def item_aplicable(
    prototipo_nodo_id: str | None,
    etapa_id: str | None,
    items: Sequence[ItemProgramaBase],
) -> ItemProgramaBase | None:
    """Item del programa base que le toca a un nodo/actividad (§7.5).

    Gana la coincidencia por `prototipo_nodo_id` —el item habla de ese nodo
    exacto—; si no hay, cae al item de su etapa, que es como se captura una
    plantilla gruesa: una duración por frente/etapa.

    Lo usan las dos entradas al cronograma —la generación de la obra
    (§11.3 A.2) y la instanciación del programa (§11.2)— para que las dos
    resuelvan igual; duplicar el criterio las dejaría discrepar.
    """
    if prototipo_nodo_id is not None:
        for item in items:
            if item.prototipo_nodo_id and item.prototipo_nodo_id == prototipo_nodo_id:
                return item

    if etapa_id is None:
        return None

    for item in items:
        if item.prototipo_nodo_id is None and item.etapa_id == etapa_id:
            return item
    return None


def _resolver(
    dependencias: Sequence[Dependencia],
    *,
    actividad_id: str,
    ids: frozenset[str],
    por_nodo: Mapping[str, str],
    no_resueltas: list[str],
) -> tuple[Dependencia, ...]:
    """Traduce los `ref` del programa base a ids de actividad.

    Un `ref` ya puede venir en ids de actividad (reinstanciar un programa que
    ya se bajó una vez), así que ese caso se respeta tal cual. Un `ref` que no
    corresponde a ninguna actividad de la obra se conserva —el motor lo
    ignora— y se acumula en `no_resueltas` para reportarlo.
    """
    resueltas: list[Dependencia] = []
    vistas: set[str] = set()

    for dep in dependencias:
        ref = dep.ref if dep.ref in ids else por_nodo.get(dep.ref, dep.ref)

        if ref == actividad_id:
            raise ErrorDeProgramacion(
                f"La actividad {actividad_id!r} quedaría dependiendo de sí "
                f"misma: el programa base la referencia como su propia "
                f"predecesora (§6)."
            )
        if ref not in ids:
            no_resueltas.append(dep.ref)
        if ref in vistas:
            # Dos renglones distintos del programa base que apuntan al mismo
            # nodo colapsan en la misma actividad; el grafo no gana nada con
            # la arista repetida y el backward pass la resolvería dos veces.
            continue

        vistas.add(ref)
        resueltas.append(
            Dependencia(ref=ref, tipo=dep.tipo, lag_dias=dep.lag_dias)
        )

    return tuple(resueltas)


def instanciar_programa(
    *,
    actividades: Sequence[ActividadProgramable],
    items: Sequence[ItemProgramaBase],
) -> ProgramaInstanciado:
    """Baja la plantilla del prototipo al cronograma de la obra (§11.2, §7.5).

    Cada actividad toma la duración, el frente y las dependencias del item que
    le aplica (`item_aplicable`). Una actividad sin item **conserva** la
    programación que ya tenía: reinstanciar un programa no debe borrar los
    ajustes manuales de lo que la plantilla no cubre (§11.2 `PATCH
    /actividades/{id}/programacion`).

    Raises:
        ErrorDeProgramacion: si no hay actividades que programar, si la
            plantilla viene vacía, o si una dependencia apunta a su propia
            actividad.
    """
    if not actividades:
        raise ErrorDeProgramacion(
            "La obra no tiene actividades: genérala desde su prototipo antes "
            "de instanciar el programa (§11.3 A.2)."
        )
    if not items:
        raise ErrorDeProgramacion(
            "El prototipo no tiene un programa base vigente: no hay plantilla "
            "de duraciones que instanciar (§7.5)."
        )

    ids = frozenset(a.id for a in actividades)
    por_nodo = {
        a.prototipo_nodo_id: a.id for a in actividades if a.prototipo_nodo_id
    }

    programadas: list[ProgramacionDeActividad] = []
    sin_item: list[str] = []
    no_resueltas: list[str] = []

    for actividad in actividades:
        item = item_aplicable(actividad.prototipo_nodo_id, actividad.etapa_id, items)

        if item is None:
            sin_item.append(actividad.id)
            programadas.append(
                ProgramacionDeActividad(
                    actividad_id=actividad.id,
                    duracion_dias=actividad.duracion_dias,
                    dependencias=_resolver(
                        actividad.dependencias,
                        actividad_id=actividad.id,
                        ids=ids,
                        por_nodo=por_nodo,
                        no_resueltas=no_resueltas,
                    ),
                    frente_id=actividad.frente_id,
                    fecha_inicio=actividad.fecha_inicio,
                    fecha_termino=actividad.fecha_termino,
                    tramos=actividad.tramos,
                    inicio_dias=actividad.inicio_dias,
                )
            )
            continue

        item = validar_item_base(item)
        programadas.append(
            ProgramacionDeActividad(
                actividad_id=actividad.id,
                duracion_dias=item.duracion_dias,
                dependencias=_resolver(
                    item.dependencias,
                    actividad_id=actividad.id,
                    ids=ids,
                    por_nodo=por_nodo,
                    no_resueltas=no_resueltas,
                ),
                # El frente del item manda, pero solo si lo trae: una
                # plantilla que no asigna frente no debe borrar el que la
                # actividad ya tenía.
                frente_id=item.frente_id or actividad.frente_id,
                fecha_inicio=actividad.fecha_inicio,
                fecha_termino=actividad.fecha_termino,
                # Los tramos viajan con la duración, no aparte: son la misma
                # decisión —cuánto trabajo y repartido cómo— y una plantilla
                # que impusiera su duración dejando los tramos viejos de la
                # actividad dejaría la suma sin cuadrar (`validar_tramos`).
                tramos=item.tramos,
                # El ancla del item manda, pero solo si la trae: una plantilla
                # sin arranque fijo no debe desclavar la actividad que alguien
                # ya había anclado en esta obra. Mismo criterio que `frente_id`.
                inicio_dias=item.inicio_dias
                if item.inicio_dias is not None
                else actividad.inicio_dias,
            )
        )

    return ProgramaInstanciado(
        actividades=tuple(programadas),
        sin_item=tuple(sin_item),
        refs_no_resueltas=tuple(sorted(set(no_resueltas))),
    )


def editar_programacion(
    actual: ActividadProgramable,
    *,
    duracion_dias: Decimal | None = None,
    dependencias: Sequence[Dependencia] | None = None,
    frente_id: str | None = None,
    fecha_inicio: date | None = None,
    fecha_termino: date | None = None,
    tramos: Sequence[Tramo] | None = None,
    inicio_dias: Decimal | None = None,
    refs_de_la_obra: frozenset[str] = frozenset(),
) -> ProgramacionDeActividad:
    """Ajuste manual del cronograma de una actividad (§11.2 `PATCH`).

    Solo se cambia lo que llega; lo demás se conserva. Una lista vacía de
    `dependencias` **sí** es un cambio: deja la actividad sin predecesoras, y
    una lista vacía de `tramos` le quita la interrupción.

    `tramos` y `duracion_dias` se validan juntos porque la duración es la suma
    de los tramos (§7.6): partir una actividad sin decir su nueva duración la
    **deriva** de los tramos —es el gesto natural del editor gráfico, arrastrar
    los pedazos—, y mandar las dos cosas en desacuerdo es un error del cliente
    que se rechaza en vez de resolverse a favor de una de las dos.

    `refs_de_la_obra` son los ids de actividad del cronograma; una dependencia
    fuera de ese conjunto se rechaza en vez de ignorarse. El motor tolera
    referencias colgantes porque un cronograma parcial debe poder calcularse
    (`cpm.calcular_cpm`), pero eso es para lo que **ya** está persistido: un
    ajuste manual que apunta a otra obra es un error del cliente, no un
    cronograma incompleto.

    El ciclo no se valida aquí: lo detecta el motor sobre el grafo completo de
    la obra —una arista sola no dice nada— y lo reporta como
    `CicloEnGrafoError` (§6).

    Raises:
        ErrorDeProgramacion: duración no positiva, fechas invertidas,
            autodependencia o dependencia fuera de la obra.
    """
    nuevos_tramos = actual.tramos if tramos is None else normalizar_tramos(tramos)

    if duracion_dias is not None:
        nueva_duracion = duracion_dias
    elif tramos is not None and nuevos_tramos:
        # Se parte la actividad sin recapturar su duración: la suma de los
        # tramos ya la dice, y pedírsela al cliente solo abriría la puerta a
        # que discrepen.
        nueva_duracion = Decimal(str(trabajo_de(0.0, nuevos_tramos)))
    else:
        nueva_duracion = actual.duracion_dias

    if nueva_duracion <= 0:
        raise ErrorDeProgramacion(
            f"La duración de una actividad debe ser positiva; llegó "
            f"{nueva_duracion} (§7.6)."
        )

    nuevos_tramos = validar_tramos(
        nuevos_tramos, nueva_duracion, sujeto=f"la actividad {actual.id!r}"
    )

    nuevas_deps = (
        actual.dependencias if dependencias is None else tuple(dependencias)
    )
    if dependencias is not None:
        vistas: set[str] = set()
        for dep in nuevas_deps:
            if dep.ref == actual.id:
                raise ErrorDeProgramacion(
                    f"La actividad {actual.id!r} no puede depender de sí misma "
                    f"(§6)."
                )
            if refs_de_la_obra and dep.ref not in refs_de_la_obra:
                raise ErrorDeProgramacion(
                    f"La dependencia {dep.ref!r} no es una actividad de esta "
                    f"obra: una precedencia solo existe dentro de su propio "
                    f"cronograma (§7.5)."
                )
            if dep.ref in vistas:
                raise ErrorDeProgramacion(
                    f"La dependencia {dep.ref!r} viene repetida: una "
                    f"precedencia se declara una sola vez (§7.5)."
                )
            vistas.add(dep.ref)

    nuevo_inicio = actual.fecha_inicio if fecha_inicio is None else fecha_inicio
    nuevo_termino = actual.fecha_termino if fecha_termino is None else fecha_termino

    if nuevo_inicio and nuevo_termino and nuevo_termino < nuevo_inicio:
        raise ErrorDeProgramacion(
            f"La fecha de término ({nuevo_termino}) es anterior a la de inicio "
            f"({nuevo_inicio}) (§7.6)."
        )

    return ProgramacionDeActividad(
        actividad_id=actual.id,
        duracion_dias=nueva_duracion,
        dependencias=nuevas_deps,
        frente_id=actual.frente_id if frente_id is None else frente_id,
        fecha_inicio=nuevo_inicio,
        fecha_termino=nuevo_termino,
        tramos=nuevos_tramos,
        # Misma convención que `frente_id`: lo que no llega no cambia. Para
        # desclavar una actividad se reescribe el programa base, que es donde
        # el ancla se decide (§7.5).
        inicio_dias=actual.inicio_dias if inicio_dias is None else inicio_dias,
    )


def nodos_cpm(
    actividades: Sequence[ActividadProgramable],
    programacion: Mapping[str, ProgramacionDeActividad] | None = None,
) -> list[NodoCPM]:
    """Arma el grafo que come el motor (§6).

    `programacion` permite calcular **sobre un cronograma que aún no se
    escribe** —lo que instanciar y editar necesitan para abortar antes de
    persistir un ciclo—; sin ella se calcula sobre lo que ya trae cada
    actividad.

    El avance y la fecha real de término salen siempre de la actividad, no de
    la programación propuesta: son ejecución (§7.6), no plan.
    """
    propuesta = programacion or {}
    nodos: list[NodoCPM] = []

    for actividad in actividades:
        plan = propuesta.get(actividad.id)
        avance = float(actividad.avance_pct)
        nodos.append(
            NodoCPM(
                ref=actividad.id,
                duracion_dias=float(
                    plan.duracion_dias if plan else actividad.duracion_dias
                ),
                dependencias=plan.dependencias if plan else actividad.dependencias,
                avance_pct=avance,
                # Igual que en `actividades_sql.nodos_cpm_de_obra`:
                # `fecha_termino` solo es la fecha **real** una vez concluida
                # la actividad; antes es la planeada y usarla como real
                # invalidaría el cálculo del desfase (§6).
                fecha_real_termino=actividad.fecha_termino if avance >= 100 else None,
                bloqueada=actividad.bloqueada,
                # Los tramos siguen a la duración: si se está evaluando una
                # programación propuesta, el span que el motor debe usar es el
                # de esa propuesta, no el de la interrupción ya persistida.
                tramos=plan.tramos if plan else actividad.tramos,
                inicio_dias=_a_float(
                    plan.inicio_dias if plan else actividad.inicio_dias
                ),
            )
        )

    return nodos


def _a_float(valor: Decimal | None) -> float | None:
    """El ancla cruza al motor como `float`, que es la escala en que trabaja."""
    return None if valor is None else float(valor)
