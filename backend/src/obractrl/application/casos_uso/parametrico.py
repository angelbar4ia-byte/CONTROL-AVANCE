"""El Paramétrico: drivers (global, por obra, mixto) y enlace de ranuras con el árbol de la obra (Ola 4B; migración 0134).

**Drivers.** Costos y Control de obra editan el valor y el modo (`fijo` / `ajustable`) del driver global y, en un driver
`ajustable`, el valor propio de una obra (Q3). Cambiar un driver **no recalcula nada guardado** (Q1): el driver solo da la altura
de lo que nace sin ella.

**Enlace de ranuras.** Cada ranura (un concepto que un elemento o una plantilla necesita) se enlaza, en una obra y por capa, con
un concepto del Presupuesto. Si el árbol de la obra no trae la partida, la ranura avisa y no cuenta. Aquí no se inventa ningún
concepto, precio ni destajo: solo se enlaza lo que ya existe en el catálogo. Todo cambio queda en la bitácora de negocio.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import MedicionNoEncontrada
from obractrl.application.casos_uso.generar_obra_desde_prototipo import ObraNoEncontrada
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.drivers import (
    CATALOGO_DE_DRIVERS,
    DefinicionDeDriver,
    ErrorDeDriver,
    ValorVigente,
    definicion_de,
    resolver,
    validar_modo,
    validar_que_edita,
    validar_valor,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import (
    Capa,
    Contexto,
    EnlaceDeRanura,
    ErrorDeEnlaceDeRanura,
    Partida,
    RanuraConocida,
    Resolucion,
    ranuras_de_plantilla,
    resolver_ranura,
    validar_que_enlaza,
    validar_ranura,
    validar_ubicacion,
)

__all__ = ["DriverNoEncontrado", "EnlaceNoEncontrado", "GestionarDrivers", "GestionarEnlacesDeRanura"]


class DriverNoEncontrado(MedicionNoEncontrada):
    """Esa clave no es un driver del Paramétrico."""


class EnlaceNoEncontrado(MedicionNoEncontrada):
    """El enlace no existe o está fuera del alcance."""


def _definicion(clave: str) -> DefinicionDeDriver:
    d = definicion_de(clave)
    if d is None:
        raise DriverNoEncontrado(f"«{clave}» no es un driver del Paramétrico.")
    return d


def _limpio(n: Decimal | None) -> Decimal | None:
    """El número como se teclea: 2.8, no 2.800000; 40, no 4E+1."""
    return None if n is None else Decimal(format(n.normalize(), "f"))


def _fila(d: DefinicionDeDriver, v: ValorVigente, *, editado: bool) -> dict[str, Any]:
    return {
        "clave": d.clave, "nombre": d.nombre, "unidad": d.unidad, "nota": d.nota, "por_confirmar": d.por_confirmar,
        "valor_inicial": _limpio(d.inicial), "modo_inicial": d.modo_inicial,
        "valor_global": _limpio(v.valor_global), "modo": v.modo, "valor_obra": _limpio(v.valor_obra),
        "valor_vigente": _limpio(v.valor), "origen": v.origen, "ajuste_ignorado": v.ajuste_ignorado, "editado": editado,
    }


class GestionarDrivers:
    def __init__(self, *, parametrico: Any, uow: UnidadDeTrabajo) -> None:
        self._p = parametrico
        self._uow = uow

    async def _obra(self, obra_id: UUID) -> None:
        if not await self._p.obra_visible(obra_id):
            raise ObraNoEncontrada(f"La obra {obra_id} no existe o está fuera de tu alcance.")

    async def listar(self, obra_id: UUID | None = None) -> list[dict[str, Any]]:
        """Los drivers con su valor vigente: el de la organización o, con obra, el de esa obra."""
        if obra_id is not None:
            await self._obra(obra_id)
        globales = await self._p.globales()
        de_obra = await self._p.de_obra(obra_id) if obra_id is not None else {}
        filas = []
        for d in CATALOGO_DE_DRIVERS:
            g, o = globales.get(d.clave), de_obra.get(d.clave)
            v = resolver(
                d,
                valor_global=g["valor"] if g else None,
                modo_global=g["modo"] if g else None,
                valor_obra=o["valor"] if o else None,
            )
            filas.append(_fila(d, v, editado=g is not None))
        return filas

    async def vigentes(self, obra_id: UUID | None = None) -> dict[str, Decimal]:
        """`clave → valor vigente`: lo que los cálculos de elementos y plantillas leen."""
        return {f["clave"]: f["valor_vigente"] for f in await self.listar(obra_id)}

    async def _uno(self, clave: str, obra_id: UUID | None) -> dict[str, Any]:
        return next(f for f in await self.listar(obra_id) if f["clave"] == clave)

    async def fijar_global(
        self, clave: str, *, valor: object | None, modo: str | None, usuario_id: UUID, rol: str
    ) -> dict[str, Any]:
        """Cambia el valor y/o el modo del driver global. Lo no enviado se conserva."""
        validar_que_edita(rol)
        d = _definicion(clave)
        if valor is None and modo is None:
            raise ErrorDeDriver("Indica el valor o el modo del driver.")
        actual = (await self._p.globales()).get(clave)
        nuevo_valor = validar_valor(d, valor) if valor is not None else (actual["valor"] if actual else d.inicial)
        nuevo_modo = validar_modo(modo) if modo is not None else (actual["modo"] if actual else d.modo_inicial)
        async with self._uow:
            await self._p.guardar_global(clave, nuevo_valor, nuevo_modo, usuario_id)
            await self._uow.commit()
        return await self._uno(clave, None)

    async def fijar_de_obra(self, obra_id: UUID, clave: str, *, valor: object, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """El valor propio de una obra para un driver ajustable (Q3: Costos y Control de obra)."""
        validar_que_edita(rol)
        d = _definicion(clave)
        await self._obra(obra_id)
        g = (await self._p.globales()).get(clave)
        modo = g["modo"] if g else d.modo_inicial
        if modo != "ajustable":
            raise ErrorDeDriver(f"«{d.nombre}» es fijo: la obra no lo ajusta. Primero se cambia a ajustable en los drivers globales.")
        limpio = validar_valor(d, valor)
        async with self._uow:
            await self._p.guardar_de_obra(obra_id, clave, limpio, usuario_id)
            await self._uow.commit()
        return await self._uno(clave, obra_id)

    async def quitar_de_obra(self, obra_id: UUID, clave: str, *, rol: str) -> dict[str, Any]:
        """La obra vuelve al valor global."""
        validar_que_edita(rol)
        _definicion(clave)
        await self._obra(obra_id)
        async with self._uow:
            await self._p.quitar_de_obra(obra_id, clave)
            await self._uow.commit()
        return await self._uno(clave, obra_id)


def _a_enlace(f: dict[str, Any]) -> EnlaceDeRanura:
    return EnlaceDeRanura(
        id=f["id"], ranura=f["ranura"], capa=Capa(f["nivel_id"], f["etapa_id"], f["ubicacion"]),
        concepto_id=f["concepto_id"], concepto_clave=f["concepto_clave"],
    )


def _a_partida(f: dict[str, Any]) -> Partida:
    return Partida(id=f["id"], concepto_id=f["concepto_id"], nivel_id=f["nivel_id"], etapa_id=f["etapa_id"], nombre=f["nombre"], orden=f["orden"])


def _resumen(r: Resolucion) -> dict[str, Any]:
    return {
        "estado": r.estado, "cuenta": r.cuenta, "por_defecto": r.por_defecto, "aviso": r.aviso,
        "enlace_id": r.enlace.id if r.enlace else None,
        "concepto_id": r.enlace.concepto_id if r.enlace else None,
        "concepto_clave": r.enlace.concepto_clave if r.enlace else None,
        "partida_id": r.partida.id if r.partida else None,
        "partida_nombre": r.partida.nombre if r.partida else None,
    }


class GestionarEnlacesDeRanura:
    def __init__(self, *, parametrico: Any, uow: UnidadDeTrabajo) -> None:
        self._p = parametrico
        self._uow = uow

    async def _obra(self, obra_id: UUID) -> None:
        if not await self._p.obra_visible(obra_id):
            raise ObraNoEncontrada(f"La obra {obra_id} no existe o está fuera de tu alcance.")

    async def listar(self, obra_id: UUID) -> dict[str, Any]:
        """Los enlaces de la obra, cada uno con lo que cuenta en su propia capa, y las capas y ranuras de plantilla para elegir."""
        await self._obra(obra_id)
        filas = await self._p.enlaces(obra_id)
        enlaces = [_a_enlace(f) for f in filas]
        partidas = [_a_partida(f) for f in await self._p.partidas(obra_id)]
        capas = await self._p.capas(obra_id)
        salida = []
        for f, e in zip(filas, enlaces, strict=True):
            r = resolver_ranura([e], partidas, e.ranura, Contexto(e.capa.nivel_id, e.capa.etapa_id, e.capa.ubicacion))
            salida.append({**f, "capa": e.capa, **{k: v for k, v in _resumen(r).items() if k != "enlace_id"}})
        return {
            "enlaces": salida,
            "ranuras_de_plantilla": [self._plantilla(r) for r in ranuras_de_plantilla()],
            "niveles": capas["niveles"],
            "etapas": capas["etapas"],
            "partidas_del_arbol": len(partidas),
        }

    @staticmethod
    def _plantilla(r: RanuraConocida) -> dict[str, Any]:
        return {"ranura": r.ranura, "nombre": r.nombre, "grupo": r.grupo, "sugerido_clave": r.sugerido_clave}

    async def resolver(
        self, obra_id: UUID, ranura: str, *, nivel_id: UUID | None, etapa_id: UUID | None, ubicacion: str | None
    ) -> dict[str, Any]:
        """Lo que cuenta una ranura donde se mide (nivel, etapa y ubicación): el concepto, su partida o el aviso."""
        await self._obra(obra_id)
        ranura = validar_ranura(ranura)
        enlaces = [_a_enlace(f) for f in await self._p.enlaces(obra_id)]
        partidas = [_a_partida(f) for f in await self._p.partidas(obra_id)]
        r = resolver_ranura(enlaces, partidas, ranura, Contexto(nivel_id, etapa_id, validar_ubicacion(ubicacion)))
        return {"ranura": ranura, **_resumen(r)}

    async def guardar(
        self,
        obra_id: UUID,
        *,
        ranura: str,
        concepto_clave: str,
        nivel_id: UUID | None,
        etapa_id: UUID | None,
        ubicacion: str | None,
        usuario_id: UUID,
        rol: str,
    ) -> tuple[dict[str, Any], bool]:
        """Enlaza la ranura, en esa capa, con un concepto que ya existe. Si la capa ya tenía enlace, le cambia el concepto."""
        validar_que_enlaza(rol)
        await self._obra(obra_id)
        ranura = validar_ranura(ranura)
        ubicacion = validar_ubicacion(ubicacion)
        concepto = await self._p.concepto_por_clave(concepto_clave) if (concepto_clave or "").strip() else None
        if concepto is None:
            raise ErrorDeEnlaceDeRanura(f"El concepto «{concepto_clave}» no existe en el catálogo: no se inventa uno aquí.")
        if nivel_id is not None and not await self._p.nivel_o_etapa_existe("nivel", nivel_id):
            raise ErrorDeEnlaceDeRanura("El nivel no existe.")
        if etapa_id is not None and not await self._p.nivel_o_etapa_existe("etapa_constructiva", etapa_id):
            raise ErrorDeEnlaceDeRanura("La etapa no existe.")
        async with self._uow:
            ident, creado = await self._p.guardar_enlace(
                obra_id=obra_id, ranura=ranura, nivel_id=nivel_id, etapa_id=etapa_id, ubicacion=ubicacion,
                concepto_id=concepto["id"], usuario_id=usuario_id,
            )
            await self._uow.commit()
        listado = await self.listar(obra_id)
        return next(e for e in listado["enlaces"] if e["id"] == ident), creado

    async def quitar(self, obra_id: UUID, enlace_id: UUID, *, rol: str) -> None:
        validar_que_enlaza(rol)
        await self._obra(obra_id)
        async with self._uow:
            if not await self._p.quitar_enlace(obra_id, enlace_id):
                raise EnlaceNoEncontrado(f"El enlace {enlace_id} no existe o está fuera de tu alcance.")
            await self._uow.commit()
