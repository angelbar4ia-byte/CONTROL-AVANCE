"""Insumos programados: qué hace falta para ejecutar la obra, y cuándo.

Spec §7.3 (APU y explosión) · §7.5 (cronograma) · §7.6 (Actividad y tramos) ·
§10.1 (catálogo de insumos) · §12.11.

## La pregunta que contesta

El sistema ya sabía dos cosas por separado: **qué se hace y cuándo** —el
cronograma, con la ventana que le calculó el CPM a cada actividad— y **qué
lleva cada concepto** —la explosión del APU, `domain.catalogos.apu.explotar`—.
Nadie las cruzaba. Lo que sale de cruzarlas es la cifra con la que se compra:

    "¿cuánto cemento necesito la semana 22, y cuándo tengo que pedirlo?"

Este módulo hace ese cruce y nada más. No lee la base, no arma las consultas y
no decide el alcance: recibe las actividades ya cargadas, las explosiones ya
calculadas y los periodos ya construidos, y devuelve la matriz. Es puro
(§12.11), así que la aritmética se fija con pruebas sin levantar nada.

## Cómo se reparte una actividad entre periodos

Proporcional a los **días de trabajo** que la actividad tiene dentro de cada
periodo. Una actividad de diez días con seis en la semana 20 y cuatro en la 21
reparte 60/40.

Y de ahí la parte que importa: **una pausa no consume material**. Si el muro
trabaja dos semanas, para para que se cuele la losa y sigue otra semana (§7.6),
la semana de en medio lleva cero, no un tercio. Lo que se reparte son los
`tramos`, no el span.

Suponer otra curva —una S, un arranque lento— sería inventar información que
nadie capturó. El reparto uniforme sobre los días trabajados es la única
lectura que no añade nada.

## El gemelo en TypeScript, y por qué se copia

`frontend/src/programacion/reparto.ts` tiene esta misma aritmética
(`intervalosDeTrabajo`, `repartirEnPeriodos`) para repartir la **cantidad de
obra** en la rejilla del editor de programa base. Aquí se reparte el **insumo**
del cronograma real. Son dos consumidores de la misma regla en dos lenguajes, y
no hay forma de compartir el código: la del editor corre sobre un borrador en
memoria que nunca tocó el servidor. La duplicación es deliberada y está anotada
en las dos cabeceras; si una cambia, la otra tiene que cambiar.

## La anticipación

"Lo requiero diez días antes de la semana en que se usa" es la mitad útil del
módulo: sirve para **pedir**, no solo para saber. Se resuelve corriendo la
necesidad hacia atrás antes de bucketear —no moviendo la actividad—, con el
plazo del insumo (`insumo.dias_entrega`, migración 0044) y, si no lo tiene, con
la anticipación global que eligió quien consulta. El cemento llega en dos días
y la cancelería en seis semanas; un solo número para los dos serviría para uno.

## Lo que NO cuadra con `v_consumo_vs_presupuesto`, y es a propósito

Esa vista (§7.7) suma **un solo nivel** de `explosion`, unido por
`concepto_id`, y solo `categoria = 'material'`. Este módulo usa
`apu.explotar`, que **recurre** por auxiliares y matrices y cubre las cuatro
categorías. Con un concepto que cuelga de una matriz, la vista reporta de menos.
La definición correcta es la recursiva —es la que calcula el precio unitario—;
la vista queda desalineada y se corrige en su turno.

Módulo puro: recibe y devuelve dataclasses, no toca la BD ni el reloj (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from obractrl.domain.catalogos.apu import ExplosionCalculada, LineaExplosion
from obractrl.domain.programacion.cpm import Tramo

__all__ = [
    "ActividadConVentana",
    "FilaDeInsumo",
    "InsumoDelCatalogo",
    "MatrizDeInsumos",
    "Periodo",
    "Reparto",
    "insumos_programados",
    "intervalos_de_trabajo",
    "repartir_en_periodos",
]

_CERO = Decimal(0)

ESCALA_CANTIDAD = Decimal("0.000001")
"""Escala de `explosion.cantidad` y `actividad.cant_programada`
(`numeric(18,6)`, migraciones 0005 y 0007). El reparto cuadra en esta escala:
redondear más arriba haría que la suma de los periodos no diera el total."""


@dataclass(frozen=True, slots=True)
class ActividadConVentana:
    """Lo que una actividad le aporta al cálculo (§7.6).

    `cantidad` es la que se decidió usar —`cant_programada`— resuelta ya por el
    caso de uso: este módulo no elige entre columnas.

    `inicio` es `None` en una obra generada que todavía no se calendariza
    (`POST /obras/{id}/programa`). No es un error y no se descarta en silencio:
    sale reportada en `MatrizDeInsumos.sin_programar`.

    `concepto_clave` es `None` en una actividad extra-catálogo (§7.6): no tiene
    concepto, así que no tiene APU y no hay nada que explotar. Sale en
    `sin_explosion`.
    """

    actividad_id: str
    obra_id: str
    concepto_clave: str | None
    descripcion: str
    cantidad: Decimal
    inicio: date | None
    fin: date | None
    tramos: tuple[Tramo, ...] = ()


@dataclass(frozen=True, slots=True)
class Periodo:
    """Una columna de la tabla: su rango de fechas y cómo se rotula.

    `desde` es inclusivo y `hasta` **exclusivo**, igual que `dias_entre` de
    `CalendarioLaboral`: así dos periodos contiguos no se pelean el día que
    los separa.

    Quien los construye es el caso de uso, leyendo la tabla `calendario` —la
    numeración de semanas es de la organización (`ordinaria` lun→dom, `obra`
    jue→mié) y no ISO—, o generándolos relativos al día 1 cuando lo que se
    simula es un programa base, que es una plantilla sin fechas propias (§7.5).
    """

    clave: str
    desde: date
    hasta: date
    etiqueta: str


@dataclass(frozen=True, slots=True)
class InsumoDelCatalogo:
    """Lo que el catálogo aporta de un insumo (§10.1).

    `dias_entrega` en `None` significa "no capturado", que no es cero: cero
    sería "llega el mismo día". Sin capturar, manda la anticipación global.
    """

    insumo_id: str
    clave: str
    descripcion: str
    unidad: str | None
    tipo: str
    costo: Decimal = _CERO
    dias_entrega: int | None = None


@dataclass(frozen=True, slots=True)
class Reparto:
    """De dónde salió una parte del renglón: el desglose que se abre.

    Se agrega por `(obra, concepto)` y no por actividad: en una manzana de
    cuarenta casas el mismo concepto son cuarenta actividades, y listarlas
    todas convertiría el desglose en otra tabla que hay que sumar con la vista.
    """

    obra_id: str
    concepto_clave: str
    cantidad: Decimal


@dataclass(frozen=True, slots=True)
class FilaDeInsumo:
    """Un renglón de la tabla: un insumo, sus periodos y su total.

    `importe` es `None` cuando quien consulta no puede ver dinero: el borde
    decide eso por rol y este módulo solo respeta la decisión. `None` no es
    cero — un importe de cero pesos diría que el insumo es gratis.
    """

    insumo: InsumoDelCatalogo
    cantidades: tuple[Decimal, ...]
    total: Decimal
    importe: Decimal | None
    desglose: tuple[Reparto, ...]


@dataclass(frozen=True, slots=True)
class MatrizDeInsumos:
    """La tabla completa, más lo que quedó fuera y por qué.

    `sin_programar` y `sin_explosion` no son errores: una obra a medio
    configurar es el caso normal. Se reportan para que la pantalla lo diga en
    vez de enseñar una tabla corta sin explicación —mismo criterio que
    `ProgramaInstanciado.sin_item` (§7.5).
    """

    periodos: tuple[Periodo, ...]
    filas: tuple[FilaDeInsumo, ...]
    sin_programar: tuple[str, ...] = ()
    sin_explosion: tuple[str, ...] = ()


def intervalos_de_trabajo(
    inicio: date, fin: date, tramos: Sequence[Tramo]
) -> tuple[tuple[date, date], ...]:
    """Intervalos en que la actividad **trabaja**, en fechas.

    Sin tramos es uno solo, de `inicio` a `fin`. Con tramos son los tramos
    corridos al arranque, y lo que queda fuera son las pausas — que es toda la
    gracia: repartir sobre el span le daría material a las semanas en que la
    actividad está parada (§7.6).

    Los offsets de los tramos están en la escala del calendario del cronograma
    (`Tramo`), y aquí se suman como días corridos sobre `inicio`. Con semana
    laboral eso corre la pausa unos días —el domingo que cae en medio—, y es
    preferible a la alternativa: pedir el calendario aquí obligaría a este
    módulo a conocerlo para una diferencia que no cambia el total repartido,
    solo en qué semana cae el borde.
    """
    if fin <= inicio:
        return ()
    if not tramos:
        return ((inicio, fin),)

    salida: list[tuple[date, date]] = []
    for tramo in tramos:
        desde = inicio + timedelta(days=tramo.offset_dias)
        hasta = inicio + timedelta(days=tramo.fin_dias)
        if hasta > desde:
            salida.append((desde, hasta))
    return tuple(salida)


def repartir_en_periodos(
    intervalos: Sequence[tuple[date, date]],
    periodos: Sequence[Periodo],
    total: Decimal,
) -> tuple[Decimal, ...]:
    """Reparte `total` entre los periodos, proporcional a los días trabajados.

    Un periodo sin trabajo lleva `0` y no un hueco: cero es un dato —esa semana
    no se ocupa nada— y hueco sería "no se sabe".

    **El último periodo con trabajo se lleva el residuo.** Repartir 100 entre
    tres periodos deja 33.333333 tres veces, que suman 99.999999; el renglón
    diría un total distinto de la suma de sus columnas y quien lo lea pensaría
    que falta algo. El residuo va al último y no se prorratea: es un céntimo de
    unidad, y hacerlo visible en un solo lugar es más honesto que esparcirlo.
    """
    trabajo = sum((hasta - desde).days for desde, hasta in intervalos)
    if trabajo <= 0 or total == 0:
        return tuple(_CERO for _ in periodos)

    partes: list[Decimal] = []
    for periodo in periodos:
        dentro = 0
        for desde, hasta in intervalos:
            solape = (min(hasta, periodo.hasta) - max(desde, periodo.desde)).days
            if solape > 0:
                dentro += solape
        partes.append(
            _CERO
            if dentro == 0
            else (total * Decimal(dentro) / Decimal(trabajo)).quantize(ESCALA_CANTIDAD)
        )

    ultimo_con_trabajo = _ultimo_no_cero(partes)
    if ultimo_con_trabajo is None:
        return tuple(partes)

    repartido = sum(partes, _CERO)
    # Solo cuadra lo que de verdad cae dentro de la ventana de los periodos: si
    # la actividad se sale del rango consultado, su parte de fuera no se debe
    # empujar al último periodo visible.
    dentro_total = _dias_dentro(intervalos, periodos)
    if dentro_total == trabajo and repartido != total:
        partes[ultimo_con_trabajo] += total - repartido
    return tuple(partes)


def insumos_programados(
    *,
    actividades: Sequence[ActividadConVentana],
    explosiones: Mapping[str, ExplosionCalculada],
    catalogo: Mapping[str, InsumoDelCatalogo],
    periodos: Sequence[Periodo],
    tipos: frozenset[str] | None = None,
    dias_anticipacion: int = 0,
    con_importe: bool = True,
) -> MatrizDeInsumos:
    """La matriz insumo × periodo del cronograma recibido.

    ``explosiones`` mapea clave de concepto → su explosión ya calculada
    (`apu.explotar`); ``catalogo`` mapea clave de insumo → lo que el catálogo
    sabe de él. Un insumo que la explosión nombra y el catálogo no conoce se
    salta: no hay unidad, ni tipo, ni con qué rotularlo.

    ``tipos`` filtra por `insumo.tipo`; `None` los trae los cuatro.
    ``con_importe`` es la decisión de rol que ya tomó el borde.
    """
    acumulado: dict[str, list[Decimal]] = {}
    desglose: dict[str, dict[tuple[str, str], Decimal]] = {}
    sin_programar: list[str] = []
    sin_explosion: list[str] = []

    for actividad in actividades:
        if actividad.concepto_clave is None:
            sin_explosion.append(actividad.actividad_id)
            continue
        explosion = explosiones.get(actividad.concepto_clave)
        if explosion is None:
            sin_explosion.append(actividad.actividad_id)
            continue
        if actividad.inicio is None or actividad.fin is None:
            sin_programar.append(actividad.actividad_id)
            continue

        intervalos = intervalos_de_trabajo(
            actividad.inicio, actividad.fin, actividad.tramos
        )
        if not intervalos:
            sin_programar.append(actividad.actividad_id)
            continue

        for linea in explosion.lineas:
            insumo = _insumo_de(linea, catalogo, tipos)
            if insumo is None:
                continue

            cantidad = actividad.cantidad * linea.cantidad
            if cantidad == 0:
                continue

            # La anticipación corre la NECESIDAD, no la actividad: se pide
            # antes, se usa cuando toca. Por eso se desplazan los intervalos y
            # no las fechas de la actividad, que siguen siendo las del CPM.
            plazo = (
                insumo.dias_entrega
                if insumo.dias_entrega is not None
                else dias_anticipacion
            )
            adelantados = _adelantar(intervalos, plazo)

            partes = repartir_en_periodos(adelantados, periodos, cantidad)
            fila = acumulado.setdefault(
                insumo.insumo_id, [_CERO for _ in periodos]
            )
            for i, parte in enumerate(partes):
                fila[i] += parte

            aportado = sum(partes, _CERO)
            if aportado != 0:
                clave = (actividad.obra_id, actividad.concepto_clave)
                por_origen = desglose.setdefault(insumo.insumo_id, {})
                por_origen[clave] = por_origen.get(clave, _CERO) + aportado

    por_id = {insumo.insumo_id: insumo for insumo in catalogo.values()}
    filas = tuple(
        sorted(
            (
                _fila(
                    insumo=por_id[insumo_id],
                    cantidades=cantidades,
                    desglose=desglose.get(insumo_id, {}),
                    con_importe=con_importe,
                )
                for insumo_id, cantidades in acumulado.items()
            ),
            key=lambda fila: (fila.insumo.tipo, fila.insumo.clave),
        )
    )

    return MatrizDeInsumos(
        periodos=tuple(periodos),
        filas=filas,
        sin_programar=tuple(sin_programar),
        sin_explosion=tuple(sin_explosion),
    )


def _fila(
    *,
    insumo: InsumoDelCatalogo,
    cantidades: Sequence[Decimal],
    desglose: Mapping[tuple[str, str], Decimal],
    con_importe: bool,
) -> FilaDeInsumo:
    total = sum(cantidades, _CERO)
    return FilaDeInsumo(
        insumo=insumo,
        cantidades=tuple(cantidades),
        total=total,
        importe=(total * insumo.costo) if con_importe else None,
        desglose=tuple(
            sorted(
                (
                    Reparto(
                        obra_id=obra_id, concepto_clave=concepto, cantidad=cantidad
                    )
                    for (obra_id, concepto), cantidad in desglose.items()
                ),
                # De mayor a menor: el desglose se abre para saber quién pide
                # tanto, y esa respuesta está arriba.
                key=lambda r: (-r.cantidad, r.concepto_clave),
            )
        ),
    )


def _insumo_de(
    linea: LineaExplosion,
    catalogo: Mapping[str, InsumoDelCatalogo],
    tipos: frozenset[str] | None,
) -> InsumoDelCatalogo | None:
    """El insumo de una línea de explosión, si aplica.

    Solo las hojas `insumo` cuentan: una línea `concepto` es un auxiliar o una
    matriz, y sus insumos ya vienen desglosados más abajo en el mismo árbol —
    sumarla contaría dos veces lo mismo.
    """
    if linea.tipo_hijo != "insumo":
        return None
    insumo = catalogo.get(linea.referencia)
    if insumo is None:
        return None
    if tipos is not None and insumo.tipo not in tipos:
        return None
    return insumo


def _adelantar(
    intervalos: Sequence[tuple[date, date]], dias: int
) -> tuple[tuple[date, date], ...]:
    """Corre los intervalos `dias` hacia atrás. Cero los deja como están."""
    if dias == 0:
        return tuple(intervalos)
    delta = timedelta(days=dias)
    return tuple((desde - delta, hasta - delta) for desde, hasta in intervalos)


def _dias_dentro(
    intervalos: Sequence[tuple[date, date]], periodos: Sequence[Periodo]
) -> int:
    """Días de trabajo que caen dentro de la ventana consultada."""
    if not periodos:
        return 0
    principio = min(periodo.desde for periodo in periodos)
    final = max(periodo.hasta for periodo in periodos)
    total = 0
    for desde, hasta in intervalos:
        solape = (min(hasta, final) - max(desde, principio)).days
        if solape > 0:
            total += solape
    return total


def _ultimo_no_cero(partes: Sequence[Decimal]) -> int | None:
    for indice in range(len(partes) - 1, -1, -1):
        if partes[indice] != 0:
            return indice
    return None
