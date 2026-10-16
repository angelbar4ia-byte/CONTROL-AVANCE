"""Las nueve causas de CONOCIMIENTO.md §13.6 — el filtro ANTERIOR a `Desviacion`.

Spec: CONOCIMIENTO.md §13.6 "Las nueve causas, y quién paga cada una"
(líneas 8716-8732) · MODELO.md §5g, D-343 → D-347 (corrección explícita del
cerebro sobre sí mismo).

**Esto NO es el vocabulario de `causa` que persiste `Desviacion.causa`.**
Esa es :class:`obractrl.domain.shared.diccionario.CausaDesviacion`, un
vocabulario fino y distinto («mercado», «retrabajo», …) que vive en la base
como enum (migración 0054). Las nueve causas de aquí resuelven algo
ANTERIOR: si el hallazgo es siquiera una `Desviacion`, o si es otra cosa
("ejecutado sin respaldo", "orden de cambio", "programa"). Tratar ambos
vocabularios como uno solo fue exactamente el error D-343 que el propio
cerebro corrigió en D-347 (MODELO.md §5g) — por eso viven en módulos y con
nombres distintos, y por eso :class:`CausaRaiz` **no tiene migración ni
columna propia**: no es un invariante de la tabla `desviacion`, es el
criterio de negocio que decide si esa tabla recibe una fila.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "CausaRaiz",
    "DestinoHallazgo",
    "QuienPaga",
    "destino_de_causa",
    "quien_paga",
]


class CausaRaiz(StrEnum):
    """Las nueve causas de CONOCIMIENTO.md §13.6 (líneas 8722-8732).

    "Lo que las separa es contra qué se comparan, y la única referencia que
    importa es el contrato del cliente" (§13.6, línea 8719-8720).
    """

    ERROR_DE_EJECUCION = "error_de_ejecucion"
    """#1. No es obra distinta; paga tú o el contratista (según quién lo
    causó) → Desviación."""

    NECESARIO_PARA_EJECUTAR = "necesario_para_ejecutar"
    """#2. No es obra distinta —es medio, no fin—; paga tú → Desviación, o
    señala un hueco del APU ("su recurrencia sí dice que el APU está
    incompleto", §13.6)."""

    OMISION_DE_PRESUPUESTO = "omision_de_presupuesto"
    """#3. El proyecto lo tenía, el presupuesto lo olvidó. No es obra
    distinta; paga tú → ejecutado sin respaldo, corrige el APU."""

    OMISION_DE_PROYECTO = "omision_de_proyecto"
    """#4. El cliente ya lo compró, el plano no lo dibujó (dentro del
    contrato). No es obra distinta; paga tú, **no es cobrable** → ejecutado
    sin respaldo, error de proyecto."""

    PETICION_NUEVA_DEL_CLIENTE = "peticion_nueva_del_cliente"
    """#5. Fuera de lo contratado. Sí es obra distinta; paga el cliente →
    orden de cambio, precio nuevo."""

    CONTRATO_CAMBIADO_SIN_PROPAGAR = "contrato_cambiado_sin_propagar"
    """#6. Autorizado, pero nadie bajó el impacto a planos/presupuesto. Sí
    es obra distinta; paga el cliente → orden de cambio (falla de
    propagación, no un evento nuevo)."""

    FALTA_DE_INSUMOS = "falta_de_insumos"
    """#7. No es obra distinta. No aplica "quién paga" de dinero —es causa
    de TIEMPO, no de costo— → programa: tramo de una actividad existente."""

    TEMPORALIDAD_O_CLIMA = "temporalidad_o_clima"
    """#8. ¿Obra distinta? Depende. Si solo detiene, nadie paga → calendario.
    Si daña, paga tú salvo que el contrato diga otra cosa → incidencia +
    merma de materiales. Ver :func:`quien_paga` y :func:`destino_de_causa`
    (parámetro ``hubo_dano``)."""

    MEJORA_DE_PROYECTO = "mejora_de_proyecto"
    """#9. Nadie la pidió, ni el proyecto ni el cliente. Sí es obra
    distinta; quién paga queda **sin definir incluso en el cerebro** (§13.6:
    "no es error que se absorba (3/4) ni petición del cliente que se cobre
    sola (5)") → incidencia, propuesta — nunca se ejecuta sola."""


class DestinoHallazgo(StrEnum):
    """A dónde va un hallazgo según cuál de las nueve causas aplica
    (CONOCIMIENTO.md §13.6, columna "A dónde va"; MODELO.md §5g, D-347).

    Ninguno de estos cuatro destinos salvo `DESVIACION` tiene tabla propia
    en ObraCtrl todavía — este encargo no las construye, solo documenta el
    hueco (ver docstring de :func:`destino_de_causa`).
    """

    DESVIACION = "desviacion"
    EJECUTADO_SIN_RESPALDO = "ejecutado_sin_respaldo"
    """GLOSARIO-DOMINIO.md: "Obra registrada sin presupuesto aprobado. Es
    una deuda medible, con antigüedad" — "No confundir con Desviación".
    Sin tabla propia en ObraCtrl todavía."""

    ORDEN_DE_CAMBIO_O_INCIDENCIA = "orden_de_cambio_o_incidencia"
    """`PROPUESTA(tipo=orden_cambio)` o `INCIDENCIA` en el cerebro.
    Ninguno de los dos nombres existe así en ObraCtrl: `Incidencia`/
    `TipoIncidencia` y `ControlCambio`/`TipoControlCambio` son capas
    INTERNAS distintas del "orden de cambio con el cliente" del cerebro
    (investigación previa de este encargo). Este módulo no las liga."""

    PROGRAMA = "programa"
    """Hueco de tiempo, no de costo — fuera de alcance de este encargo."""


class QuienPaga(StrEnum):
    """Quién absorbe el monto de la causa raíz (CONOCIMIENTO.md §13.6,
    columna "Quién paga"). "Tú" en el texto del cerebro es la constructora
    (quien construye y pacta con el cliente), no el cliente ni un
    contratista — de ahí `CONSTRUCTORA` y no un genérico "nosotros"."""

    CLIENTE = "cliente"
    CONSTRUCTORA = "constructora"
    CONTRATISTA = "contratista"
    NADIE = "nadie"
    SIN_DEFINIR = "sin_definir"
    """Causa #9: "sin definir incluso en el cerebro" (§13.6). No se inventa
    una respuesta que el cerebro no da."""


def destino_de_causa(
    causa: CausaRaiz, *, hubo_dano: bool | None = None
) -> DestinoHallazgo:
    """A dónde va un hallazgo, según cuál de las nueve causas de §13.6 aplica.

    Función pura: **no se persiste**, no es un campo de `Desviacion` — es el
    filtro anterior que decide si una `Desviacion` siquiera se escribe
    (MODELO.md §5g, D-343 → D-347: "de las nueve, solo 1 ... y 2 ...
    terminan ahí").

    ``hubo_dano`` solo importa para la causa #8 (temporalidad o clima), que
    el propio §13.6 describe como condicional ("depende — si solo detiene,
    no [es obra distinta]; si daña, la reparación sí"): sin daño el hallazgo
    se queda en calendario (programa); con daño se registra como incidencia
    con su merma de materiales. Se deja en `None` (equivalente a "no dañó")
    porque el caso por default de §13.6 es "si solo detiene" — tratar el
    daño como la opción que hay que pedir explícitamente, no la que se
    asume.

    No existe un parámetro de contexto para la causa #2: "Desviación, o
    señala un hueco del APU" no son dos destinos alternos de esta función
    —MODELO.md §5g ya resuelve la ambigüedad ("de las nueve, solo 1 ... y 2
    ... terminan ahí [en DESVIACION]")—, es una observación aparte sobre qué
    hacer con la recurrencia, fuera del alcance de esta función.
    """
    if causa in (CausaRaiz.ERROR_DE_EJECUCION, CausaRaiz.NECESARIO_PARA_EJECUTAR):
        return DestinoHallazgo.DESVIACION
    if causa in (CausaRaiz.OMISION_DE_PRESUPUESTO, CausaRaiz.OMISION_DE_PROYECTO):
        return DestinoHallazgo.EJECUTADO_SIN_RESPALDO
    if causa in (
        CausaRaiz.PETICION_NUEVA_DEL_CLIENTE,
        CausaRaiz.CONTRATO_CAMBIADO_SIN_PROPAGAR,
        CausaRaiz.MEJORA_DE_PROYECTO,
    ):
        return DestinoHallazgo.ORDEN_DE_CAMBIO_O_INCIDENCIA
    if causa is CausaRaiz.FALTA_DE_INSUMOS:
        return DestinoHallazgo.PROGRAMA
    # TEMPORALIDAD_O_CLIMA: el único destino condicionado por el contexto.
    return (
        DestinoHallazgo.ORDEN_DE_CAMBIO_O_INCIDENCIA
        if hubo_dano
        else DestinoHallazgo.PROGRAMA
    )


def quien_paga(
    causa: CausaRaiz,
    *,
    contratista_activo: bool | None = None,
    hubo_dano: bool | None = None,
) -> QuienPaga | None:
    """Quién absorbe el monto de la causa raíz (CONOCIMIENTO.md §13.6).

    Derivada, no un campo estático: las causas #1 y #8 dependen de contexto
    que la tabla de §13.6 no resuelve con un solo valor.

    - ``contratista_activo`` solo importa para la causa #1 (error de
      ejecución): "paga tú o el contratista" (§13.6) depende de si el
      contratista responsable del error sigue activo (y por tanto se le
      puede cobrar la corrección) — si no se sabe o ya no está, el costo lo
      absorbe la constructora.
    - ``hubo_dano`` solo importa para la causa #8 (temporalidad o clima):
      "si solo detiene, nadie [paga]; si daña, Tú (salvo que el contrato
      diga otra cosa)" (§13.6). Esa excepción contractual es una condición
      de negocio por obra que este dominio no modela —no hay tabla de
      cláusulas de contrato de la que leerla—, así que el default sin
      excepción es lo que esta función devuelve; quien la use y conozca el
      contrato decide si la anula.

    La causa #7 (falta de insumos) no tiene "quién paga" de dinero —es
    causa de tiempo, no de costo (§13.6)— y devuelve `None`: forzar un
    valor de `QuienPaga` ahí inventaría una respuesta que la tabla fuente
    no da.
    """
    if causa is CausaRaiz.ERROR_DE_EJECUCION:
        return QuienPaga.CONTRATISTA if contratista_activo else QuienPaga.CONSTRUCTORA
    if causa in (
        CausaRaiz.NECESARIO_PARA_EJECUTAR,
        CausaRaiz.OMISION_DE_PRESUPUESTO,
        CausaRaiz.OMISION_DE_PROYECTO,
    ):
        return QuienPaga.CONSTRUCTORA
    if causa in (
        CausaRaiz.PETICION_NUEVA_DEL_CLIENTE,
        CausaRaiz.CONTRATO_CAMBIADO_SIN_PROPAGAR,
    ):
        return QuienPaga.CLIENTE
    if causa is CausaRaiz.FALTA_DE_INSUMOS:
        return None
    if causa is CausaRaiz.TEMPORALIDAD_O_CLIMA:
        return QuienPaga.CONSTRUCTORA if hubo_dano else QuienPaga.NADIE
    # MEJORA_DE_PROYECTO (#9): sin definir incluso en el cerebro.
    return QuienPaga.SIN_DEFINIR
