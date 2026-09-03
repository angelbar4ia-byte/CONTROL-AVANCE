"""Caso de uso: insumos programados (§7.3, §7.5, §11.2).

Carga lo que el dominio necesita —actividades en alcance, explosión de sus
conceptos, catálogo de insumos, periodos— y deja que
`domain.insumos.programado` haga el cruce. Ninguna regla vive aquí, solo la
secuencia; es la misma forma que Rendimientos (Fase 13).

**Solo lee.** No abre unidad de trabajo, no versiona y no persiste: la tabla se
deriva cada vez que se consulta. Guardarla obligaría a invalidarla en cada
cambio del cronograma, que es todos los días.

## Dos fuentes, un mismo dominio

* **Cronograma real** — `actividad` con la ventana que le dio el CPM. Es la
  respuesta para una obra que ya existe.
* **Simulación por prototipo** — el presupuesto vigente del prototipo × N
  casas, colocado sobre el programa base. Contesta *"¿qué necesito para
  cuarenta ZAFIRO?"* antes de generar una sola obra, que es cuando se cotiza
  una manzana. Los periodos van rotulados *Semana 1, 2…* y no con semanas del
  año: un programa base es una plantilla sin fechas propias (§7.5) y ponerle
  fechas sería inventarlas.

El dominio no sabe de cuál viene: las dos producen `ActividadConVentana`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from obractrl.application.casos_uso.calcular_cpu import componentes_por_clave
from obractrl.domain.catalogos.apu import ErrorDeAPU, ExplosionCalculada, explotar
from obractrl.domain.insumos.programado import (
    ActividadConVentana,
    InsumoDelCatalogo,
    MatrizDeInsumos,
    Periodo,
    insumos_programados,
)
from obractrl.domain.programacion.calendario import CalendarioLaboral
from obractrl.domain.programacion.cpm import (
    Dependencia,
    NodoCPM,
    Tramo,
    calcular_cpm,
)
from obractrl.domain.shared.diccionario import TipoSemana

__all__ = [
    "CalendarioSinGenerar",
    "ComandoInsumosProgramados",
    "ConsultarInsumosProgramados",
    "Granularidad",
    "InsumosProgramados",
    "PrototipoSinPrograma",
    "a_actividad",
]

Granularidad = str
"""`semana` o `mes`. Es una etiqueta de presentación, no un invariante del
§4: quién agrupa cómo no cambia ninguna regla del negocio."""

SEMANA = "semana"
MES = "mes"

_CERO = Decimal(0)
_DIAS_POR_SEMANA = 7


class CalendarioSinGenerar(LookupError):
    """El rango pedido cae en años sin calendario generado (§3.1).

    Es un 404 y no un 500: la organización todavía no corrió
    `app.generar_calendario()` para esos años, y el mensaje dice justo eso.
    """


class PrototipoSinPrograma(LookupError):
    """El prototipo no tiene programa base vigente o no tiene presupuesto.

    Sin uno de los dos no hay nada que simular: el programa da las ventanas y
    el presupuesto las cantidades.
    """


@dataclass(frozen=True, slots=True)
class InsumosProgramados:
    """Lo que el programa pide, y lo que el almacén ya entregó.

    El `surtido` viaja aparte de la matriz y no dentro: la matriz es del
    dominio, que no sabe que existe un almacén (§11.1). Juntarlos es del borde.
    """

    matriz: MatrizDeInsumos
    surtido: dict[str, Decimal]


@dataclass(frozen=True, slots=True)
class ComandoInsumosProgramados:
    """Lo que la consulta pide. Todo opcional salvo el rango de tiempo.

    `obra_id`, `residente_id` y `supervisor_id` **enfocan**; el alcance lo
    impone RLS (§12.4). Sin ninguno, la consulta cubre todas las obras que el
    rol alcance.

    `con_importe` lo decide el borde por rol: cantidades para los cuatro,
    dinero solo para Control y Super intendente.
    """

    desde: date
    hasta: date
    granularidad: Granularidad = SEMANA
    obra_id: UUID | None = None
    residente_id: UUID | None = None
    supervisor_id: UUID | None = None
    prototipo_id: UUID | None = None
    n_casas: int = 1
    tipos: frozenset[str] | None = None
    dias_anticipacion: int = 0
    con_importe: bool = True
    tipo_semana: TipoSemana = TipoSemana.ORDINARIA


class ConsultarInsumosProgramados:
    """`GET /insumos-programados` (§11.2)."""

    def __init__(
        self,
        *,
        actividades,
        conceptos,
        insumos,
        unidades,
        calendario,
        obras,
        presupuestos,
        materiales,
        nodos,
        ruta=None,
    ) -> None:
        self._actividades = actividades
        self._conceptos = conceptos
        self._insumos = insumos
        self._unidades = unidades
        self._calendario = calendario
        self._obras = obras
        self._presupuestos = presupuestos
        self._materiales = materiales
        self._nodos = nodos
        self._ruta = ruta

    async def ejecutar(
        self, cmd: ComandoInsumosProgramados
    ) -> InsumosProgramados:
        if cmd.prototipo_id is not None:
            filas, actividades = await self._simular(cmd)
        else:
            filas = await self._actividades.actividades_para_insumos(
                obra_id=cmd.obra_id,
                residente_id=cmd.residente_id,
                supervisor_id=cmd.supervisor_id,
                desde=cmd.desde,
                hasta=cmd.hasta,
            )
            actividades = [a_actividad(fila) for fila in filas]
            # Las fechas del CPM **no se persisten**: `guardar_resultado_cpm`
            # solo guarda criticidad, holgura y desfase, y lo dice —
            # `calcular_cpm` es puro y barato, así que se recalcula bajo
            # demanda para no tener dos significados en `fecha_termino`.
            # Consecuencia para este módulo: sin recalcular aquí, toda obra
            # cuyo residente no haya capturado fechas a mano saldría entera en
            # `sin_programar`. Se pide la ruta y se usa su ventana.
            actividades = await self.con_ventana_del_cpm(cmd.obra_id, actividades)

        periodos = await self.periodos(cmd)
        catalogo = await self.catalogo()
        explosiones = await self.explosiones(filas)

        matriz = insumos_programados(
            actividades=actividades,
            explosiones=explosiones,
            catalogo=catalogo,
            periodos=periodos,
            tipos=cmd.tipos,
            dias_anticipacion=cmd.dias_anticipacion,
            con_importe=cmd.con_importe,
        )
        return InsumosProgramados(matriz=matriz, surtido=await self._surtido(cmd, filas))

    async def _surtido(
        self, cmd: ComandoInsumosProgramados, filas: Sequence[dict]
    ) -> dict[str, Decimal]:
        """Lo que ya salió del almacén, por insumo.

        Solo tiene sentido contra obras reales: una simulación por prototipo no
        tiene almacén del que haya salido nada.
        """
        if cmd.prototipo_id is not None:
            return {}
        obras = {fila["obra_id"] for fila in filas if fila.get("obra_id")}
        return await self._materiales.surtido_por_insumo(obra_ids=sorted(obras))

    # --- Carga ------------------------------------------------------------

    async def con_ventana_del_cpm(
        self, obra_id: UUID | None, actividades: list[ActividadConVentana]
    ) -> list[ActividadConVentana]:
        """Le pone a cada actividad la ventana que el CPM calcula ahora.

        Sin obra —una consulta por residente o por supervisor, que barre
        varias— no se recalcula: la ruta se pide obra por obra y hacerlo aquí
        multiplicaría el trabajo por el número de obras del alcance. En ese caso
        manda lo que la actividad tenga capturado, y lo que no, sale en
        `sin_programar`.

        Una fecha **capturada** gana sobre la calculada: si alguien la fijó a
        mano es una decisión, y el motor no la debe pisar (§7.6).
        """
        if obra_id is None or self._ruta is None:
            return actividades

        ruta = await self._ruta.ejecutar(obra_id)
        ventana = {
            str(a.actividad_id): (a.inicio_temprano, a.fin_temprano)
            for a in ruta.actividades
        }

        salida: list[ActividadConVentana] = []
        for actividad in actividades:
            calculada = ventana.get(actividad.actividad_id)
            if calculada is None:
                salida.append(actividad)
                continue
            inicio, fin = calculada
            salida.append(
                replace(
                    actividad,
                    inicio=actividad.inicio or inicio,
                    fin=actividad.fin or fin,
                )
            )
        return salida

    async def catalogo(self) -> dict[str, InsumoDelCatalogo]:
        """El catálogo entero, indexado por clave.

        Público porque la planeación por obra carga exactamente lo mismo
        (`consultar_planeacion`): dos cargadores del mismo dato acabarían
        diciendo cosas distintas del mismo programa.

        Se trae completo y no insumo por insumo: el dominio explota por clave
        (§3.3) y necesita poder resolver cualquiera que aparezca en el árbol,
        que es justo lo que no se sabe antes de explotar. Son ~780 filas.
        """
        filas = await self._insumos.listar()
        # La clave de la unidad no viene con el insumo (`_COLUMNAS` trae
        # `unidad_id`), y son decenas contra cientos de insumos: se trae el
        # catálogo de unidades entero y se cruza aquí en vez de pedir un join
        # que solo esta consulta necesitaría.
        unidades = {
            str(u["id"]): str(u["clave"]) for u in await self._unidades.listar()
        }
        return {
            str(fila["clave"]): InsumoDelCatalogo(
                insumo_id=str(fila["id"]),
                clave=str(fila["clave"]),
                descripcion=str(fila["descripcion"]),
                unidad=unidades.get(str(fila.get("unidad_id"))),
                tipo=str(fila["tipo"]),
                costo=_decimal(
                    fila.get("costo_base_actualizado") or fila.get("costo_base")
                ),
                dias_entrega=fila.get("dias_entrega"),
            )
            for fila in filas
        }

    async def explosiones(
        self, filas: Sequence[dict]
    ) -> dict[str, ExplosionCalculada]:
        """Explota de una sola pasada los conceptos que aparecen.

        Una consulta para **todas** las raíces (`composicion_recursiva_de`) y
        luego N llamadas al dominio sobre el mismo mapa: los auxiliares que
        varios conceptos comparten se leen una vez, no una por padre. Hacerlo
        concepto por concepto serían dos consultas por cada uno, cada una con
        su propio recorrido recursivo.

        Un concepto cuyo APU tiene un ciclo (`CicloEnExplosion`, §7.3) tumbaría
        la consulta entera; se omite ese concepto y los demás se calculan. La
        pantalla enseña lo que sí se pudo, que es más útil que un error sobre
        toda la obra por un renglón mal cargado del catálogo.
        """
        ids = {
            fila["concepto_id"] for fila in filas if fila.get("concepto_id")
        }
        if not ids:
            return {}

        crudas = await self._conceptos.composicion_recursiva_de(sorted(ids))
        composiciones, costos = componentes_por_clave(crudas)

        claves = {
            str(fila["concepto_clave"])
            for fila in filas
            if fila.get("concepto_clave")
        }
        salida: dict[str, ExplosionCalculada] = {}
        for clave in claves:
            try:
                salida[clave] = explotar(
                    clave, composiciones=composiciones, costos_insumo=costos
                )
            except ErrorDeAPU:
                continue
        return salida

    async def _simular(
        self, cmd: ComandoInsumosProgramados
    ) -> tuple[list[dict], list[ActividadConVentana]]:
        """"¿Qué necesito para N casas de este prototipo?"

        Antes de generar una sola obra ya se puede contestar, y es cuando se
        cotiza una manzana. Se juntan las dos mitades que el prototipo sí
        tiene: el **programa base** vigente da las ventanas y el **presupuesto**
        vigente las cantidades, multiplicadas por el número de casas.

        El arranque es `cmd.desde`, el primer día del rango consultado: un
        programa base no tiene fechas propias (§7.5), así que la simulación
        contesta "si empezara ese día". El CPM las coloca con el mismo motor
        que el cronograma real, con el calendario laboral de la plantilla.
        """
        items = await self._obras.items_programa_base(cmd.prototipo_id)
        presupuesto = await self._presupuestos.vigente_de_prototipo(cmd.prototipo_id)
        if not items or presupuesto is None:
            raise PrototipoSinPrograma(
                "El prototipo necesita programa base vigente y presupuesto "
                "vigente para simularse: el primero da las ventanas y el "
                "segundo las cantidades (§7.5, §10.8)."
            )

        partidas = await self._presupuestos.partidas(presupuesto["id"])
        nodos = await self._nodos.por_prototipo(cmd.prototipo_id)
        programados = {
            str(item["prototipo_nodo_id"])
            for item in items
            if item.get("prototipo_nodo_id")
        }
        # El programa base casi nunca se captura al mismo nivel que el
        # presupuesto: la plantilla dice "PLANTA BAJA dura 60 días" y las
        # cantidades cuelgan de los conceptos que hay debajo. Cada partida se
        # asocia al **ancestro programado más cercano**, y hereda su ventana.
        # Es el mismo reparto en paralelo que el editor del programa base ya
        # aplica hacia abajo: las ramas de un nivel corren simultáneas.
        techo = _ancestro_programado(nodos, programados)

        por_nodo: dict[str, dict] = {}
        for partida in partidas:
            nodo = partida.get("prototipo_nodo_id")
            if not nodo or not partida.get("concepto_clave"):
                continue
            ventana = techo.get(str(nodo))
            if ventana is None:
                continue
            clave = (ventana, str(partida["concepto_clave"]))
            acumulado = por_nodo.setdefault(
                f"{ventana}|{partida['concepto_clave']}",
                {
                    "ventana": clave[0],
                    "concepto_clave": partida["concepto_clave"],
                    "concepto_id": partida["concepto_id"],
                    "descripcion": partida.get("concepto_descripcion") or "",
                    "cantidad": _CERO,
                },
            )
            acumulado["cantidad"] += _decimal(partida.get("cantidad"))

        dias = await self._obras.calendario_programa_base(cmd.prototipo_id)
        calendario = CalendarioLaboral.de(dias)
        nodos = [
            NodoCPM(
                ref=str(item["prototipo_nodo_id"]),
                duracion_dias=float(item["duracion_dias"]),
                dependencias=tuple(
                    Dependencia.desde_jsonb(d) for d in (item["dependencias"] or [])
                ),
                tramos=tuple(Tramo.desde_jsonb(t) for t in (item["tramos"] or [])),
                inicio_dias=(
                    None
                    if item.get("inicio_dias") is None
                    else float(item["inicio_dias"])
                ),
            )
            for item in items
            if item.get("prototipo_nodo_id")
        ]
        resultado = calcular_cpm(
            nodos, cmd.desde, fecha_corte=cmd.desde, calendario=calendario
        )

        filas: list[dict] = []
        actividades: list[ActividadConVentana] = []
        for clave, partida in por_nodo.items():
            calculo = resultado.get(partida["ventana"])
            if calculo is None:
                continue
            filas.append(
                {
                    "concepto_id": partida["concepto_id"],
                    "concepto_clave": partida["concepto_clave"],
                }
            )
            actividades.append(
                ActividadConVentana(
                    actividad_id=clave,
                    obra_id=str(cmd.prototipo_id),
                    concepto_clave=str(partida["concepto_clave"]),
                    descripcion=str(partida["descripcion"]),
                    cantidad=partida["cantidad"] * cmd.n_casas,
                    inicio=calculo.inicio_temprano,
                    fin=calculo.fin_temprano,
                    # Los tramos ya los consumió el CPM al colocar la ventana;
                    # volver a aplicarlos aquí los contaría dos veces.
                    tramos=(),
                )
            )
        return filas, actividades

    async def periodos(self, cmd: ComandoInsumosProgramados) -> list[Periodo]:
        semanas = await self._calendario.semanas_entre(
            cmd.desde, cmd.hasta, cmd.tipo_semana
        )
        if not semanas:
            raise CalendarioSinGenerar(
                f"No hay calendario de tipo {cmd.tipo_semana.value!r} entre "
                f"{cmd.desde.isoformat()} y {cmd.hasta.isoformat()}. Genera el "
                f"calendario de esos años antes de consultar (§3.1)."
            )
        if cmd.granularidad == MES:
            return _por_mes(semanas)
        return [_periodo_de_semana(fila) for fila in semanas]


# --- Traductores ---------------------------------------------------------


def a_actividad(fila: dict) -> ActividadConVentana:
    """Fila del repo → lo que el dominio consume.

    La cantidad es `cant_programada` —lo que se mandó hacer—, con `cant_base`
    de respaldo para las obras generadas antes de la migración 0044, que
    nacieron con la programada en cero.
    """
    programada = _decimal(fila.get("cant_programada"))
    return ActividadConVentana(
        actividad_id=str(fila["id"]),
        obra_id=str(fila["obra_id"]),
        concepto_clave=_texto(fila.get("concepto_clave")),
        descripcion=str(fila.get("descripcion") or ""),
        cantidad=programada if programada != 0 else _decimal(fila.get("cant_base")),
        inicio=fila.get("fecha_inicio"),
        fin=fila.get("fecha_termino"),
        tramos=tuple(Tramo.desde_jsonb(t) for t in (fila.get("tramos") or [])),
        frente_id=_texto(fila.get("frente_id")),
        especialidad_id=_texto(fila.get("especialidad_id")),
    )


def _ancestro_programado(
    nodos: Sequence[dict], programados: set[str]
) -> dict[str, str]:
    """Para cada nodo, el ancestro más cercano que sí tiene programa base.

    Incluye al nodo mismo si él está programado. Un nodo que no cuelga de
    ninguno programado no aparece: no hay ventana en la que colocarlo, y
    ponerle una inventada sería peor que dejarlo fuera.

    El tope de saltos es la red contra un `parent_id` en ciclo, que sin ella
    colgaría la consulta — mismo criterio que `etapaNodoDe` en el editor.
    """
    padre = {
        str(n["id"]): (str(n["parent_id"]) if n.get("parent_id") else None)
        for n in nodos
    }
    salida: dict[str, str] = {}
    for nodo_id in padre:
        actual: str | None = nodo_id
        for _ in range(32):
            if actual is None:
                break
            if actual in programados:
                salida[nodo_id] = actual
                break
            actual = padre.get(actual)
    return salida


def _periodo_de_semana(fila: dict) -> Periodo:
    """Una semana del calendario de la organización.

    `fecha_fin` es inclusiva en la tabla y `Periodo.hasta` es exclusiva, de ahí
    el día que se suma: sin él, dos semanas contiguas se pelearían el domingo.
    """
    return Periodo(
        clave=f"{fila['anio']}-S{int(fila['semana']):02d}",
        desde=fila["fecha_inicio"],
        hasta=fila["fecha_fin"] + timedelta(days=1),
        etiqueta=f"S{int(fila['semana'])}",
    )


def _por_mes(semanas: Sequence[dict]) -> list[Periodo]:
    """Agrupa las semanas en meses **por la columna `mes` del calendario**.

    No por `fecha.month`: una semana a caballo entre dos meses cae en el que la
    organización decidió al generar su calendario (`app.generar_calendario`), y
    derivarlo de la fecha la pondría en uno u otro según de qué lado se mire —
    y la suma de los meses dejaría de dar el total.
    """
    grupos: dict[tuple[int, int], list[dict]] = {}
    for fila in semanas:
        grupos.setdefault((int(fila["anio"]), int(fila["mes"])), []).append(fila)

    return [
        Periodo(
            clave=f"{anio}-{mes:02d}",
            desde=min(f["fecha_inicio"] for f in filas),
            hasta=max(f["fecha_fin"] for f in filas) + timedelta(days=1),
            etiqueta=f"{_MESES[mes - 1]} {str(anio)[2:]}",
        )
        for (anio, mes), filas in sorted(grupos.items())
    ]


_MESES = (
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
)


def _decimal(valor: object) -> Decimal:
    if valor is None or valor == "":
        return _CERO
    return Decimal(str(valor))


def _texto(valor: object) -> str | None:
    return None if valor is None else str(valor)
