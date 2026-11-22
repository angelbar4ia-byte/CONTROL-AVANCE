"""Las escaleras de una zona de losa (Fase 4a): las escaleras de la zona, su cálculo con las cotas de las zonas y el plano, y la propuesta de su concepto nuevo.

Junta lo que ya existe sin duplicarlo: las **zonas** de losa con sus cotas (fase 1, `zonas_de_losa`), el **catálogo vigente** (para la conciliación contra EST-01510,
sin editarlo), las **propuestas** de concepto nuevo (versionado y autorización de Control de obra) y la capa **«espacio»** (0143). El cálculo vive en el dominio
(`escalera`); aquí solo se arma su entrada desde la base.

Las cotas salen de las zonas: la escalera arranca en el piso de su zona (`cota_piso_m`) y llega al piso de otra zona (`zona_llegada_id`) o, si no se dice, a la cara
alta de la losa de su propia zona (piso + altura libre + espesor). Se pueden teclear las dos (mandan sobre las de las zonas). Si una zona cambia de cota, la escalera
se recalcula sola: no guarda el desnivel.

Medición derivada: una escalera puede tomar el recorrido horizontal de **una línea del plano** (`trazo_id`); su longitud sale de la geometría y de la escala del plano
**al calcular**, no se guarda. Sin escala calibrada se toma 1 unidad de plano = 1 m y el cálculo lo dice. Solo Control de obra escribe escaleras (lo exige la API y también
RLS); Costos o Control de obra proponen el concepto.

Descansos propios y escalones de abanico (Fase 4d, migración 0148): se reemplazan por lista (`cambiar_descansos`, `cambiar_abanicos`), se prueban contra el cálculo antes de
guardarse y entran al mismo cálculo y a las mismas tomas. Un polígono del plano da el área de UN descanso (la base lo impide) y no puede ser además una losa de la zona.

Sin doble conteo: una línea del plano no sirve a dos escaleras (la base lo impide y `solapes_de_escaleras` también lo dice antes de escribir); la escalera y la losa se
pagan con conceptos distintos y el hueco de la escalera ya se resta del área de la losa; cada escalera cae en **un** espacio.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import TrazoNoEncontrado
from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.casos_uso.matriz_de_losa import (
    CONSERVAR_ESPACIO,
    _largo_de_linea_m,
)
from obractrl.application.casos_uso.propuestas_de_losa import (
    GestionarPropuestasDeLosa,
)
from obractrl.application.casos_uso.zonas_de_losa import (
    ZonaDeLosaNoEncontrada,
    _poligonos,
)
from obractrl.application.puertos.escalera_de_zona import RepositorioEscalerasDeZona
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.application.puertos.zonas_de_losa import RepositorioZonasDeLosa
from obractrl.domain.cuantificacion.comparacion_con_catalogo import (
    comparar_con_concepto,
    expandir_composicion,
)
from obractrl.domain.cuantificacion.enlaces_de_ranura import Partida
from obractrl.domain.cuantificacion.escalera import (
    CONCEPTO_DE_ESCALON,
    AbanicoDeEscalera,
    DescansoDeEscalera,
    EntradaEscalera,
    ErrorDeEscalera,
    calcular_escalera,
    concepto_nuevo_de_descanso,
    elemento_de_escalera,
    solapes_de_escaleras,
    validar_abanico,
    validar_descanso,
    validar_parametros,
)
from obractrl.domain.cuantificacion.espacios import resolver_matriz_por_espacio
from obractrl.domain.cuantificacion.matriz_de_losa import area_de_poligonos

__all__ = ["EscaleraNoEncontrada", "GestionarEscaleras", "GestionarPropuestasDeEscalera"]

_CAMPOS = ("peldanos", "contrahuella_max_m", "huella_m", "ancho_m", "espesor_m", "rampas", "largo_descanso_m")
_COTAS = ("cota_arranque_m", "cota_llegada_m")


class EscaleraNoEncontrada(ElementoParametricoNoEncontrado):
    """La escalera no existe o salió del alcance (RLS): indistinguibles a propósito (§12.4)."""


def _numero(valor: Any) -> Any:
    return float(valor) if isinstance(valor, Decimal) else valor


_DESCANSO = ("posicion", "giro_grados", "largo_m", "ancho_m", "espesor_m")
_ABANICO = ("posicion", "escalones", "ancho_interior_m", "ancho_exterior_m", "radio_huella_m")


def _descanso_visible(f: dict[str, Any]) -> dict[str, Any]:
    return {"id": f["id"], "trazo_id": f.get("trazo_id"), **{c: _numero(f[c]) for c in _DESCANSO}}


def _abanico_visible(f: dict[str, Any]) -> dict[str, Any]:
    return {"id": f["id"], **{c: _numero(f[c]) for c in _ABANICO}}


class GestionarPropuestasDeEscalera(GestionarPropuestasDeLosa):
    """Las propuestas del concepto nuevo del descanso (EJ-820): el mismo ciclo y la misma tabla que la losa (`propuesta_de_estructura`, 0131)."""

    async def listar(self, elemento_clave: str) -> list[dict[str, Any]]:
        if not elemento_de_escalera(elemento_clave):
            raise ElementoParametricoNoEncontrado(f"No hay un elemento de escalera «{elemento_clave}» en la biblioteca.")
        return list(await self._propuestas.del_elemento(elemento_clave))

    async def proponer_concepto_de_escalera(self, elemento_clave: str, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """El concepto nuevo del descanso por m² (regla F7), con clave provisional, sin destajo ni precio. La escalera usa EST-01510 del catálogo."""
        if not elemento_de_escalera(elemento_clave):
            raise ElementoParametricoNoEncontrado(f"No hay un elemento de escalera «{elemento_clave}» en la biblioteca.")
        return await self.proponer([concepto_nuevo_de_descanso()], usuario_id=usuario_id, rol=rol)


class GestionarEscaleras:
    def __init__(
        self,
        *,
        zonas: RepositorioZonasDeLosa,
        escaleras: RepositorioEscalerasDeZona,
        propuestas: GestionarPropuestasDeEscalera,
        conceptos: Any,
        insumos: Any,
        uow: UnidadDeTrabajo,
        parametrico: Any | None = None,
        sincronizador: Any | None = None,
    ) -> None:
        # Con el sincronizador de tomas, una escalera que se agrega, cambia o quita rehace lo que la escalera paga en las partidas (0143).
        self._sincronizador = sincronizador
        # Con el repositorio del Paramétrico (0143), el cálculo dice en qué partida del árbol se mide lo de cada espacio.
        self._parametrico = parametrico
        self._zonas = zonas
        self._escaleras = escaleras
        self._propuestas = propuestas
        self._conceptos = conceptos
        self._insumos = insumos
        self._uow = uow

    # ── Contexto ────────────────────────────────────────────────────────────────────────────────────────

    async def _zona(self, zona_id: UUID) -> dict[str, Any]:
        z = await self._zonas.zona(zona_id)
        if z is None:
            raise ZonaDeLosaNoEncontrada(f"La zona de losa {zona_id} no existe o no está en tu alcance.")
        return z

    async def _escala(self, plano_id: UUID) -> tuple[float, bool, UUID]:
        plano = await self._zonas.plano(plano_id)
        if plano is None:
            raise ZonaDeLosaNoEncontrada(f"El plano {plano_id} no existe o no está en tu alcance.")
        definida = plano["escala_m_por_unidad"] is not None
        return (float(plano["escala_m_por_unidad"]) if definida else 1.0), definida, plano["obra_id"]

    async def _resincronizar(self, plano_id: UUID) -> None:
        """Lo que la escalera paga en las partidas se rehace (en la misma transacción)."""
        if self._sincronizador is None:
            return
        _, _, obra_id = await self._escala(plano_id)
        await self._sincronizador.de_la_obra(obra_id)

    @staticmethod
    def _fila(f: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f["id"], "zona_id": f["zona_id"], "elemento_clave": f["elemento_clave"], "zona_llegada_id": f.get("zona_llegada_id"),
            "trazo_id": f["trazo_id"], "espacio_id": f.get("espacio_id"),
            **{c: _numero(f[c]) for c in (*_CAMPOS, *_COTAS)},
        }

    # ── Las escaleras de la zona ────────────────────────────────────────────────────────────────────────

    async def escaleras(self, zona_id: UUID) -> list[dict[str, Any]]:
        await self._zona(zona_id)
        descansos = await self._escaleras.descansos_de_la_zona(zona_id)
        abanicos = await self._escaleras.abanicos_de_la_zona(zona_id)
        return [self._con_hijas(f, descansos, abanicos) for f in await self._escaleras.de_la_zona(zona_id)]

    def _con_hijas(self, f: dict[str, Any], descansos: dict[UUID, list[dict[str, Any]]], abanicos: dict[UUID, list[dict[str, Any]]]) -> dict[str, Any]:
        clave = UUID(str(f["id"]))
        return {
            **self._fila(f), "descansos": [_descanso_visible(d) for d in descansos.get(clave, [])], "abanicos": [_abanico_visible(a) for a in abanicos.get(clave, [])],
        }

    async def _datos(
        self, zona: dict[str, Any], *, elemento_clave: str, zona_llegada_id: UUID | None, cota_arranque_m: float | None, cota_llegada_m: float | None,
        trazo_id: UUID | None, espacio_id: UUID | None, parametros: dict[str, Any], propia: UUID | None = None,
    ) -> dict[str, Any]:
        if not elemento_de_escalera(elemento_clave):
            raise ErrorDeEscalera(f"«{elemento_clave}» no es un elemento de escalera de la biblioteca (ESC-FORJADA).")
        validados = validar_parametros(parametros)
        _, _, obra_id = await self._escala(zona["plano_id"])
        if zona_llegada_id is not None and cota_llegada_m is not None:
            raise ErrorDeEscalera("La llegada es la zona de llegada o una cota tecleada, no las dos.")
        if zona_llegada_id is not None:
            if zona_llegada_id == zona["id"]:
                raise ErrorDeEscalera("La zona de llegada es la misma de arranque: elige otra zona o deja que llegue a la cara alta de su losa.")
            llegada = await self._zonas.zona(zona_llegada_id)
            if llegada is None or llegada["plano_id"] != zona["plano_id"]:
                raise ErrorDeEscalera("La zona de llegada no existe o es de otro plano.")
        for que, cota in (("arranque", cota_arranque_m), ("llegada", cota_llegada_m)):
            if cota is not None and not -30.0 <= cota <= 100.0:
                raise ErrorDeEscalera(f"La cota de {que} va de -30 a 100 m.")
        if espacio_id is not None and not await self._escaleras.espacio_existe(obra_id, espacio_id):
            raise ErrorDeEscalera("El espacio no existe en esta obra.")
        if trazo_id is not None:
            trazo = await self._zonas.trazo(trazo_id)
            if trazo is None:
                raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
            if trazo["tipo"] != "LINESTRING" or trazo["hueco_de"] is not None:
                raise ErrorDeEscalera("Solo una línea del plano (no un hueco, un polígono ni un punto) puede dar el recorrido de la escalera.")
            if trazo["plano_id"] != zona["plano_id"]:
                raise ErrorDeEscalera("La línea es de otro plano que la zona.")
            escala, _, _ = await self._escala(zona["plano_id"])
            if _largo_de_linea_m(trazo["geojson"], escala) < 0.001:
                raise ErrorDeEscalera("La línea no tiene largo.")
            ya = await self._escaleras.con_la_linea(trazo_id)
            if ya is not None and ya != propia:
                raise ErrorDeEscalera("Esa línea ya da el recorrido de otra escalera: se contaría dos veces.")
        return {
            "elemento_clave": elemento_clave, "zona_llegada_id": zona_llegada_id, "cota_arranque_m": cota_arranque_m, "cota_llegada_m": cota_llegada_m,
            "trazo_id": trazo_id, "espacio_id": espacio_id, **validados,
        }

    async def agregar(
        self, zona_id: UUID, *, elemento_clave: str, zona_llegada_id: UUID | None, cota_arranque_m: float | None, cota_llegada_m: float | None,
        trazo_id: UUID | None, espacio_id: UUID | None, parametros: dict[str, Any], autor_id: UUID,
    ) -> dict[str, Any]:
        zona = await self._zona(zona_id)
        datos = await self._datos(
            zona, elemento_clave=elemento_clave, zona_llegada_id=zona_llegada_id, cota_arranque_m=cota_arranque_m, cota_llegada_m=cota_llegada_m,
            trazo_id=trazo_id, espacio_id=espacio_id, parametros=parametros,
        )
        async with self._uow:
            nueva = await self._escaleras.agregar(zona_id=zona_id, datos=datos, autor_id=autor_id)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()
        return await self._escalera(nueva)

    async def _escalera(self, escalera_id: UUID) -> dict[str, Any]:
        f = await self._escaleras.uno(escalera_id)
        if f is None:
            raise EscaleraNoEncontrada(f"La escalera {escalera_id} no existe o no está en tu alcance.")
        return self._con_hijas(f, await self._escaleras.descansos_de_la_zona(f["zona_id"]), await self._escaleras.abanicos_de_la_zona(f["zona_id"]))

    async def cambiar(
        self, escalera_id: UUID, *, elemento_clave: str, zona_llegada_id: UUID | None, cota_arranque_m: float | None, cota_llegada_m: float | None,
        trazo_id: UUID | None, parametros: dict[str, Any], espacio_id: Any = CONSERVAR_ESPACIO,
    ) -> dict[str, Any]:
        f = await self._escaleras.uno(escalera_id)
        if f is None:
            raise EscaleraNoEncontrada(f"La escalera {escalera_id} no existe o no está en tu alcance.")
        if espacio_id is CONSERVAR_ESPACIO:
            espacio_id = f.get("espacio_id")
        zona = await self._zona(f["zona_id"])
        datos = await self._datos(
            zona, elemento_clave=elemento_clave, zona_llegada_id=zona_llegada_id, cota_arranque_m=cota_arranque_m, cota_llegada_m=cota_llegada_m,
            trazo_id=trazo_id, espacio_id=espacio_id, parametros=parametros, propia=escalera_id,
        )
        # Bajar las rampas deja sin lugar a los descansos y abanicos de las posiciones que ya no existen: se rechaza con el motivo, en vez de dejar la escalera sin cálculo.
        nuevas = int(datos["rampas"])
        sobran = [d["posicion"] for d in (await self._escaleras.descansos_de_la_zona(f["zona_id"])).get(UUID(str(f["id"])), []) if d["posicion"] > nuevas - 1]
        sobran += [a["posicion"] for a in (await self._escaleras.abanicos_de_la_zona(f["zona_id"])).get(UUID(str(f["id"])), []) if a["posicion"] > nuevas]
        if sobran:
            raise ErrorDeEscalera(
                f"Con {nuevas} {'rampa' if nuevas == 1 else 'rampas'} quedarían descansos o abanicos en las posiciones {sorted(set(sobran))}, que ya no existen: quítalos o muévelos antes."
            )
        async with self._uow:
            await self._escaleras.actualizar(escalera_id, datos)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()
        return await self._escalera(escalera_id)

    async def quitar(self, escalera_id: UUID) -> None:
        f = await self._escaleras.uno(escalera_id)
        if f is None:
            raise EscaleraNoEncontrada(f"La escalera {escalera_id} no existe o no está en tu alcance.")
        zona = await self._zona(f["zona_id"])
        async with self._uow:
            await self._escaleras.eliminar(escalera_id)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()

    # ── Descansos propios y escalones de abanico (0148) ─────────────────────────────────────────────────

    def _entrada_de(
        self, f: dict[str, Any], arranque: float, llegada: float, descansos: list[dict[str, Any]], abanicos: list[dict[str, Any]],
        recorrido: float | None = None, areas: dict[str, float] | None = None,
    ) -> EntradaEscalera:
        areas = areas or {}
        return EntradaEscalera(
            cota_arranque_m=arranque, cota_llegada_m=llegada, recorrido_m=recorrido, espacio_id=str(f["espacio_id"]) if f.get("espacio_id") else None,
            descansos=tuple(
                DescansoDeEscalera(
                    id=str(d["id"]) if d.get("id") else None, area_m2=areas.get(str(d["trazo_id"])) if d.get("trazo_id") else None,
                    **{c: _numero(d.get(c)) for c in _DESCANSO},
                )
                for d in descansos
            ),
            abanicos=tuple(AbanicoDeEscalera(id=str(a["id"]) if a.get("id") else None, **{c: _numero(a[c]) for c in _ABANICO}) for a in abanicos),
            **{c: _numero(f[c]) for c in _CAMPOS},
        )

    async def _probar(
        self, zona: dict[str, Any], f: dict[str, Any], descansos: list[dict[str, Any]], abanicos: list[dict[str, Any]], escala: float,
    ) -> None:
        """Si la escalera calcula sin las listas nuevas pero no con ellas, el cambio no vale: se rechaza con el motivo del cálculo."""
        arranque, llegada, _ = await self._cotas(zona, f)
        recorrido = _largo_de_linea_m(f["geojson"], escala) if f.get("geojson") else None
        try:
            calcular_escalera(self._entrada_de(f, arranque, llegada, [], [], recorrido))
        except ErrorDeEscalera:
            return  # la escalera ya no calculaba por otra causa (cotas, huella): no se puede probar el cambio
        areas = await self._areas_de_poligonos(descansos, escala)
        calcular_escalera(self._entrada_de(f, arranque, llegada, descansos, abanicos, recorrido, areas))

    async def _areas_de_poligonos(self, descansos: list[dict[str, Any]], escala: float) -> dict[str, float]:
        areas: dict[str, float] = {}
        for d in descansos:
            if d.get("trazo_id"):
                trazo = await self._zonas.trazo(UUID(str(d["trazo_id"])))
                if trazo is not None:
                    areas[str(d["trazo_id"])] = area_de_poligonos(_poligonos(trazo["geojson"], escala))
        return areas

    async def cambiar_descansos(self, escalera_id: UUID, descansos: list[dict[str, Any]], autor_id: UUID) -> dict[str, Any]:
        """Deja como únicos descansos propios de la escalera los que vienen (vacío = quita todos y vuelve al descanso implícito). Cada uno se valida; las posiciones no
        se repiten; un polígono del plano da el área de UN descanso y no puede ser además una losa."""
        f = await self._escaleras.uno(escalera_id)
        if f is None:
            raise EscaleraNoEncontrada(f"La escalera {escalera_id} no existe o no está en tu alcance.")
        zona = await self._zona(f["zona_id"])
        escala, _, _ = await self._escala(zona["plano_id"])
        validados: list[dict[str, Any]] = []
        for d in descansos:
            v = validar_descanso(d)
            trazo_id = d.get("trazo_id")
            if v["posicion"] > int(f["rampas"]) - 1:
                raise ErrorDeEscalera(
                    f"El descanso de la posición {v['posicion']} va entre la rampa {v['posicion']} y la siguiente, pero la escalera tiene {f['rampas']} "
                    f"{'rampa' if int(f['rampas']) == 1 else 'rampas'}: sube las rampas o cambia la posición."
                )
            if any(x["posicion"] == v["posicion"] for x in validados):
                raise ErrorDeEscalera(f"Hay dos descansos en la posición {v['posicion']}: se contaría dos veces.")
            if trazo_id is not None:
                await self._validar_poligono(zona, UUID(str(trazo_id)), escalera_id, [x["trazo_id"] for x in validados], escala)
            validados.append({**v, "trazo_id": UUID(str(trazo_id)) if trazo_id is not None else None})
        await self._probar(zona, f, validados, [_abanico_visible(a) for a in (await self._escaleras.abanicos_de_la_zona(f["zona_id"])).get(UUID(str(f["id"])), [])], escala)
        async with self._uow:
            await self._escaleras.reemplazar_descansos(escalera_id, validados, autor_id)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()
        return await self._escalera(escalera_id)

    async def _validar_poligono(self, zona: dict[str, Any], trazo_id: UUID, escalera_id: UUID, ya: list[Any], escala: float) -> None:
        trazo = await self._zonas.trazo(trazo_id)
        if trazo is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if trazo["tipo"] not in ("POLYGON", "MULTIPOLYGON") or trazo["hueco_de"] is not None:
            raise ErrorDeEscalera("Solo un polígono del plano (no un hueco, una línea ni un punto) puede dar el área del descanso.")
        if trazo["plano_id"] != zona["plano_id"]:
            raise ErrorDeEscalera("El polígono es de otro plano que la zona.")
        if await self._escaleras.trazo_es_de_losa(trazo_id):
            raise ErrorDeEscalera("Ese polígono ya es una losa de una zona: contaría su área en la losa y en el descanso.")
        if trazo_id in [UUID(str(x)) for x in ya if x is not None]:
            raise ErrorDeEscalera("Ese polígono ya da el área de otro descanso de esta escalera: se contaría dos veces.")
        otra = await self._escaleras.descanso_con_el_poligono(trazo_id)
        if otra is not None and otra != escalera_id:
            raise ErrorDeEscalera("Ese polígono ya da el área del descanso de otra escalera: se contaría dos veces.")
        if area_de_poligonos(_poligonos(trazo["geojson"], escala)) < 0.001:
            raise ErrorDeEscalera("El polígono no tiene área.")

    async def cambiar_abanicos(self, escalera_id: UUID, abanicos: list[dict[str, Any]], autor_id: UUID) -> dict[str, Any]:
        """Deja como únicos grupos de abanico de la escalera los que vienen (vacío = quita todos). Los escalones de abanico forman parte de los peldaños del desnivel:
        si no caben, el cambio se rechaza con el motivo del cálculo."""
        f = await self._escaleras.uno(escalera_id)
        if f is None:
            raise EscaleraNoEncontrada(f"La escalera {escalera_id} no existe o no está en tu alcance.")
        zona = await self._zona(f["zona_id"])
        escala, _, _ = await self._escala(zona["plano_id"])
        validados = [validar_abanico(a) for a in abanicos]
        if len({a["posicion"] for a in validados}) != len(validados):
            raise ErrorDeEscalera("Hay dos grupos de abanico en la misma posición: junta sus escalones en uno.")
        descansos = [_descanso_visible(d) for d in (await self._escaleras.descansos_de_la_zona(f["zona_id"])).get(UUID(str(f["id"])), [])]
        await self._probar(zona, f, descansos, validados, escala)
        async with self._uow:
            await self._escaleras.reemplazar_abanicos(escalera_id, validados, autor_id)
            await self._resincronizar(zona["plano_id"])
            await self._uow.commit()
        return await self._escalera(escalera_id)

    # ── El cálculo ──────────────────────────────────────────────────────────────────────────────────────

    async def _cotas(self, zona: dict[str, Any], f: dict[str, Any]) -> tuple[float, float, dict[str, str]]:
        """Las cotas con que se calcula: las tecleadas mandan; si no, las de las zonas (arranque = piso de la zona; llegada = piso de la zona de llegada o cara alta
        de la losa de la zona de arranque)."""
        if f.get("cota_arranque_m") is not None:
            arranque, origen_a = float(f["cota_arranque_m"]), "explicita"
        else:
            arranque, origen_a = float(zona["cota_piso_m"]), "zona"
        if f.get("cota_llegada_m") is not None:
            llegada, origen_l = float(f["cota_llegada_m"]), "explicita"
        elif f.get("zona_llegada_id") is not None and (destino := await self._zonas.zona(f["zona_llegada_id"])) is not None:
            llegada, origen_l = float(destino["cota_piso_m"]), "zona_de_llegada"
        else:
            llegada, origen_l = float(zona["cota_piso_m"]) + float(zona["altura_libre_m"]) + float(zona["espesor_m"]), "losa_de_la_zona"
        return arranque, llegada, {"arranque": origen_a, "llegada": origen_l}

    async def calculo(self, zona_id: UUID, *, conciliar: bool = False) -> dict[str, Any]:
        """Las escaleras de la zona calculadas con las cotas de las zonas y lo que hay en el plano, el estado de su concepto propuesto, lo que paga cada espacio y, si se
        pide, la conciliación contra EST-01510 del catálogo vigente. Una escalera con un dato que no vale se devuelve con su `error` y sin cálculo."""
        zona = await self._zona(zona_id)
        plano_id = zona["plano_id"]
        escala, escala_definida, obra_id = await self._escala(plano_id)

        filas = await self._escaleras.de_la_zona(zona_id)
        descansos_por = await self._escaleras.descansos_de_la_zona(zona_id)
        abanicos_por = await self._escaleras.abanicos_de_la_zona(zona_id)
        calculadas: list[dict[str, Any]] = []
        for f in filas:
            arranque, llegada, origen = await self._cotas(zona, f)
            suyos = descansos_por.get(UUID(str(f["id"])), [])
            item: dict[str, Any] = {
                "id": f["id"], "trazo_id": f["trazo_id"], "espacio_id": f.get("espacio_id"), "zona_llegada_id": f.get("zona_llegada_id"),
                "origen_de_cotas": origen, "descansos": [_descanso_visible(d) for d in suyos],
                "abanicos": [_abanico_visible(a) for a in abanicos_por.get(UUID(str(f["id"])), [])], "error": None, "calculo": None, "conciliacion": None,
            }
            recorrido = _largo_de_linea_m(f["geojson"], escala) if f.get("geojson") else None
            areas = {
                str(d["trazo_id"]): area_de_poligonos(_poligonos(d["geojson"], escala)) for d in suyos if d.get("trazo_id") and d.get("geojson")
            }
            try:
                r = calcular_escalera(self._entrada_de(f, arranque, llegada, item["descansos"], item["abanicos"], recorrido, areas))
            except ErrorDeEscalera as e:
                item["error"] = str(e)
                calculadas.append(item)
                continue
            if f["trazo_id"] and not f.get("geojson"):
                r["advertencias"].insert(0, "La línea del plano que daba el recorrido ya no existe: la huella vuelve a la tecleada.")
            if not escala_definida and (recorrido is not None or areas):
                r["advertencias"].insert(0, "El plano no tiene escala calibrada: se toma 1 unidad de plano = 1 m para el recorrido y las áreas.")
            for c in r["conceptos"]:
                c["propuesta"] = await self._propuestas.estado_de(c["concepto"]["clave"]) if c["concepto"]["provisional"] else None
            item["calculo"] = r
            if conciliar:
                item["conciliacion"] = await self._conciliar(r)
            calculadas.append(item)

        validas = [c["calculo"] for c in calculadas if c["calculo"] is not None]
        por_espacio = await self._por_espacio(obra_id, _juntar_por_espacio(validas))
        return {
            "zona": {
                "id": zona["id"], "plano_id": plano_id, "nombre": zona["nombre"], "nivel": zona["nivel"], "cota_piso_m": float(zona["cota_piso_m"]),
                "cota_de_la_losa_m": float(zona["cota_piso_m"]) + float(zona["altura_libre_m"]) + float(zona["espesor_m"]),
            },
            "escala_definida": escala_definida,
            "escaleras": calculadas,
            "totales": _totales(validas),
            "por_espacio": por_espacio,
            "advertencias": _advertencias_de_la_zona(filas, calculadas),
        }

    async def _por_espacio(self, obra_id: UUID, grupos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anota, por espacio, en qué partida del árbol se mide cada concepto de la escalera (o por qué no cuenta). Sin el Paramétrico no hay árbol que consultar y
        los conceptos quedan sin resolución."""
        nombres: dict[UUID, str] = {}
        partidas: list[Partida] = []
        concepto_id_de: dict[str, UUID] = {}
        if self._parametrico is not None:
            nombres = {UUID(str(e["id"])): e["nombre"] for e in (await self._parametrico.capas(obra_id)).get("espacios", [])}
            partidas = [
                Partida(
                    id=f["id"], concepto_id=f["concepto_id"], nivel_id=f["nivel_id"], etapa_id=f["etapa_id"], nombre=f["nombre"],
                    orden=f["orden"], espacio_id=f.get("espacio_id"),
                )
                for f in await self._parametrico.partidas(obra_id)
            ]
            for clave in sorted({c["concepto"]["clave"] for g in grupos for c in g["conceptos"]}):
                concepto = await self._parametrico.concepto_por_clave(clave)
                if concepto is not None:
                    concepto_id_de[clave] = UUID(str(concepto["id"]))
        return resolver_matriz_por_espacio(grupos, partidas=partidas, concepto_id_de=concepto_id_de, nombres=nombres)

    async def _conciliar(self, r: dict[str, Any]) -> dict[str, Any]:
        """La escalera contra la composición real de EST-01510 del catálogo vigente, **por escalón de 1.20 m** (auxiliares expandidos hasta los insumos). Se compara lo
        que el elemento calcula por escalón (concreto y acero de la rampa) con lo que el concepto lleva por pieza. No se edita nada."""
        clave = CONCEPTO_DE_ESCALON["clave"]
        concepto = await self._conceptos.obtener_por_clave(clave)
        if concepto is None:
            return {
                "concepto": {"clave": clave, "descripcion": CONCEPTO_DE_ESCALON["descripcion"], "unidad": "pza"},
                "nota": f"El concepto {clave} no está en el catálogo vigente: no hay con qué conciliar.", "filas": [], "mano_de_obra": [],
                "resumen": {}, "coincide": False,
            }
        composicion = expandir_composicion(await self._conceptos.composicion_recursiva(concepto["id"]), clave)
        escalones = float(r["geometria"]["escalones_de_catalogo"])
        de_la_rampa = _insumos_de_peldanos(r["insumos"])
        conocidos = await self._insumos.por_claves(sorted({f.clave.upper() for f in composicion} | {i["clave"].upper() for i in de_la_rampa}))
        composicion = [
            replace(
                f, clave=f.clave.upper(),
                descripcion=conocidos[f.clave.upper()][1].descripcion if f.clave.upper() in conocidos else f.descripcion,
                unidad=(conocidos[f.clave.upper()][1].unidad or "") if f.clave.upper() in conocidos else f.unidad,
            )
            for f in composicion
        ]
        por_escalon: dict[str, float] = {}
        if escalones > 0:
            for i in de_la_rampa:  # la rampa y el abanico llevan el mismo concreto y el mismo acero: se suman
                por_escalon[i["clave"].upper()] = por_escalon.get(i["clave"].upper(), 0.0) + float(i["cantidad"]) / escalones
        comparado = comparar_con_concepto(por_escalon, composicion, descripciones={k: v[1].descripcion for k, v in conocidos.items()})
        return {
            "concepto": {"clave": clave, "descripcion": str(concepto.get("descripcion") or ""), "unidad": str(concepto.get("unidad") or "")},
            "nota": (
                "El concepto del catálogo es por pieza (un escalón de 1.20 m): se compara lo que la escalera calcula por escalón con lo que el concepto lleva por pieza. "
                "Tabique, mezcla y cimbraplay no se calculan (aparecen «solo en el catálogo»). Lo que el catálogo trae distinto se muestra, no se corrige."
            ),
            "filas": comparado["filas"],
            "mano_de_obra": comparado["mano_de_obra"],
            "resumen": comparado["resumen"],
            "coincide": comparado["coincide"],
        }

    # ── Propuestas ──────────────────────────────────────────────────────────────────────────────────────

    async def proponer_conceptos(self, zona_id: UUID, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """Propone el concepto nuevo que las escaleras de la zona necesitan (el del descanso, solo si alguna lo lleva). Idempotente: lo que ya está propuesto o
        autorizado se omite. El escalón usa EST-01510 del catálogo y no propone nada."""
        c = await self.calculo(zona_id)
        necesita = any(k["concepto"]["provisional"] for e in c["escaleras"] if e["calculo"] for k in e["calculo"]["conceptos"])
        if not necesita:
            return {"creadas": [], "omitidas": []}
        return await self._propuestas.proponer([concepto_nuevo_de_descanso()], usuario_id=usuario_id, rol=rol)


def _juntar_por_espacio(calculadas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Junta el `por_espacio` de todas las escaleras de la zona: un grupo por espacio y, en él, un renglón por concepto con las cantidades sumadas. Cada escalera cae en
    un solo espacio, así que la suma de los grupos es la de las escaleras (sin doble conteo)."""
    grupos: dict[str | None, dict[str, Any]] = {}
    for r in calculadas:
        for g in r["por_espacio"]:
            suyo = grupos.setdefault(g["espacio_id"], {"espacio_id": g["espacio_id"], "conceptos": {}})
            for c in g["conceptos"]:
                previo = suyo["conceptos"].get(c["concepto"]["clave"])
                if previo is None:
                    suyo["conceptos"][c["concepto"]["clave"]] = {**c, "propuesta": None}
                else:
                    previo["cantidad"] += c["cantidad"]
    orden = sorted(grupos, key=lambda e: (e is not None, str(e)))
    return [{**grupos[e], "conceptos": list(grupos[e]["conceptos"].values())} for e in orden]


def _insumos_de_peldanos(insumos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lo que la composición de EST-01510 lleva por escalón: el concreto y el acero de las rampas y de los escalones de abanico (el descanso se paga aparte, con EJ-820)."""
    return [i for i in insumos if i["parte"] in ("rampa", "abanico")]


def _totales(calculadas: list[dict[str, Any]]) -> dict[str, Any]:
    conceptos: dict[str, dict[str, Any]] = {}
    for r in calculadas:
        for c in r["conceptos"]:
            clave = c["concepto"]["clave"]
            previo = conceptos.get(clave)
            if previo is None:
                conceptos[clave] = {"concepto": c["concepto"], "unidad": c["unidad"], "cantidad": c["cantidad"], "propuesta": c.get("propuesta")}
            else:
                previo["cantidad"] += c["cantidad"]
    return {
        "peldanos": sum(r["geometria"]["peldanos"] for r in calculadas),
        "escalones_de_catalogo": sum(r["geometria"]["escalones_de_catalogo"] for r in calculadas),
        "area_de_descanso_m2": sum(r["geometria"]["area_de_descanso_m2"] for r in calculadas),
        "peldanos_de_abanico": sum(r["geometria"]["peldanos_de_abanico"] for r in calculadas),
        "area_de_abanico_m2": sum(r["geometria"]["area_de_abanico_m2"] for r in calculadas),
        "conceptos": list(conceptos.values()),
    }


def _advertencias_de_la_zona(filas: list[dict[str, Any]], calculadas: list[dict[str, Any]]) -> list[str]:
    avisos = solapes_de_escaleras([{"id": f["id"], "trazo_id": f["trazo_id"]} for f in filas])
    avisos.extend(f"Una escalera no se puede calcular: {c['error']}" for c in calculadas if c["error"])
    return avisos
