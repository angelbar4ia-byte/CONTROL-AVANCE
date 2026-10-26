"""Casos de uso: las partes de una obra y sus plantas (migración 0074; D-571, D-575).

Una **parte** es una etapa de construcción o un concepto independiente (losas, pisos): la
unidad que los escenarios de arranque envían, autorizan y programan por separado
(`domain.partes`). Aquí solo se secuencia: leer las partes, marcar una actividad como parte
independiente y fijar el número de plantas (1 o 2) de una obra o de un prototipo.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.casos_uso.gestionar_programacion import ActividadNoProgramable
from obractrl.application.eventos import PartesCambiaronDeEstado, PublicadorEventos
from obractrl.application.puertos.partes import RepositorioPartes
from obractrl.application.puertos.repositorios import (
    RepositorioConfiguracion,
    RepositorioObras,
    UnidadDeTrabajo,
)
from obractrl.domain.partes.alertas import (
    AVISO_DIAS,
    IMPORTANTE_DIAS,
    dias_para_necesitarla,
    severidad_del_desfase,
    validar_umbrales,
)
from obractrl.domain.partes.estado import (
    ORDEN,
    PERMISOS,
    Accion,
    ErrorDeParte,
    EstadoDeParte,
    ParteNoPermitida,
    aplicar,
    deja_programa_por_revisar,
)
from obractrl.domain.partes.parte import ActividadParaParte, Parte, agrupar_en_partes
from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "CambiarEstadoDePartes",
    "ComandoCambiarEstadoDePartes",
    "ConsultarAlertasDePartes",
    "ConsultarArranque",
    "ConsultarBitacoraDePartes",
    "ConsultarDesfaseDePartes",
    "ConsultarPartes",
    "ErrorDeParte",
    "ErrorDePlantas",
    "FijarCandadoDeAsignar",
    "FijarDesfaseDePartes",
    "FijarPlantasDeObra",
    "FijarPlantasDePrototipo",
    "MarcarParteIndependiente",
    "ParteNoEncontrada",
    "ParteNoPermitida",
    "PrototipoNoEncontrado",
]


class ErrorDePlantas(ValueError):
    """Las plantas son 1 o 2 (planta baja y alta; el roof garden no cuenta)."""


class ParteNoEncontrada(LookupError):
    """La obra no tiene esa parte (o la obra no se ve)."""


class PrototipoNoEncontrado(LookupError):
    """El prototipo no existe o está fuera del alcance (RLS)."""


def _plantas_validas(plantas: int | None) -> int | None:
    if plantas is not None and plantas not in (1, 2):
        raise ErrorDePlantas(f"Una casa tiene 1 o 2 plantas, no {plantas}.")
    return plantas


async def _partes_de(partes: RepositorioPartes, obra_id: UUID) -> list[Parte]:
    actividades = [
        ActividadParaParte(
            id=str(f["id"]),
            descripcion=f["descripcion"],
            avance_pct=Decimal(str(f["avance_pct"] or 0)),
            importe=Decimal(str(f["importe"] or 0)),
            etapa_id=str(f["etapa_id"]) if f["etapa_id"] else None,
            etapa_nombre=f["etapa_nombre"],
            nivel_clave=f["nivel_clave"],
            independiente=bool(f["independiente"]),
            fecha_inicio=f["fecha_inicio"],
        )
        for f in await partes.actividades_de_obra(obra_id)
    ]
    return agrupar_en_partes(actividades)


class ConsultarPartes:
    """`GET /obras/{id}/partes`: las partes de la obra con su importe y su avance."""

    def __init__(self, *, partes: RepositorioPartes, obras: RepositorioObras) -> None:
        self._partes = partes
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> dict[str, Any]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        plantas = await self._partes.plantas_de_obra(obra_id) or {}
        estados = await self._partes.estados_de_obra(obra_id)
        por_revisar = await self._partes.programas_por_revisar(obra_id)
        return {
            "obra_id": obra_id,
            "plantas": plantas.get("plantas"),
            "plantas_del_prototipo": plantas.get("plantas_del_prototipo"),
            "partes": [
                {
                    "clave": p.clave,
                    "tipo": p.tipo.value,
                    "id": UUID(p.id) if p.id else None,
                    "nombre": p.nombre,
                    "estado": estados.get(p.clave, EstadoDeParte.CUANTIFICANDO.value),
                    "programa_por_revisar": p.clave in por_revisar,
                    "n_actividades": len(p.actividad_ids),
                    "actividad_ids": [UUID(i) for i in p.actividad_ids],
                    "importe": p.importe,
                    "avance_pct": p.avance_pct,
                }
                for p in await _partes_de(self._partes, obra_id)
            ],
        }


class MarcarParteIndependiente:
    """Una actividad pasa a ser una parte por sí sola (o vuelve a viajar con su etapa)."""

    def __init__(self, *, partes: RepositorioPartes, uow: UnidadDeTrabajo) -> None:
        self._partes = partes
        self._uow = uow

    async def ejecutar(self, actividad_id: UUID, independiente: bool) -> None:
        antes = await self._partes.parte_de_actividad(actividad_id)
        if antes is None:
            raise ActividadNoProgramable(f"Actividad {actividad_id} no encontrada en tu alcance.")
        async with self._uow:
            if not await self._partes.marcar_independiente(actividad_id, independiente):
                raise ActividadNoProgramable(
                    f"Actividad {actividad_id} ya no está en tu alcance."
                )
            despues = await self._partes.parte_de_actividad(actividad_id)
            if despues is not None and despues["clave"] != antes["clave"]:
                # La parte nueva sigue el paso de la que dejó: no vuelve a cuantificando.
                estados = await self._partes.estados_de_obra(antes["obra_id"])
                heredado = estados.get(antes["clave"])
                if heredado is not None and despues["clave"] not in estados:
                    await self._partes.fijar_estado(
                        antes["obra_id"], despues["clave"], heredado, None
                    )
            await self._uow.commit()


class FijarPlantasDeObra:
    def __init__(self, *, partes: RepositorioPartes, uow: UnidadDeTrabajo) -> None:
        self._partes = partes
        self._uow = uow

    async def ejecutar(self, obra_id: UUID, plantas: int | None) -> None:
        plantas = _plantas_validas(plantas)
        async with self._uow:
            if not await self._partes.fijar_plantas_de_obra(obra_id, plantas):
                raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
            await self._uow.commit()


class FijarPlantasDePrototipo:
    def __init__(self, *, partes: RepositorioPartes, uow: UnidadDeTrabajo) -> None:
        self._partes = partes
        self._uow = uow

    async def ejecutar(self, prototipo_id: UUID, plantas: int | None) -> None:
        plantas = _plantas_validas(plantas)
        async with self._uow:
            if not await self._partes.fijar_plantas_de_prototipo(prototipo_id, plantas):
                raise PrototipoNoEncontrado(
                    f"Prototipo {prototipo_id} no encontrado en tu alcance."
                )
            await self._uow.commit()


@dataclass(frozen=True, slots=True)
class ComandoCambiarEstadoDePartes:
    obra_id: UUID
    accion: Accion
    usuario_id: UUID
    rol: Rol
    claves: tuple[str, ...] = ()
    todas: bool = False
    a: EstadoDeParte | None = None
    nota: str | None = None


class CambiarEstadoDePartes:
    """Manda, autoriza, valida, programa, asigna o devuelve **una, varias o todas** las partes
    de una obra («total o por partes», D-571).

    Es **todo o nada**: se calcula el paso de cada parte antes de escribir, y si una no puede
    darlo (permiso o estado) no se escribe ninguna. Con `todas` se toman solo las partes que
    están en el paso que la acción pide; si no hay ninguna, se dice.
    """

    def __init__(
        self,
        *,
        partes: RepositorioPartes,
        obras: RepositorioObras,
        uow: UnidadDeTrabajo,
        eventos: PublicadorEventos,
    ) -> None:
        self._partes = partes
        self._obras = obras
        self._uow = uow
        self._eventos = eventos

    async def ejecutar(self, cmd: ComandoCambiarEstadoDePartes) -> list[dict[str, str]]:
        if not cmd.todas and not cmd.claves:
            raise ErrorDeParte("Dime qué partes, o pide todas.")
        # El permiso va primero: quien no puede no se entera de cómo está la obra.
        if cmd.rol not in PERMISOS[cmd.accion]:
            raise ParteNoPermitida(
                f"El rol {cmd.rol.value!r} no puede hacer {cmd.accion.value.replace('_', ' ')!r} "
                "sobre una parte."
            )
        if await self._obras.obtener(cmd.obra_id) is None:
            raise ObraNoEncontrada(f"Obra {cmd.obra_id} no encontrada en tu alcance.")

        existentes = {p.clave for p in await _partes_de(self._partes, cmd.obra_id)}
        estados = await self._partes.estados_de_obra(cmd.obra_id)

        def estado_de(clave: str) -> EstadoDeParte:
            return EstadoDeParte(estados.get(clave, EstadoDeParte.CUANTIFICANDO.value))

        if cmd.todas:
            candidatas = sorted(existentes)
            claves: list[str] = []
            for clave in candidatas:
                try:
                    aplicar(cmd.accion, estado=estado_de(clave), rol=cmd.rol, a=cmd.a)
                except ErrorDeParte:
                    continue
                claves.append(clave)
            if not claves:
                raise ErrorDeParte(
                    f"Ninguna parte está en el paso que pide {cmd.accion.value.replace('_', ' ')!r}."
                )
        else:
            claves = list(dict.fromkeys(cmd.claves))
            desconocidas = [c for c in claves if c not in existentes]
            if desconocidas:
                raise ParteNoEncontrada(f"La obra no tiene las partes: {', '.join(desconocidas)}.")

        # El candado de asignar (D-574), por obra: con él puesto, validar exige una anotación y
        # asignar exige que quien validó la haya dejado.
        if cmd.accion in (Accion.VALIDAR, Accion.ASIGNAR) and await self._partes.candado_de_obra(
            cmd.obra_id
        ):
            if cmd.accion is Accion.VALIDAR and not (cmd.nota or "").strip():
                raise ErrorDeParte(
                    "Esta obra tiene puesto el candado de asignar: quien valida deja una anotación."
                )
            if cmd.accion is Accion.ASIGNAR:
                con_nota = await self._partes.validaciones_con_anotacion(cmd.obra_id)
                sin = [c for c in claves if c not in con_nota]
                if sin:
                    raise ErrorDeParte(
                        "Esta obra tiene puesto el candado de asignar: falta la anotación de quien "
                        f"validó {', '.join(sin)}. Devuelve la parte y vuelve a validarla."
                    )

        # Se calcula todo antes de escribir: o pasan todas, o ninguna.
        pasos = [
            (clave, estado_de(clave), aplicar(cmd.accion, estado=estado_de(clave), rol=cmd.rol, a=cmd.a))
            for clave in claves
        ]

        async with self._uow:
            for clave, de, a in pasos:
                # Devolver una parte que ya tenía programa lo deja «por revisar»; volver a
                # programarla (programar) lo quita.
                revisar = (
                    True
                    if cmd.accion is Accion.DEVOLVER and deja_programa_por_revisar(de)
                    else False
                    if cmd.accion is Accion.PROGRAMAR
                    else None
                )
                await self._partes.fijar_estado(
                    cmd.obra_id, clave, a.value, cmd.usuario_id, programa_por_revisar=revisar
                )
                await self._partes.registrar_transicion(
                    obra_id=cmd.obra_id,
                    clave=clave,
                    accion=cmd.accion.value,
                    de=de.value,
                    a=a.value,
                    usuario_id=cmd.usuario_id,
                    rol=cmd.rol.value,
                    nota=cmd.nota,
                )
            await self._uow.commit()

        await self._eventos.publicar(
            PartesCambiaronDeEstado(
                obra_id=cmd.obra_id,
                accion=cmd.accion.value,
                claves=tuple(c for c, _, _ in pasos),
                estados=tuple(a.value for _, _, a in pasos),
                usuario_id=cmd.usuario_id,
                programa_por_revisar=tuple(
                    c
                    for c, de, _ in pasos
                    if cmd.accion is Accion.DEVOLVER and deja_programa_por_revisar(de)
                ),
            )
        )
        return [{"clave": c, "de": de.value, "a": a.value} for c, de, a in pasos]


class ConsultarBitacoraDePartes:
    """`GET /obras/{id}/partes/bitacora`: quién mandó, autorizó o devolvió qué."""

    def __init__(self, *, partes: RepositorioPartes, obras: RepositorioObras) -> None:
        self._partes = partes
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> list[dict[str, Any]]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        return await self._partes.bitacora_de_obra(obra_id)


_CLAVE_AVISO = "desfase_presupuesto_aviso_dias"
_CLAVE_IMPORTANTE = "desfase_presupuesto_importante_dias"


async def _umbrales(config: RepositorioConfiguracion) -> tuple[int, int]:
    aviso = int(await config.decimal(_CLAVE_AVISO, Decimal(AVISO_DIAS)))
    importante = int(await config.decimal(_CLAVE_IMPORTANTE, Decimal(IMPORTANTE_DIAS)))
    return aviso, importante


class ConsultarAlertasDePartes:
    """`GET /obras/{id}/partes/alertas`: el presupuesto debe ir por delante del programa.

    Una parte sin autorizar cuyo programa la necesita pronto avisa (a las 2 semanas) o es
    importante (a la semana o vencida). Los umbrales son globales (D-577). Avisa; no bloquea.
    """

    def __init__(
        self,
        *,
        partes: RepositorioPartes,
        obras: RepositorioObras,
        configuracion: RepositorioConfiguracion,
    ) -> None:
        self._partes = partes
        self._obras = obras
        self._config = configuracion

    async def ejecutar(self, obra_id: UUID, *, hoy: date | None = None) -> dict[str, Any]:
        if await self._obras.obtener(obra_id) is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        hoy = hoy or date.today()
        aviso, importante = await _umbrales(self._config)
        estados = await self._partes.estados_de_obra(obra_id)
        alertas = []
        for p in await _partes_de(self._partes, obra_id):
            estado = EstadoDeParte(estados.get(p.clave, EstadoDeParte.CUANTIFICANDO.value))
            if p.inicio is None or ORDEN.index(estado) >= ORDEN.index(EstadoDeParte.AUTORIZADA):
                continue  # ya autorizada, o el programa aún no la necesita en una fecha
            dias = dias_para_necesitarla(p.inicio, hoy)
            severidad = severidad_del_desfase(dias, aviso_dias=aviso, importante_dias=importante)
            if severidad is not None:
                alertas.append(
                    {
                        "clave": p.clave,
                        "nombre": p.nombre,
                        "estado": estado.value,
                        "inicio": p.inicio,
                        "dias": dias,
                        "severidad": severidad.value,
                    }
                )
        alertas.sort(key=lambda a: (a["dias"], a["nombre"]))
        return {
            "obra_id": obra_id,
            "aviso_dias": aviso,
            "importante_dias": importante,
            "alertas": alertas,
        }


class ConsultarArranque:
    """`GET /obras/{id}/arranque`: lo que la junta de arranque tiene a la vista (D-574).

    «Todo validado» es un requisito de la junta: aquí se lista qué partes aún no están
    autorizadas. **Avisa; lo que impide es asignar (el candado, por obra).**
    """

    def __init__(self, *, partes: RepositorioPartes, obras: RepositorioObras) -> None:
        self._partes = partes
        self._obras = obras

    async def ejecutar(self, obra_id: UUID) -> dict[str, Any]:
        obra = await self._obras.obtener(obra_id)
        if obra is None:
            raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
        estados = await self._partes.estados_de_obra(obra_id)
        por_revisar = await self._partes.programas_por_revisar(obra_id)
        partes = await _partes_de(self._partes, obra_id)
        conteo: dict[str, int] = {e.value: 0 for e in EstadoDeParte}
        sin_autorizar = []
        for p in partes:
            estado = EstadoDeParte(estados.get(p.clave, EstadoDeParte.CUANTIFICANDO.value))
            conteo[estado.value] += 1
            if ORDEN.index(estado) < ORDEN.index(EstadoDeParte.AUTORIZADA):
                sin_autorizar.append(
                    {"clave": p.clave, "nombre": p.nombre, "estado": estado.value}
                )
        return {
            "obra_id": obra_id,
            "candado_asignar": bool(await self._partes.candado_de_obra(obra_id)),
            "total": len(partes),
            "por_estado": conteo,
            "sin_autorizar": sin_autorizar,
            "todo_validado": bool(partes) and not sin_autorizar,
            "programas_por_revisar": len(por_revisar),
        }


class FijarCandadoDeAsignar:
    def __init__(self, *, partes: RepositorioPartes, uow: UnidadDeTrabajo) -> None:
        self._partes = partes
        self._uow = uow

    async def ejecutar(self, obra_id: UUID, activo: bool) -> None:
        async with self._uow:
            if not await self._partes.fijar_candado(obra_id, activo):
                raise ObraNoEncontrada(f"Obra {obra_id} no encontrada en tu alcance.")
            await self._uow.commit()


class ConsultarDesfaseDePartes:
    """`GET /configuracion/desfase-de-partes`: los umbrales globales de la alerta (D-577)."""

    def __init__(self, *, configuracion: RepositorioConfiguracion) -> None:
        self._config = configuracion

    async def ejecutar(self) -> dict[str, int]:
        aviso, importante = await _umbrales(self._config)
        return {"aviso_dias": aviso, "importante_dias": importante}


class FijarDesfaseDePartes:
    """`PUT /configuracion/desfase-de-partes`: Control de obra edita los umbrales (D-577)."""

    def __init__(self, *, configuracion: Any, uow: UnidadDeTrabajo) -> None:
        self._config = configuracion
        self._uow = uow

    async def ejecutar(self, aviso_dias: int, importante_dias: int) -> dict[str, int]:
        aviso, importante = validar_umbrales(aviso_dias, importante_dias)
        async with self._uow:
            await self._config.fijar(_CLAVE_AVISO, aviso)
            await self._config.fijar(_CLAVE_IMPORTANTE, importante)
            await self._uow.commit()
        return {"aviso_dias": aviso, "importante_dias": importante}
