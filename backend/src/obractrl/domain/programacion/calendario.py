"""Calendario del cronograma: semana laboral o semana natural.

Spec §6 (ruta crítica) · §7.5 (ProgramaBase · ProgramaObra) · §5.1 (Control de
obra administra la programación) · §12.11.

## El problema que resuelve

El motor CPM razona en **números de día**: la actividad arranca en el día 12 y
dura 5. Convertir esos números a fechas era, hasta aquí, sumar días corridos —
`fecha_inicio + 12 días`—, que es una **semana natural**: sábado y domingo
cuentan como días de trabajo. En obra no es así. Una actividad de 5 días que
arranca lunes termina el viernes, no el miércoles siguiente.

Este módulo es la única pieza que sabe traducir entre las dos escalas. El motor
sigue siendo aritmética entera sobre índices de día y **no cambia**: el
calendario entra sólo en el borde, cuando un índice se vuelve una fecha.

## Semana natural = caso particular, no caso especial

`SEMANA_NATURAL` es el calendario cuyos días hábiles son los siete. No hay una
rama "sin calendario": con los siete días ningún día se salta, el índice de día
hábil coincide con el de día corrido y la conversión degenera **exactamente**
en la suma de `timedelta` que el motor hacía antes. Por eso es el default en
todos lados y por eso no puede haber una regresión escondida: no hay dos
implementaciones que se puedan desincronizar.

`SEMANA_LABORAL` es lunes a sábado, que es la semana normal de obra en México —
no lunes a viernes. Es sólo un valor sugerido: los días hábiles son
configurables porque hay frentes que trabajan domingo y cuadrillas que
descansan sábado.

## Qué significa cada cifra bajo cada calendario

Todas las cifras de días del contexto Programación —`duracion_dias`, el
`lag_dias` de una dependencia, el `offset_dias` de un tramo, la holgura y el
desfase— viven en la **misma escala que el calendario del cronograma**:

* Semana natural: son días corridos. Un lag de 2 son dos días de calendario.
* Semana laboral: son días **hábiles**. Un lag de 2 son dos días de trabajo, y
  si caen encima de un domingo la fecha resultante se corre lo que haga falta.

Que todas compartan escala no es un detalle: la holgura sólo se puede comparar
con el desfase —"el atraso ya se comió la holgura", §6— si las dos cuentan lo
mismo. Mezclar días hábiles con días corridos daría una alerta que se dispara
cuando no debe cada vez que un fin de semana cae en medio.

## Días festivos

No están, y es deliberado: son otra cosa —un calendario de excepciones con
fechas concretas, no un patrón semanal. Cuando entren, lo hacen como un
conjunto de fechas no laborables que este mismo objeto reste encima del patrón
(`es_habil` es el único punto que tendría que consultarlo); ni el motor ni el
significado de ninguna de las cifras de arriba cambian.

Módulo puro: no toca la BD ni el reloj (§12.11).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

__all__ = [
    "DIAS_DE_LA_SEMANA",
    "SEMANA_LABORAL",
    "SEMANA_NATURAL",
    "CalendarioInvalidoError",
    "CalendarioLaboral",
]

DIAS_DE_LA_SEMANA = (1, 2, 3, 4, 5, 6, 7)
"""Numeración ISO-8601: 1 = lunes … 7 = domingo.

Es la de `date.isoweekday()` y la de `isodow` en Postgres. No se usa
`extract(dow)` (0 = domingo) porque ahí el domingo rompe el orden natural y la
semana laboral típica dejaría de ser un rango contiguo.
"""

_LUNES_EPOCA = date(1, 1, 1)
"""Ancla del eje global de días hábiles. `date(1, 1, 1)` es lunes en el
calendario proléptico gregoriano que usa Python (`toordinal() == 1`), así que
`toordinal() - 1` da directamente los días transcurridos desde un lunes y el
resto de la semana sale de un `divmod` sin correcciones."""


class CalendarioInvalidoError(ValueError):
    """El conjunto de días hábiles no describe una semana de trabajo."""


@dataclass(frozen=True, slots=True)
class CalendarioLaboral:
    """Qué días de la semana cuentan como trabajo (§7.5).

    `dias_habiles` es una tupla **ordenada y sin repetidos** de días ISO; usa
    `de()` para construirlo desde cualquier iterable, que es lo que hace la
    normalización. Un calendario vacío no existe: un cronograma sin ningún día
    hábil no termina nunca.
    """

    dias_habiles: tuple[int, ...] = DIAS_DE_LA_SEMANA

    _acumulado: tuple[int, ...] = field(
        init=False, repr=False, compare=False, default=()
    )
    """Tabla derivada, no un segundo dato: `_acumulado[i]` = días hábiles entre
    el lunes y el i-ésimo día de la semana, sin contarlo. Ocho entradas, de 0
    (lunes) a 7 (semana completa). Se precalcula una vez porque el motor
    convierte cuatro fechas por actividad y una obra grande trae decenas de
    miles; queda fuera de `compare` para que la identidad del calendario siga
    siendo sólo su conjunto de días."""

    def __post_init__(self) -> None:
        dias = self.dias_habiles
        if not dias:
            raise CalendarioInvalidoError(
                "Un calendario sin días hábiles no programa nada: un cronograma "
                "en el que no se trabaja ningún día de la semana no termina "
                "nunca (§7.5)."
            )
        if any(dia not in DIAS_DE_LA_SEMANA for dia in dias):
            raise CalendarioInvalidoError(
                f"Los días hábiles se numeran del 1 (lunes) al 7 (domingo) en "
                f"ISO-8601; llegó {list(dias)} (§7.5)."
            )
        if list(dias) != sorted(set(dias)):
            raise CalendarioInvalidoError(
                f"Los días hábiles vienen ordenados y sin repetirse; llegó "
                f"{list(dias)}. Usa `CalendarioLaboral.de()` para normalizarlos."
            )

        habiles = 0
        tabla = [0]
        for iso in DIAS_DE_LA_SEMANA:
            if iso in dias:
                habiles += 1
            tabla.append(habiles)
        object.__setattr__(self, "_acumulado", tuple(tabla))

    @classmethod
    def de(cls, dias: Iterable[int] | None) -> CalendarioLaboral:
        """Calendario desde cualquier iterable de días ISO, ya normalizado.

        `None` es semana natural: es lo que devuelve la BD cuando el cronograma
        no existe todavía, y es el default que conserva el comportamiento
        histórico del motor.
        """
        if dias is None:
            return SEMANA_NATURAL
        return cls(tuple(sorted({int(dia) for dia in dias})))

    @property
    def es_natural(self) -> bool:
        """Se trabajan los siete días: días hábiles y días corridos coinciden."""
        return self.dias_habiles == DIAS_DE_LA_SEMANA

    def a_lista(self) -> list[int]:
        """Forma en que viaja a la BD (`smallint[]`) y a la API."""
        return list(self.dias_habiles)

    def es_habil(self, dia: date) -> bool:
        """¿Se trabaja este día? Único punto que tendría que consultar un
        calendario de festivos el día que exista (ver el docstring del módulo)."""
        return dia.isoweekday() in self.dias_habiles

    def primer_habil(self, desde: date) -> date:
        """Primer día hábil en `desde` o después.

        Es el ancla del cronograma: una obra cuya `fecha_inicio` cae en domingo
        con semana laboral no arranca el domingo — arranca el lunes. Fijar el
        arranque en un día que nadie trabaja dejaría la primera actividad
        empezando y terminando el mismo día para el Gantt y para el residente.
        """
        for _ in range(7):
            if self.es_habil(desde):
                return desde
            desde += timedelta(days=1)
        raise AssertionError(  # pragma: no cover - __post_init__ lo impide
            "Un calendario con al menos un día hábil siempre encuentra uno en "
            "siete intentos."
        )

    # --- Eje global de días hábiles --------------------------------------
    #
    # Internamente el módulo numera TODOS los días hábiles de la historia desde
    # `_LUNES_EPOCA`. Con ese índice global, las dos operaciones que el motor
    # necesita —fecha de un índice, distancia entre dos fechas— son aritmética
    # de `divmod` en O(1), sin recorrer día por día. Importa: el CPM convierte
    # cuatro fechas por actividad y una obra grande trae decenas de miles.

    def _indice_global(self, dia: date) -> int:
        """Cuántos días hábiles hay antes de `dia` desde `_LUNES_EPOCA`.

        Con semana natural es exactamente `dia.toordinal() - 1`, lo que hace
        que `dias_entre` degenere en la resta de fechas de siempre.
        """
        semanas, resto = divmod(dia.toordinal() - _LUNES_EPOCA.toordinal(), 7)
        return semanas * len(self.dias_habiles) + self._acumulado[resto]

    def _fecha_de_indice(self, indice: int) -> date:
        """Inversa de `_indice_global` sobre los días hábiles."""
        semanas, resto = divmod(indice, len(self.dias_habiles))
        return date.fromordinal(
            _LUNES_EPOCA.toordinal() + semanas * 7 + self.dias_habiles[resto] - 1
        )

    # --- Lo que consume el motor -----------------------------------------

    def conversor(self, fecha_inicio: date) -> Callable[[float], date]:
        """Función que traduce un índice de día del CPM a una fecha.

        El índice es relativo al arranque del cronograma —día 0 = la primera
        fecha en que se trabaja— y **puede ser negativo**: el backward pass
        produce inicios tardíos anteriores al arranque cuando hay lags
        negativos, y esa fecha tiene que ser real para que el Gantt la dibuje.

        Es una fábrica y no un método suelto porque fija el ancla una sola vez
        por cálculo, en vez de recalcularla en cada una de las cuatro fechas de
        cada actividad.

        Con semana natural devuelve literalmente `fecha_inicio + timedelta(...)`,
        que es la expresión que el motor tenía antes de que existiera este
        módulo. No es una optimización: es la garantía de que el default no
        mueve ni un día, ni siquiera en los redondeos de un índice fraccionario.
        """
        if self.es_natural:
            return lambda indice: fecha_inicio + timedelta(days=indice)

        base = self._indice_global(self.primer_habil(fecha_inicio))

        def convertir(indice: float) -> date:
            return self._fecha_de_indice(base + _dias_enteros(indice))

        return convertir

    def dias_entre(self, desde: date, hasta: date) -> int:
        """Días hábiles de `desde` a `hasta`, con signo (`hasta` no se cuenta).

        Es la escala en la que el motor mide el **desfase**: "lleva tres días de
        atraso" son tres días de trabajo perdidos, no tres casillas del
        calendario, y así se puede comparar contra la holgura (§6).

        Con semana natural es exactamente `(hasta - desde).days`.
        """
        if self.es_natural:
            return (hasta - desde).days
        return self._indice_global(hasta) - self._indice_global(desde)


def _dias_enteros(indice: float) -> int:
    """Parte entera de un índice de día, como la calculaba `timedelta`.

    Las duraciones son `numeric(8,2)` y los lags viajan como float, así que un
    índice puede salir fraccionario (8.3 días) o casi entero por acumulación de
    error (19.999999999999996). `date + timedelta(days=x)` se queda con
    `timedelta.days`, que redondea a microsegundos y **después** trunca hacia
    abajo; reimplementarlo con `math.floor` daría un día distinto justo en esos
    casos límite. Se delega en `timedelta` para que las dos escalas partan el
    día exactamente igual.
    """
    return timedelta(days=indice).days


SEMANA_NATURAL = CalendarioLaboral(DIAS_DE_LA_SEMANA)
"""Los siete días cuentan: el comportamiento histórico del motor y el default
en la BD, en el dominio y en la API (§6)."""

SEMANA_LABORAL = CalendarioLaboral((1, 2, 3, 4, 5, 6))
"""Lunes a sábado: la semana de trabajo normal en obra en México.

Es un valor sugerido, no el único "laboral" posible — de ahí que el dato que se
guarda sea el conjunto de días y no un boolean (migración 0040).
"""
