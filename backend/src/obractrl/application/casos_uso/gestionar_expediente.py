"""Casos de uso del expediente técnico de la obra.

Spec §7.9 (`ExpedienteDoc`) · §11.2 ("**Expediente** — `GET/POST
/obras/{id}/expediente` — todos lectura / (C, SI) subida · `GET
/obras/{id}/expediente/pdf` (job)") · §11.1 (contexto Expediente) · §12.11.

Tres casos de uso, ninguno con reglas propias:

- `AgregarDocumento` — el dominio valida rol, nombre y clave
  (`domain.expediente.reglas`) y el repo persiste; misma forma lineal que
  `registrar_revision_fisica.py`.
- `ConsultarExpediente` — lista los documentos de una obra.
- `ArmarExpediente` — la **vista agregada** del §11.2: reúne documentos,
  evidencias, cierres y estimaciones de la obra.

`ArmarExpediente` es el punto donde se ve por qué existen los puertos: el
expediente cruza cuatro contextos (Expediente, Cierres, Estimación,
Incidencias/Revisiones) y **no consulta ni una tabla ajena** —le pide a cada
dueño su parte por su puerto y el dominio (`domain.reportes.expediente`) la
une (§11.1: ningún módulo lee las tablas ni el estado interno de otro).

El mismo agregado alimenta la respuesta JSON y el PDF (`adapters/export`), así
que las sumas del expediente se calculan una sola vez, en el dominio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import (
    ObraNoEncontrada,
)
from obractrl.application.puertos.repositorios import (
    RepositorioCierres,
    RepositorioEstimaciones,
    RepositorioExpediente,
    RepositorioIncidencias,
    RepositorioObras,
    RepositorioRevisiones,
    UnidadDeTrabajo,
)
from obractrl.domain.expediente.reglas import DocumentoExpediente, ErrorDeExpediente
from obractrl.domain.reportes.expediente import ExpedienteTecnico
from obractrl.domain.shared.diccionario import Rol, TipoExpedienteDoc

__all__ = [
    "AgregarDocumento",
    "ArmarExpediente",
    "ComandoAgregarDocumento",
    "ConsultarExpediente",
    "DocumentoAgregado",
    "ErrorDeExpediente",
    "ObraNoEncontrada",
]


@dataclass(frozen=True, slots=True)
class ComandoAgregarDocumento:
    obra_id: UUID
    usuario_id: UUID
    rol: Rol
    tipo: TipoExpedienteDoc
    nombre: str
    url: str
    """Clave del objeto ya subido a R2, no una URL firmada (§12.2)."""


@dataclass(frozen=True, slots=True)
class DocumentoAgregado:
    id: UUID
    documento: DocumentoExpediente


class AgregarDocumento:
    """Control de obra o Super intendente suben un documento (§11.2)."""

    def __init__(
        self, *, expediente: RepositorioExpediente, uow: UnidadDeTrabajo
    ) -> None:
        self._expediente = expediente
        self._uow = uow

    async def ejecutar(self, cmd: ComandoAgregarDocumento) -> DocumentoAgregado:
        documento = DocumentoExpediente.subir(
            obra_id=str(cmd.obra_id),
            tipo=cmd.tipo,
            nombre=cmd.nombre,
            url=cmd.url,
            subido_por=str(cmd.usuario_id),
            rol=cmd.rol,
        )

        async with self._uow:
            documento_id = await self._expediente.crear(
                obra_id=cmd.obra_id,
                tipo=documento.tipo.value,
                nombre=documento.nombre,
                url=documento.url,
                subido_por=cmd.usuario_id,
            )
            await self._uow.commit()

        return DocumentoAgregado(id=documento_id, documento=documento)


class ConsultarExpediente:
    """Documentos de una obra (§11.2 `GET /obras/{id}/expediente`)."""

    def __init__(self, *, expediente: RepositorioExpediente) -> None:
        self._expediente = expediente

    async def listar(
        self, obra_id: UUID, *, tipo: TipoExpedienteDoc | None = None
    ) -> list[dict]:
        """RLS ya acota el alcance: la lectura es de todos los roles (§11.2)."""
        return await self._expediente.listar(
            obra_id, tipo=tipo.value if tipo else None
        )


class ArmarExpediente:
    """Vista agregada del expediente de una obra (§11.2, §7.9).

    Cada dependencia es el puerto del contexto que **posee** ese dato. Si
    mañana Cierres se vuelve un microservicio, aquí solo cambia la
    implementación del puerto (§11.1: la fachada es la futura frontera del
    servicio).
    """

    def __init__(
        self,
        *,
        expediente: RepositorioExpediente,
        obras: RepositorioObras,
        cierres: RepositorioCierres,
        estimaciones: RepositorioEstimaciones,
        revisiones: RepositorioRevisiones,
        incidencias: RepositorioIncidencias,
    ) -> None:
        self._expediente = expediente
        self._obras = obras
        self._cierres = cierres
        self._estimaciones = estimaciones
        self._revisiones = revisiones
        self._incidencias = incidencias

    async def ejecutar(self, obra_id: UUID) -> ExpedienteTecnico:
        obra = await self._obras.obtener(obra_id)
        if obra is None:
            # RLS hace indistinguible "no existe" de "no la puedes ver"
            # (§12.4): el mismo 404 que en el resto de la API.
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")

        return ExpedienteTecnico.armar(
            obra=obra,
            # El reloj entra por el borde: el dominio no lo consulta (§12.11).
            generado_en=datetime.now(UTC),
            documentos=await self._expediente.listar(obra_id),
            cierres=await self._cierres.listar_de_obra(obra_id),
            estimaciones=await self._estimaciones.listar(obra_id),
            revisiones=await self._revisiones.listar(obra_id=obra_id),
            incidencias=await self._incidencias.listar(obra_id=obra_id),
        )
