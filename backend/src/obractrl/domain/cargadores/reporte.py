"""Resultado de una carga: errores por fila, bandeja y conteos.

Spec §9.3 (reporte de errores por fila/columna) · §10.3 (bandeja de
pendientes) · §9.4 (`CargaDatos.resumen`).

Dos salidas distintas y no intercambiables:

- **Error de fila** — el dato está mal y nadie puede arreglarlo desde la app:
  falta la clave, la cantidad no es un número, la fila no se parsea. Se
  reporta con fila/columna/valor/motivo y esa fila **no entra**; el resto del
  archivo sí (§9.3: una fila mala no aborta el archivo).
- **Pendiente** — el dato podría estar bien pero el sistema no puede decidir
  solo: un alias que no reconoce, un motivo de almacén no catalogado, un CPU
  nuevo. Cae en la bandeja del §10.3 con una **propuesta**; el humano
  confirma y lo resuelto re-alimenta la carga. No se inventa el valor ni se
  pierde la fila en silencio.

Módulo puro (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

__all__ = [
    "ErrorDeFila",
    "ErrorEnFila",
    "LecturaCarga",
    "PendientePropuesto",
    "ResumenCarga",
    "TipoPendiente",
]


class TipoPendiente(StrEnum):
    """Tipos de la bandeja (§10.3).

    Espeja exactamente el comentario de `pendiente.tipo` en
    `database/migrations/20260814000010_soporte_y_cargas.sql`. La columna es
    `text` libre, pero el conjunto es el del §10.3: agregar uno es decidir
    una excepción nueva del negocio, no un detalle de implementación.
    """

    MAPEO_NO_RECONOCIDO = "mapeo_no_reconocido"
    """Un alias del archivo no cruza con ningún registro oficial (§10.3)."""

    CPU_NUEVO = "cpu_nuevo"
    """El archivo trae un concepto que el catálogo aún no conoce (§10.3)."""

    UNIDAD = "unidad"
    """Unidad desconocida: hay que homologarla con su factor (§10.3, §3.5)."""

    IVA = "iva"
    """La casilla de IVA no se puede derivar de la familia (§3.5)."""

    FILA_NO_PARSEADA = "fila_no_parseada"
    """La fila no encaja en el formato del archivo (§10.3)."""

    MOTIVO_ALMACEN = "motivo_almacen"
    """Motivo de almacén no catalogado (§10.5): sin él no hay bucket de KPI."""

    CONCEPTO_EN_CONFLICTO = "concepto_en_conflicto"
    """Dos prototipos traen composiciones distintas para la misma clave de
    concepto (extensión propia, cargador de presupuesto jerárquico). El
    catálogo compartido se queda como estaba — no se sobreescribe en
    automático — hasta que alguien lo resuelva a mano."""

    DESCRIPCION_DISTINTA = "descripcion_distinta"
    """La clave cruzó contra un catálogo base, pero la descripción que trae
    esta fila no coincide con la registrada (extensión propia, homologación
    con alerta de CPU/árbol contra catálogos base, §8.7). **No crítico**: la
    clave manda (§3.3) y el cruce se aplica igual — esto solo abre la alerta
    para que alguien revise después cuál descripción es la correcta."""

    WBS_INCONSISTENTE = "wbs_inconsistente"
    """El archivo trae su propia columna WBS y no coincide con la que el
    cargador de presupuesto jerárquico calcula de la secuencia de TIPO
    (extensión propia, §7.4). **No crítico**: no es de la identidad de la
    fila (eso lo da CLAVE PADRE → CLAVE HIJO, o NIVEL + posición en el
    árbol nativo de OPUS, §3.3) — es solo una alerta para que alguien
    decida si carga la fila o corrige el archivo antes."""

    NIVEL_INCONSISTENTE = "nivel_inconsistente"
    """El árbol nativo de OPUS (`NIVEL` + posición, sin `clave_padre`,
    extensión propia, §árbol en `domain.cargadores.presupuesto.
    construir_arboles`) trae una fila cuyo `NIVEL` no es consistente con el
    de su padre en la pila: salta más de un nivel de profundidad, o no
    queda ningún padre en la pila a media reconstrucción (ni es la
    primera fila del archivo ni declara nivel 0). **No crítico**: la fila
    se sigue procesando igual —colgada del padre más cercano que haya—;
    esto solo avisa para que alguien revise si el archivo trae un hueco."""

    TRABAJO_SIN_CLASE = "trabajo_sin_clase"
    """Un componente `Tipo=Contrato` de la matriz nativa de OPUS
    (`ANALISIS_DE_BASICOS_CONCEPTOS.csv`, extensión propia, §domain.
    cargadores.cpu._agrupar_conceptos_matriz) se cargó como la categoría
    genérica `CategoriaExplosion.TRABAJO` en vez de `destajo`/
    `subcontrato` porque su clave de insumo no cruzó contra
    `CATALOGO_DE_TRABAJOS.csv` (§cabeceras.TRABAJOS_OPUS) —no vino
    ``clase_trabajo`` en la llamada, o la clave simplemente no está en
    ese catálogo—. **No crítico**: la fila se carga igual con la
    categoría genérica —esto solo marca la fila para que alguien la
    reclasifique a mano; no es un heurístico por prefijo de clave, eso el
    cerebro ya lo prohíbe explícitamente."""


@dataclass(frozen=True, slots=True)
class ErrorDeFila:
    """Un renglón del reporte de errores (§9.3).

    ``fila`` es el número **del archivo** (base 1, contando el encabezado),
    para que quien abra el Excel llegue directo al renglón malo.
    """

    fila: int
    motivo: str
    columna: str | None = None
    valor: str | None = None

    def como_dict(self) -> dict[str, object]:
        """Forma serializable para `carga_datos.errores` (jsonb, §9.4)."""
        return {
            "fila": self.fila,
            "columna": self.columna,
            "valor": self.valor,
            "motivo": self.motivo,
        }


class ErrorEnFila(Exception):
    """Fila inválida, lanzada por los validadores de dominio.

    Excepción y no valor de retorno para que un validador pueda abortar desde
    donde detecta el problema sin arrastrar un ``| None`` por toda la firma.
    El pipeline la atrapa **por fila** y la convierte en :class:`ErrorDeFila`,
    que es lo que garantiza que una fila mala no tumbe el archivo (§9.3).
    """

    def __init__(self, motivo: str, *, columna: str | None = None, valor: object = None) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.columna = columna
        self.valor = None if valor is None else str(valor)

    def con_fila(self, fila: int) -> ErrorDeFila:
        """Ubica el error en el archivo. El número de fila lo sabe el lector."""
        return ErrorDeFila(
            fila=fila, motivo=self.motivo, columna=self.columna, valor=self.valor
        )


@dataclass(frozen=True, slots=True)
class PendientePropuesto:
    """Excepción que espera confirmación humana (§10.3).

    ``propuesta`` es lo que el sistema **sugiere** —nunca lo que decidió—:
    "el sistema propone, el humano confirma". ``origen_ref`` es la liga al
    origen (archivo + fila) que exige el §10.3.
    """

    tipo: TipoPendiente
    entidad: str
    valor_origen: str
    propuesta: dict[str, object] = field(default_factory=dict)
    critico: bool = False
    """Si bloquea el cierre de la carga (§10.3)."""

    origen_ref: str | None = None

    def como_dict(self) -> dict[str, object]:
        return {
            "tipo": str(self.tipo),
            "entidad": self.entidad,
            "valor_origen": self.valor_origen,
            "propuesta": self.propuesta,
            "critico": self.critico,
            "origen_ref": self.origen_ref,
        }


@dataclass(frozen=True, slots=True)
class ResumenCarga:
    """Conteos de `carga_datos.resumen` (§9.4, §9.3 "dry-run obligatorio")."""

    filas: int = 0
    insertados: int = 0
    actualizados: int = 0
    omitidos: int = 0
    errores: int = 0
    pendientes: int = 0

    def como_dict(self) -> dict[str, int]:
        return {
            "filas": self.filas,
            "insertados": self.insertados,
            "actualizados": self.actualizados,
            "omitidos": self.omitidos,
            "errores": self.errores,
            "pendientes": self.pendientes,
        }


@dataclass(frozen=True, slots=True)
class LecturaCarga:
    """Lo que el lector del archivo entrega al caso de uso.

    ``registros`` son entidades **ya validadas** por el dominio del cargador
    (`FilaMaterial`, `ConceptoCargado`, `FilaMovimiento`); el tipo concreto
    depende del cargador y por eso viaja como `tuple[object, ...]`. El caso de
    uso sabe qué cargador pidió y por tanto qué esperar.
    """

    registros: tuple[object, ...] = ()
    errores: tuple[ErrorDeFila, ...] = ()
    pendientes: tuple[PendientePropuesto, ...] = ()
    filas_leidas: int = 0
    omitidos: int = 0
    """Filas válidas descartadas por duplicado de clave dentro del archivo (§10.2)."""
