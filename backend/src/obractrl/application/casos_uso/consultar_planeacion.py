"""Caso de uso: planeación por obra (§8.3, §11.3).

Contesta la pregunta del jefe de obra —*"cuántas cuadrillas necesito para
alcanzar la meta programada por frente"*— y presenta al lado quién lleva cada
frente en esa obra.

**Solo lee y escribe el trato.** La cifra de cuadrillas se **deriva** cada vez:
sale del programa y del rendimiento del catálogo, y guardarla obligaría a
invalidarla en cada cambio del cronograma, que es todos los días. Lo que sí se
persiste es la decisión —quién lo lleva y con cuántas cuadrillas— porque eso no
se deriva de nada.

## Por qué reusa el módulo de insumos

`insumos.programado.jornadas_por_frente` ya reparte cualquier cantidad sobre
los periodos honrando los tramos, y filtrada a `tipo = 'mano_obra'` esa
cantidad **son** jornadas. Dividirlas entre los días hábiles del periodo da
cuadrillas (`planeacion.cuadrillas`). Escribir un segundo repartidor aquí
garantizaría que un día el material y la gente dijeran cosas distintas sobre el
mismo programa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from obractrl.application.casos_uso.consultar_insumos_programados import (
    ComandoInsumosProgramados,
    ConsultarInsumosProgramados,
    a_actividad,
)
from obractrl.domain.insumos.programado import Periodo, jornadas_por_frente
from obractrl.domain.planeacion.cuadrillas import DemandaDeFrente, demanda_por_frente
from obractrl.domain.programacion.calendario import CalendarioLaboral
from obractrl.domain.shared.diccionario import TipoSemana

__all__ = [
    "AsignarFrenteDeObra",
    "ComandoAsignarFrente",
    "ComandoPlaneacion",
    "ConsultarPlaneacion",
    "FrenteDeObra",
    "OficioDeFrente",
    "PlaneacionDeObra",
]

SIN_FRENTE = ""
"""Clave con la que se agrupa lo que todavía no tiene frente asignado.

No se descarta: es trabajo real que alguien tiene que hacer, y esconderlo haría
que el total de la obra no cuadrara con la suma de sus frentes. La pantalla lo
rotula como pendiente de mapear (§8.3, migración 0045).
"""


@dataclass(frozen=True, slots=True)
class ComandoPlaneacion:
    obra_id: UUID
    desde: date
    hasta: date
    granularidad: str = "semana"
    tipo_semana: TipoSemana = TipoSemana.ORDINARIA


@dataclass(frozen=True, slots=True)
class ComandoAsignarFrente:
    """El trato: quién lleva un frente en una obra y con cuánta gente."""

    obra_id: UUID
    frente_id: UUID
    contratista_id: UUID | None = None
    cuadrillas_plan: int | None = None
    notas: str | None = None


@dataclass(frozen=True, slots=True)
class OficioDeFrente:
    """El desglose de un frente por oficio (§8.3, migración 0047).

    Hace falta porque el frente solo es demasiado grueso para contratar: en la
    obra real OBRA concentra el 90% de las jornadas, y nadie contrata "noventa
    por ciento de la obra". Partido por oficio —estructura, acabados,
    albañilería— cada renglón ya es algo que se le pide a alguien.

    La suma de los oficios de un frente es el frente: salen del mismo reparto
    (`jornadas_por_frente` con otro agrupador), no de un segundo cálculo.
    """

    especialidad_id: str
    clave: str
    nombre: str
    demanda: DemandaDeFrente


@dataclass(frozen=True, slots=True)
class FrenteDeObra:
    """Un renglón de la vista por frente: lo que pide y lo que se decidió."""

    frente_id: str
    frente_clave: str
    frente_nombre: str
    demanda: DemandaDeFrente
    contratista_id: str | None = None
    contratista_nombre: str | None = None
    cuadrillas_plan: int | None = None
    """Lo que el residente decidió, al lado de `demanda.pico_cuadrillas`, que
    es lo que el cálculo sugiere. Las dos se enseñan: la sugerencia sale de un
    rendimiento del catálogo y la decisión la toma quien conoce al contratista.
    """
    notas: str | None = None

    oficios: tuple[OficioDeFrente, ...] = ()
    """Cómo se reparte por oficio lo que este frente pide."""


@dataclass(frozen=True, slots=True)
class PlaneacionDeObra:
    periodos: tuple[Periodo, ...]
    dias_habiles: tuple[int, ...]
    frentes: tuple[FrenteDeObra, ...]


class ConsultarPlaneacion:
    """`GET /obras/{id}/planeacion/frentes` (§11.2)."""

    def __init__(
        self,
        *,
        insumos: ConsultarInsumosProgramados,
        actividades,
        planeacion,
        frentes,
        especialidades=None,
    ) -> None:
        self._insumos = insumos
        self._actividades = actividades
        self._planeacion = planeacion
        self._frentes = frentes
        self._especialidades = especialidades

    async def ejecutar(self, cmd: ComandoPlaneacion) -> PlaneacionDeObra:
        # Se reusa el cargador de insumos programados entero: mismas
        # actividades, misma explosión, mismos periodos. Lo único distinto es
        # qué se hace con el resultado.
        base = ComandoInsumosProgramados(
            desde=cmd.desde,
            hasta=cmd.hasta,
            granularidad=cmd.granularidad,
            obra_id=cmd.obra_id,
            tipo_semana=cmd.tipo_semana,
        )
        filas = await self._actividades.actividades_para_insumos(
            obra_id=cmd.obra_id, desde=cmd.desde, hasta=cmd.hasta
        )
        # Igual que en insumos programados: las fechas del CPM no se
        # persisten, así que la ventana se pide fresca. Sin esto, una obra
        # cuyo residente no capturó fechas a mano saldría entera sin programar
        # y la tabla no diría nada.
        actividades = await self._insumos.con_ventana_del_cpm(
            cmd.obra_id, [a_actividad(fila) for fila in filas]
        )
        periodos = await self._insumos.periodos(base)
        catalogo = await self._insumos.catalogo()
        explosiones = await self._insumos.explosiones(filas)

        jornadas = jornadas_por_frente(
            actividades=actividades,
            explosiones=explosiones,
            catalogo=catalogo,
            periodos=periodos,
        )
        # El mismo reparto agrupado por el par frente-oficio. Se pide aparte y
        # no se deriva del anterior porque una actividad aporta a los dos ejes
        # a la vez: repartir dos veces la misma cantidad es correcto, dividir
        # el resultado del primero entre oficios sería inventar una proporción.
        por_oficio = jornadas_por_frente(
            actividades=actividades,
            explosiones=explosiones,
            catalogo=catalogo,
            periodos=periodos,
            agrupar=_por_frente_y_oficio,
        )

        calendario = CalendarioLaboral.de(
            await self._planeacion.dias_habiles_de_obra(cmd.obra_id)
        )
        dias_habiles = tuple(_habiles_en(periodo, calendario) for periodo in periodos)

        asignado = {
            str(fila["frente_id"]): fila
            for fila in await self._planeacion.frentes_de_obra(cmd.obra_id)
        }
        # El catálogo se lee aparte para poder nombrar un frente que tiene
        # carga pero ningún trato todavía: sin esto saldría con la clave en
        # blanco, que es el estado más común antes de contratar.
        catalogo_frentes = {
            str(f["id"]): f for f in await self._frentes.listar(solo_activos=False)
        }
        catalogo_oficios = {
            str(f["id"]): f
            for f in (
                await self._especialidades.listar(solo_activos=False)
                if self._especialidades is not None
                else []
            )
        }

        demandas = demanda_por_frente(
            jornadas_por_frente=jornadas,
            dias_habiles_por_periodo=dias_habiles,
        )

        return PlaneacionDeObra(
            periodos=tuple(periodos),
            dias_habiles=dias_habiles,
            frentes=tuple(
                _renglon(
                    demanda,
                    asignado.get(demanda.frente_id),
                    catalogo_frentes.get(demanda.frente_id),
                    _oficios_de(
                        demanda.frente_id, por_oficio, dias_habiles, catalogo_oficios
                    ),
                )
                for demanda in demandas
            ),
        )


SEPARADOR_EJES = "|"
"""Separa los dos ejes en la clave compuesta del agrupador.

Los dos son uuid o cadena vacía, y ninguno puede contener una barra, así que
partir por la primera devuelve exactamente lo que se juntó.
"""


def _por_frente_y_oficio(actividad) -> str:
    """Agrupador del cruce: `frente|oficio`.

    Una clave compuesta y no dos pasadas porque el reparto sobre los periodos
    tiene que ser el mismo que el del frente: dos recorridos distintos
    divergirían y la suma de los oficios dejaría de dar el frente.
    """
    return (
        f"{actividad.frente_id or ''}"
        f"{SEPARADOR_EJES}"
        f"{actividad.especialidad_id or ''}"
    )


def _oficios_de(
    frente_id: str,
    por_oficio: dict[str, tuple],
    dias_habiles: tuple[int, ...],
    catalogo: dict[str, dict],
) -> tuple[OficioDeFrente, ...]:
    """El desglose por oficio de un frente, ordenado por pico.

    Un oficio que el catálogo no nombra sale como "Sin oficio": es el concepto
    al que todavía no se le capturó especialidad. No se descarta, porque
    entonces la suma de los oficios ya no daría el frente y la tabla dejaría de
    cuadrar consigo misma.
    """
    del_frente = {
        clave.split(SEPARADOR_EJES, 1)[1]: valores
        for clave, valores in por_oficio.items()
        if clave.split(SEPARADOR_EJES, 1)[0] == frente_id
    }
    if not del_frente:
        return ()

    salida = []
    for demanda in demanda_por_frente(
        jornadas_por_frente=del_frente, dias_habiles_por_periodo=dias_habiles
    ):
        oficio = catalogo.get(demanda.frente_id)
        salida.append(
            OficioDeFrente(
                especialidad_id=demanda.frente_id,
                clave=str(oficio["clave"]) if oficio else "—",
                nombre=str(oficio["nombre"]) if oficio else "Sin oficio",
                demanda=demanda,
            )
        )
    return tuple(salida)


def _renglon(
    demanda: DemandaDeFrente,
    trato: dict | None,
    frente: dict | None,
    oficios: tuple[OficioDeFrente, ...] = (),
) -> FrenteDeObra:
    if demanda.frente_id == SIN_FRENTE:
        return FrenteDeObra(
            frente_id=SIN_FRENTE,
            frente_clave="—",
            frente_nombre="Sin frente asignado",
            demanda=demanda,
            oficios=oficios,
        )

    clave = str(frente["clave"]) if frente else ""
    nombre = str(frente["nombre"]) if frente else ""

    if trato is None:
        # El frente tiene carga pero nadie ha dicho quién lo lleva. Es el
        # estado normal antes de contratar, no un hueco de datos.
        return FrenteDeObra(
            frente_id=demanda.frente_id,
            frente_clave=clave,
            frente_nombre=nombre,
            demanda=demanda,
            oficios=oficios,
        )
    return FrenteDeObra(
        frente_id=demanda.frente_id,
        frente_clave=clave,
        frente_nombre=nombre,
        demanda=demanda,
        contratista_id=str(trato["contratista_id"]) if trato["contratista_id"] else None,
        contratista_nombre=trato["contratista_nombre"],
        cuadrillas_plan=trato["cuadrillas_plan"],
        notas=trato["notas"],
        oficios=oficios,
    )


def _habiles_en(periodo: Periodo, calendario: CalendarioLaboral) -> int:
    """Días que se trabajan dentro del periodo.

    Sale del calendario del cronograma de la obra (0040) y no de contar días
    corridos: dividir 40 jornadas entre 7 daría 5.7 cuadrillas donde de verdad
    hacen falta 8, porque el sábado y el domingo no se trabajan.
    """
    return max(0, calendario.dias_entre(periodo.desde, periodo.hasta))


class AsignarFrenteDeObra:
    """`PUT /obras/{id}/planeacion/frentes/{frente_id}` (§11.2).

    Guarda el trato: quién lleva ese frente en esa obra y con cuántas
    cuadrillas. Idempotente por el par —asignarlo dos veces es cambiar de
    contratista, no crear un segundo trato— y por eso no devuelve 201.

    Lo planifica el **residente** (§4): el programa base es una guía y quien
    decide con qué gente se cumple es quien está en la obra. RLS acota a las
    suyas, así que la guarda de rol solo evita ofrecerlo a quien no planifica.
    """

    def __init__(self, *, planeacion, uow) -> None:
        self._planeacion = planeacion
        self._uow = uow

    async def ejecutar(self, cmd: ComandoAsignarFrente) -> UUID:
        async with self._uow:
            asignado = await self._planeacion.asignar_frente(
                obra_id=cmd.obra_id,
                frente_id=cmd.frente_id,
                contratista_id=cmd.contratista_id,
                cuadrillas_plan=cmd.cuadrillas_plan,
                notas=cmd.notas,
            )
            await self._uow.commit()
        return asignado
