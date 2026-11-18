"""Las plantillas de muro, el artefacto: alta, edición con versiones, validación contra la matriz y elección en el trazo (plan de
elementos de muro, Ola 4A; M-1, M-19, Q9).

Costos y Control de obra editan (M-15); solo **Control de obra valida**. Toda plantilla nace «por validar» y cualquier cambio la deja
así; al cambiar una plantilla ya validada nace una versión nueva y los trazos ya medidos conservan la anterior (Q9). La validación
compara los conceptos de cada elemento con su matriz del catálogo (`validar_contra_matriz`); nunca corrige ni inventa precios.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.cuantificar import (
    MedicionNoEncontrada,
    TrazoNoEncontrado,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.cuantificacion.comparacion_con_catalogo import expandir_composicion
from obractrl.domain.cuantificacion.materiales_de_elemento import claves_de_materiales
from obractrl.domain.cuantificacion.muro_plantilla import (
    Alerta,
    ConceptoDelElemento,
    ElementoParaValidar,
    ErrorDePlantillaDeMuro,
    InfoDeElemento,
    cambia_la_plantilla,
    clase_de_elemento,
    normalizar_plantilla,
    puede_validar,
    requiere_version_nueva,
    validar_contra_matriz,
    validar_que_edita,
    validar_que_valida,
)
from obractrl.domain.cuantificacion.muro_tabique import (
    ELEMENTOS_DE_TABIQUE,
    definicion_de,
)
from obractrl.domain.cuantificacion.muro_tipo import acabado_normalizado
from obractrl.domain.cuantificacion.muro_ubicacion import MATERIALES_DE_MURO
from obractrl.domain.cuantificacion.prototipos_de_muro import (
    PROTOTIPOS,
    plantas_de,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = ["GestionarPlantillasDeMuro", "PlantillaEnUso", "PlantillaNoEncontrada"]

_PARTE_DE_MATERIAL = {"concreto": "concreto", "varilla": "acero", "armex": "acero", "anillo": "estribos", "alambre": "alambre", "cimbra": "cimbra"}
_PARTES_BASE = ("concreto", "acero", "cimbra")


class PlantillaNoEncontrada(MedicionNoEncontrada):
    """La plantilla no existe o está fuera de tu alcance."""


class PlantillaEnUso(ErrorDePlantillaDeMuro):
    """Algún trazo usa una versión de la plantilla: no se borra."""


def _es_de_muro_de_tabique(clave: str) -> bool:
    e = ELEMENTOS_DE_TABIQUE.get(clave.strip().upper())
    return e is not None and e.categoria[0] == "muros"


class GestionarPlantillasDeMuro:
    def __init__(
        self, *, plantillas: Any, elementos: Any, conceptos: Any, trazos: Any, uow: UnidadDeTrabajo, tomas: Any | None = None
    ) -> None:
        self._plantillas = plantillas
        self._elementos = elementos
        self._conceptos = conceptos
        self._trazos = trazos
        self._uow = uow
        # Lo que un concepto toma de lo que trae la plantilla (castillos estimados y cadenas): al elegirla o cambiarla se rehace (SincronizarTomas).
        self._tomas = tomas

    # --- Lectura -------------------------------------------------------------------------------------------------

    async def listar(self) -> list[dict[str, Any]]:
        return [_ficha(p) for p in await self._plantillas.listar()]

    async def obtener(self, plantilla_id: UUID) -> dict[str, Any]:
        return _ficha(await self._existente(plantilla_id))

    async def versiones(self, plantilla_id: UUID) -> list[dict[str, Any]]:
        p = await self._existente(plantilla_id)
        return [_ficha(v) for v in await self._plantillas.versiones(p["raiz_id"])]

    async def _existente(self, plantilla_id: UUID) -> dict[str, Any]:
        p = await self._plantillas.obtener(plantilla_id)
        if p is None:
            raise PlantillaNoEncontrada(f"La plantilla de muro {plantilla_id} no existe o está fuera de tu alcance.")
        return p  # type: ignore[no-any-return]

    # --- Alta y edición --------------------------------------------------------------------------------------------

    async def _normalizar(self, entrada: Mapping[str, Any]) -> dict[str, Any]:
        catalogo = {str(e["clave"]).upper(): e for e in await self._elementos.listar()}
        info: dict[str, InfoDeElemento] = {}
        elementos: list[dict[str, Any]] = []
        for x in entrada.get("elementos") or []:
            ref = str(x.get("ref") or "").strip()
            el = catalogo.get(ref.upper())
            if el is not None:
                clase = clase_de_elemento(str(el["categoria"]), str(el["subcategoria"]))
                if clase is not None:
                    ref = str(el["clave"])
                    info[ref] = InfoDeElemento(
                        ref=ref, nombre=str(el["nombre"]), clase=clase, categoria=str(el["categoria"]),
                        subcategoria=str(el["subcategoria"]), provisional=el.get("estado_autorizacion") == "pendiente",
                    )
            elif _es_de_muro_de_tabique(ref):
                ref = ref.upper()
                info[ref] = InfoDeElemento(ref=ref, nombre=ELEMENTOS_DE_TABIQUE[ref].nombre, clase="muro")
            elementos.append({**x, "ref": ref})
        return normalizar_plantilla({**entrada, "elementos": elementos}, info)

    async def crear(self, entrada: Mapping[str, Any], *, autor_id: UUID, rol: str) -> dict[str, Any]:
        validar_que_edita(rol)
        datos = await self._normalizar(entrada)
        nuevo = uuid.uuid4()
        async with self._uow:
            await self._plantillas.crear(plantilla_id=nuevo, raiz_id=nuevo, version=1, datos=datos, autor_id=autor_id, rol=rol)
            await self._uow.commit()
        return await self.obtener(nuevo)

    async def actualizar(self, plantilla_id: UUID, entrada: Mapping[str, Any], *, autor_id: UUID, rol: str) -> dict[str, Any]:
        """Cambia una plantilla. Por validar: se edita en el lugar. Validada: nace la versión siguiente (por validar) y la anterior
        queda para los trazos que ya la usan (Q9)."""
        validar_que_edita(rol)
        actual = await self._existente(plantilla_id)
        if not actual["vigente"]:
            raise ErrorDePlantillaDeMuro(
                f"La versión {actual['version']} de «{actual['nombre']}» ya no es la vigente: edita la versión vigente."
            )
        datos = await self._normalizar(entrada)
        if not cambia_la_plantilla(actual, datos):
            return {**_ficha(actual), "version_nueva": False}
        if requiere_version_nueva(actual["validacion"]):
            nuevo = uuid.uuid4()
            async with self._uow:
                await self._plantillas.retirar(plantilla_id)
                await self._plantillas.crear(
                    plantilla_id=nuevo, raiz_id=actual["raiz_id"], version=int(actual["version"]) + 1, datos=datos,
                    autor_id=autor_id, rol=rol,
                )
                await self._uow.commit()
            return {**(await self.obtener(nuevo)), "version_nueva": True}
        async with self._uow:
            await self._plantillas.reemplazar(plantilla_id, datos, autor_id=autor_id, rol=rol)
            if self._tomas is not None:
                # Los trazos que ya usan esta versión (aún por validar) cambian lo que sus conceptos toman.
                for obra_id in await self._plantillas.obras_de_la_plantilla(plantilla_id):
                    await self._tomas.de_la_obra(obra_id)
            await self._uow.commit()
        return {**(await self.obtener(plantilla_id)), "version_nueva": False}

    async def eliminar(self, plantilla_id: UUID, *, rol: str) -> None:
        validar_que_edita(rol)
        p = await self._existente(plantilla_id)
        if await self._plantillas.trazos_de_la_raiz(p["raiz_id"]):
            raise PlantillaEnUso(f"«{p['nombre']}» la usan trazos ya medidos: no se borra.")
        async with self._uow:
            await self._plantillas.eliminar_raiz(p["raiz_id"])
            await self._uow.commit()

    # --- Validación contra la matriz -------------------------------------------------------------------------------

    async def revisar(self, plantilla_id: UUID) -> dict[str, Any]:
        """Lo que no cuadra entre los elementos de la plantilla y la matriz de sus conceptos. No cambia nada."""
        p = await self._existente(plantilla_id)
        alertas = await self._alertas(p)
        return _informe(p, alertas)

    async def validar(self, plantilla_id: UUID, *, usuario_id: UUID, rol: str, aceptar_alertas: bool) -> dict[str, Any]:
        """Control de obra valida la plantilla. Con alertas que bloquean no se puede; con alertas por revisar hay que aceptarlas
        expresamente (`aceptar_alertas`)."""
        validar_que_valida(rol)
        p = await self._existente(plantilla_id)
        if not p["vigente"]:
            raise ErrorDePlantillaDeMuro("Solo se valida la versión vigente de la plantilla.")
        alertas = await self._alertas(p)
        if not puede_validar(alertas):
            motivos = "; ".join(a.mensaje for a in alertas if a.nivel == "bloquea")
            raise ErrorDePlantillaDeMuro(f"No se puede validar la plantilla: {motivos}")
        if alertas and not aceptar_alertas:
            raise ErrorDePlantillaDeMuro(
                f"La plantilla tiene {len(alertas)} alertas por revisar: revísalas y acéptalas para validarla (aceptar_alertas)."
            )
        if p["validacion"] != "validada":
            async with self._uow:
                await self._plantillas.validar(plantilla_id, usuario_id=usuario_id)
                await self._uow.commit()
        p = await self._existente(plantilla_id)
        return _informe(p, alertas)

    async def _alertas(self, p: Mapping[str, Any]) -> list[Alerta]:
        elementos = {str(e["clave"]).upper(): e for e in await self._elementos.listar()}
        alertas: list[Alerta] = []
        para_validar: list[ElementoParaValidar] = []
        instancias = list(p["elementos"] or [])
        material = MATERIALES_DE_MURO.get(str(p["material"]), {})
        implicito = material.get("elemento")
        if implicito and not any(i.get("clase") == "muro" for i in instancias):
            instancias.append({"uid": str(implicito), "ref": str(implicito), "clase": "muro", "implicito": True})
        for i in instancias:
            ref, uid = str(i["ref"]), str(i["uid"])
            if i["clase"] == "muro":
                if not _es_de_muro_de_tabique(ref):
                    alertas.append(Alerta("bloquea", "elemento_inexistente", uid, ref, f"El elemento de muro {ref} ya no existe."))
                    continue
                para_validar.append(await self._del_muro(uid, ref, implicito=bool(i.get("implicito"))))
                continue
            el = elementos.get(ref.upper())
            if el is None:
                alertas.append(Alerta("bloquea", "elemento_inexistente", uid, ref, f"El elemento {ref} ya no está en el catálogo."))
                continue
            para_validar.append(await self._del_catalogo(uid, el, i["clase"]))
        return [*alertas, *validar_contra_matriz(para_validar)]

    async def _matriz(self, concepto_id: UUID | None, clave: str) -> frozenset[str] | None:
        if concepto_id is None:
            return None
        composicion = expandir_composicion(await self._conceptos.composicion_recursiva(concepto_id), clave)
        claves = frozenset(c.clave.upper() for c in composicion if not c.es_mano_de_obra)
        return claves or None

    async def _del_catalogo(self, uid: str, el: Mapping[str, Any], clase: str) -> ElementoParaValidar:
        materiales = dict(el.get("materiales") or {})
        partes: dict[str, frozenset[str]] = {}
        for material, clave in claves_de_materiales(materiales):
            parte = _PARTE_DE_MATERIAL.get(material)
            if parte:
                partes[parte] = partes.get(parte, frozenset()) | {clave.upper()}
        for base in _PARTES_BASE:
            partes.setdefault(base, frozenset())
        conceptos: list[ConceptoDelElemento] = []
        for f in await self._elementos.conceptos_por_contexto(el["id"]):
            toma = frozenset(k for k, v in dict(f["toma"] or {}).items() if v)
            propuesto = f["estado"] != "autorizado" or f["concepto_id"] is None
            matriz = None if propuesto else await self._matriz(f["concepto_id"], str(f["clave"]))
            estado = "propuesto" if propuesto else ("sin_matriz" if matriz is None else "autorizado")
            alto = f.get("alto_hasta_m")
            conceptos.append(
                ConceptoDelElemento(
                    clave=str(f["clave"]), toma=toma, estado=estado,
                    contexto=(f["nivel_min"], f["nivel_max"], f["ubicacion"], Decimal(str(alto)) if alto is not None else None),
                    matriz=matriz,
                )
            )
        return ElementoParaValidar(
            uid=uid, ref=str(el["clave"]), nombre=str(el["nombre"]), clase=clase, partes=partes, conceptos=conceptos,
            provisional=el.get("estado_autorizacion") == "pendiente",
        )

    async def _del_muro(self, uid: str, ref: str, *, implicito: bool) -> ElementoParaValidar:
        d = definicion_de(ref)
        insumos = frozenset({str(d["pieza"]["insumo"]).upper(), str(d["mezcla"]).upper()})
        conceptos: list[ConceptoDelElemento] = []
        for c in d["conceptos"]:
            if c["en_catalogo"]:
                fila = await self._conceptos.obtener_por_clave(c["clave"])
                matriz = await self._matriz(fila["id"] if fila else None, c["clave"])
                estado = "autorizado" if matriz is not None else "sin_matriz"
            else:
                matriz, estado = None, "propuesto"
            conceptos.append(
                ConceptoDelElemento(
                    clave=c["clave"], toma=frozenset({"muro"}), estado=estado, contexto=(c["nivel_desde"], None, None, None), matriz=matriz
                )
            )
        return ElementoParaValidar(
            uid=uid, ref=ref, nombre=str(d["nombre"]), clase="muro", partes={"muro": insumos}, conceptos=conceptos, implicito=implicito
        )

    # --- Prototipos ---------------------------------------------------------------------------------------

    async def prototipos(self) -> list[dict[str, Any]]:
        """Los prototipos con sus plantas y la plantilla de confinado vigente de cada una (o `None`: estructura aún sin capturar)."""
        vigentes = {(p.get("prototipo"), p.get("planta")): p for p in await self._plantillas.listar() if p.get("prototipo")}
        salida: list[dict[str, Any]] = []
        for pr in PROTOTIPOS:
            plantas: list[str | None] = [None] if pr["global"] else list(plantas_de(pr["clave"]))
            salida.append(
                {
                    "clave": pr["clave"], "nombre": pr["nombre"], "plantas": pr["plantas"], "es_global": bool(pr["global"]),
                    "muro_m2": pr["muro_m2"],
                    "plantillas": [
                        {
                            "planta": planta,
                            "plantilla_id": (vigentes[(pr["clave"], planta)]["id"] if (pr["clave"], planta) in vigentes else None),
                            "nombre": (vigentes[(pr["clave"], planta)]["nombre"] if (pr["clave"], planta) in vigentes else None),
                            "por_confirmar": bool(vigentes[(pr["clave"], planta)]["por_confirmar"]) if (pr["clave"], planta) in vigentes else None,
                        }
                        for planta in plantas
                    ],
                }
            )
        return salida

    async def _rehacer_tomas(self, trazo_id: UUID) -> None:
        """Elegir o desligar la plantilla cambia lo que sus conceptos toman (castillos estimados y cadenas): se rehace dentro de la transacción."""
        if self._tomas is not None:
            await self._tomas.de_la_obra_del_trazo(trazo_id)

    # --- Elegir la plantilla en un trazo ---------------------------------------------------------------------------

    async def elegir_en_trazo(self, trazo_id: UUID, plantilla_id: UUID | None) -> dict[str, Any]:
        """El Cuantificador elige la plantilla de muro de un trazo (M-1): el muro toma su tipo, material, ubicación y acabado y
        guarda la **versión** elegida (si la plantilla cambia después, este trazo conserva la suya, Q9). `None` la desliga."""
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if not await self._trazos.es_linea(trazo_id):
            raise ErrorDeCuantificacion("La plantilla de muro se elige sobre una línea.")
        actual = await self._trazos.clasificacion_de_muro(trazo_id)
        if plantilla_id is None:
            async with self._uow:
                await self._trazos.clasificar_muro(
                    trazo_id=trazo_id, tipo=actual["tipo"], acabado=actual["acabado"], material=actual["material"],
                    ubicacion=actual["ubicacion"], plantilla_id=None,
                )
                await self._rehacer_tomas(trazo_id)
                await self._uow.commit()
        else:
            p = await self._existente(plantilla_id)
            async with self._uow:
                await self._trazos.clasificar_muro(
                    trazo_id=trazo_id, tipo=p["tipo"], acabado=acabado_normalizado(p["acabado"]), material=p["material"],
                    ubicacion=p["ubicacion"], plantilla_id=p["id"],
                )
                await self._rehacer_tomas(trazo_id)
                await self._uow.commit()
        c = await self._trazos.clasificacion_de_muro(trazo_id)
        return {**c, "acabado": acabado_normalizado(c["acabado"]) if c["tipo"] else None}


def _ficha(p: Mapping[str, Any]) -> dict[str, Any]:
    return dict(p)


def _informe(p: Mapping[str, Any], alertas: list[Alerta]) -> dict[str, Any]:
    return {
        "plantilla": _ficha(p),
        "alertas": alertas,
        "bloquea": not puede_validar(alertas),
        "validable": puede_validar(alertas),
    }
