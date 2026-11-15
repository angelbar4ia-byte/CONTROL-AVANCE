"""«Confirmar cálculo → actualizar APU» y la conciliación en las dos direcciones (plan de elementos de muro, fase I; M-131).

El **APU manda**: las compras y la estimación se pagan con el APU del concepto. El cálculo de un elemento (su receta puesta en
los insumos que eligió) es la salida de material que justifica esa estimación. Al **confirmar el cálculo**, los coeficientes del
elemento pasan al APU del concepto: se cambian los renglones directos del APU (los que vienen dentro de un auxiliar no se
tocan) y se publica una **versión nueva del CPU**; la composición de la versión anterior se conserva. Costos **propone** esa
actualización y Control de obra la autoriza; la de Control de obra se aplica al momento. En los dos casos queda una versión del
concepto con lo que había antes, lo que hay ahora, quién lo propuso, quién lo autorizó y cuándo. Nada de esto inventa precios: un
insumo que se agrega entra con el costo que ya tiene en la base de insumos (cero si es provisional).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from obractrl.application.casos_uso.calcular_cpu import (
    _versiones_de_dominio,
    componentes_por_clave,
)
from obractrl.application.casos_uso.elementos_parametricos import (
    ElementoParametricoNoEncontrado,
)
from obractrl.application.puertos.repositorios import UnidadDeTrabajo
from obractrl.domain.catalogos.apu import explotar, publicar_version
from obractrl.domain.cuantificacion.actualizacion_de_apu import (
    CambioDeApu,
    LineaDelApu,
    conciliar,
    planear,
)
from obractrl.domain.cuantificacion.autorizacion_de_elementos import (
    siguiente_version,
    validar_que_autoriza,
    validar_que_propone,
)
from obractrl.domain.cuantificacion.comparacion_con_catalogo import expandir_composicion
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
    normalizar_parametros,
)
from obractrl.domain.cuantificacion.materiales_de_elemento import (
    cantidades_por_insumo,
    claves_de_materiales,
)
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = ["ActualizarApuDesdeElemento"]

_DEC = Decimal("0.000001")


def _cantidad_de(fila: dict[str, Any]) -> Decimal:
    cantidad = Decimal(str(fila.get("cantidad") or 0))
    return cantidad if cantidad != 0 else Decimal(str(fila.get("rendimiento") or 0))


class ActualizarApuDesdeElemento:
    def __init__(self, *, elementos: Any, insumos: Any, conceptos: Any, versiones: Any, uow: UnidadDeTrabajo) -> None:
        self._elementos = elementos
        self._insumos = insumos
        self._conceptos = conceptos
        self._versiones = versiones
        self._uow = uow

    # --- Lectura ------------------------------------------------------------------------------------------------

    async def _fila(self, elemento_id: UUID, fila_id: UUID) -> tuple[dict[str, Any], dict[str, Any]]:
        elemento = await self._elementos.obtener(elemento_id)
        if elemento is None:
            raise ElementoParametricoNoEncontrado(f"El elemento {elemento_id} no existe o está fuera de tu alcance.")
        fila = await self._elementos.concepto_por_contexto(elemento_id, fila_id)
        if fila is None:
            raise ElementoParametricoNoEncontrado(f"El concepto {fila_id} no es de este elemento.")
        return elemento, fila

    async def _salida(self, elemento: dict[str, Any], fila: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
        """Lo que calcula el elemento de cada insumo, por unidad del concepto: la salida de material."""
        materiales = dict(elemento.get("materiales") or {})
        parametros = normalizar_parametros(elemento["tipo"], dict(elemento["parametros"] or {}))
        propias = await self._insumos.por_claves([c for _, c in claves_de_materiales(materiales)])
        toma = {m: bool(v) for m, v in dict(fila["toma"] or {}).items()}
        cantidades, avisos = cantidades_por_insumo(
            elemento["tipo"], parametros, materiales, unidad=fila["unidad"], toma=toma,
            unidades_de_insumo={k.upper(): (v[1].unidad or "") for k, v in propias.items()},
        )
        return {k.upper(): float(v) for k, v in cantidades.items()}, avisos

    async def _apu(self, fila: dict[str, Any]) -> tuple[list[LineaDelApu], list[dict[str, Any]], dict[str, Any]]:
        """El APU del concepto con los auxiliares expandidos hasta los insumos, y las filas crudas de la composición."""
        if fila["concepto_id"] is None:
            return [], [], {}
        filas = await self._conceptos.composicion_recursiva(fila["concepto_id"])
        clave = str(fila["clave"])
        # Lo que llega por renglones directos del concepto (el resto viene dentro de un auxiliar).
        directas: dict[str, Decimal] = {}
        for f in filas:
            if f["concepto_clave"] == clave and f["tipo_hijo"] == "insumo" and str(f["categoria"]) == "material":
                k = str(f["insumo_clave"]).upper()
                directas[k] = directas.get(k, Decimal(0)) + _cantidad_de(f)

        totales: dict[str, float] = {}
        mano: dict[str, float] = {}
        costos: dict[str, float] = {}
        for c in expandir_composicion(filas, clave):
            k = c.clave.upper()
            destino = mano if c.es_mano_de_obra else totales
            destino[k] = destino.get(k, 0.0) + c.cantidad
            if c.costo:
                costos.setdefault(k, c.costo)
        conocidos = await self._insumos.por_claves(sorted({*totales, *mano}))
        lineas: list[LineaDelApu] = []
        for k, cantidad in totales.items():
            ins = conocidos.get(k)
            precio = ins[1].precio if ins and ins[1].precio else None
            lineas.append(
                LineaDelApu(
                    clave=k, cantidad=cantidad, directa=float(directas[k]) if k in directas else None,
                    descripcion=ins[1].descripcion if ins else "", unidad=(ins[1].unidad or "") if ins else "",
                    costo=costos.get(k, precio),
                )
            )
        return lineas, filas, conocidos

    @staticmethod
    def _precio(filas: list[dict[str, Any]], clave: str) -> PrecioUnitario:
        composiciones, costos = componentes_por_clave(filas)
        return explotar(clave, composiciones=composiciones, costos_insumo=costos).precio

    @staticmethod
    def _filas_con_cambios(filas: list[dict[str, Any]], clave: str, cambios: list[CambioDeApu], precios: dict[str, float | None]) -> list[dict[str, Any]]:
        """Las filas de la composición como quedarían al aplicar los cambios (para calcular el precio nuevo sin escribir)."""
        nuevas = [dict(f) for f in filas]
        for c in cambios:
            if c.accion == "actualizar":
                coincidencias = [
                    f for f in nuevas
                    if f["concepto_clave"] == clave and f["tipo_hijo"] == "insumo" and str(f["categoria"]) == "material"
                    and str(f["insumo_clave"]).upper() == c.clave
                ]
                if coincidencias:
                    resto = sum((_cantidad_de(f) for f in coincidencias[1:]), Decimal(0))
                    primera = coincidencias[0]
                    primera["cantidad"] = max(Decimal(str(c.despues)) - resto, Decimal(0))
                    if primera["cantidad"] == 0:
                        primera["rendimiento"] = 0
            else:
                nuevas.append(
                    {
                        "concepto_clave": clave, "tipo_hijo": "insumo", "categoria": "material", "cantidad": Decimal(str(c.despues)),
                        "rendimiento": 0, "costo_unitario": None, "orden": 10**6, "insumo_clave": c.clave,
                        "costo_insumo_vigente": precios.get(c.clave), "concepto_hijo_clave": None,
                    }
                )
        return nuevas

    async def _planear(self, elemento: dict[str, Any], fila: dict[str, Any]) -> dict[str, Any]:
        salida, avisos = await self._salida(elemento, fila)
        lineas, filas, conocidos = await self._apu(fila)
        en_el_apu = {x.clave for x in lineas}
        faltantes = [k for k in salida if k not in en_el_apu]
        extra = await self._insumos.por_claves(faltantes) if faltantes else {}
        plan = planear(
            salida, lineas, insumos_existentes=list(extra),
            descripciones={k: v[1].descripcion for k, v in {**conocidos, **extra}.items()},
        )
        precios = {k: (v[1].precio if v[1].precio else None) for k, v in {**conocidos, **extra}.items()}
        pu_antes = pu_despues = None
        if fila["concepto_id"] is not None:
            clave = str(fila["clave"])
            pu_antes = self._precio(filas, clave)
            pu_despues = self._precio(self._filas_con_cambios(filas, clave, plan.cambios, precios), clave)
        return {
            "plan": plan, "salida": salida, "avisos": avisos, "lineas": lineas, "filas": filas, "precios": precios,
            "pu_antes": pu_antes, "pu_despues": pu_despues,
        }

    async def plan(self, elemento_id: UUID, fila_id: UUID) -> dict[str, Any]:
        """Lo que haría confirmar el cálculo del elemento sobre el APU del concepto, insumo por insumo, y el precio unitario con
        el cálculo confirmado contra el vigente."""
        elemento, fila = await self._fila(elemento_id, fila_id)
        p = await self._planear(elemento, fila)
        pendiente = await self._versiones.pendiente_de(await self._versiones.raiz_de(elemento_id), fila_id, "apu")
        return {
            "fila_id": fila_id,
            "concepto_clave": fila["clave"],
            "concepto_descripcion": fila["descripcion"],
            "unidad": fila["unidad"],
            "sin_catalogo": fila["concepto_id"] is None,
            "manda": "apu",
            "filas": p["plan"].filas,
            "avisos": [*p["avisos"], *p["plan"].avisos],
            "hay_cambios": p["plan"].hay_cambios,
            "pu_vigente": float(p["pu_antes"].total.monto) if p["pu_antes"] else None,
            "pu_con_el_calculo": float(p["pu_despues"].total.monto) if p["pu_despues"] else None,
            "propuesta_pendiente": pendiente["id"] if pendiente else None,
        }

    async def conciliacion(self, elemento_id: UUID, fila_id: UUID, cantidad: float) -> dict[str, Any]:
        """El estimado por APU contra la salida del cálculo del elemento, en las dos direcciones, para `cantidad` del concepto."""
        if cantidad <= 0:
            raise ErrorDeElementoParametrico("La cantidad del concepto es mayor que cero.")
        elemento, fila = await self._fila(elemento_id, fila_id)
        p = await self._planear(elemento, fila)
        resultado = conciliar(p["salida"], p["lineas"], cantidad=cantidad, precios=p["precios"])
        return {
            "fila_id": fila_id, "concepto_clave": fila["clave"], "unidad": fila["unidad"], "sin_catalogo": fila["concepto_id"] is None,
            "avisos": p["avisos"], **resultado,
        }

    # --- Escritura ----------------------------------------------------------------------------------------------

    async def confirmar(self, elemento_id: UUID, fila_id: UUID, *, usuario_id: UUID, rol: str) -> dict[str, Any]:
        """«Confirmar cálculo → actualizar APU». Control de obra lo aplica y queda como la versión siguiente del concepto; Costos
        lo propone y el APU vigente rige hasta que Control de obra lo autorice."""
        validar_que_propone(rol)
        elemento, fila = await self._fila(elemento_id, fila_id)
        if fila["concepto_id"] is None:
            raise ErrorDeElementoParametrico(
                f"{fila['clave']} es un concepto nuevo: aún no está en el catálogo ni tiene APU. Autorízalo antes de actualizar su APU."
            )
        p = await self._planear(elemento, fila)
        plan = p["plan"]
        if not plan.hay_cambios:
            raise ErrorDeElementoParametrico("El cálculo del elemento ya coincide con el APU: no hay nada que actualizar.")
        raiz = await self._versiones.raiz_de(elemento_id)
        detalle = {
            "cambios": [{"clave": c.clave, "accion": c.accion, "antes": c.antes, "despues": c.despues} for c in plan.cambios],
            "pu_antes": float(p["pu_antes"].total.monto), "pu_despues": float(p["pu_despues"].total.monto),
            "concepto_clave": fila["clave"],
        }
        resumen = f"APU de {fila['clave']}: " + "; ".join(
            f"{c.clave} {'—' if c.antes is None else f'{c.antes:g}'} → {c.despues:g}" for c in plan.cambios
        )
        if rol == "control_obra":
            async with self._uow:
                await self._aplicar(fila, plan.cambios, p)
                numero = siguiente_version(await self._versiones.autorizadas(raiz, fila_id))
                revision = await self._versiones.registrar(
                    elemento_id=elemento_id, raiz_id=raiz, fila_id=fila_id, clase="apu", estado="autorizada", version=numero,
                    resumen=resumen, detalle=detalle, propuso_id=usuario_id, propuso_rol=rol, decidio_id=usuario_id, decidio_rol=rol,
                )
                await self._uow.commit()
            return {"aplicado": True, "revision_id": revision, "version": numero, "resumen": resumen, **_pu(detalle)}
        async with self._uow:
            revision = await self._versiones.registrar(
                elemento_id=elemento_id, raiz_id=raiz, fila_id=fila_id, clase="apu", estado="pendiente", version=None,
                resumen=resumen, detalle=detalle, propuso_id=usuario_id, propuso_rol=rol,
            )
            await self._uow.commit()
        return {"aplicado": False, "revision_id": revision, "version": None, "resumen": resumen, **_pu(detalle)}

    async def autorizar(self, revision: dict[str, Any], *, usuario_id: UUID, rol: str) -> int:
        """Control de obra autoriza la actualización propuesta por Costos: se aplican los coeficientes que Costos propuso y queda
        la versión siguiente del concepto. Devuelve su número."""
        validar_que_autoriza(rol)
        elemento, fila = await self._fila(revision["elemento_id"], revision["fila_id"])
        cambios = [
            CambioDeApu(str(c["clave"]), str(c["accion"]), None if c["antes"] is None else float(c["antes"]), float(c["despues"]))
            for c in dict(revision["detalle"]).get("cambios", [])
        ]
        if fila["concepto_id"] is None:
            raise ErrorDeElementoParametrico("El concepto de esta propuesta ya no está en el catálogo.")
        p = await self._planear(elemento, fila)
        async with self._uow:
            await self._aplicar(fila, cambios, p)
            numero = siguiente_version(await self._versiones.autorizadas(revision["raiz_id"], revision["fila_id"]))
            await self._versiones.decidir(revision["id"], estado="autorizada", version=numero, decidio_id=usuario_id, decidio_rol=rol)
            await self._uow.commit()
        return numero

    async def _aplicar(self, fila: dict[str, Any], cambios: list[CambioDeApu], p: dict[str, Any]) -> None:
        """Cambia los renglones directos del APU y publica la versión nueva del CPU con el precio resultante."""
        concepto_id: UUID = fila["concepto_id"]
        clave = str(fila["clave"])
        renglones = await self._conceptos.renglones_del_apu(concepto_id)
        cpu = await self._conceptos.cpu_vigente(concepto_id)
        filas_nuevas = self._filas_con_cambios(p["filas"], clave, cambios, p["precios"])
        precio = self._precio(filas_nuevas, clave)
        # Las cantidades nuevas por renglón (el primer renglón directo del insumo lleva el ajuste).
        nuevas: dict[UUID, Decimal] = {}
        for c in cambios:
            if c.accion != "actualizar":
                continue
            coincidencias = [
                r for r in renglones
                if r["tipo_hijo"] == "insumo" and str(r["categoria"]) == "material" and str(r["insumo_clave"] or "").upper() == c.clave
            ]
            if not coincidencias:
                raise ErrorDeElementoParametrico(f"El APU ya no trae {c.clave}: vuelve a calcular la actualización.")
            resto = sum((_cantidad_de(r) for r in coincidencias[1:]), Decimal(0))
            nuevas[coincidencias[0]["id"]] = max(Decimal(str(c.despues)) - resto, Decimal(0)).quantize(_DEC)
        a_agregar = [c for c in cambios if c.accion == "agregar"]
        insumos = await self._insumos.por_claves([c.clave for c in a_agregar]) if a_agregar else {}
        for c in a_agregar:
            if c.clave not in insumos:
                raise ErrorDeElementoParametrico(f"El insumo {c.clave} no existe en la base: créalo antes de llevarlo al APU.")

        def _importe(r: dict[str, Any], cantidad: Decimal) -> Decimal:
            viejo = _cantidad_de(r)
            if viejo != 0:
                return (Decimal(str(r["importe"] or 0)) * cantidad / viejo).quantize(Decimal("0.0001"))
            return (cantidad * Decimal(str(r["costo_unitario"] or 0))).quantize(Decimal("0.0001"))

        def _fila_copiada(r: dict[str, Any]) -> dict[str, Any]:
            cantidad = nuevas.get(r["id"])
            copia = {
                "tipo_hijo": str(r["tipo_hijo"]), "insumo_id": r["insumo_id"], "concepto_hijo_id": r["concepto_hijo_id"],
                "categoria": str(r["categoria"]), "cantidad": r["cantidad"], "rendimiento": r["rendimiento"],
                "costo_unitario": r["costo_unitario"], "importe": r["importe"], "orden": r["orden"],
            }
            if cantidad is not None:
                copia.update(cantidad=cantidad, rendimiento=0 if cantidad == 0 else r["rendimiento"], importe=_importe(r, cantidad))
            return copia

        def _fila_nueva(c: CambioDeApu, orden: int) -> dict[str, Any]:
            insumo_id, ins = insumos[c.clave]
            costo = Decimal(str(ins.precio or 0))
            cantidad = Decimal(str(c.despues)).quantize(_DEC)
            return {
                "tipo_hijo": "insumo", "insumo_id": insumo_id, "concepto_hijo_id": None, "categoria": "material", "cantidad": cantidad,
                "rendimiento": 0, "costo_unitario": costo, "importe": (cantidad * costo).quantize(Decimal("0.0001")), "orden": orden,
            }

        orden = max((int(r["orden"] or 0) for r in renglones), default=0) + 1
        adjuntas = [r for r in renglones if cpu is not None and r["cpu_id"] == cpu["id"]]
        vivas = [r for r in renglones if r["cpu_id"] is None]
        # La composición viva se cambia en sitio; lo agregado entra donde está la composición del concepto.
        for r in vivas:
            if r["id"] in nuevas:
                await self._conceptos.actualizar_renglon_del_apu(
                    r["id"], cantidad=nuevas[r["id"]], rendimiento=Decimal(0) if nuevas[r["id"]] == 0 else Decimal(str(r["rendimiento"] or 0)),
                    importe=_importe(r, nuevas[r["id"]]),
                )
        if not adjuntas:
            await self._conceptos.agregar_explosion(concepto_id, cpu_id=None, filas=[_fila_nueva(c, orden + i) for i, c in enumerate(a_agregar)])
        versiones = _versiones_de_dominio(await self._conceptos.versiones_cpu(concepto_id))
        nueva, retiradas = publicar_version(versiones, PrecioUnitario(total=Dinero(precio.total.monto), destajo=Dinero(precio.destajo.monto)))
        cpu_id = await self._conceptos.publicar_version_cpu(
            concepto_id, version=nueva.version, precio_unitario=nueva.precio.total.monto, precio_destajo=nueva.precio.destajo.monto,
            variante=None, retirar=list(retiradas),
        )
        if adjuntas:
            # La versión nueva lleva su propia copia de la composición: la anterior queda como estaba, en el histórico.
            copias = [_fila_copiada(r) for r in adjuntas] + [_fila_nueva(c, orden + i) for i, c in enumerate(a_agregar)]
            await self._conceptos.agregar_explosion(concepto_id, cpu_id=cpu_id, filas=copias)


def _pu(detalle: dict[str, Any]) -> dict[str, Any]:
    return {"pu_antes": detalle["pu_antes"], "pu_despues": detalle["pu_despues"]}

