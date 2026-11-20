"""El Paramétrico: drivers (global, por obra, mixto) y enlace de ranuras con el árbol de la obra (Ola 4B; migración 0134).

**Drivers.** Costos y Control de obra PROPONEN el valor y el modo (`fijo` / `ajustable`) del driver global y, en un driver
`ajustable`, el valor propio de una obra (Q3); solo **Control de obra autoriza** (F3, 2026-11-19): lo que propone Control de obra
nace autorizado y se aplica; lo de Costos queda pendiente y no cambia nada hasta que Control de obra lo autorice. Cada propuesta guarda
quién, cuándo y el valor anterior (`propuesta_de_driver`, 0141). Los drivers inmutables (`escarpio_minimo`, `corona_cimiento_cm`, F4) no
se proponen. Cambiar un driver **no recalcula nada guardado** (Q1): el driver solo da la altura de lo que nace sin ella.

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
from obractrl.domain.cuantificacion.autorizacion_de_drivers import (
    PropuestaValidada,
    armar_propuesta,
    estado_de_alta,
    validar_que_autoriza,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.consumidores_de_drivers import (
    SIN_CONSUMIDOR_POR_AHORA,
    consumidores_de,
)
from obractrl.domain.cuantificacion.drivers import (
    CATALOGO_DE_DRIVERS,
    DefinicionDeDriver,
    ErrorDeDriver,
    ValorVigente,
    definicion_de,
    resolver,
    validar_que_edita,
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

__all__ = [
    "DriverNoEncontrado",
    "EnlaceNoEncontrado",
    "GestionarDrivers",
    "GestionarEnlacesDeRanura",
    "GestionarNumeroDeNivel",
    "NivelNoEncontrado",
    "PropuestaDeDriverNoEncontrada",
    "resueltos_de",
    "vigentes_de_obra",
]


class DriverNoEncontrado(MedicionNoEncontrada):
    """Esa clave no es un driver del Paramétrico."""


class PropuestaDeDriverNoEncontrada(MedicionNoEncontrada):
    """La propuesta de cambio de un driver no existe o está fuera del alcance."""


class NivelNoEncontrado(MedicionNoEncontrada):
    """El nivel no existe o está fuera del alcance."""


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


def _propuesta(p: dict[str, Any] | None) -> dict[str, Any] | None:
    """La propuesta con sus números como se teclean (10, no 10.000000)."""
    if p is None:
        return None
    return {**p, "valor": _limpio(p["valor"]), "valor_anterior": _limpio(p["valor_anterior"])}


def _fila(d: DefinicionDeDriver, v: ValorVigente, *, editado: bool, pendientes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "clave": d.clave, "nombre": d.nombre, "unidad": d.unidad, "nota": d.nota, "por_confirmar": d.por_confirmar,
        "valor_inicial": _limpio(d.inicial), "modo_inicial": d.modo_inicial,
        "valor_global": _limpio(v.valor_global), "modo": v.modo, "valor_obra": _limpio(v.valor_obra),
        "valor_vigente": _limpio(v.valor), "origen": v.origen, "ajuste_ignorado": v.ajuste_ignorado, "editado": editado,
        "lo_usan": [
            {"id": c.id, "tipo": c.tipo, "nombre": c.nombre, "lectura": "constante" if d.clave in c.constantes else "driver"}
            for c in consumidores_de(d.clave)
        ],
        "sin_consumidor": SIN_CONSUMIDOR_POR_AHORA.get(d.clave),
        "inmutable": d.inmutable,
        "propuestas_pendientes": [_propuesta(p) for p in (pendientes or []) if p["clave"] == d.clave],
    }


async def resueltos_de(parametrico: Any, obra_id: UUID | None) -> list[tuple[DefinicionDeDriver, ValorVigente, bool]]:
    """Cada driver del catálogo con su valor vigente (el de la obra, si se da, o el de la organización) y si el global ya fue editado.

    No revisa que la obra sea visible: quien la llama ya trabaja dentro de su alcance (el trazo, el cálculo con su `obra_id`)."""
    globales = await parametrico.globales()
    de_obra = await parametrico.de_obra(obra_id) if obra_id is not None else {}
    salida = []
    for d in CATALOGO_DE_DRIVERS:
        g, o = globales.get(d.clave), de_obra.get(d.clave)
        v = resolver(
            d,
            valor_global=g["valor"] if g else None,
            modo_global=g["modo"] if g else None,
            valor_obra=o["valor"] if o else None,
        )
        salida.append((d, v, g is not None))
    return salida


async def vigentes_de_obra(parametrico: Any, obra_id: UUID) -> dict[str, ValorVigente]:
    """`clave → valor vigente` de una obra, sin revisar visibilidad (para los casos de uso que ya tienen el trazo en su alcance)."""
    return {v.clave: v for _, v, _ in await resueltos_de(parametrico, obra_id)}


class GestionarDrivers:
    def __init__(self, *, parametrico: Any, uow: UnidadDeTrabajo) -> None:
        self._p = parametrico
        self._uow = uow

    async def _obra(self, obra_id: UUID) -> None:
        if not await self._p.obra_visible(obra_id):
            raise ObraNoEncontrada(f"La obra {obra_id} no existe o está fuera de tu alcance.")

    async def _resueltos(self, obra_id: UUID | None) -> list[tuple[DefinicionDeDriver, ValorVigente, bool]]:
        if obra_id is not None:
            await self._obra(obra_id)
        return await resueltos_de(self._p, obra_id)

    async def listar(self, obra_id: UUID | None = None) -> list[dict[str, Any]]:
        """Los drivers con su valor vigente: el de la organización o, con obra, el de esa obra; cada uno con sus propuestas pendientes."""
        resueltos = await self._resueltos(obra_id)
        pendientes = await self._p.propuestas_de_driver(estado="pendiente", obra_id=obra_id)
        if obra_id is None:
            pendientes = [p for p in pendientes if p["alcance"] == "global"]
        return [_fila(d, v, editado=editado, pendientes=pendientes) for d, v, editado in resueltos]

    async def valores(self, obra_id: UUID | None) -> dict[str, ValorVigente] | None:
        """Los valores vigentes con su origen, para los cálculos de elementos. Sin obra: `None` (el cálculo vale lo de siempre).

        Con una obra que no existe o está fuera del alcance levanta `ObraNoEncontrada` (404)."""
        if obra_id is None:
            return None
        return {v.clave: v for _, v, _ in await self._resueltos(obra_id)}

    async def vigentes(self, obra_id: UUID | None = None) -> dict[str, Decimal]:
        """`clave → valor vigente`: lo que los cálculos de elementos y plantillas leen."""
        return {f["clave"]: f["valor_vigente"] for f in await self.listar(obra_id)}

    async def _uno(self, clave: str, obra_id: UUID | None) -> dict[str, Any]:
        return next(f for f in await self.listar(obra_id) if f["clave"] == clave)

    # --- propuestas (F3) ------------------------------------------------------------------------------------------------------

    async def _antes(self, d: DefinicionDeDriver, alcance: str, obra_id: UUID | None) -> tuple[Decimal | None, str | None]:
        """El valor y el modo que hoy tiene lo que la propuesta cambia (para guardar el «antes»)."""
        if alcance == "global":
            g = (await self._p.globales()).get(d.clave)
            return (g["valor"] if g else d.inicial), (g["modo"] if g else d.modo_inicial)
        assert obra_id is not None
        o = (await self._p.de_obra(obra_id)).get(d.clave)
        return (o["valor"] if o else None), None

    async def _modo_global(self, d: DefinicionDeDriver) -> str:
        g = (await self._p.globales()).get(d.clave)
        return g["modo"] if g else d.modo_inicial

    async def _aplicar(self, d: DefinicionDeDriver, p: PropuestaValidada, obra_id: UUID | None, usuario_id: UUID) -> None:
        """Escribe el valor (solo lo ejecuta una propuesta autorizada o de Control de obra: RLS lo exige)."""
        if p.alcance == "global":
            actual = (await self._p.globales()).get(d.clave)
            valor = p.valor if p.valor is not None else (actual["valor"] if actual else d.inicial)
            modo = p.modo if p.modo is not None else (actual["modo"] if actual else d.modo_inicial)
            await self._p.guardar_global(d.clave, valor, modo, usuario_id)
        elif p.accion == "quitar":
            assert obra_id is not None
            await self._p.quitar_de_obra(obra_id, d.clave)
        else:
            assert obra_id is not None and p.valor is not None
            await self._p.guardar_de_obra(obra_id, d.clave, p.valor, usuario_id)

    async def _proponer(
        self, d: DefinicionDeDriver, p: PropuestaValidada, obra_id: UUID | None, *, usuario_id: UUID, rol: str
    ) -> dict[str, Any]:
        """Registra la propuesta: con Control de obra nace autorizada y se aplica; con Costos queda pendiente y no cambia nada."""
        pendientes = await self._p.propuestas_de_driver(estado="pendiente", obra_id=obra_id, clave=d.clave)
        if any(x["alcance"] == p.alcance and x["obra_id"] == obra_id for x in pendientes):
            raise ErrorDeDriver(f"«{d.nombre}» ya tiene un cambio propuesto pendiente: Control de obra lo decide primero.")
        estado = estado_de_alta(rol)
        antes_valor, antes_modo = await self._antes(d, p.alcance, obra_id)
        async with self._uow:
            ident = await self._p.registrar_propuesta_de_driver(
                clave=d.clave, alcance=p.alcance, obra_id=obra_id, accion=p.accion, valor=p.valor, modo=p.modo,
                valor_anterior=antes_valor, modo_anterior=antes_modo, estado=estado, propuso_id=usuario_id, propuso_rol=rol,
                decidio_id=usuario_id if estado == "autorizada" else None, decidio_rol=rol if estado == "autorizada" else None,
            )
            if estado == "autorizada":
                await self._aplicar(d, p, obra_id, usuario_id)
            await self._uow.commit()
        fila = await self._uno(d.clave, obra_id)
        return {**fila, "propuesta": _propuesta(await self._p.obtener_propuesta_de_driver(ident))}

    async def fijar_global(
        self, clave: str, *, valor: object | None, modo: str | None, usuario_id: UUID, rol: str
    ) -> dict[str, Any]:
        """Propone cambiar el valor y/o el modo del driver global (lo no enviado se conserva). Con Control de obra se aplica al instante;
        con Costos queda pendiente de su autorización. Devuelve el driver tal como queda y la propuesta."""
        validar_que_edita(rol)
        validar_que_propone(rol)
        d = _definicion(clave)
        p = armar_propuesta(d, alcance="global", valor=valor, modo=modo)
        return await self._proponer(d, p, None, usuario_id=usuario_id, rol=rol)

    async def fijar_de_obra(self, obra_id: UUID, clave: str, *, valor: object, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Propone el valor propio de una obra para un driver ajustable (Q3, F3)."""
        validar_que_edita(rol)
        validar_que_propone(rol)
        d = _definicion(clave)
        await self._obra(obra_id)
        p = armar_propuesta(d, alcance="obra", valor=valor, modo_global_actual=await self._modo_global(d))  # type: ignore[arg-type]
        return await self._proponer(d, p, obra_id, usuario_id=usuario_id, rol=rol)

    async def quitar_de_obra(self, obra_id: UUID, clave: str, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Propone que la obra vuelva al valor global (se aplica al autorizarse)."""
        validar_que_edita(rol)
        validar_que_propone(rol)
        d = _definicion(clave)
        await self._obra(obra_id)
        p = armar_propuesta(d, alcance="obra", accion="quitar")
        return await self._proponer(d, p, obra_id, usuario_id=usuario_id, rol=rol)

    async def propuestas(
        self, *, estado: str | None = None, obra_id: UUID | None = None, clave: str | None = None
    ) -> list[dict[str, Any]]:
        """Las propuestas con quién propuso, quién decidió y cuándo (la bitácora de los drivers)."""
        if obra_id is not None:
            await self._obra(obra_id)
        if clave is not None:
            _definicion(clave)
        return [_propuesta(p) or p for p in await self._p.propuestas_de_driver(estado=estado, obra_id=obra_id, clave=clave)]

    async def _pendiente(self, propuesta_id: UUID) -> dict[str, Any]:
        p = await self._p.obtener_propuesta_de_driver(propuesta_id)
        if p is None:
            raise PropuestaDeDriverNoEncontrada(f"La propuesta {propuesta_id} no existe o está fuera de tu alcance.")
        if p["estado"] != "pendiente":
            raise ErrorDeDriver("Esta propuesta ya fue decidida.")
        return p  # type: ignore[no-any-return]

    async def autorizar(self, propuesta_id: UUID, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Solo Control de obra: aplica el cambio propuesto (revisado otra vez contra lo que vale hoy) y deja quién y cuándo."""
        validar_que_autoriza(rol)
        prop = await self._pendiente(propuesta_id)
        d = _definicion(prop["clave"])
        obra_id = prop["obra_id"]
        p = armar_propuesta(
            d, alcance=prop["alcance"], accion=prop["accion"], valor=prop["valor"], modo=prop["modo"],
            modo_global_actual=await self._modo_global(d),  # type: ignore[arg-type]
        )
        async with self._uow:
            await self._aplicar(d, p, obra_id, usuario_id)
            await self._p.decidir_propuesta_de_driver(propuesta_id, estado="autorizada", decidio_id=usuario_id, decidio_rol=rol, motivo=None)
            await self._uow.commit()
        return {**await self._uno(d.clave, obra_id), "propuesta": _propuesta(await self._p.obtener_propuesta_de_driver(propuesta_id))}

    async def rechazar(self, propuesta_id: UUID, *, usuario_id: UUID, rol: str, motivo: str | None) -> dict[str, Any]:
        validar_que_autoriza(rol)
        prop = await self._pendiente(propuesta_id)
        limpio = " ".join((motivo or "").split())[:300] or None
        async with self._uow:
            await self._p.decidir_propuesta_de_driver(propuesta_id, estado="rechazada", decidio_id=usuario_id, decidio_rol=rol, motivo=limpio)
            await self._uow.commit()
        return {**await self._uno(prop["clave"], prop["obra_id"]), "propuesta": _propuesta(await self._p.obtener_propuesta_de_driver(propuesta_id))}


def _a_enlace(f: dict[str, Any]) -> EnlaceDeRanura:
    return EnlaceDeRanura(
        id=f["id"], ranura=f["ranura"], capa=Capa(f["nivel_id"], f["etapa_id"], f["ubicacion"], f.get("espacio_id")),
        concepto_id=f["concepto_id"], concepto_clave=f["concepto_clave"],
    )


def _a_partida(f: dict[str, Any]) -> Partida:
    return Partida(
        id=f["id"], concepto_id=f["concepto_id"], nivel_id=f["nivel_id"], etapa_id=f["etapa_id"], nombre=f["nombre"], orden=f["orden"],
        espacio_id=f.get("espacio_id"),
    )


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
        filas_de_partidas = await self._p.partidas(obra_id)
        partidas = [_a_partida(f) for f in filas_de_partidas]
        en_el_arbol = {f["concepto_clave"]: f["concepto_descripcion"] for f in filas_de_partidas}
        capas = await self._p.capas(obra_id)
        salida = []
        for f, e in zip(filas, enlaces, strict=True):
            r = resolver_ranura([e], partidas, e.ranura, Contexto(e.capa.nivel_id, e.capa.etapa_id, e.capa.ubicacion, e.capa.espacio_id))
            salida.append({**f, "capa": e.capa, **{k: v for k, v in _resumen(r).items() if k != "enlace_id"}})
        return {
            "enlaces": salida,
            "ranuras_de_plantilla": [self._plantilla(r) for r in ranuras_de_plantilla()],
            "niveles": capas["niveles"],
            "etapas": capas["etapas"],
            "espacios": capas.get("espacios", []),
            "partidas_del_arbol": len(partidas),
            "conceptos_del_arbol": [{"clave": k, "descripcion": en_el_arbol[k]} for k in sorted(en_el_arbol)],
        }

    @staticmethod
    def _plantilla(r: RanuraConocida) -> dict[str, Any]:
        return {"ranura": r.ranura, "nombre": r.nombre, "grupo": r.grupo, "sugerido_clave": r.sugerido_clave}

    async def resolver(
        self, obra_id: UUID, ranura: str, *, nivel_id: UUID | None, etapa_id: UUID | None, ubicacion: str | None,
        espacio_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Lo que cuenta una ranura donde se mide (espacio, nivel, etapa y ubicación): el concepto, su partida o el aviso."""
        await self._obra(obra_id)
        ranura = validar_ranura(ranura)
        enlaces = [_a_enlace(f) for f in await self._p.enlaces(obra_id)]
        partidas = [_a_partida(f) for f in await self._p.partidas(obra_id)]
        r = resolver_ranura(enlaces, partidas, ranura, Contexto(nivel_id, etapa_id, validar_ubicacion(ubicacion), espacio_id))
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
        espacio_id: UUID | None = None,
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
        if espacio_id is not None and not await self._p.espacio_existe(obra_id, espacio_id):
            raise ErrorDeEnlaceDeRanura("El espacio no existe en esta obra.")
        async with self._uow:
            ident, creado = await self._p.guardar_enlace(
                obra_id=obra_id, ranura=ranura, nivel_id=nivel_id, etapa_id=etapa_id, ubicacion=ubicacion,
                concepto_id=concepto["id"], usuario_id=usuario_id, espacio_id=espacio_id,
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


class GestionarNumeroDeNivel:
    """F5 (2026-11-19): el nivel del contexto es un campo EXPLÍCITO (`nivel.numero_de_nivel`, PB = 1), no `nivel.orden`, cuando hay saltos de nivel
    (un entrepiso de 3.00 y otro de 4.20 en la misma planta, un sótano). Con él se eligen los conceptos de un elemento; sin él, `orden` solo
    mientras los niveles sean consecutivos; con saltos y sin número, no se descarta ningún concepto."""

    def __init__(self, *, parametrico: Any, uow: UnidadDeTrabajo) -> None:
        self._p = parametrico
        self._uow = uow

    async def fijar(self, nivel_id: UUID, numero: int | None) -> dict[str, Any]:
        if numero is not None and not 1 <= numero <= 99:
            raise ErrorDeEnlaceDeRanura("El número de nivel va de 1 (PB) a 99.")
        async with self._uow:
            fila = await self._p.fijar_numero_de_nivel(nivel_id, numero)
            if fila is None:
                raise NivelNoEncontrado(f"El nivel {nivel_id} no existe o está fuera de tu alcance.")
            await self._uow.commit()
        return fila
