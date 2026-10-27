"""Casos de uso: ver las desviaciones de una obra y capturar su causa.

Spec cerebro MODELO.md §5g · CONOCIMIENTO.md §13.6. El cuantificador **escribe**
desviaciones al medir un plano contra la cantidad base (`cuantificar.py`); hasta
aquí nada las mostraba ni dejaba capturar su causa, así que la regla de captura
4 —«la causa se agrega después, sin penalizar»— no tenía por dónde cumplirse.

Las cuatro reglas de captura del cerebro, y dónde se cumplen:

  1. la detección no depende de nadie: `causa` nace `null` (`crear`);
  2. quien corrige el catálogo mira patrones, no causas: consultas agregadas
     (`patrones_*`), aparte;
  3. «sin causa» es un estado válido: la lista las trae igual, sin penalizar;
  4. la causa se agrega después: `CapturarCausaDeDesviacion`, en cualquier
     momento y también para corregirla.

Capturar la causa es de quien ve la obra (RLS acota el alcance): el que sabe por
qué se desvió es quien está cerca del trabajo, no un rol en particular.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.repositorios import (
    RegistroNoEncontrado,
    RepositorioDesviaciones,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.domain.desviacion.desviacion import (
    CAUSA_ES_DE_TIPO,
    Desviacion,
    ErrorDeDesviacion,
)
from obractrl.domain.shared.diccionario import CausaDesviacion, TipoDesviacion

__all__ = [
    "CapturarCausaDeDesviacion",
    "ComandoCapturarCausa",
    "ConsultarDesviaciones",
    "DesviacionNoEncontrada",
    "ErrorDeDesviacion",
    "causas_posibles",
]


class DesviacionNoEncontrada(LookupError):
    """No existe o salió del alcance (RLS): indistinguibles a propósito (§12.4)."""


def causas_posibles(tipo: TipoDesviacion) -> list[str]:
    """Las causas del vocabulario controlado que caben en una desviación de este
    `tipo`. Es la mitad de la regla que el dominio puede validar sin consultar la
    categoría del insumo (ver `domain/desviacion/desviacion.py`)."""
    return [causa.value for causa, de in CAUSA_ES_DE_TIPO.items() if de is tipo]


@dataclass(frozen=True, slots=True)
class ComandoCapturarCausa:
    desviacion_id: UUID
    causa: CausaDesviacion
    usuario_id: UUID


class ConsultarDesviaciones:
    """`GET /obras/{id}/desviaciones`."""

    def __init__(
        self, *, desviaciones: RepositorioDesviaciones, obras: RepositorioObras
    ) -> None:
        self._desviaciones = desviaciones
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> list[dict[str, Any]]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        filas = await self._desviaciones.de_obra(obra_id)
        return [
            {**fila, "causas_posibles": causas_posibles(TipoDesviacion(str(fila["tipo"])))}
            for fila in filas
        ]


class CapturarCausaDeDesviacion:
    """`PUT /desviaciones/{id}/causa`.

    Vale cualquier momento después de detectar la desviación, y también corregir
    una causa ya capturada: quien la capturó pudo equivocarse, y el cerebro no
    penaliza ni vence la captura. Que la causa sea del lado correcto (`precio` o
    `consumo`) lo valida el dominio al armar la `Desviacion` ya con su causa.
    """

    def __init__(
        self, *, desviaciones: RepositorioDesviaciones, uow: UnidadDeTrabajo
    ) -> None:
        self._desviaciones = desviaciones
        self._uow = uow

    async def ejecutar(self, cmd: ComandoCapturarCausa) -> None:
        fila = await self._desviaciones.obtener(cmd.desviacion_id)
        if fila is None:
            raise DesviacionNoEncontrada(
                f"Desviación {cmd.desviacion_id} no encontrada en tu alcance."
            )

        # Armar la entidad con la causa nueva es la validación: lanza
        # `ErrorDeDesviacion` si la causa es del otro factor.
        Desviacion(
            insumo_id=str(fila["insumo_id"]) if fila["insumo_id"] else None,
            concepto_id=str(fila["concepto_id"]) if fila["concepto_id"] else None,
            obra_id=str(fila["obra_id"]),
            tipo=TipoDesviacion(str(fila["tipo"])),
            monto=fila["monto"],
            cantidad_plan=fila["cantidad_plan"],
            cantidad_real=fila["cantidad_real"],
            precio_plan=fila["precio_plan"],
            precio_real=fila["precio_real"],
            detectada_en=fila["detectada_en"],
            causa=cmd.causa,
        )

        async with self._uow:
            try:
                await self._desviaciones.capturar_causa(
                    cmd.desviacion_id,
                    causa=cmd.causa.value,
                    usuario_id=cmd.usuario_id,
                )
            except RegistroNoEncontrado as exc:
                raise DesviacionNoEncontrada(
                    f"Desviación {cmd.desviacion_id} ya no está en tu alcance."
                ) from exc
            await self._uow.commit()
