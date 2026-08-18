"""Expediente técnico de una obra: el agregado que reúne su acervo.

Spec §7.9 (`ExpedienteDoc`, `Evidencia`) · §11.2 ("**Expediente** — `GET/POST
/obras/{id}/expediente` … `GET /obras/{id}/expediente/pdf` (job)") · §11.3 D
(el Control de obra aporta "calidad/expediente" al cierre de obra) · §3.5
(importes en MXN).

**De dónde salen las evidencias.** El §7.9 declara una tabla `Evidencia`
genérica, pero hoy nada escribe en ella: la API guarda las claves de R2
*dentro* de cada entidad —`revision_fisica.fotos`, `incidencia.evidencias`,
`solicitud_cierre.adjuntos` (§7.8)— porque el binario nunca viaja por la API y
lo que se persiste es la clave del objeto (§12.2,
`adapters/api/v1/evidencias.py`). Este agregado las **reúne** de esas tres
fuentes en vez de inventar una cuarta: cada evidencia dice de dónde viene, que
es lo que un expediente auditable necesita.

Módulo puro: sin BD, sin FastAPI, sin reloj —`generado_en` se recibe— y por
eso 100% testeable (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from obractrl.domain.shared.diccionario import (
    EstatusEstimacion,
    EstatusSolicitudCierre,
    TipoExpedienteDoc,
)
from obractrl.domain.shared.valores import Dinero

__all__ = [
    "CierreDelExpediente",
    "DocumentoDelExpediente",
    "EstimacionDelExpediente",
    "EvidenciaDelExpediente",
    "ExpedienteTecnico",
    "OrigenDeEvidencia",
]


class OrigenDeEvidencia:
    """De qué entidad del §7.8 salió la clave de R2."""

    REVISION = "revision_fisica"
    INCIDENCIA = "incidencia"
    CIERRE = "solicitud_cierre"


@dataclass(frozen=True, slots=True)
class DocumentoDelExpediente:
    """Un `ExpedienteDoc` (§7.9)."""

    id: str
    tipo: TipoExpedienteDoc
    nombre: str
    clave: str
    """Clave del objeto en R2 (`expediente_doc.url`), no una URL firmada."""
    fecha: datetime | None = None
    subido_por: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenciaDelExpediente:
    """Una clave de R2 referenciada por alguna entidad de la obra (§7.8)."""

    origen: str
    origen_id: str
    clave: str
    fecha: date | None = None


@dataclass(frozen=True, slots=True)
class CierreDelExpediente:
    """Una `SolicitudCierre` de la obra (§7.8, §11.3 C)."""

    id: str
    actividad_id: str
    estatus: EstatusSolicitudCierre
    cantidad: Decimal
    monto: Dinero
    fecha_solicitud: datetime | None = None
    fecha_valida: datetime | None = None


@dataclass(frozen=True, slots=True)
class EstimacionDelExpediente:
    """Una `Estimacion` de la obra (§7.6, §11.3 E)."""

    id: str
    folio: str | None
    semana: int
    anio: int
    modo: str
    estatus: EstatusEstimacion
    monto: Dinero


def _dinero(valor: object) -> Dinero:
    """`Dinero` desde lo que devuelve el repo (`Decimal`, `int` o `None`)."""
    return Dinero(0) if valor is None else Dinero(valor)  # type: ignore[arg-type]


def _claves(valor: object) -> list[str]:
    """Lista de claves de R2 de una columna `jsonb` (§7.8).

    Se filtra lo que no sea un texto no vacío: la columna es `jsonb` libre y
    un `null` suelto o un objeto a medio migrar no debe tumbar el expediente
    completo de la obra.
    """
    if not isinstance(valor, list):
        return []
    return [item.strip() for item in valor if isinstance(item, str) and item.strip()]


@dataclass(frozen=True, slots=True)
class ExpedienteTecnico:
    """Todo el expediente de una obra en un solo agregado (§7.9, §11.2).

    Alimenta la vista JSON y el PDF (`adapters/export/pdf.py`) con exactamente
    los mismos números: las sumas se definen aquí una vez.
    """

    obra_id: str
    obra_clave: str
    generado_en: datetime
    documentos: tuple[DocumentoDelExpediente, ...] = ()
    evidencias: tuple[EvidenciaDelExpediente, ...] = ()
    cierres: tuple[CierreDelExpediente, ...] = ()
    estimaciones: tuple[EstimacionDelExpediente, ...] = ()
    avance_pct: Decimal = Decimal(0)
    obra_estatus: str | None = None

    @property
    def monto_cerrado(self) -> Dinero:
        """Σ de los cierres **validados** (§11.3 C.3).

        Solo los validados: un cierre `solicitada` o `rechazada` todavía no es
        obra reconocida, y el expediente es el documento que sostiene el
        cierre de obra del §11.3 D.
        """
        total = Dinero(0)
        for cierre in self.cierres:
            if cierre.estatus is EstatusSolicitudCierre.VALIDADA:
                total = total + cierre.monto
        return total

    @property
    def monto_estimado(self) -> Dinero:
        """Σ de las estimaciones **validadas** (§11.3 E.4).

        Mismo criterio que `monto_cerrado`: una estimación en `borrador` o
        `enviada` aún puede cambiar de monto, así que no suma al expediente.
        """
        total = Dinero(0)
        for estimacion in self.estimaciones:
            if estimacion.estatus is EstatusEstimacion.VALIDADA:
                total = total + estimacion.monto
        return total

    @property
    def n_evidencias(self) -> int:
        return len(self.evidencias)

    @property
    def documentos_por_tipo(self) -> dict[TipoExpedienteDoc, int]:
        """Cuántos documentos hay de cada tipo del §7.9."""
        conteo: dict[TipoExpedienteDoc, int] = {}
        for documento in self.documentos:
            conteo[documento.tipo] = conteo.get(documento.tipo, 0) + 1
        return conteo

    @property
    def evidencias_por_origen(self) -> dict[str, int]:
        conteo: dict[str, int] = {}
        for evidencia in self.evidencias:
            conteo[evidencia.origen] = conteo.get(evidencia.origen, 0) + 1
        return conteo

    @classmethod
    def armar(
        cls,
        *,
        obra: dict,
        generado_en: datetime,
        documentos: list[dict] | None = None,
        cierres: list[dict] | None = None,
        estimaciones: list[dict] | None = None,
        revisiones: list[dict] | None = None,
        incidencias: list[dict] | None = None,
    ) -> ExpedienteTecnico:
        """Arma el expediente desde las filas crudas de cada puerto.

        Cada lista llega del repositorio **de su propio contexto** —cierres,
        estimaciones, revisiones, incidencias—, nunca de una consulta que
        cruce sus tablas: el §11.1 exige que ningún módulo lea las tablas de
        otro, así que la unión ocurre aquí, en el dominio, sobre datos que
        cada dueño ya devolvió.
        """
        return cls(
            obra_id=str(obra["id"]),
            obra_clave=str(obra.get("clave") or ""),
            obra_estatus=str(obra["estatus"]) if obra.get("estatus") else None,
            avance_pct=Decimal(str(obra.get("avance_pct") or 0)),
            generado_en=generado_en,
            documentos=tuple(_documento(fila) for fila in documentos or []),
            cierres=tuple(_cierre(fila) for fila in cierres or []),
            estimaciones=tuple(_estimacion(fila) for fila in estimaciones or []),
            evidencias=tuple(
                _evidencias(
                    cierres=cierres or [],
                    revisiones=revisiones or [],
                    incidencias=incidencias or [],
                )
            ),
        )


def _documento(fila: dict) -> DocumentoDelExpediente:
    return DocumentoDelExpediente(
        id=str(fila["id"]),
        tipo=TipoExpedienteDoc(str(fila["tipo"])),
        nombre=str(fila["nombre"]),
        clave=str(fila["url"]),
        fecha=fila.get("fecha"),
        subido_por=str(fila["subido_por"]) if fila.get("subido_por") else None,
    )


def _cierre(fila: dict) -> CierreDelExpediente:
    return CierreDelExpediente(
        id=str(fila["id"]),
        actividad_id=str(fila["actividad_id"]),
        estatus=EstatusSolicitudCierre(str(fila["estatus"])),
        cantidad=Decimal(str(fila.get("cantidad") or 0)),
        monto=_dinero(fila.get("monto")),
        fecha_solicitud=fila.get("fecha_solicitud"),
        fecha_valida=fila.get("fecha_valida"),
    )


def _estimacion(fila: dict) -> EstimacionDelExpediente:
    return EstimacionDelExpediente(
        id=str(fila["id"]),
        folio=str(fila["folio"]) if fila.get("folio") else None,
        semana=int(fila["semana"]),
        anio=int(fila["anio"]),
        modo=str(fila["modo"]),
        estatus=EstatusEstimacion(str(fila["estatus"])),
        monto=_dinero(fila.get("monto_total")),
    )


def _evidencias(
    *, cierres: list[dict], revisiones: list[dict], incidencias: list[dict]
) -> list[EvidenciaDelExpediente]:
    """Reúne las claves de R2 de las tres entidades que las guardan (§7.8)."""
    reunidas: list[EvidenciaDelExpediente] = []

    for fila in revisiones:
        for clave in _claves(fila.get("fotos")):
            reunidas.append(
                EvidenciaDelExpediente(
                    origen=OrigenDeEvidencia.REVISION,
                    origen_id=str(fila["id"]),
                    clave=clave,
                    fecha=fila.get("fecha"),
                )
            )

    for fila in incidencias:
        for clave in _claves(fila.get("evidencias")):
            reunidas.append(
                EvidenciaDelExpediente(
                    origen=OrigenDeEvidencia.INCIDENCIA,
                    origen_id=str(fila["id"]),
                    clave=clave,
                    fecha=fila.get("fecha_creada"),
                )
            )

    for fila in cierres:
        for clave in _claves(fila.get("adjuntos")):
            reunidas.append(
                EvidenciaDelExpediente(
                    origen=OrigenDeEvidencia.CIERRE,
                    origen_id=str(fila["id"]),
                    clave=clave,
                    fecha=fila.get("fecha_solicitud"),
                )
            )

    return reunidas
