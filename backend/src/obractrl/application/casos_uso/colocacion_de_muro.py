"""Colocar en el plano lo que trae la plantilla de un muro y ver a qué conceptos alimenta (Ola 4C; M-4, Q5).

`ver` no cambia nada: dice qué castillos y cadenas lleva la plantilla en ESTE muro (su largo, su altura, su nivel), cuántos ya están
colocados y qué concepto paga cada parte en ese contexto, o por qué no cuenta (falta la partida en el árbol, concepto sin autorizar).
`colocar` pone los castillos ubicados como vanos `castillo` —instancias del elemento de la plantilla— y rehace lo que los conceptos toman;
es idempotente: reemplaza solo las instancias de la plantilla, no los castillos ni los vanos puestos a mano. `retirar` las quita.

Un muro sin plantilla se comporta como siempre (la regla vieja del «muro con cadena» sigue en `GestionarVanos.agregar`).

**Cambiar de plantilla** (`ver_cambio`, `cambiar_plantilla`): un trazo pasa de la plantilla 1 (muro confinado: propone los castillos) a la 2
(«muros y cadena»: los castillos reales se siembran uno por uno) y viceversa **sin perder lo medido**: la medición del muro y todos sus
vanos se conservan. `ver_cambio` dice antes qué cambia (qué deja de estimarse, qué empieza a estimarse, los castillos ya sembrados); solo
con `retirar_castillos` se quitan los castillos sembrados (por ejemplo, al volver a un muro confinado que ya los estima).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.conceptos_de_lo_colocado import (
    conceptos_de_lo_colocado,
    nivel_para_conceptos,
)
from obractrl.application.casos_uso.cuantificar import (
    GestionarVanos,
    TrazoNoEncontrado,
    VanoCambiado,
    area_de_muro,
)
from obractrl.application.casos_uso.parametrico import vigentes_de_obra
from obractrl.application.casos_uso.plantillas_de_muro import PlantillaNoEncontrada
from obractrl.domain.cuantificacion.colocacion_de_plantilla import (
    Colocacion,
    ConceptoColocado,
    colocar_plantilla,
    piezas_en_texto,
    sembrados_por_tipo,
)
from obractrl.domain.cuantificacion.elementos_parametricos import normalizar_parametros
from obractrl.domain.cuantificacion.muro_tipo import acabado_normalizado
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion
from obractrl.domain.shared.diccionario import Rol

__all__ = ["ColocarElementosDeMuro"]

_PREFIJO_DE_CASTILLO = "K"


def _concepto_dict(c: ConceptoColocado) -> dict[str, Any]:
    return {
        "ranura": c.ranura, "concepto_id": c.concepto_id, "clave": c.clave, "unidad": c.unidad, "cantidad": c.cantidad,
        "cuenta": c.cuenta, "estado": c.estado, "origen": c.origen, "aviso": c.aviso, "partida_id": c.partida_id,
    }


class ColocarElementosDeMuro(GestionarVanos):
    def __init__(self, *, elementos: Any, parametrico: Any, plantillas: Any | None = None, **deps: Any) -> None:
        super().__init__(elementos=elementos, **deps)
        self._parametrico = parametrico
        # Las plantillas de muro: para cambiar de una a otra.
        self._plantillas = plantillas
        # (bruto, vanos, neto) del último muro leído por `_plan`.
        self._area: tuple[Decimal, Decimal, Decimal] = (Decimal(0), Decimal(0), Decimal(0))

    async def _separacion_de_castillos(self, contexto: dict[str, Any]) -> Decimal | None:
        """El driver `separacion_castillos` vigente en la obra del muro (la separación de un castillo que la plantilla no fija)."""
        if not contexto.get("obra_id"):
            return None
        vigentes = await vigentes_de_obra(self._parametrico, UUID(str(contexto["obra_id"])))
        v = vigentes.get("separacion_castillos")
        return v.valor if v is not None else None

    async def _sembrados(self, trazo_id: UUID, plantilla: dict[str, Any] | None) -> dict[str, Decimal]:
        """Las piezas de castillo ya sembradas en el muro, por tipo K: el confinado las descuenta de las que estima (no se cuentan dos veces)."""
        return sembrados_por_tipo(await self._trazos.vanos_de_trazo(trazo_id), (plantilla["elementos"] or []) if plantilla else [])

    async def _plan(self, trazo_id: UUID) -> tuple[dict[str, Any], dict[str, Any], Colocacion, dict[str, dict[str, Any]]]:
        """(plantilla, contexto del trazo, lo que coloca la plantilla en este muro, los elementos por clave). Levanta 404 o 422."""
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if not await self._trazos.es_linea(trazo_id):
            raise ErrorDeCuantificacion("La plantilla se coloca sobre una línea (un muro).")
        plantilla = await self._trazos.plantilla_de_muro(trazo_id)
        if plantilla is None:
            raise ErrorDeCuantificacion("Este muro no tiene plantilla: elige una en su detalle para colocar sus elementos.")
        contexto = await self._elementos.contexto_de_trazo(trazo_id) or {}
        catalogo = {e["clave"]: e for e in await self._elementos.listar()}
        anchos: dict[str, Decimal] = {}
        for e in plantilla["elementos"] or []:
            el = catalogo.get(str(e.get("ref")))
            if e.get("clase") == "castillo" and el is not None:
                p = normalizar_parametros(el["tipo"], dict(el["parametros"] or {}))
                anchos[str(e["ref"])] = Decimal(str(p["largo"]))
        largo, altura = await self._trazos.largo_del_eje(trazo_id), await self._altura_del_muro(trazo_id)
        self._area = await area_de_muro(self._trazos, trazo_id, largo, altura)
        colocacion = colocar_plantilla(
            plantilla["elementos"] or [],
            largo_m=largo,
            altura_m=altura,
            anchos_m=anchos,
            separacion_m=await self._separacion_de_castillos(contexto),
            area_m2=self._area[2],
            sembrados=await self._sembrados(trazo_id, plantilla),
        )
        return plantilla, contexto, colocacion, catalogo

    async def ver_colocacion(self, trazo_id: UUID) -> dict[str, Any]:
        plantilla, contexto, colocacion, catalogo = await self._plan(trazo_id)
        area = self._area
        puestos = [v for v in await self._trazos.vanos_de_trazo(trazo_id) if v.get("elemento_uid")]
        obra_id = UUID(str(contexto["obra_id"])) if contexto.get("obra_id") else None
        # Los castillos (estimados y ubicados) y las cadenas alimentan conceptos: la cadena cuenta el largo del muro en ml (no se coloca).
        grupos = [
            {
                "elemento_id": catalogo[i.ref]["id"], "ref": i.ref, "uid": i.uid,
                "numero_de_nivel": contexto.get("numero_de_nivel"), "nivel_id": contexto.get("nivel_id"), "etapa_id": contexto.get("etapa_id"),
                "ubicacion": contexto.get("ubicacion"),
                **(
                    {"alto_m": i.alto_m, "piezas": i.piezas_exactas}
                    if i.clase == "castillo"
                    else {"alto_m": None, "piezas": 1, "metros": i.metros}
                ),
            }
            for i in colocacion.instancias
            if i.ref in catalogo and (i.clase == "cadena" or (i.clase == "castillo" and i.alto_m is not None and i.piezas_exactas > 0))
        ]
        conceptos: dict[str, tuple[list[ConceptoColocado], list[str]]] = {}
        if obra_id is not None and grupos:
            for g, cs, avisos in await conceptos_de_lo_colocado(
                elementos=self._elementos, parametrico=self._parametrico, obra_id=obra_id, instancias=grupos
            ):
                conceptos[g["uid"]] = (cs, avisos)
        avisos_generales = list(colocacion.avisos)
        origenes = {str(e.get("uid")): e.get("origen") for e in plantilla["elementos"] or []}
        elementos = []
        for i in colocacion.instancias:
            cs, avisos = conceptos.get(i.uid, ([], []))
            avisos_generales.extend(avisos)
            elementos.append(
                {
                    "uid": i.uid, "ref": i.ref, "nombre": catalogo.get(i.ref, {}).get("nombre", i.ref), "clase": i.clase, "modo": i.modo,
                    "regla": i.regla, "piezas_estimadas": i.piezas_estimadas, "piezas_sembradas": i.piezas_sembradas,
                    "piezas_contadas": i.piezas_exactas, "origen": origenes.get(i.uid),
                    "piezas": i.piezas, "alto_m": i.alto_m, "z_m": i.z_m, "metros": i.metros,
                    "posiciones_m": list(i.posiciones_m), "se_coloca": i.se_coloca,
                    "colocados": sum(int(v["piezas"]) for v in puestos if v["elemento_uid"] == i.uid),
                    "descuento_m2_por_cara": i.descuento_m2_por_cara,
                    "conceptos": [_concepto_dict(c) for c in cs],
                }
            )
        return {
            "trazo_id": trazo_id,
            "plantilla_id": plantilla["id"], "plantilla": plantilla["nombre"], "version": plantilla["version"], "tipo": plantilla["tipo"],
            "largo_m": colocacion.largo_m, "altura_m": colocacion.altura_m,
            "area_bruta_m2": area[0], "vanos_m2": area[1], "area_neta_m2": area[2], "area_usada": "neto" if area[1] > 0 else "bruto",
            "nivel": nivel_para_conceptos(contexto.get("numero_de_nivel")), "ubicacion": contexto.get("ubicacion"),
            "elementos": elementos,
            "avisos": list(dict.fromkeys(avisos_generales)),
        }

    async def _claves_libres(self, trazo_id: UUID, cuantas: int) -> list[str]:
        usadas = {str(v["clave"]).upper() for v in await self._trazos.vanos_de_trazo(trazo_id) if not v.get("elemento_uid")}
        claves: list[str] = []
        n = 1
        while len(claves) < cuantas:
            clave = f"{_PREFIJO_DE_CASTILLO}-{n:02d}"
            if clave not in usadas:
                claves.append(clave)
            n += 1
        return claves

    async def colocar(self, trazo_id: UUID, *, rol: Rol, autor_id: UUID, detectada_en: datetime) -> dict[str, Any]:
        _, _, colocacion, _ = await self._plan(trazo_id)
        a_colocar = [i for i in colocacion.instancias if i.se_coloca]
        if not a_colocar:
            raise ErrorDeCuantificacion(
                "La plantilla de este muro no lleva castillos ubicados: no hay nada que colocar en el plano "
                "(los castillos estimados solo se cuentan)."
            )
        claves = await self._claves_libres(trazo_id, sum(i.piezas for i in a_colocar))
        quitados = 0

        async def poner() -> UUID:
            nonlocal quitados
            quitados = await self._trazos.quitar_instancias_de_plantilla(trazo_id, [i.uid for i in a_colocar])
            primero: UUID | None = None
            for i in a_colocar:
                assert i.alto_m is not None and i.ancho_m is not None
                for posicion in i.posiciones_m:
                    vano_id = await self._trazos.crear_vano(
                        trazo_id=trazo_id, clave=claves.pop(0), tipo="castillo", ancho_m=i.ancho_m, alto_m=i.alto_m,
                        antepecho_m=Decimal(0), piezas=1, posicion_m=posicion, autor_id=autor_id, elemento_uid=i.uid,
                    )
                    primero = primero or vano_id
            assert primero is not None
            return primero

        r: VanoCambiado = await self._cambiar(trazo_id, rol, autor_id, detectada_en, poner)
        return {
            "colocados": sum(i.piezas for i in a_colocar),
            "reemplazados": quitados,
            "recalculos": r.recalculos,
            "descuento_m2_por_cara": sum((i.descuento_m2_por_cara for i in a_colocar), Decimal(0)),
        }

    async def retirar(self, trazo_id: UUID, *, rol: Rol, autor_id: UUID, detectada_en: datetime) -> dict[str, Any]:
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        quitados = 0
        plantilla = await self._trazos.plantilla_de_muro(trazo_id)
        # Solo lo que la plantilla coloca (sus castillos ubicados): un castillo sembrado a mano de otro K no se toca.
        uids = [str(e["uid"]) for e in (plantilla["elementos"] if plantilla else []) or [] if e.get("clase") == "castillo" and e.get("modo") == "ubicado"]

        async def quitar() -> UUID:
            nonlocal quitados
            quitados = await self._trazos.quitar_instancias_de_plantilla(trazo_id, uids if plantilla is not None else None)
            return trazo_id

        r = await self._cambiar(trazo_id, rol, autor_id, detectada_en, quitar)
        return {"retirados": quitados, "recalculos": r.recalculos}

    # --- Cambiar de plantilla sin perder lo medido --------------------------------------------------------------------

    async def _estimado_de(
        self,
        plantilla: dict[str, Any] | None,
        *,
        largo: Decimal,
        altura: Decimal,
        separacion: Decimal | None,
        area_m2: Decimal,
        sembrados: dict[str, Decimal],
    ) -> Colocacion | None:
        """Lo que la plantilla cuenta en este muro sin colocarlo (castillos estimados y cadenas); `None` si la plantilla no cabe en el muro."""
        if plantilla is None:
            return None
        elementos = [e for e in plantilla["elementos"] or [] if e.get("clase") == "cadena" or (e.get("clase") == "castillo" and e.get("modo") == "estimado")]
        try:
            return colocar_plantilla(elementos, largo_m=largo, altura_m=altura, anchos_m={}, separacion_m=separacion, area_m2=area_m2, sembrados=sembrados)
        except ErrorDeCuantificacion:
            return None

    @staticmethod
    def _efectos(antes: Colocacion | None, despues: Colocacion | None) -> list[dict[str, Any]]:
        """Qué elementos que la plantilla cuenta (castillos estimados y cadenas) dejan de contarse, empiezan o siguen."""
        previos = {i.uid: i for i in (antes.instancias if antes else [])}
        nuevos = {i.uid: i for i in (despues.instancias if despues else [])}
        salida: list[dict[str, Any]] = []
        for uid in dict.fromkeys([*previos, *nuevos]):
            i = nuevos.get(uid) or previos[uid]
            efecto = "sigue" if uid in previos and uid in nuevos else ("nuevo" if uid in nuevos else "deja")
            salida.append(
                {
                    "uid": uid, "ref": i.ref, "clase": i.clase, "efecto": efecto, "regla": i.regla,
                    "piezas": i.piezas_exactas if i.clase == "castillo" else Decimal(0), "metros": i.metros,
                    "piezas_estimadas": i.piezas_estimadas, "piezas_sembradas": i.piezas_sembradas,
                }
            )
        return salida

    async def version_vigente(self, trazo_id: UUID) -> dict[str, Any]:
        """La plantilla del muro frente a la versión vigente de la misma plantilla (C4). Un muro ya medido conserva la versión que eligió (Q9);
        si hay una más nueva se ofrece «actualizar a la versión vigente», que pasa por `ver_cambio` (qué cambia) y `cambiar_plantilla`. No cambia nada."""
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if not await self._trazos.es_linea(trazo_id):
            raise ErrorDeCuantificacion("La plantilla se consulta sobre una línea (un muro).")
        actual = await self._trazos.plantilla_de_muro(trazo_id)
        if actual is None or self._plantillas is None:
            return {"trazo_id": trazo_id, "actual": None, "vigente": None, "hay_version_nueva": False}
        vigente = next((v for v in await self._plantillas.versiones(actual["raiz_id"]) if v["vigente"]), None)

        def ficha(p: dict[str, Any]) -> dict[str, Any]:
            return {"id": p["id"], "nombre": p["nombre"], "version": p["version"], "tipo": p["tipo"]}

        return {
            "trazo_id": trazo_id,
            "actual": ficha(actual),
            "vigente": ficha(vigente) if vigente is not None else None,
            "hay_version_nueva": vigente is not None and vigente["id"] != actual["id"],
        }

    async def ver_cambio(self, trazo_id: UUID, hacia_id: UUID) -> dict[str, Any]:
        """Qué cambia si el muro pasa a la plantilla `hacia_id`: el tipo, el material y la ubicación; los castillos estimados y las cadenas
        que dejan de contarse, empiezan o siguen; los castillos ya sembrados; y lo que se conserva. No cambia nada."""
        if await self._trazos.obtener(trazo_id) is None:
            raise TrazoNoEncontrado(f"El trazo {trazo_id} no existe o no está en tu alcance.")
        if not await self._trazos.es_linea(trazo_id):
            raise ErrorDeCuantificacion("La plantilla se cambia sobre una línea (un muro).")
        hacia = await self._plantillas.obtener(hacia_id) if self._plantillas is not None else None
        if hacia is None:
            raise PlantillaNoEncontrada(f"La plantilla de muro {hacia_id} no existe o está fuera de tu alcance.")
        actual = await self._trazos.plantilla_de_muro(trazo_id)
        clasificacion = await self._trazos.clasificacion_de_muro(trazo_id)
        contexto = await self._elementos.contexto_de_trazo(trazo_id) or {}
        largo, altura = await self._trazos.largo_del_eje(trazo_id), await self._altura_del_muro(trazo_id)
        separacion = await self._separacion_de_castillos(contexto)
        neta = (await area_de_muro(self._trazos, trazo_id, largo, altura))[2]
        vanos = await self._trazos.vanos_de_trazo(trazo_id)
        # Los castillos ya sembrados se conservan y la plantilla de confinado no los cuenta otra vez (se descuentan, por tipo K, de los que estima).
        por_tipo = sembrados_por_tipo(vanos, (actual["elementos"] or []) if actual else [])
        por_tipo_hacia = sembrados_por_tipo(vanos, hacia["elementos"] or [])
        efectos = self._efectos(
            await self._estimado_de(actual, largo=largo, altura=altura, separacion=separacion, area_m2=neta, sembrados=por_tipo),
            await self._estimado_de(hacia, largo=largo, altura=altura, separacion=separacion, area_m2=neta, sembrados=por_tipo_hacia),
        )
        sembrados = [v for v in vanos if v["tipo"] == "castillo" and v.get("elemento_uid")]
        otros = [v for v in vanos if not (v["tipo"] == "castillo" and v.get("elemento_uid"))]
        por_colocar = sum(
            1 for e in hacia["elementos"] or [] if e.get("clase") == "castillo" and e.get("modo") == "ubicado"
        )
        cambia = [
            {"campo": campo, "de": clasificacion.get(campo), "a": hacia[campo]}
            for campo in ("tipo", "material", "ubicacion")
            if clasificacion.get(campo) != hacia[campo]
        ]
        avisos: list[str] = []
        if actual is not None and actual["id"] == hacia["id"]:
            avisos.append("El muro ya tiene esta plantilla.")
        if any(e["clase"] == "castillo" and e["efecto"] == "deja" for e in efectos):
            avisos.append("Los castillos que la plantilla actual estimaba dejan de contarse por regla.")
        if hacia["tipo"] == "con_cadena" and any(e["clase"] == "castillo" and e["efecto"] == "deja" for e in efectos):
            avisos.append("La plantilla nueva es de «muros y cadena»: los castillos reales se siembran uno por uno en el plano, cada uno de su tipo K.")
        if hacia["tipo"] == "confinado" and sembrados:
            for e in efectos:
                if e["clase"] == "castillo" and e["efecto"] != "deja" and e["piezas_sembradas"] > 0:
                    avisos.append(
                        f"Castillos {e['ref']}: estimados {piezas_en_texto(e['piezas_estimadas'])}, sembrados {piezas_en_texto(e['piezas_sembradas'])}, "
                        f"contados {piezas_en_texto(e['piezas'])}. "
                        "Los sembrados se conservan y no se cuentan dos veces."
                    )
            avisos.append(
                f"El muro tiene {len(sembrados)} castillo{'s' if len(sembrados) != 1 else ''} sembrado{'s' if len(sembrados) != 1 else ''}: "
                "se conservan y la plantilla nueva no los cuenta otra vez (descuenta, por tipo K, los sembrados de los que estima). "
                "Solo se retiran si tú lo pides."
            )
        if hacia["tipo"] == "con_cadena" and por_colocar:
            avisos.append("La plantilla nueva lleva castillos ubicados: colócalos con «Colocar los elementos de la plantilla».")
        if hacia["tipo"] != "con_cadena" and hacia["tipo"] != "confinado":
            avisos.append("Un muro de tabique no lleva castillos ni cadenas.")
        if hacia["validacion"] != "validada":
            avisos.append("La plantilla nueva aún está por validar: es provisional.")
        acabado_capturado = clasificacion.get("acabado") is not None
        if acabado_capturado:
            avisos.append("El acabado ya capturado se conserva: la plantilla es la guía (tipo, material, ubicación y elementos), no pisa el acabado.")
        conserva = [f"La medición del muro ({altura:g} m de alto × {largo:.2f} m de largo)."]
        if otros:
            conserva.append(f"{len(otros)} vano{'s' if len(otros) != 1 else ''} (puertas, ventanas, pasos y castillos a mano sin elemento).")
        if acabado_capturado:
            conserva.append("El acabado ya capturado (por cara y capa).")
        if sembrados:
            conserva.append(f"{len(sembrados)} castillo{'s' if len(sembrados) != 1 else ''} sembrado{'s' if len(sembrados) != 1 else ''} con su elemento.")
        return {
            "trazo_id": trazo_id,
            "de": None if actual is None else {"id": actual["id"], "nombre": actual["nombre"], "version": actual["version"], "tipo": actual["tipo"]},
            "hacia": {"id": hacia["id"], "nombre": hacia["nombre"], "version": hacia["version"], "tipo": hacia["tipo"]},
            "cambia": cambia, "efectos": efectos, "acabado_se_conserva": acabado_capturado,
            "castillos_sembrados": len(sembrados), "castillos_por_colocar": por_colocar,
            "conserva": conserva, "avisos": list(dict.fromkeys(avisos)),
        }

    async def cambiar_plantilla(
        self, trazo_id: UUID, hacia_id: UUID, *, retirar_castillos: bool, rol: Rol, autor_id: UUID, detectada_en: datetime
    ) -> dict[str, Any]:
        """El muro pasa a la plantilla `hacia_id`: toma su tipo, material y ubicación y guarda la versión (Q9). El acabado ya capturado se
        conserva (la plantilla es la guía). La medición y los vanos se conservan; los castillos sembrados solo se quitan con
        `retirar_castillos`. Rehace lo que los conceptos toman."""
        antes = await self.ver_cambio(trazo_id, hacia_id)
        clasificacion = await self._trazos.clasificacion_de_muro(trazo_id)
        hacia = await self._plantillas.obtener(hacia_id)
        assert hacia is not None
        retirados = 0

        async def aplicar() -> UUID:
            nonlocal retirados
            await self._trazos.clasificar_muro(
                trazo_id=trazo_id, tipo=hacia["tipo"], material=hacia["material"],
                # La plantilla es la guía, no pisa el acabado ya capturado; sin acabado capturado toma el de la plantilla.
                acabado=clasificacion["acabado"] if clasificacion.get("acabado") is not None else acabado_normalizado(hacia["acabado"]),
                ubicacion=hacia["ubicacion"], plantilla_id=hacia["id"],
            )
            if retirar_castillos:
                retirados = await self._trazos.quitar_instancias_de_plantilla(trazo_id)
            return trazo_id

        r = await self._cambiar(trazo_id, rol, autor_id, detectada_en, aplicar)
        return {
            "antes": antes["de"], "despues": antes["hacia"], "retirados": retirados,
            "conservados": 0 if retirar_castillos else antes["castillos_sembrados"],
            "recalculos": r.recalculos, "avisos": antes["avisos"],
        }
