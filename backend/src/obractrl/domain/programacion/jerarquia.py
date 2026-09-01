"""Programación jerárquica sobre el árbol WBS (§7.4, §7.5, §7.6, §6).

Spec §6 (ruta crítica) · §7.4 (árbol WBS) · §7.5 (ProgramaBase · ProgramaObra) ·
§7.6 (campos de programación de la Actividad) · §11.2 · §12.11.

## El pedido

El jefe de obra lo dijo así: *"la programación debe funcionar como el árbol WBS,
por nivel y hereda a los parientes y viceversa, si se modifica el pariente
modifica al padre, lo mismo para etapas y conceptos, se pueden programar por
niveles, por etapas y por conceptos o se puede elegir los niveles de
profundidad"*. Es el comportamiento de las **tareas resumen** de MS Project: se
planea grueso —20 días para toda la etapa `ESTRUCTURA PB`— y eso baja al
detalle, o se planea fino —el muro 10, el castillo 8, la cadena 5— y eso sube al
resumen.

## El hecho del modelo que este módulo NO rompe

Al generar una obra (§11.3 A.2, `domain.obras.generacion`) **sólo las hojas de
tipo `concepto` se vuelven `Actividad`**. `nivel` y `etapa` son estructura: sólo
agrupan y heredan `nivel_id`/`etapa_id` al concepto de abajo.

Eso se queda igual. Las barras de nivel y de etapa son **derivadas**, no filas
nuevas de `actividad`: si el resumen fuera una actividad más, su cantidad, su
avance y su costo se sumarían encima de los de sus hijos y el §6 (avance
ponderado) y el §7.6 (cantidades) contarían todo dos veces. Por eso aquí no se
crea nada: se reparte hacia abajo sobre las hojas que ya existen y se resume
hacia arriba sin persistir el resumen.

## Las dos direcciones

**Hacia abajo — reparto secuencial.** Programar 20 días en una etapa con ocho
conceptos debajo los acomoda **uno tras otro** dentro de esos 20 días. Los días
se reparten en proporción al **importe** de cada concepto (`cant_base ×
precio_unitario`), no en partes iguales: el muro de $122k se lleva más días que
el castillo de $10k, que es como se comporta la obra de verdad. Sin importes
—una obra sin presupuesto, o todos en cero— el reparto es igual para todos, que
es la única repartición defendible cuando no hay con qué distinguirlos.

`repartir_ventana` recibe los **pesos ya calculados**, no las hojas: quién
decide el peso es del llamador. Hoy lo decide `pesos_por_importe`; el día que se
derive la duración de `cantidad ÷ rendimiento del destajo` —el muro de 317 m² a
20 m²/día son 16 días, que es lo que el usuario quiere después— entra como otra
función que produce pesos y el reparto no se toca.

**Hacia arriba — rollup.** Un nodo con hijos programados deriva de ellos:
inicio = el más temprano, fin = el más tardío, duración = ese span, y avance =
el **ponderado por importe** de sus hojas. Ponderado y no promedio simple porque
un promedio simple diría que la etapa va al 50 % cuando el muro de $122k está en
cero y el castillo de $10k terminado (§6, avance por peso).

## El conflicto no se resuelve solo

Si la etapa trae 20 días capturados y sus conceptos ya suman lo suyo (10+8+5=23),
**ninguna de las dos cifras gana en silencio**: `resumir_arbol` marca el nodo en
conflicto y el usuario elige, caso por caso, cuál conservar. Que el padre pisara
al hijo borraría un ajuste fino que alguien capturó a propósito; que el hijo
ganara volvería inútil la captura gruesa. Es un aviso no bloqueante —el mismo
criterio que `ProgramaInstanciado.sin_item` (§7.5)—, no un pendiente de la
bandeja (§10.3): un pendiente sobrevive a la sesión y necesita quien lo cierre,
y este conflicto desaparece en cuanto el usuario toca cualquiera de las dos
cifras. Materializarlo como fila sería inventarle un ciclo de vida a un cálculo.

Módulo puro: recibe y devuelve dataclasses, no toca la BD ni el reloj (§12.11).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal

from obractrl.domain.programacion.calendario import (
    SEMANA_NATURAL,
    CalendarioLaboral,
)
from obractrl.domain.programacion.reglas import (
    DURACION_POR_DEFECTO,
    ErrorDeProgramacion,
)
from obractrl.domain.shared.diccionario import ClaseNodo

__all__ = [
    "MINIMO_REPARTIBLE",
    "Colocacion",
    "ConflictoJerarquia",
    "ErrorDeJerarquia",
    "HojaProgramable",
    "NodoWBS",
    "ResumenNodo",
    "es_captura_manual",
    "hojas_por_nodo",
    "nodos_capturables",
    "pesos_por_importe",
    "repartir_secuencial",
    "repartir_ventana",
    "resumir_arbol",
]

MINIMO_REPARTIBLE = Decimal("0.01")
"""Piso de la duración que le puede tocar a una hoja en un reparto.

`actividad.duracion_dias` es un `numeric(8,2)` con `check (duracion_dias > 0)`
(migración 0007), así que una centésima de día es literalmente el valor positivo
más chico que la columna sabe guardar. Redondear por debajo de eso no dejaría
una actividad "de cero días": dejaría un `INSERT` que revienta contra el check.
"""

_CENTESIMA = Decimal("0.01")
"""Escala de `numeric(8,2)`. El reparto cuadra en esta escala y no en la de
`Decimal` completo: si repartiera con precisión infinita, la suma de lo que se
escribe —ya recortado por la columna— no daría la ventana."""


class ErrorDeJerarquia(ErrorDeProgramacion):
    """El reparto o el resumen pedido no es realizable (§7.5).

    Hereda de `ErrorDeProgramacion` a propósito: para el borde de la API es el
    mismo 422 que cualquier otra programación inválida (§11.2), y los casos de
    uso que ya atrapan `ErrorDeProgramacion` —la replicación masiva, por
    ejemplo— no necesitan aprender un tipo nuevo para seguir siendo de mejor
    esfuerzo.
    """


# --- Lo que el módulo necesita saber del árbol y de sus hojas -------------


@dataclass(frozen=True, slots=True)
class NodoWBS:
    """Un nodo del árbol del prototipo visto por la programación (§7.4).

    Es la misma fila que `RepositorioObras.arbol_prototipo` sirve y que consume
    `domain.obras.generacion.NodoPrototipo`, recortada a lo que la jerarquía
    necesita: aquí no interesan la cantidad ni el concepto —esos ya viajan en la
    hoja—, sólo quién cuelga de quién y de qué tipo es cada quien.

    Llega en recorrido en profundidad, padre antes que hijos, que es como lo
    ordena el repositorio.
    """

    id: str
    tipo: ClaseNodo
    nombre: str
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class HojaProgramable:
    """Una `Actividad` colgada de su nodo del árbol (§7.6).

    Es la hoja `concepto` del §11.3 A.2 con lo que la jerarquía mira: de dónde
    cuelga, cuánto vale y cómo va programada hoy.

    `importe` es `cant_base × precio_unitario` de la propia actividad y no una
    lectura del `partida_presupuesto` vigente, aunque las dos cifras sean la
    misma en origen: la actividad **es** el registro que la obra guarda de ese
    importe (lo copió el workflow A del CPU vigente, §11.3 A.2), y leerlo de ahí
    evita cruzar la frontera al contexto Presupuesto por un dato que ya se tiene
    (§11.1). De regalo, un extra de catálogo (§5.1) —que nunca estuvo en el
    presupuesto— también pesa lo que vale en vez de pesar cero.
    """

    actividad_id: str
    prototipo_nodo_id: str | None = None
    importe: Decimal = Decimal(0)
    duracion_dias: Decimal = DURACION_POR_DEFECTO
    fecha_inicio: date | None = None
    fecha_termino: date | None = None
    """Las fechas **capturadas** de la actividad (§7.6). `None` es "nadie las
    ha fijado", y ese `None` es información: es lo que distingue una hoja que
    alguien programó de una recién generada (`es_captura_manual`)."""
    inicio_calculado: date | None = None
    termino_calculado: date | None = None
    """Las fechas que **derivó el motor** para esta actividad (§6).

    Van aparte y no rellenando las de arriba, aunque para dibujar la barra sean
    intercambiables, porque para decidir si hay conflicto **no** lo son: si el
    inicio temprano del CPM se guardara como si fuera captura, toda actividad de
    toda obra pasaría por "programada a mano" —el motor siempre da una fecha— y
    el aviso del §7.5 saldría en cada nodo de cada obra desde el primer día.
    """
    avance_pct: Decimal = Decimal(0)

    @property
    def programada_a_mano(self) -> bool:
        """¿Alguien capturó la programación de esta hoja? (`es_captura_manual`)"""
        return es_captura_manual(
            duracion_dias=self.duracion_dias,
            fecha_inicio=self.fecha_inicio,
            fecha_termino=self.fecha_termino,
        )

    @property
    def inicio_efectivo(self) -> date | None:
        """Con qué fecha se dibuja: manda lo capturado y el motor cubre el hueco."""
        return self.fecha_inicio or self.inicio_calculado

    @property
    def termino_efectivo(self) -> date | None:
        return self.fecha_termino or self.termino_calculado


def es_captura_manual(
    *,
    duracion_dias: Decimal,
    fecha_inicio: date | None,
    fecha_termino: date | None,
) -> bool:
    """¿La programación de una hoja la puso una persona? (§7.6)

    No hay una columna que lo diga, y agregarla sería guardar un dato que sólo
    sirve para este aviso. Lo que sí distingue es la **huella** de la captura:
    una actividad recién generada sin plantilla nace con la duración por defecto
    y sin fechas (§11.3 A.2, `DURACION_POR_DEFECTO`), así que cualquier
    desviación de ese estado —otra duración, o fechas ya fijadas— es alguien que
    programó, sea a mano por el `PATCH` (§11.2) o bajando el programa base.

    El falso negativo es conocido y es el inofensivo: una hoja que de verdad
    dura un día y no trae fechas se deja repartir sin avisar. El falso positivo
    —marcar un conflicto donde nadie capturó nada— sería el caro, porque
    llenaría de avisos la primera programación de cada obra.
    """
    if fecha_inicio is not None or fecha_termino is not None:
        return True
    return duracion_dias != DURACION_POR_DEFECTO


# --- Hacia abajo: el reparto secuencial -----------------------------------


@dataclass(frozen=True, slots=True)
class Colocacion:
    """Dónde queda una hoja dentro de la ventana de su nodo padre.

    `offset_dias` se mide desde el arranque de la ventana y en la escala del
    calendario del cronograma, igual que el `offset_dias` de un `Tramo` (§7.6):
    con semana laboral son días hábiles.
    """

    actividad_id: str
    duracion_dias: Decimal
    offset_dias: Decimal
    fecha_inicio: date
    fecha_termino: date
    """Día en que la hoja deja de ocupar el calendario, **exclusivo**, igual que
    el `fin_temprano` del motor (`cpm.calcular_cpm`): una hoja de un día tiene
    `fecha_termino = fecha_inicio + 1`. Es la convención que ya dibuja el Gantt
    y la que hace que la suma de las colocaciones cierre exactamente en el fin
    de la ventana, sin un día de sobra por cada hoja."""


def pesos_por_importe(
    hojas: Sequence[HojaProgramable],
) -> tuple[tuple[str, Decimal], ...]:
    """Peso de cada hoja para el reparto: su importe (§7.3, §6).

    Decisión tomada con el usuario: los días de una ventana gruesa se reparten
    en proporción a `cantidad × precio unitario`, no en partes iguales. El muro
    de $122 000 se lleva más días que el castillo de $10 000 porque en obra
    efectivamente los lleva.

    Es **una** manera de pesar, no la única prevista: la siguiente que el
    usuario quiere es `cantidad ÷ rendimiento del destajo` —el muro de 317 m² a
    20 m²/día son 16 días, y `rendimiento` ya existe en el catálogo de mano de
    obra—. Por eso lo que `repartir_ventana` recibe son los pesos y no las
    hojas: meter esa regla es escribir otra función de esta forma, no rehacer el
    reparto.
    """
    return tuple((hoja.actividad_id, max(hoja.importe, Decimal(0))) for hoja in hojas)


def repartir_ventana(
    ventana_dias: Decimal, pesos: Sequence[tuple[str, Decimal]]
) -> tuple[tuple[str, Decimal], ...]:
    """Parte una ventana de días entre varios sujetos, en proporción a su peso.

    Devuelve `(clave, dias)` en el mismo orden en que llegaron los pesos, y la
    suma de los `dias` es **exactamente** `ventana_dias` redondeada a la escala
    de la columna (`numeric(8,2)`): la ventana que el usuario capturó es la que
    tiene que ocupar el conjunto, y un reparto que dejara medio día suelto haría
    que el resumen del padre no reprodujera la cifra que él mismo escribió.

    Para que cuadre, cada parte se **trunca** a centésimas y el residuo que
    sobra por el truncamiento se le da al de mayor peso. Repartir el residuo
    entre varios lo volvería a partir en fracciones que no caben en la columna;
    dárselo al más grande lo diluye donde menos se nota.

    Sin pesos utilizables —lista de ceros, o negativos— el reparto es **igual
    para todos**: es lo único defendible cuando no hay con qué distinguirlos, y
    es el caso real de una obra que todavía no tiene presupuesto cargado.

    Raises:
        ErrorDeJerarquia: sin sujetos que repartir, con una ventana no positiva,
            o cuando la ventana no alcanza ni para darle a cada uno el mínimo
            que la columna sabe guardar (`MINIMO_REPARTIBLE`).
    """
    if not pesos:
        raise ErrorDeJerarquia(
            "No hay nada debajo de este nodo que programar: una ventana sólo se "
            "reparte entre las hojas que cuelgan de él (§7.4)."
        )

    ventana = Decimal(ventana_dias).quantize(_CENTESIMA, rounding=ROUND_DOWN)
    if ventana <= 0:
        raise ErrorDeJerarquia(
            f"La ventana de {ventana_dias} días no es programable: la duración "
            f"de un nodo del árbol debe ser positiva, igual que la de una "
            f"actividad (§7.5)."
        )

    minimo_total = MINIMO_REPARTIBLE * len(pesos)
    if ventana < minimo_total:
        raise ErrorDeJerarquia(
            f"La ventana de {ventana} días no alcanza para los {len(pesos)} "
            f"conceptos que cuelgan del nodo: a cada uno le tocarían menos de "
            f"{MINIMO_REPARTIBLE} días, que es lo mínimo que el cronograma sabe "
            f"guardar. Programa menos profundo o alarga la ventana (§7.6)."
        )

    total = sum((peso for _, peso in pesos if peso > 0), Decimal(0))
    if total <= 0:
        # Sin presupuesto o con todos los importes en cero: partes iguales. No
        # se falla —una obra sin presupuesto cargado tiene que poder programarse
        # igual— ni se inventa un orden de importancia que nadie capturó.
        efectivos = [(clave, Decimal(1)) for clave, _ in pesos]
        total = Decimal(len(pesos))
    else:
        # Un peso no positivo dentro de un conjunto que sí tiene importes no se
        # queda sin días: recibe el mínimo y compite por el residuo como
        # cualquier otro. Darle cero sería escribir una duración que el check de
        # la columna rechaza.
        efectivos = [(clave, max(peso, Decimal(0))) for clave, peso in pesos]

    partes: list[Decimal] = []
    for _, peso in efectivos:
        bruto = (ventana * peso / total).quantize(_CENTESIMA, rounding=ROUND_DOWN)
        partes.append(max(bruto, MINIMO_REPARTIBLE))

    residuo = ventana - sum(partes, Decimal(0))
    mayor = max(range(len(partes)), key=lambda i: (efectivos[i][1], -i))
    partes[mayor] += residuo
    if partes[mayor] < MINIMO_REPARTIBLE:
        # Sólo pasa cuando muchos pesos diminutos se subieron al mínimo y entre
        # todos se comieron la ventana. Es el mismo problema que el guardia de
        # arriba, visto después de repartir, y se reporta igual en vez de
        # escribir una duración inválida.
        raise ErrorDeJerarquia(
            f"La ventana de {ventana} días no alcanza para repartirse entre "
            f"{len(pesos)} conceptos con estos importes: los más chicos se "
            f"llevan el mínimo y no queda nada para el mayor (§7.6)."
        )

    return tuple(
        (clave, parte) for (clave, _), parte in zip(efectivos, partes, strict=True)
    )


def repartir_secuencial(
    *,
    hojas: Sequence[HojaProgramable],
    ventana_dias: Decimal,
    inicio: date,
    calendario: CalendarioLaboral = SEMANA_NATURAL,
    pesos: Sequence[tuple[str, Decimal]] | None = None,
) -> tuple[Colocacion, ...]:
    """Acomoda las hojas de un nodo **una tras otra** dentro de su ventana.

    Es la mitad "hacia abajo" del pedido: 20 días capturados en la etapa
    `ESTRUCTURA PB` con ocho conceptos debajo dejan a los ocho en fila, sin
    huecos ni traslapes, ocupando exactamente esos 20 días. Cada hoja arranca
    donde cerró la anterior, así que el `offset` de la hoja *k* es la suma de
    las duraciones de las *k−1* anteriores.

    **No se inventan dependencias.** La secuencia se expresa con fechas y
    duraciones, que es lo que el `PATCH` del §11.2 ya escribe y lo que el Gantt
    dibuja. Encadenar las ocho con aristas `FS` habría metido precedencias que
    nadie declaró: podrían chocar con las que el programa base sí trae, y
    bastaría una de vuelta para que el motor levantara `CicloEnGrafoError` sobre
    un cronograma que el usuario nunca escribió (§6).

    `pesos` permite pasar otro criterio de reparto; sin él pesa el importe
    (`pesos_por_importe`). `inicio` es el ancla de la ventana y `calendario` el
    del cronograma: con semana laboral los días que se saltan no se cuentan, ni
    en las duraciones ni en los offsets (§7.5, 0040).

    Raises:
        ErrorDeJerarquia: lo que levante `repartir_ventana`.
    """
    reparto = repartir_ventana(ventana_dias, pesos or pesos_por_importe(hojas))
    fecha_de = calendario.conversor(inicio)

    colocaciones: list[Colocacion] = []
    offset = Decimal(0)
    for actividad_id, dias in reparto:
        colocaciones.append(
            Colocacion(
                actividad_id=actividad_id,
                duracion_dias=dias,
                offset_dias=offset,
                fecha_inicio=fecha_de(float(offset)),
                fecha_termino=fecha_de(float(offset + dias)),
            )
        )
        offset += dias

    return tuple(colocaciones)


# --- Hacia arriba: el rollup ----------------------------------------------


@dataclass(frozen=True, slots=True)
class ConflictoJerarquia:
    """Un nodo cuya ventana capturada no cuadra con lo que traen sus hojas.

    No es un error: es la pregunta que hay que hacerle al usuario. Las dos
    cifras se devuelven las dos —`dias_capturados` y `dias_derivados`— porque la
    decisión es cuál conservar, y presentarle sólo una lo obligaría a ir a
    buscar la otra.
    """

    nodo_id: str
    nombre: str
    dias_capturados: Decimal
    """Los días que el programa base declara para este nodo del árbol (§7.5)."""
    dias_derivados: Decimal
    """El span que hoy ocupan sus hojas ya programadas (§6)."""
    actividades: tuple[str, ...]
    """Las hojas programadas a mano que están en desacuerdo con la ventana. Son
    las que el usuario perdería si decidiera conservar la cifra del padre."""


@dataclass(frozen=True, slots=True)
class ResumenNodo:
    """La barra resumen de un nodo `nivel` o `etapa` (§7.4, §6).

    **Derivada, nunca persistida.** Todo lo de aquí se recalcula de las hojas
    cada vez que se pide: si el resumen se guardara, sería un segundo lugar
    donde vive la misma cifra y el primero en desincronizarse en cuanto alguien
    ajustara una actividad por el `PATCH` (§11.2).
    """

    nodo_id: str
    tipo: ClaseNodo
    nombre: str
    parent_id: str | None
    profundidad: int
    """Cuántos ancestros tiene, la raíz en 0. Es lo que deja "elegir los niveles
    de profundidad" sin depender de que el árbol ponga etapa arriba de nivel o
    al revés."""
    actividades: tuple[str, ...]
    """Las hojas que cuelgan de este nodo, a cualquier distancia."""
    fecha_inicio: date | None
    fecha_termino: date | None
    duracion_dias: Decimal
    """El **span** del resumen: los días de calendario entre el inicio más
    temprano y el fin más tardío de sus hojas, contados con el calendario del
    cronograma. No es la suma de las duraciones de las hojas —eso son días de
    trabajo, y dos conceptos que corren en paralelo sumarían el doble de lo que
    la etapa realmente ocupa (`duracion_hojas_dias` sí es esa suma)."""
    duracion_hojas_dias: Decimal
    """Suma de los días de **trabajo** de sus hojas. Coincide con el span
    cuando las hojas van una tras otra —que es como las deja el reparto— y es
    menor cuando se traslapan."""
    avance_pct: Decimal
    """Avance ponderado por importe (§6). Con todos los importes en cero es el
    promedio simple de las hojas: sin pesos, todas valen lo mismo."""
    importe: Decimal
    conflicto: ConflictoJerarquia | None = None


def hojas_por_nodo(
    nodos: Sequence[NodoWBS], hojas: Sequence[HojaProgramable]
) -> dict[str, tuple[HojaProgramable, ...]]:
    """Todas las hojas que cuelgan de cada nodo, a cualquier profundidad (§7.4).

    Una hoja cuenta para su nodo y para **todos** sus ancestros: la etapa resume
    lo que hay debajo de sus niveles, no sólo lo que le cuelga directo.

    Las hojas cuyo `prototipo_nodo_id` no está en el árbol se ignoran en vez de
    reventar: un extra de catálogo (§5.1) es una actividad real de la obra que
    no nació de ningún nodo del prototipo, y no tiene resumen al cual sumar.

    Raises:
        ErrorDeJerarquia: si el árbol tiene un nodo repetido o un ciclo.
    """
    indice: dict[str, NodoWBS] = {}
    for nodo in nodos:
        if nodo.id in indice:
            raise ErrorDeJerarquia(
                f"El árbol del prototipo trae el nodo {nodo.id!r} dos veces: no "
                f"se puede resumir (§7.4)."
            )
        indice[nodo.id] = nodo

    acumulado: dict[str, list[HojaProgramable]] = {nodo.id: [] for nodo in nodos}

    for hoja in hojas:
        actual = indice.get(hoja.prototipo_nodo_id or "")
        vistos: set[str] = set()
        while actual is not None:
            if actual.id in vistos:
                raise ErrorDeJerarquia(
                    f"El árbol del prototipo tiene un ciclo en el nodo "
                    f"{actual.id!r}: no se puede subir el resumen (§7.4)."
                )
            vistos.add(actual.id)
            acumulado[actual.id].append(hoja)
            actual = indice.get(actual.parent_id or "") if actual.parent_id else None

    return {nodo_id: tuple(lista) for nodo_id, lista in acumulado.items()}


def _profundidades(nodos: Sequence[NodoWBS]) -> dict[str, int]:
    """Distancia de cada nodo a su raíz. El árbol llega padre-antes-que-hijos
    (`RepositorioObras.arbol_prototipo`), así que una sola pasada basta."""
    profundidad: dict[str, int] = {}
    for nodo in nodos:
        if nodo.parent_id is None or nodo.parent_id not in profundidad:
            profundidad[nodo.id] = 0
        else:
            profundidad[nodo.id] = profundidad[nodo.parent_id] + 1
    return profundidad


def _avance_ponderado(hojas: Sequence[HojaProgramable]) -> Decimal:
    """Avance del resumen, pesado por importe (§6).

    Un promedio simple diría que la etapa va al 50 % con el muro de $122k en
    cero y el castillo de $10k terminado. Con importes en cero cae al promedio
    simple, que es lo correcto cuando ninguna hoja pesa más que otra.
    """
    if not hojas:
        return Decimal(0)

    total = sum((max(h.importe, Decimal(0)) for h in hojas), Decimal(0))
    if total <= 0:
        acumulado = sum((h.avance_pct for h in hojas), Decimal(0))
        return (acumulado / len(hojas)).quantize(_CENTESIMA)

    acumulado = sum(
        (max(h.importe, Decimal(0)) * h.avance_pct for h in hojas), Decimal(0)
    )
    return (acumulado / total).quantize(_CENTESIMA)


def resumir_arbol(
    *,
    nodos: Sequence[NodoWBS],
    hojas: Sequence[HojaProgramable],
    calendario: CalendarioLaboral = SEMANA_NATURAL,
    ventanas: Mapping[str, Decimal] | None = None,
) -> tuple[ResumenNodo, ...]:
    """Sube el cronograma de las hojas a las barras de nivel y etapa (§7.4, §6).

    Es la mitad "hacia arriba" del pedido: *"si se modifica el pariente modifica
    al padre"*. Cada nodo con hojas debajo saca su inicio del más temprano de
    ellas, su fin del más tardío, su duración de ese span y su avance del
    ponderado por importe.

    Devuelve un resumen por nodo **con hojas debajo**, en el orden en que llegó
    el árbol —recorrido en profundidad, padre antes que hijos—, que es el orden
    en que se dibuja el Gantt. Un nodo sin ninguna hoja no aparece: no hay nada
    que resumir y una barra vacía en el Gantt sólo estorba.

    `ventanas` son los días que el programa base declara para nodos del árbol
    —la captura gruesa por nivel o por etapa (§7.5)—. Cuando un nodo trae
    ventana y sus hojas ya vienen programadas a mano con otro span, el resumen
    sale con `conflicto`: las dos cifras, y las hojas que están en desacuerdo.
    Nada se corrige aquí — quién gana lo decide el usuario.

    Raises:
        ErrorDeJerarquia: si el árbol trae un nodo repetido o un ciclo.
    """
    por_nodo = hojas_por_nodo(nodos, hojas)
    profundidad = _profundidades(nodos)
    declaradas = ventanas or {}

    resumenes: list[ResumenNodo] = []
    for nodo in nodos:
        del_nodo = por_nodo[nodo.id]
        if not del_nodo:
            continue

        # La barra se dibuja con las fechas efectivas —capturadas, y el motor
        # cubriendo el hueco— para que una obra recién generada ya tenga
        # resumen. Una hoja sin ninguna de las dos no entra al span, pero sí
        # cuenta para el avance y el importe, que existen desde que la actividad
        # existe (§7.6).
        inicios = [h.inicio_efectivo for h in del_nodo if h.inicio_efectivo]
        fines = [h.termino_efectivo for h in del_nodo if h.termino_efectivo]
        inicio = min(inicios) if inicios else None
        fin = max(fines) if fines else None

        span = (
            Decimal(calendario.dias_entre(inicio, fin))
            if inicio is not None and fin is not None
            else Decimal(0)
        )
        trabajo = sum((h.duracion_dias for h in del_nodo), Decimal(0))

        resumenes.append(
            ResumenNodo(
                nodo_id=nodo.id,
                tipo=nodo.tipo,
                nombre=nodo.nombre,
                parent_id=nodo.parent_id,
                profundidad=profundidad.get(nodo.id, 0),
                actividades=tuple(h.actividad_id for h in del_nodo),
                fecha_inicio=inicio,
                fecha_termino=fin,
                duracion_dias=span,
                duracion_hojas_dias=trabajo,
                avance_pct=_avance_ponderado(del_nodo),
                importe=sum((h.importe for h in del_nodo), Decimal(0)),
                conflicto=_conflicto_de(
                    nodo=nodo,
                    hojas=del_nodo,
                    ventana=declaradas.get(nodo.id),
                    calendario=calendario,
                ),
            )
        )

    return tuple(resumenes)


def _conflicto_de(
    *,
    nodo: NodoWBS,
    hojas: Sequence[HojaProgramable],
    ventana: Decimal | None,
    calendario: CalendarioLaboral,
) -> ConflictoJerarquia | None:
    """El desacuerdo entre la ventana capturada de un nodo y sus hojas.

    Hacen falta las **dos** condiciones para avisar, y ninguna sobra:

    * que alguna hoja esté programada a mano (`es_captura_manual`). Sin eso, un
      árbol recién generado —todas las hojas en su día por defecto— dispararía
      un conflicto en cada etapa la primera vez que alguien abre la pantalla, y
      un aviso que sale siempre deja de leerse;
    * que las cifras difieran de verdad.

    La cifra derivada se calcula **sólo con lo capturado**, no con lo que el
    motor dedujo: se compara contra el span de las fechas que alguien fijó y,
    cuando nadie fijó ninguna, contra la suma de los días de trabajo —que es el
    "10+8+5 = 23" del pedido—. Si entrara aquí el inicio temprano del CPM, tres
    conceptos sin dependencias saldrían "en paralelo" y el desacuerdo se
    mediría contra 10 en vez de contra 23: una cifra que el usuario no capturó
    y que no reconocería.
    """
    if ventana is None:
        return None

    programadas = tuple(h for h in hojas if h.programada_a_mano)
    if not programadas:
        return None

    inicios = [h.fecha_inicio for h in hojas if h.fecha_inicio is not None]
    fines = [h.fecha_termino for h in hojas if h.fecha_termino is not None]
    if inicios and fines:
        derivado = Decimal(calendario.dias_entre(min(inicios), max(fines)))
    else:
        derivado = sum((h.duracion_dias for h in hojas), Decimal(0))

    if derivado == ventana:
        return None

    return ConflictoJerarquia(
        nodo_id=nodo.id,
        nombre=nodo.nombre,
        dias_capturados=ventana,
        dias_derivados=derivado,
        actividades=tuple(h.actividad_id for h in programadas),
    )


def nodos_capturables(
    nodos: Sequence[NodoWBS], profundidad: ClaseNodo
) -> tuple[str, ...]:
    """Los nodos del árbol en los que se captura a la profundidad elegida (§7.5).

    `profundidad` es la sugerencia guardada en `programa_base.profundidad_captura`
    (migración 0041): programar por nivel, por etapa o por concepto. Se resuelve
    por **tipo de nodo** y no por distancia a la raíz porque el árbol no siempre
    pone etapa arriba de nivel —el prototipo lo arma quien carga el presupuesto
    (§10.6)— y una regla por distancia diría cosas distintas en dos prototipos
    que se ven igual en pantalla.

    Es una **sugerencia**, no una jaula: el editor arranca aquí para que todo el
    equipo vea lo mismo, y cualquiera puede bajar a capturar más fino cuando le
    haga falta (`ResumenNodo.profundidad` le da con qué).
    """
    return tuple(nodo.id for nodo in nodos if nodo.tipo is profundidad)
