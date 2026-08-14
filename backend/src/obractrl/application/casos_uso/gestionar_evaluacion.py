"""Casos de uso: evaluación de desempeño, 3 niveles (§11.3 workflow H).

Spec §6 · §7.8 · §12.11 (capa de aplicación).

Dos casos de uso, misma forma que `gestionar_cierre.py`: cada uno carga lo
que necesita de los repos, deja que `domain.evaluaciones.reglas.Evaluacion`
decida si el permiso o el dato es válido, y solo entonces persiste. Ninguna
regla de negocio vive aquí, solo la secuencia.

`CrearEvaluacion` es el único caso de uso que también toca `RepositorioObras`
—vía su puerto, no su SQL concreto (§12.11)— y solo para el caso
`nivel=auto, sujeto=obra`: necesita el `residente_id` de la obra para que el
dominio verifique "su propia obra" (§11.3 H.1). Ninguna otra combinación de
nivel/sujeto lo requiere.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioEvaluaciones,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.domain.evaluaciones.reglas import (
    ErrorDeEvaluacion,
    Evaluacion,
    RespuestaEvaluacion,
)
from obractrl.domain.shared.diccionario import NivelEvaluacion, Rol, SujetoEvaluacion

__all__ = [
    "AgregarRespuestas",
    "ComandoAgregarRespuestas",
    "ComandoCrearEvaluacion",
    "CrearEvaluacion",
    "ErrorDeEvaluacion",
    "EvaluacionCreada",
    "EvaluacionNoEncontrada",
    "RespuestaEntrada",
]


class EvaluacionNoEncontrada(LookupError):
    """La evaluación —o un recurso relacionado necesario para crearla, como
    la obra en `nivel=auto`— no existe o está fuera del alcance del usuario
    (RLS)."""


@dataclass(frozen=True, slots=True)
class ComandoCrearEvaluacion:
    nivel: NivelEvaluacion
    evaluador_id: UUID
    rol: Rol
    sujeto_tipo: SujetoEvaluacion
    sujeto_id: UUID
    periodo: str
    obra_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class RespuestaEntrada:
    criterio_id: UUID
    valor: Decimal
    comentario: str | None = None


@dataclass(frozen=True, slots=True)
class ComandoAgregarRespuestas:
    evaluacion_id: UUID
    usuario_id: UUID
    respuestas: list[RespuestaEntrada]


@dataclass(frozen=True, slots=True)
class EvaluacionCreada:
    id: UUID
    evaluacion: Evaluacion


def _reconstruir(fila: dict, respuestas: list[dict]) -> Evaluacion:
    """Reconstruye la entidad desde lo persistido, para agregarle respuestas
    —no pasa por `Evaluacion.crear`, eso ya ocurrió."""
    return Evaluacion(
        sujeto_tipo=SujetoEvaluacion(fila["sujeto_tipo"]),
        sujeto_id=str(fila["sujeto_id"]),
        evaluador_id=str(fila["evaluador_id"]),
        nivel=NivelEvaluacion(fila["nivel"]),
        periodo=fila["periodo"],
        obra_id=str(fila["obra_id"]) if fila["obra_id"] else None,
        puntaje=Decimal(str(fila["puntaje"])) if fila["puntaje"] is not None else None,
        comentarios=fila["comentarios"],
        respuestas=[
            RespuestaEvaluacion(
                criterio_id=str(respuesta["criterio_id"]),
                valor=Decimal(str(respuesta["valor"])),
                comentario=respuesta["comentario"],
            )
            for respuesta in respuestas
        ],
    )


class CrearEvaluacion:
    """Crea una evaluación en el nivel que corresponda (§11.3 H).

    El nivel lo decide el body de la petición, no la ruta ni una guarda de
    rol fija: `POST /evaluaciones` deja pasar los cuatro roles y es
    `Evaluacion.crear` quien decide si ese rol puede crear ese nivel —igual
    que `SolicitudCierre.solicitar` valida `rol=Residente` puertas adentro
    del dominio, no en el router (§11.2, §12.11).
    """

    def __init__(
        self,
        *,
        evaluaciones: RepositorioEvaluaciones,
        obras: RepositorioObras,
        uow: UnidadDeTrabajo,
    ) -> None:
        self._evaluaciones = evaluaciones
        self._obras = obras
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCrearEvaluacion) -> EvaluacionCreada:
        obra_id = cmd.obra_id
        if cmd.sujeto_tipo is SujetoEvaluacion.OBRA and obra_id is None:
            # Para sujeto=obra la obra evaluada ES el sujeto (§7.8).
            obra_id = cmd.sujeto_id

        obra_residente_id: str | None = None
        if cmd.nivel is NivelEvaluacion.AUTO and cmd.sujeto_tipo is SujetoEvaluacion.OBRA:
            obra = await self._obras.obtener(obra_id) if obra_id else None
            if obra is None:
                raise EvaluacionNoEncontrada(
                    f"Obra {obra_id} no encontrada en tu alcance; no se puede "
                    f"autoevaluar."
                )
            obra_residente_id = str(obra["residente_id"])

        evaluacion = Evaluacion.crear(
            nivel=cmd.nivel,
            evaluador_id=str(cmd.evaluador_id),
            rol=cmd.rol,
            sujeto_tipo=cmd.sujeto_tipo,
            sujeto_id=str(cmd.sujeto_id),
            periodo=cmd.periodo,
            obra_id=str(obra_id) if obra_id else None,
            obra_residente_id=obra_residente_id,
        )

        async with self._uow:
            evaluacion_id = await self._evaluaciones.crear(
                sujeto_tipo=evaluacion.sujeto_tipo.value,
                sujeto_id=UUID(evaluacion.sujeto_id),
                evaluador_id=UUID(evaluacion.evaluador_id),
                nivel=evaluacion.nivel.value,
                periodo=evaluacion.periodo,
                obra_id=UUID(evaluacion.obra_id) if evaluacion.obra_id else None,
            )
            await self._uow.commit()

        return EvaluacionCreada(id=evaluacion_id, evaluacion=evaluacion)


class AgregarRespuestas:
    """Registra respuestas contra el catálogo de criterios (§7.8)."""

    def __init__(
        self, *, evaluaciones: RepositorioEvaluaciones, uow: UnidadDeTrabajo
    ) -> None:
        self._evaluaciones = evaluaciones
        self._uow = uow

    async def ejecutar(self, cmd: ComandoAgregarRespuestas) -> Evaluacion:
        fila = await self._evaluaciones.obtener(cmd.evaluacion_id)
        if fila is None:
            raise EvaluacionNoEncontrada(
                f"Evaluación {cmd.evaluacion_id} no encontrada en tu alcance."
            )
        existentes = await self._evaluaciones.respuestas_de(cmd.evaluacion_id)
        evaluacion = _reconstruir(fila, existentes)

        pesos = await self._evaluaciones.pesos_de_criterios(
            [respuesta.criterio_id for respuesta in cmd.respuestas]
        )
        nuevas = [
            RespuestaEvaluacion(
                criterio_id=str(respuesta.criterio_id),
                valor=respuesta.valor,
                comentario=respuesta.comentario,
            )
            for respuesta in cmd.respuestas
        ]
        evaluacion.agregar_respuestas(
            nuevas,
            usuario_id=str(cmd.usuario_id),
            pesos={str(criterio_id): peso for criterio_id, peso in pesos.items()},
        )

        async with self._uow:
            try:
                await self._evaluaciones.agregar_respuestas(
                    cmd.evaluacion_id,
                    respuestas=[
                        {
                            "criterio_id": respuesta.criterio_id,
                            "valor": respuesta.valor,
                            "comentario": respuesta.comentario,
                        }
                        for respuesta in nuevas
                    ],
                    puntaje=evaluacion.puntaje,
                )
            except RegistroNoEncontrado as exc:
                raise EvaluacionNoEncontrada(
                    f"Evaluación {cmd.evaluacion_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()

        return evaluacion
