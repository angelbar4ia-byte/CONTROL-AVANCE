"""Mediciones: la capa sombra del cuantificador (migración 0088).

Una medición agrupa trazos de un tipo —área, lineal o conteo— sin depender de ningún concepto y se
**asigna** a uno o varios. Asignar crea los enlaces de sus trazos (y los de sus submediciones) y un
trazo que entra después hereda los de su medición y los de las que la contienen; el motor de
cantidades no cambia: sigue siendo `medida × factor` por enlace vigente. Los enlaces que nacen de una
asignación se quitan solos —quedan como evidencia, no vigentes— al quitar la asignación o al sacar el
trazo de la medición.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import (
    MedicionNoEncontrada,
    NodoActividad,
    PlanoNoEncontrado,
    TrazoNoEncontrado,
    _avisar_reaperturas,
    _recalcular_nodo,
    aplicar_asignaciones_a_trazo,
)
from obractrl.application.eventos import PublicadorEventos
from obractrl.application.puertos.cuantificacion import (
    RepositorioEnlacesCuantificacion,
    RepositorioMatrices,
    RepositorioMediciones,
    RepositorioPlanos,
)
from obractrl.application.puertos.repositorios import (
    RepositorioActividades,
    RepositorioDesviaciones,
    RepositorioPrototipoNodo,
    UnidadDeTrabajo,
)
from obractrl.domain.cuantificacion.medicion import (
    TIPOS_DE_MEDICION,
    medida_admitida,
    motivo_de_incompatibilidad,
    normalizar_nombre,
)
from obractrl.domain.cuantificacion.reglas import (
    EnlaceCuantificacion,
    ErrorDeCuantificacion,
)
from obractrl.domain.shared.diccionario import (
    MedidaCuantificacion,
    TipoNodoCuantificacion,
)

__all__ = [
    "ComandoCrearAsignacion",
    "ComandoCrearMedicion",
    "GestionarMediciones",
    "MedicionNoEncontrada",
    "ResultadoDeAsignacion",
]

@dataclass(frozen=True, slots=True)
class ComandoCrearMedicion:
    plano_id: UUID
    nombre: str
    tipo: str
    autor_id: UUID
    parent_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ComandoCrearAsignacion:
    medicion_id: UUID
    actividad_id: UUID
    medida: str
    factor: Decimal
    autor_id: UUID
    matriz_concepto_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class ResultadoDeAsignacion:
    asignacion_id: UUID | None
    trazos_enlazados: int
    recalculos: tuple = field(default_factory=tuple)


class GestionarMediciones:
    """Crear, renombrar y borrar mediciones; meter y sacar trazos; asignarlas a conceptos."""

    def __init__(
        self,
        *,
        mediciones: RepositorioMediciones,
        planos: RepositorioPlanos,
        enlaces: RepositorioEnlacesCuantificacion,
        actividades: RepositorioActividades,
        prototipo_nodos: RepositorioPrototipoNodo,
        desviaciones: RepositorioDesviaciones,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos | None = None,
        matrices: RepositorioMatrices | None = None,
    ) -> None:
        self._mediciones = mediciones
        self._planos = planos
        self._enlaces = enlaces
        self._actividades = actividades
        self._prototipo_nodos = prototipo_nodos
        self._desviaciones = desviaciones
        self._uow = uow
        self._eventos = eventos
        self._matrices = matrices

    async def listar(self, plano_id: UUID) -> list[dict]:
        """Las mediciones de un plano con lo que miden y a qué conceptos alimentan."""
        if await self._planos.obtener(plano_id) is None:
            raise PlanoNoEncontrado(f"El plano {plano_id} no existe o está fuera de tu alcance.")
        return await self._mediciones.de_plano(plano_id)

    # --- las mediciones mismas ------------------------------------------------------------------

    async def crear(self, cmd: ComandoCrearMedicion) -> UUID:
        nombre = normalizar_nombre(cmd.nombre)
        if cmd.tipo not in TIPOS_DE_MEDICION:
            raise ErrorDeCuantificacion("El tipo de una medición es área, lineal o conteo.")
        if await self._planos.obtener(cmd.plano_id) is None:
            raise PlanoNoEncontrado(f"El plano {cmd.plano_id} no existe o está fuera de tu alcance.")
        if cmd.parent_id is not None:
            madre = await self._mediciones.obtener(cmd.parent_id)
            if madre is None:
                raise MedicionNoEncontrada(f"La medición {cmd.parent_id} no existe o está fuera de tu alcance.")
            if madre["plano_id"] != cmd.plano_id:
                raise ErrorDeCuantificacion("La medición madre es de otro plano.")
            if madre["tipo"] != cmd.tipo:
                raise ErrorDeCuantificacion(
                    "Una submedición es del mismo tipo que su madre: los espacios de una losa "
                    "(área) son de área."
                )
        if await self._mediciones.existe_hermana(plano_id=cmd.plano_id, parent_id=cmd.parent_id, nombre=nombre):
            raise ErrorDeCuantificacion(f"Ya hay una medición llamada «{nombre}» en ese lugar.")
        async with self._uow:
            medicion_id = await self._mediciones.crear(
                plano_id=cmd.plano_id,
                nombre=nombre,
                tipo=cmd.tipo,
                parent_id=cmd.parent_id,
                autor_id=cmd.autor_id,
            )
            await self._uow.commit()
        return medicion_id

    async def renombrar(self, medicion_id: UUID, nombre: str) -> None:
        nuevo = normalizar_nombre(nombre)
        m = await self._mediciones.obtener(medicion_id)
        if m is None:
            raise MedicionNoEncontrada(f"La medición {medicion_id} no existe o está fuera de tu alcance.")
        if await self._mediciones.existe_hermana(
            plano_id=m["plano_id"], parent_id=m["parent_id"], nombre=nuevo, excepto=medicion_id
        ):
            raise ErrorDeCuantificacion(f"Ya hay una medición llamada «{nuevo}» en ese lugar.")
        async with self._uow:
            await self._mediciones.renombrar(medicion_id, nuevo)
            await self._uow.commit()

    async def eliminar(self, medicion_id: UUID) -> None:
        """Solo se borra una medición sin asignaciones ni submediciones; sus trazos quedan sueltos."""
        if await self._mediciones.obtener(medicion_id) is None:
            raise MedicionNoEncontrada(f"La medición {medicion_id} no existe o está fuera de tu alcance.")
        dep = await self._mediciones.dependencias(medicion_id)
        if dep["asignaciones"] > 0:
            raise ErrorDeCuantificacion(
                "Esta medición alimenta conceptos: quita primero sus asignaciones y después bórrala."
            )
        if dep["hijas"] > 0:
            raise ErrorDeCuantificacion("Esta medición tiene submediciones: bórralas o muévelas primero.")
        async with self._uow:
            await self._mediciones.eliminar(medicion_id)
            await self._uow.commit()

    # --- trazos dentro de la medición ------------------------------------------------------------

    async def asignar_trazo(
        self,
        *,
        trazo_id: UUID,
        medicion_id: UUID | None,
        usuario_id: UUID,
        detectada_en: datetime,
    ) -> tuple:
        """Mete un trazo suelto en una medición (o lo saca, con `None`). Al salir de una, pierde los
        enlaces que le venían de ella; al entrar a otra, recibe los suyos."""
        info = await self._mediciones.info_de_trazo(trazo_id)
        if info is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o está fuera de tu alcance.")
        if info["hueco_de"] is not None:
            raise ErrorDeCuantificacion("Un hueco no se asigna: va con el área de la que resta.")
        if medicion_id is not None:
            m = await self._mediciones.obtener(medicion_id)
            if m is None:
                raise MedicionNoEncontrada(f"La medición {medicion_id} no existe o está fuera de tu alcance.")
            if m["plano_id"] != info["plano_id"]:
                raise ErrorDeCuantificacion("El trazo y la medición son de planos distintos.")
            motivo = motivo_de_incompatibilidad(m["tipo"], info["geometria"], bool(info["tiene_forma"]))
            if motivo is not None:
                raise ErrorDeCuantificacion(motivo)
        anterior = info["medicion_id"]
        if anterior == medicion_id:
            return ()

        tocados: set[NodoActividad] = set()
        async with self._uow:
            if anterior is not None:
                tocados |= await self._desenlazar(trazo_id, anterior)
            await self._mediciones.poner_trazo(trazo_id, medicion_id)
            if medicion_id is not None:
                tocados |= await aplicar_asignaciones_a_trazo(
                    trazo_id=trazo_id,
                    medicion_id=medicion_id,
                    mediciones=self._mediciones,
                    enlaces=self._enlaces,
                )
            recalculos = await self._recalcular(tocados, detectada_en)
            await self._uow.commit()
        await _avisar_reaperturas(self._eventos, recalculos, usuario_id)
        return recalculos

    async def _desenlazar(self, trazo_id: UUID, medicion_id: UUID) -> set[NodoActividad]:
        """Quita los enlaces que le vinieron al trazo de su medición y de las que la contienen."""
        tocados: set[NodoActividad] = set()
        for a in await self._mediciones.asignaciones_de(await self._mediciones.con_ancestros(medicion_id)):
            for e in await self._mediciones.enlaces_de_asignacion(a["id"]):
                if e["trazo_id"] == trazo_id:
                    await self._enlaces.marcar_no_vigente(e["id"])
                    tocados.add((a["actividad_id"], a["matriz_concepto_id"]))
        return tocados

    # --- asignar a conceptos ---------------------------------------------------------------------

    async def crear_asignacion(
        self, cmd: ComandoCrearAsignacion, *, detectada_en: datetime
    ) -> ResultadoDeAsignacion:
        m = await self._mediciones.obtener(cmd.medicion_id)
        if m is None:
            raise MedicionNoEncontrada(f"La medición {cmd.medicion_id} no existe o está fuera de tu alcance.")
        if not medida_admitida(m["tipo"], cmd.medida):
            raise ErrorDeCuantificacion(
                f"Una medición de tipo {m['tipo']} no se asigna con la medida «{cmd.medida}»."
            )
        if cmd.factor <= 0:
            raise ErrorDeCuantificacion("El factor debe ser un número mayor que cero.")
        if cmd.medida == "conteo" and cmd.factor != cmd.factor.to_integral_value():
            raise ErrorDeCuantificacion("Un enlace de conteo lleva un factor entero: ya cuenta instancias.")
        if not await self._mediciones.actividad_de_la_obra(cmd.actividad_id, m["plano_id"]):
            raise ErrorDeCuantificacion("Ese concepto no es de la obra de este plano.")
        if cmd.matriz_concepto_id is not None and self._matrices is not None:
            arbol = await self._matrices.arbol_de_actividad(cmd.actividad_id)
            if arbol is None or cmd.matriz_concepto_id not in {x["concepto_id"] for x in arbol["matrices"]}:
                raise ErrorDeCuantificacion(
                    "Esa no es una matriz interna del concepto de la actividad: solo se miden las que "
                    "su receta contiene (D-583)."
                )
        # La misma medida del mismo concepto no se asigna dos veces en una misma rama: se contaría doble.
        rama = list(
            dict.fromkeys(
                [*await self._mediciones.con_ancestros(cmd.medicion_id), *await self._mediciones.con_descendientes(cmd.medicion_id)]
            )
        )
        if await self._mediciones.asignacion_equivalente(
            medicion_ids=rama,
            actividad_id=cmd.actividad_id,
            matriz_concepto_id=cmd.matriz_concepto_id,
            medida=cmd.medida,
        ):
            raise ErrorDeCuantificacion(
                "Ese concepto ya recibe esa medida de esta medición, de una que la contiene o de una "
                "que contiene: se contaría doble."
            )

        async with self._uow:
            asignacion_id = await self._mediciones.crear_asignacion(
                medicion_id=cmd.medicion_id,
                actividad_id=cmd.actividad_id,
                matriz_concepto_id=cmd.matriz_concepto_id,
                medida=cmd.medida,
                factor=cmd.factor,
                autor_id=cmd.autor_id,
            )
            trazos = await self._mediciones.trazos_de(await self._mediciones.con_descendientes(cmd.medicion_id))
            for trazo_id in trazos:
                if await self._mediciones.enlace_vigente_equivalente(
                    trazo_id=trazo_id,
                    actividad_id=cmd.actividad_id,
                    matriz_concepto_id=cmd.matriz_concepto_id,
                    medida=cmd.medida,
                ):
                    continue
                validado = EnlaceCuantificacion(
                    trazo_id=str(trazo_id),
                    actividad_id=str(cmd.actividad_id),
                    prototipo_nodo_id=None,
                    medida=MedidaCuantificacion(cmd.medida),
                    factor=cmd.factor,
                    matriz_concepto_id=str(cmd.matriz_concepto_id) if cmd.matriz_concepto_id else None,
                )
                await self._enlaces.crear(
                    trazo_id=trazo_id,
                    actividad_id=cmd.actividad_id,
                    prototipo_nodo_id=None,
                    matriz_concepto_id=cmd.matriz_concepto_id,
                    medida=validado.medida.value,
                    factor=validado.factor,
                    asignacion_id=asignacion_id,
                )
            recalculos = await self._recalcular({(cmd.actividad_id, cmd.matriz_concepto_id)}, detectada_en)
            await self._uow.commit()
        await _avisar_reaperturas(self._eventos, recalculos, cmd.autor_id)
        return ResultadoDeAsignacion(asignacion_id=asignacion_id, trazos_enlazados=len(trazos), recalculos=recalculos)

    async def quitar_asignacion(
        self, asignacion_id: UUID, *, usuario_id: UUID, detectada_en: datetime
    ) -> ResultadoDeAsignacion:
        a = await self._mediciones.obtener_asignacion(asignacion_id)
        if a is None:
            raise MedicionNoEncontrada(f"La asignación {asignacion_id} no existe o está fuera de tu alcance.")
        async with self._uow:
            enlaces = await self._mediciones.enlaces_de_asignacion(asignacion_id)
            for e in enlaces:
                await self._enlaces.marcar_no_vigente(e["id"])
            await self._mediciones.eliminar_asignacion(asignacion_id)
            recalculos = await self._recalcular({(a["actividad_id"], a["matriz_concepto_id"])}, detectada_en)
            await self._uow.commit()
        await _avisar_reaperturas(self._eventos, recalculos, usuario_id)
        return ResultadoDeAsignacion(asignacion_id=None, trazos_enlazados=len(enlaces), recalculos=recalculos)

    async def _recalcular(self, nodos: set[NodoActividad], detectada_en: datetime) -> tuple:
        return tuple(
            [
                await _recalcular_nodo(
                    tipo_nodo=TipoNodoCuantificacion.ACTIVIDAD,
                    actividad_id=actividad_id,
                    prototipo_nodo_id=None,
                    matriz_concepto_id=matriz_id,
                    enlaces=self._enlaces,
                    actividades=self._actividades,
                    prototipo_nodos=self._prototipo_nodos,
                    desviaciones=self._desviaciones,
                    detectada_en=detectada_en,
                    matrices=self._matrices,
                )
                for actividad_id, matriz_id in nodos
            ]
        )
