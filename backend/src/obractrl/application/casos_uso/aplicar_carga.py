"""Aplicadores: bajar una lectura validada al catálogo (§9.2 paso "Commit").

Spec §9.2 (pipeline) · §10.2 (los tres modos) · §10.3 (bandeja) · §10.5
(valuación y motivos) · §10.6 (qué trae cada archivo) · §10.8 (versión y
snapshot) · §12.11 (la aplicación orquesta el dominio por puertos).

Un **aplicador** por archivo del §10.6. Todos hacen lo mismo en el mismo
orden y por eso comparten forma:

1. Traen el conjunto **vigente** por sus puertos (§10.8 compara contra la
   versión vigente, así que cargarlo entero no es un lujo: es el diff).
2. Homologan lo que el archivo trae contra los catálogos (§10.3). Lo que no
   cruza **no se inventa**: cae en la bandeja.
3. Calculan el diff con `domain.cargadores.versionado` según el modo (§10.2).
4. Escriben, dejando en el `snapshot` el antes/después de cada registro para
   que el lote se pueda revertir como unidad (§10.8).

En `dry_run` se hace todo menos el paso 4: el resumen y la bandeja salen
idénticos, que es lo que hace útil a la vista previa (§9.3).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid4

from obractrl.application.puertos.cargadores import RepositorioCargas
from obractrl.application.puertos.repositorios import (
    RepositorioConceptos,
    RepositorioContratistas,
    RepositorioCuadrillas,
    RepositorioFamilias,
    RepositorioFrentes,
    RepositorioInsumos,
    RepositorioMateriales,
    RepositorioNivelesEtapas,
    RepositorioObras,
    RepositorioPresupuestos,
    RepositorioPrototipoNodo,
    RepositorioPrototipos,
    RepositorioProyectos,
    RepositorioUnidades,
)
from obractrl.domain.cargadores.almacen import FilaMovimiento, importe_con_iva
from obractrl.domain.cargadores.claves_automaticas import generar_clave_automatica
from obractrl.domain.cargadores.conceptos_base import FilaConceptoBase
from obractrl.domain.cargadores.contratistas import FilaContratista
from obractrl.domain.cargadores.cpu import ComponenteCargado, ConceptoCargado
from obractrl.domain.cargadores.cuadrillas import CuadrillaCargada
from obractrl.domain.cargadores.etapas_constructivas import FilaEtapaConstructiva
from obractrl.domain.cargadores.familias import FilaFamilia
from obractrl.domain.cargadores.homologacion import Homologador
from obractrl.domain.cargadores.mano_de_obra import FilaManoObra
from obractrl.domain.cargadores.materiales import FilaMaterial
from obractrl.domain.cargadores.niveles import FilaNivel
from obractrl.domain.cargadores.presupuesto import (
    ArbolPrototipoCargado,
    NodoLeido,
    TipoNodoPresupuesto,
    es_etapa_con_componentes_directos,
)
from obractrl.domain.cargadores.prototipos import FilaPrototipo
from obractrl.domain.cargadores.reporte import (
    ErrorDeFila,
    LecturaCarga,
    PendientePropuesto,
    TipoPendiente,
)
from obractrl.domain.cargadores.unidades import FilaUnidad
from obractrl.domain.cargadores.versionado import Cambio, Diff, diferenciar
from obractrl.domain.catalogos.apu import (
    Componente,
    ErrorDeAPU,
    VersionCPU,
    calcular_cpu,
    publicar_version,
)
from obractrl.domain.catalogos.reglas import resolver_iva
from obractrl.domain.materiales.reglas import ErrorDeMaterial, validar_signo_salida
from obractrl.domain.proyectos.reglas import ErrorDeProyecto, Prototipo
from obractrl.domain.shared.diccionario import (
    CategoriaExplosion,
    ModoCarga,
    TipoConcepto,
    TipoHijoExplosion,
    TipoInsumo,
)
from obractrl.domain.shared.normalizacion import normalizar, similar
from obractrl.domain.shared.valores import Dinero, PrecioUnitario

__all__ = [
    "Aplicacion",
    "AplicadorAlmacen",
    "AplicadorCPU",
    "AplicadorConceptosBase",
    "AplicadorCuadrillas",
    "AplicadorDeCarga",
    "AplicadorDePrototipos",
    "AplicadorEtapasConstructivas",
    "AplicadorManoObra",
    "AplicadorMateriales",
    "AplicadorNiveles",
    "AplicadorPresupuesto",
    "AplicadorPrototipos",
]

_ESTATUS_BAJA = "inactivo"
"""Baja **lógica** para el modo Reemplazar (§10.2).

Un `delete` real no es opción: `explosion` y `salida_almacen` referencian
`insumo`, y borrar el catálogo se llevaría por delante APUs y movimientos
históricos que la carga no está sustituyendo. "Sustituye todo el conjunto"
se cumple sacando de circulación lo que el archivo ya no trae.
"""


@dataclass(frozen=True, slots=True)
class Aplicacion:
    """Lo que un aplicador reporta al caso de uso."""

    diff: Diff
    operaciones: tuple[dict[str, Any], ...] = ()
    """Antes/después por registro tocado, en orden de ejecución (§10.8)."""

    pendientes: tuple[PendientePropuesto, ...] = ()
    errores: tuple[ErrorDeFila, ...] = ()
    insertados: int = 0
    actualizados: int = 0
    omitidos: int = 0
    detalle: dict[str, Any] = field(default_factory=dict)
    """Datos propios del cargador para el resumen (§9.4)."""


@runtime_checkable
class AplicadorDeCarga(Protocol):
    """Puerto de escritura de una carga. Uno por archivo del §10.6."""

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion: ...


def _operacion(
    tabla: str,
    registro_id: UUID | str,
    operacion: str,
    *,
    antes: dict[str, Any] | None = None,
    despues: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tabla": tabla,
        "registro_id": str(registro_id),
        "operacion": operacion,
        "antes": antes,
        "despues": despues,
    }


def _pendiente_de_mapeo(
    entidad: str, valor: str, fila: int, *, critico: bool
) -> PendientePropuesto:
    return PendientePropuesto(
        tipo=TipoPendiente.MAPEO_NO_RECONOCIDO,
        entidad=entidad,
        valor_origen=valor,
        propuesta={"accion": f"Homologar {entidad} o darlo de alta en el catálogo."},
        critico=critico,
        origen_ref=f"fila {fila}",
    )


async def _resolver_o_dar_de_alta(
    valor: str,
    *,
    homologador: Homologador,
    id_por_clave: dict[str, UUID],
    creadas: dict[str, UUID | None],
    crear: Callable[[dict[str, Any]], Awaitable[UUID]],
    dry_run: bool,
) -> UUID | None:
    """Unidad o familia: si el archivo trae una que no cruza contra el
    catálogo, se da de alta con ese mismo texto como clave y nombre, en vez
    de solo dejar un pendiente sin que nadie la cree (§8.7).

    Es la excepción a "lo que no cruza no se inventa" (§10.3) porque el
    riesgo es distinto al de un concepto o un precio: una unidad o familia
    de más se corrige después con un alta/homologación, sin que eso
    signifique que alguien perdió datos o que un precio salió mal. Bloquear
    la carga entera por una unidad nueva —el caso normal, no la excepción,
    en un catálogo que recién empieza a cargarse— es peor que crearla.

    Dentro de la misma carga la misma clave nueva se da de alta una sola
    vez (`creadas` la recuerda tal cual vino en el archivo); en `dry_run`
    no se escribe nada, pero cuenta igual para que la vista previa no
    prometa un alta que después no aplica igual (§9.3).
    """
    clave = homologador.resolver(valor)
    if clave is not None:
        return id_por_clave.get(clave)
    if valor not in creadas:
        creadas[valor] = None if dry_run else await crear({"clave": valor, "nombre": valor})
    return creadas[valor]


async def _resolver_o_dar_de_alta_con_alerta(
    valor: str,
    descripcion: str | None,
    *,
    homologador: Homologador,
    id_por_clave: dict[str, UUID],
    filas_por_clave: dict[str, dict[str, Any]],
    creadas: dict[str, UUID | None],
    crear: Callable[[dict[str, Any]], Awaitable[UUID]],
    entidad: str,
    fila: int,
    pendientes: list[PendientePropuesto],
    dry_run: bool,
    campo_descripcion: str = "descripcion",
) -> UUID | None:
    """Como `_resolver_o_dar_de_alta`, pero vigilando la descripción cuando
    SÍ cruza por clave (§8.7: homologación con alerta, no bloqueo).

    Es para cuando CPU o el árbol referencian **de pasada** un catálogo base
    que no es el suyo (un insumo, en concreto): la clave sigue mandando
    (§3.3) y el cruce se resuelve igual que siempre. Lo único que agrega es
    una alerta —no crítica, nunca bloquea la carga— cuando la descripción
    que trae esta fila no se parece a la que el catálogo ya tiene para esa
    clave, para que alguien la revise después. Sin descripción que comparar
    (``descripcion`` vacío, o la clave no cruzó y se va a dar de alta), se
    comporta exactamente como la versión simple.
    """
    clave = homologador.resolver(valor)
    if clave is not None:
        if descripcion:
            descripcion_catalogo = filas_por_clave.get(clave, {}).get(campo_descripcion)
            if descripcion_catalogo and not similar(descripcion, str(descripcion_catalogo)):
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.DESCRIPCION_DISTINTA,
                        entidad=entidad,
                        valor_origen=valor,
                        propuesta={
                            "clave": clave,
                            "descripcion_archivo": descripcion,
                            "descripcion_catalogo": str(descripcion_catalogo),
                        },
                        critico=False,
                        origen_ref=f"fila {fila}",
                    )
                )
        return id_por_clave.get(clave)
    if valor not in creadas:
        creadas[valor] = None if dry_run else await crear({"clave": valor, "nombre": valor})
    return creadas[valor]


# --- Materiales (§10.6 `CABECERAS_MATERIALES.xlsx`) -----------------------

_CAMPOS_MATERIAL = (
    "descripcion",
    "unidad_id",
    "familia_id",
    "costo_base",
    "costo_base_actualizado",
    "costo_promedio_almacen",
    "costo_ultimo",
    "iva_aplica",
)
"""Campos que este cargador gobierna. El diff solo mira estos: si el archivo
no habla de un campo, cambiarlo no sería carga sino invención."""

_CAMPOS_RESTAURABLES_INSUMO = (
    *_CAMPOS_MATERIAL,
    "origen",
    "factor_conversion",
    "estatus",
)
"""Lo que el snapshot guarda como ``antes``: debe coincidir con lo que la
reversa sabe restaurar (`adapters/repos/cargas_sql._RESTAURAR`)."""


class AplicadorMateriales:
    """Catálogo de materiales (§10.6, §10.1).

    Un material es un `Insumo` con ``tipo='material'`` (§7.3): esto alimenta
    el catálogo de insumos, no una tabla aparte.
    """

    def __init__(
        self,
        *,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        familias: RepositorioFamilias,
        cargas: RepositorioCargas,
    ) -> None:
        self._insumos = insumos
        self._unidades = unidades
        self._familias = familias
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._insumos.listar(
            tipo=str(TipoInsumo.MATERIAL), solo_activos=False
        )
        por_clave = {str(fila["clave"]): fila for fila in vigentes_filas}

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}
        unidades_por_clave = {str(f["clave"]): f for f in unidades_filas}

        familias_filas = await self._familias.listar(
            aplica_a="material", solo_activos=False
        )
        familias = Homologador.desde(
            familias_filas, mapeos=await self._cargas.mapeos("familia")
        )
        id_familia = {str(f["clave"]): f["id"] for f in familias_filas}

        pendientes: list[PendientePropuesto] = []
        entrantes: dict[str, dict[str, Any]] = {}
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevas_familias: dict[str, UUID | None] = {}

        for registro in lectura.registros:
            material: FilaMaterial = registro  # type: ignore[assignment]
            actual = por_clave.get(material.llave, {})

            unidad_id = actual.get("unidad_id")
            if material.clave_unidad:

                async def _dar_de_alta_unidad(
                    _datos: dict[str, Any],
                    *,
                    _clave: str = material.clave_unidad,
                    _nombre: str | None = material.unidad,
                ) -> UUID:
                    return await self._unidades.crear_o_existente(
                        {"clave": _clave, "nombre": _nombre or _clave}
                    )

                unidad_id = await _resolver_o_dar_de_alta_con_alerta(
                    material.clave_unidad,
                    material.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    filas_por_clave=unidades_por_clave,
                    creadas=nuevas_unidades,
                    crear=_dar_de_alta_unidad,
                    entidad="unidad",
                    fila=material.fila,
                    pendientes=pendientes,
                    dry_run=dry_run,
                    campo_descripcion="nombre",
                )
            elif material.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    material.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear_o_existente,
                    dry_run=dry_run,
                )

            familia_id = actual.get("familia_id")
            if material.familia:
                familia_id = await _resolver_o_dar_de_alta(
                    material.familia,
                    homologador=familias,
                    id_por_clave=id_familia,
                    creadas=nuevas_familias,
                    crear=self._familias.crear_o_existente,
                    dry_run=dry_run,
                )

            # Regla del cargador: **lo que el archivo no trae, no se toca**.
            # Un archivo sin columna de costo o sin casilla de IVA actualiza
            # descripciones sin vaciar el resto del catálogo — que es lo que
            # el modo Actualizar promete (§10.2) y lo que el §3.4 exige del
            # catálogo como fuente de verdad.
            entrantes[material.llave] = {
                "descripcion": material.descripcion,
                "unidad_id": unidad_id,
                "familia_id": familia_id,
                "costo_base": _o_vigente(material.costo_base, actual, "costo_base"),
                # §10.5: "costo_base_actualizado = el costo último más
                # reciente (costo vigente)".
                "costo_base_actualizado": _o_vigente(
                    material.costo_ultimo, actual, "costo_base_actualizado"
                ),
                "costo_promedio_almacen": _o_vigente(
                    material.costo_promedio, actual, "costo_promedio_almacen"
                ),
                "costo_ultimo": _o_vigente(material.costo_ultimo, actual, "costo_ultimo"),
                "iva_aplica": _o_vigente(material.iva, actual, "iva_aplica"),
            }

        vigentes = {
            clave: {campo: fila.get(campo) for campo in _CAMPOS_MATERIAL}
            for clave, fila in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._insumos.crear(
                    {
                        "tipo": str(TipoInsumo.MATERIAL),
                        "clave": alta.clave,
                        "descripcion": alta.despues["descripcion"],
                        "unidad_id": alta.despues["unidad_id"],
                        "familia_id": alta.despues["familia_id"],
                        "costo_base": alta.despues["costo_base"],
                        "iva_aplica": alta.despues["iva_aplica"],
                    }
                )
                extras = {
                    campo: alta.despues[campo]
                    for campo in (
                        "costo_base_actualizado",
                        "costo_promedio_almacen",
                        "costo_ultimo",
                    )
                    if alta.despues.get(campo) is not None
                }
                if extras:
                    await self._insumos.actualizar(nuevo_id, extras)
                operaciones.append(
                    _operacion("insumo", nuevo_id, "insert", despues=dict(alta.despues))
                )

            for cambio in diff.cambios:
                fila = por_clave[cambio.clave]
                # Se escriben **todos** los campos gestionados, incluidos los
                # que quedaron en `None`: a estas alturas `None` ya no
                # significa "el archivo no lo trae" —eso se resolvió al armar
                # `entrantes`— sino "así queda".
                await self._insumos.actualizar(fila["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "insumo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_INSUMO),
                        despues=dict(cambio.despues),
                    )
                )

            for baja in diff.bajas:
                fila = por_clave[baja.clave]
                await self._insumos.actualizar(fila["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "insumo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_INSUMO),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={
                "unidades_creadas": len(nuevas_unidades),
                "familias_creadas": len(nuevas_familias),
            },
        )


@dataclass(frozen=True, slots=True)
class _Resolucion:
    """Lo que se pudo resolver de un catálogo, y cómo."""

    id: UUID | None
    aproximada: str | None = None
    """El nombre del catálogo con el que empató, cuando no fue exacto.

    Se guarda para reportarlo: una coincidencia aproximada es una decisión que
    alguien tiene que poder revisar, y callarla la volvería invisible.
    """


class _CatalogoPorNombre:
    """Índice de un catálogo para buscar por clave **o** por nombre.

    Los archivos reales de la constructora no traen la clave del catálogo: la
    etapa dice `OBRA` y el contratista dice `INSTALACIONES`, que son los
    *nombres*. Exigir la clave obligaría a traducir a mano cincuenta filas cada
    vez que se sube el archivo.

    Dos pasos siempre, y un tercero solo cuando se pide:

    1. Clave exacta (§3.3: la clave manda cuando viene).
    2. Nombre normalizado — sin acentos, sin mayúsculas, sin dobles espacios.
    3. Parecido (`similar`, §8.6) **solo con `tolerante=True`**, y se reporta.

    La tolerancia es opt-in porque los dos usos son distintos y confundirlos
    corrompe el catálogo:

    * El archivo que **define** el catálogo se lee exacto. `similar` trata una
      subcadena como coincidencia, así que `CARPINTERIA OBRA` empataría con
      `CARPINTERIA` y las doce filas de la primera se irían a la segunda —
      borrando una distinción que el cliente sí hace.
    * El archivo que solo lo **referencia** puede ser tolerante. El catálogo de
      contratistas escribe `SUBCONTRATO` donde el de etapas escribe
      `SUBCONTRATOS`: es el mismo frente en singular y en plural, y no crear
      nada nuevo hace que el peor caso sea apuntar a la fila de al lado.

    Adivinar en silencio sería inaceptable en los dos casos, así que quien
    resuelve por parecido sale nombrado en el reporte de la carga.
    """

    def __init__(
        self, filas: list[dict[str, Any]], mapeos: Mapping[str, str] | None = None
    ) -> None:
        self._por_clave = {normalizar(f["clave"]): f["id"] for f in filas}
        self._por_nombre = {normalizar(f["nombre"]): f["id"] for f in filas}
        self._nombres = [(normalizar(f["nombre"]), str(f["nombre"]), f["id"]) for f in filas]
        # Homologaciones confirmadas por una persona (§10.3). Se aplican antes
        # que nada: si alguien ya dijo que `EQUIPAMIENTOS` es `EQUIPAMIENTO`,
        # la carga no lo vuelve a preguntar ni a crear.
        self._alias = {
            normalizar(alias): normalizar(canonica)
            for alias, canonica in (mapeos or {}).items()
        }

    def agregar(self, *, clave: str, nombre: str, id_: Any) -> None:
        """Registra lo que se acaba de crear, para que lo siguiente lo vea.

        Sin esto, `EQUIPAMIENTO` y `EQUIPAMIENTOS` en el mismo archivo crean dos
        filas: la segunda no encuentra a la primera porque el índice se leyó una
        vez al empezar. El archivo trae las dos formas del mismo oficio y el
        catálogo acabaría con las dos.
        """
        self._por_clave[normalizar(clave)] = id_
        self._por_nombre[normalizar(nombre)] = id_
        self._nombres.append((normalizar(nombre), nombre, id_))

    def resolver(self, referencia: object, *, tolerante: bool = False) -> _Resolucion:
        texto = normalizar(referencia)
        if not texto:
            return _Resolucion(id=None)
        texto = self._alias.get(texto, texto)
        exacto = self._por_clave.get(texto) or self._por_nombre.get(texto)
        if exacto is not None:
            return _Resolucion(id=exacto)
        if not tolerante:
            return _Resolucion(id=None)
        for normalizado, nombre, id_ in self._nombres:
            if similar(texto, normalizado):
                return _Resolucion(id=id_, aproximada=nombre)
        return _Resolucion(id=None)


def _clave_desde_nombre(nombre: str, tomadas: set[str]) -> str:
    """Una clave corta y estable para un catálogo que llega solo con nombres.

    Los archivos de la constructora traen `OBRA`, `CARPINTERIA OBRA`,
    `BARDA PERIMETRAL` — nombres, sin código. Hace falta uno porque la clave es
    la identidad con la que se vuelve a cargar el mismo archivo mañana (§3.3);
    sin ella, la segunda carga crearía todo otra vez.

    Tres intentos, en orden: las tres primeras letras, las iniciales de las
    palabras, y un consecutivo. Determinista: el mismo nombre da la misma clave
    en cualquier orden de carga, que es lo que hace la recarga idempotente.
    """
    limpio = "".join(c for c in normalizar(nombre).upper() if c.isalnum() or c == " ")
    palabras = [p for p in limpio.split() if p]
    if not palabras:
        return "X"

    candidatos = [palabras[0][:3]]
    if len(palabras) > 1:
        # `CARPINTERIA OBRA` → `CAO`, no `CO`: tres letras se leen de un vistazo
        # en una tabla y dos se confunden con una unidad.
        candidatos.append(palabras[0][:2] + palabras[1][:1])
        candidatos.append(palabras[0][:1] + palabras[1][:2])
        candidatos.append("".join(p[0] for p in palabras[:4]))
    for candidato in candidatos:
        if candidato and candidato not in tomadas:
            return candidato

    base = candidatos[0] or "X"
    numero = 2
    while f"{base}{numero}" in tomadas:
        numero += 1
    return f"{base}{numero}"


async def _mapear_clasificacion(
    *,
    por_referencia: dict[str, list[str]],
    catalogo,
    asignar,
    crear_faltantes: bool,
    dry_run: bool = False,
    mapeos: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Le pone a cada grupo de claves la clasificación que el archivo les da.

    Va aparte del diff de identidad a propósito: el diff decide qué se da de
    alta y qué cambió de nombre, y esto decide a qué frente u oficio pertenece
    cada uno. Mezclarlos haría que corregir una descripción y remapear un frente
    fueran el mismo cambio, y el reporte de la carga ya no diría cuál pasó.

    Una llamada por clasificación y no por fila: son cuatro frentes para
    cincuenta etapas, y quinientas idas a la base para el mismo dato.

    En `dry_run` resuelve igual pero no escribe: la previsualización tiene que
    poder decir qué frentes se crearían y cuántas etapas se moverían, que es
    justo lo que alguien quiere ver antes de aceptar la carga. Un preview que
    callara esta parte dejaría el cambio más grande sin revisar.
    """
    vigentes = await catalogo.listar(solo_activos=False)
    indice = _CatalogoPorNombre(vigentes, mapeos)
    tomadas = {str(f["clave"]).upper() for f in vigentes}

    asignadas = 0
    creadas: list[str] = []
    sin_resolver: list[str] = []
    aproximadas: list[str] = []

    for referencia, claves in sorted(por_referencia.items()):
        resuelta = indice.resolver(referencia)
        destino = resuelta.id
        if destino is None:
            if not crear_faltantes:
                sin_resolver.append(referencia)
                continue
            # El archivo del cliente es la autoridad sobre su propio
            # vocabulario: sembrar una lista a mano ya salió mal una vez.
            clave_nueva = _clave_desde_nombre(referencia, tomadas)
            tomadas.add(clave_nueva)
            creadas.append(f"{clave_nueva} · {referencia}")
            if dry_run:
                # Un id de mentira, nunca escrito: sirve para que la
                # previsualización vea lo que ella misma acaba de "crear" y no
                # cuente dos veces `EQUIPAMIENTO` y `EQUIPAMIENTOS`. Con `None`
                # el índice lo daría por no encontrado y el preview mentiría
                # sobre lo que la carga real haría.
                indice.agregar(clave=clave_nueva, nombre=referencia, id_=uuid4())
                asignadas += len(claves)
                continue
            destino = await catalogo.crear(
                {"clave": clave_nueva, "nombre": referencia, "orden": len(creadas)}
            )
            indice.agregar(clave=clave_nueva, nombre=referencia, id_=destino)
        elif resuelta.aproximada is not None:
            aproximadas.append(f"{referencia} → {resuelta.aproximada}")

        if dry_run:
            asignadas += len(claves)
            continue
        asignadas += await asignar(destino, claves)

    return {
        "asignadas": asignadas,
        "creadas": creadas,
        "sin_resolver": sorted(set(sin_resolver)),
        "resueltas_por_parecido": sorted(set(aproximadas)),
    }


async def _resolver_todas(
    referencias: Sequence[object],
    catalogo: _CatalogoPorNombre,
    sin_resolver: list[str],
    aproximadas: list[str],
    *,
    crear=None,
    creadas: list[str] | None = None,
    tomadas: set[str] | None = None,
) -> list[UUID]:
    """Resuelve una lista de referencias, apuntando lo que no salió limpio.

    Una que no exista **no** tumba la fila: el contratista entra igual y la
    referencia sale reportada. Perder el alta de quien está trabajando en la
    obra por un frente mal escrito sería desproporcionado.

    Con `crear`, lo que no existe se da de alta en vez de reportarse. Se usa
    para los **oficios** y no para los frentes, y la asimetría es a propósito:

    * Los frentes son cuatro y su autoridad es el catálogo de etapas. Uno que
      no resuelva aquí es casi siempre un error de dedo, y crearlo metería un
      quinto frente fantasma en la pantalla de planeación.
    * Los oficios los declara cada contratista sobre sí mismo. `LIMPIEZA` y
      `URBANIZACION` no aparecen en ningún concepto y aun así son reales: sin
      crearlos, veintinueve contratistas entrarían casi sin capacidades y el
      cruce que justifica capturarlas no se podría hacer.

    Lo creado se reporta en `creadas`, que es lo que vuelve revisable la
    decisión.
    """
    ids: list[UUID] = []
    for referencia in referencias:
        resuelta = catalogo.resolver(referencia, tolerante=True)
        if resuelta.id is None:
            if crear is None:
                sin_resolver.append(str(referencia))
                continue
            nombre = str(referencia)
            clave_nueva = _clave_desde_nombre(nombre, tomadas if tomadas is not None else set())
            if tomadas is not None:
                tomadas.add(clave_nueva)
            nuevo = await crear({"clave": clave_nueva, "nombre": nombre})
            catalogo.agregar(clave=clave_nueva, nombre=nombre, id_=nuevo)
            if creadas is not None:
                creadas.append(f"{clave_nueva} · {nombre}")
            ids.append(nuevo)
            continue
        if resuelta.aproximada is not None:
            aproximadas.append(f"{referencia} → {resuelta.aproximada}")
        ids.append(resuelta.id)
    return ids


def _recorte(fila: dict[str, Any], campos: tuple[str, ...]) -> dict[str, Any]:
    return {campo: fila.get(campo) for campo in campos}


def _o_vigente(valor: Any, actual: dict[str, Any], campo: str) -> Any:
    """``valor`` si el archivo lo trajo; si no, lo que ya está en el catálogo.

    Es la regla que separa "el archivo dice que vale cero" de "el archivo no
    habla de esto". Sin ella, cargar un `.xlsx` sin la columna de costo
    pondría en cero todo el catálogo (§3.4: el catálogo es la fuente de
    verdad; una carga lo actualiza, no lo vacía).
    """
    return actual.get(campo) if valor is None else valor


# --- Mano de obra / Destajos (§10.6 `CABECERAS_MANO_DE_OBRA.xlsx`) --------

_CAMPOS_MANO_OBRA = (
    "descripcion",
    "unidad_id",
    "familia_id",
    "costo_base",
    "cuadrilla_id",
    "rendimiento_teorico",
)
"""Campos que este cargador gobierna. Sin el trío de valuación de almacén
(§10.5) ni `iva_aplica`: ese archivo no trae esas columnas — son de
materiales, no de mano de obra."""

_CAMPOS_RESTAURABLES_MANO_OBRA = (
    *_CAMPOS_MANO_OBRA,
    "estatus",
)
"""Lo que el snapshot guarda como ``antes`` (`adapters/repos/
cargas_sql._RESTAURAR`)."""


class AplicadorManoObra:
    """Mano de obra / destajos y Subcontratos (§10.6) — mismo cargador.

    `CABECERAS_MANO_DE_OBRA.xlsx` y `catalogo_de_SUBCONTRATOS.xlsx` traen
    exactamente las mismas cabeceras; lo único que cambia es el tipo de
    insumo (constructor ``tipo``, §10.1). Copia estructural de
    `AplicadorMateriales`: cada fila es un `Insumo` (§7.3), mismo catálogo,
    mismo diff/versionado.
    Además homologa —o da de alta, mismo criterio que unidad/familia
    (§8.7)— la `cuadrilla` que ejecuta el destajo, y si el archivo trae
    rendimiento teórico se lo asienta también a la cuadrilla ("la cuadrilla
    asume el rendimiento" del destajo que se le asigna): un efecto
    colateral fuera del diff de insumo, porque la cuadrilla no es lo que
    esta carga está versionando.
    """

    def __init__(
        self,
        *,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        familias: RepositorioFamilias,
        cuadrillas: RepositorioCuadrillas,
        cargas: RepositorioCargas,
        tipo: TipoInsumo = TipoInsumo.MANO_OBRA,
    ) -> None:
        self._insumos = insumos
        self._unidades = unidades
        self._familias = familias
        self._cuadrillas = cuadrillas
        self._cargas = cargas
        # MANO_OBRA o SUBCONTRATO (§10.6): mismo archivo, mismo flujo; el
        # tipo de insumo que gobierna es lo único que cambia entre los dos
        # cargadores (`CargadorManoObra`/`CargadorSubcontratos`).
        self._tipo = tipo

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._insumos.listar(
            tipo=str(self._tipo), solo_activos=False
        )
        por_clave = {str(fila["clave"]): fila for fila in vigentes_filas}

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}
        unidades_por_clave = {str(f["clave"]): f for f in unidades_filas}

        # Sin ámbito propio de "mano_obra" en `familia.aplica_a` (§10.1 solo
        # define material/concepto): un destajo es un insumo igual que un
        # material, así que comparte el mismo árbol de familias que ellos.
        familias_filas = await self._familias.listar(
            aplica_a="material", solo_activos=False
        )
        familias = Homologador.desde(
            familias_filas, mapeos=await self._cargas.mapeos("familia")
        )
        id_familia = {str(f["clave"]): f["id"] for f in familias_filas}

        cuadrillas_filas = await self._cuadrillas.listar(solo_activos=False)
        cuadrillas = Homologador.desde(
            cuadrillas_filas, mapeos=await self._cargas.mapeos("cuadrilla")
        )
        id_cuadrilla = {str(f["clave"]): f["id"] for f in cuadrillas_filas}

        pendientes: list[PendientePropuesto] = []
        entrantes: dict[str, dict[str, Any]] = {}
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevas_familias: dict[str, UUID | None] = {}
        nuevas_cuadrillas: dict[str, UUID | None] = {}
        rendimientos_por_cuadrilla: dict[UUID, Decimal] = {}

        for registro in lectura.registros:
            destajo: FilaManoObra = registro  # type: ignore[assignment]
            actual = por_clave.get(destajo.llave, {})

            unidad_id = actual.get("unidad_id")
            if destajo.clave_unidad:

                async def _dar_de_alta_unidad(
                    _datos: dict[str, Any],
                    *,
                    _clave: str = destajo.clave_unidad,
                    _nombre: str | None = destajo.unidad,
                ) -> UUID:
                    return await self._unidades.crear_o_existente(
                        {"clave": _clave, "nombre": _nombre or _clave}
                    )

                unidad_id = await _resolver_o_dar_de_alta_con_alerta(
                    destajo.clave_unidad,
                    destajo.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    filas_por_clave=unidades_por_clave,
                    creadas=nuevas_unidades,
                    crear=_dar_de_alta_unidad,
                    entidad="unidad",
                    fila=destajo.fila,
                    pendientes=pendientes,
                    dry_run=dry_run,
                    campo_descripcion="nombre",
                )
            elif destajo.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    destajo.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear_o_existente,
                    dry_run=dry_run,
                )

            familia_id = actual.get("familia_id")
            if destajo.familia:
                familia_id = await _resolver_o_dar_de_alta(
                    destajo.familia,
                    homologador=familias,
                    id_por_clave=id_familia,
                    creadas=nuevas_familias,
                    crear=self._familias.crear_o_existente,
                    dry_run=dry_run,
                )

            cuadrilla_id = actual.get("cuadrilla_id")
            if destajo.cuadrilla:
                cuadrilla_id = await _resolver_o_dar_de_alta(
                    destajo.cuadrilla,
                    homologador=cuadrillas,
                    id_por_clave=id_cuadrilla,
                    creadas=nuevas_cuadrillas,
                    crear=self._cuadrillas.crear_o_existente,
                    dry_run=dry_run,
                )
                if cuadrilla_id is not None and destajo.rendimiento_teorico is not None:
                    rendimientos_por_cuadrilla[cuadrilla_id] = destajo.rendimiento_teorico

            entrantes[destajo.llave] = {
                "descripcion": destajo.descripcion,
                "unidad_id": unidad_id,
                "familia_id": familia_id,
                "costo_base": _o_vigente(destajo.costo_base, actual, "costo_base"),
                "cuadrilla_id": cuadrilla_id,
                "rendimiento_teorico": _o_vigente(
                    destajo.rendimiento_teorico, actual, "rendimiento_teorico"
                ),
            }

        vigentes = {
            clave: {campo: fila.get(campo) for campo in _CAMPOS_MANO_OBRA}
            for clave, fila in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._insumos.crear(
                    {
                        "tipo": str(self._tipo),
                        "clave": alta.clave,
                        "descripcion": alta.despues["descripcion"],
                        "unidad_id": alta.despues["unidad_id"],
                        "familia_id": alta.despues["familia_id"],
                        "costo_base": alta.despues["costo_base"],
                        "cuadrilla_id": alta.despues["cuadrilla_id"],
                        "rendimiento_teorico": alta.despues["rendimiento_teorico"],
                    }
                )
                operaciones.append(
                    _operacion("insumo", nuevo_id, "insert", despues=dict(alta.despues))
                )

            for cambio in diff.cambios:
                fila = por_clave[cambio.clave]
                await self._insumos.actualizar(fila["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "insumo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_MANO_OBRA),
                        despues=dict(cambio.despues),
                    )
                )

            for baja in diff.bajas:
                fila = por_clave[baja.clave]
                await self._insumos.actualizar(fila["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "insumo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_MANO_OBRA),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

            for cuadrilla_id, rendimiento in rendimientos_por_cuadrilla.items():
                await self._cuadrillas.actualizar_rendimiento(cuadrilla_id, rendimiento)

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={
                "unidades_creadas": len(nuevas_unidades),
                "familias_creadas": len(nuevas_familias),
                "cuadrillas_creadas": len(nuevas_cuadrillas),
            },
        )


# --- Catálogo base de conceptos (§8.7 `CABECERAS_CONCEPTOS.xlsx`) --------


class AplicadorConceptosBase:
    """Catálogo base de conceptos (§8.7): identidad únicamente.

    Clave, descripción y unidad — nada de composición. Escribe `concepto`
    con ``familia_id`` sin tocar (§3.4: lo que el archivo no trae, no se
    toca) y ``tipo`` fijo por constructor (``CONCEPTO`` por defecto) en el
    alta — mismo criterio que `AplicadorManoObra` fijando
    ``tipo=SUBCONTRATO`` para `CargadorSubcontratos`: un concepto auxiliar
    (`CargadorConceptosAuxiliares`, §7.3) es un `concepto` más, solo que
    ``tipo=AUXILIAR``, y la clave es única sin importar el tipo
    (`uq_concepto_clave`) — comparten catálogo, no lo duplican. La
    composición del concepto (qué lleva, con qué costo) es CPU
    (`AplicadorCPU`, abajo), un cargador aparte que además puede homologar
    contra lo que este catálogo ya haya dado de alta.
    """

    def __init__(
        self,
        *,
        conceptos: RepositorioConceptos,
        unidades: RepositorioUnidades,
        cargas: RepositorioCargas,
        tipo: TipoConcepto = TipoConcepto.CONCEPTO,
        prefijo_clave: str = "CPT",
        especialidades=None,
    ) -> None:
        self._conceptos = conceptos
        self._unidades = unidades
        self._cargas = cargas
        self._tipo = tipo
        self._prefijo_clave = prefijo_clave
        self._especialidades = especialidades

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._conceptos.listar(solo_activos=False)
        por_clave = {str(fila["clave"]): fila for fila in vigentes_filas}

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}
        unidades_por_clave = {str(f["clave"]): f for f in unidades_filas}

        pendientes: list[PendientePropuesto] = []
        entrantes: dict[str, dict[str, Any]] = {}
        conceptos_por_oficio: dict[str, list[str]] = {}
        nuevas_unidades: dict[str, UUID | None] = {}
        claves_generadas = 0
        # Semilla del consecutivo con el catálogo vigente; crece con cada
        # clave que este archivo genera, para que dos filas sin clave en el
        # mismo archivo no propongan el mismo número (§8.7). Una fila sin
        # clave no tiene identidad estable entre una carga y la siguiente
        # —la clave generada AQUÍ es su identidad de ahora en adelante—, así
        # que volver a subir el mismo archivo sin editarle la clave crea un
        # concepto nuevo cada vez, no actualiza el anterior. Es la misma
        # consecuencia de "la clave manda" (§3.3): sin ella no hay con qué
        # reconocer que es la misma fila.
        claves_conocidas = list(por_clave.keys())

        for registro in lectura.registros:
            base: FilaConceptoBase = registro  # type: ignore[assignment]
            if base.clave is not None:
                clave = str(base.clave)
            else:
                clave = generar_clave_automatica(self._prefijo_clave, claves_conocidas)
                claves_conocidas.append(clave)
                claves_generadas += 1
            actual = por_clave.get(clave, {})

            unidad_id = actual.get("unidad_id")
            if base.clave_unidad:

                async def _dar_de_alta_unidad(
                    _datos: dict[str, Any],
                    *,
                    _clave: str = base.clave_unidad,
                    _nombre: str | None = base.unidad,
                ) -> UUID:
                    return await self._unidades.crear_o_existente(
                        {"clave": _clave, "nombre": _nombre or _clave}
                    )

                unidad_id = await _resolver_o_dar_de_alta_con_alerta(
                    base.clave_unidad,
                    base.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    filas_por_clave=unidades_por_clave,
                    creadas=nuevas_unidades,
                    crear=_dar_de_alta_unidad,
                    entidad="unidad",
                    fila=base.fila,
                    pendientes=pendientes,
                    dry_run=dry_run,
                    campo_descripcion="nombre",
                )
            elif base.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    base.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear_o_existente,
                    dry_run=dry_run,
                )

            entrantes[clave] = {
                "descripcion": base.descripcion,
                "unidad_id": unidad_id,
            }
            if base.especialidad:
                conceptos_por_oficio.setdefault(base.especialidad, []).append(clave)

        vigentes = {
            clave: {
                "descripcion": fila.get("descripcion"),
                "unidad_id": fila.get("unidad_id"),
            }
            for clave, fila in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._conceptos.crear(
                    {
                        "tipo": str(self._tipo),
                        "clave": alta.clave,
                        "descripcion": alta.despues["descripcion"],
                        "unidad_id": alta.despues["unidad_id"],
                    }
                )
                operaciones.append(
                    _operacion("concepto", nuevo_id, "insert", despues=dict(alta.despues))
                )

            for cambio in diff.cambios:
                fila = por_clave[cambio.clave]
                await self._conceptos.actualizar(fila["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "concepto",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_CONCEPTO_BASE),
                        despues=dict(cambio.despues),
                    )
                )

            for baja in diff.bajas:
                fila = por_clave[baja.clave]
                await self._conceptos.actualizar(fila["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "concepto",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_RESTAURABLES_CONCEPTO_BASE),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        detalle: dict[str, Any] = {
            "unidades_creadas": len(nuevas_unidades),
            "claves_generadas": claves_generadas,
        }
        if conceptos_por_oficio and self._especialidades is not None:
            detalle["especialidades"] = await _mapear_clasificacion(
                por_referencia=conceptos_por_oficio,
                catalogo=self._especialidades,
                asignar=lambda destino, claves: (
                    self._especialidades.asignar_a_conceptos(destino, claves)
                ),
                crear_faltantes=True,
                dry_run=dry_run,
                # Lo que una persona ya homologó (§10.3): fusionar dos oficios
                # desde la pantalla no se puede deshacer en la siguiente carga.
                mapeos=await self._cargas.mapeos("especialidad"),
            )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle=detalle,
        )


_CAMPOS_RESTAURABLES_CONCEPTO_BASE = (
    "tipo",
    "descripcion",
    "unidad_id",
    "familia_id",
    "estatus",
)
"""Lo que el snapshot guarda como ``antes`` (`adapters/repos/
cargas_sql._RESTAURAR`). Incluye ``tipo``/``familia_id`` aunque este
cargador no los escriba: el UPDATE de la reversa fija los cinco campos sin
condición (`_RESTAURAR["concepto"]`), así que omitirlos aquí los dejaría en
NULL al revertir — mismo criterio que `AplicadorCPU` usa para su propio
`_recorte` de concepto."""


# --- Unidades y familias (§3.5) -------------------------------------------
#
# Hasta hoy nadie las versionaba: otras cargas (materiales, mano de obra,
# CPU, conceptos base) las tocan de pasada con `crear_o_existente` para
# auto-dar de alta una que no existía, pero eso no se registra en el
# snapshot —no es lo que esa carga versiona— y por eso `unidad`/`familia`
# no estaban en `cargas_sql._ELIMINAR` (ver el comentario ahí). Este es el
# cargador **dueño** del catálogo: sí registra sus inserts/updates/bajas,
# mismo patrón que `AplicadorConceptosBase` (identidad únicamente, con baja
# lógica en modo Reemplazar porque a diferencia de nivel/etapa_constructiva
# esta tabla sí tiene `estatus`, migración 0005).

_CAMPOS_RESTAURABLES_UNIDAD = ("nombre", "sinonimos", "factor", "estatus")
"""Lo que el snapshot guarda como ``antes`` (`cargas_sql._RESTAURAR["unidad"]`)."""

_CAMPOS_RESTAURABLES_CONTRATISTA = (
    "razon_social", "rfc", "contacto", "telefono", "email", "estatus",
)
"""Lo que el snapshot guarda como ``antes`` (`cargas_sql._RESTAURAR["contratista"]`).
Los frentes **no** entran: viven en la tabla puente y el UPDATE de la reversa
no los toca, así que revertir una carga deja al contratista con los frentes que
esa carga le puso. Es una pérdida conocida y menor —son capacidad de catálogo,
no dinero ni programa— y arreglarla pediría versionar el puente entero."""

_CAMPOS_RESTAURABLES_FAMILIA = ("nombre", "parent_id", "aplica_a", "iva_aplica", "estatus")
"""Lo que el snapshot guarda como ``antes`` (`cargas_sql._RESTAURAR["familia"]`).
Incluye ``parent_id``/``aplica_a``/``iva_aplica`` aunque este cargador no los
escriba: el UPDATE de la reversa fija los cinco campos sin condición, así que
omitirlos aquí los dejaría en su default al revertir."""


class AplicadorUnidades:
    """Catálogo base de unidades (§3.5): identidad únicamente — clave y
    nombre. Sinónimos/factor quedan en su default; se ajustan a mano desde
    el catálogo, igual que `AplicadorNiveles` deja `orden`/`importe`."""

    def __init__(self, *, unidades: RepositorioUnidades, cargas: RepositorioCargas) -> None:
        self._unidades = unidades
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._unidades.listar(solo_activos=False)
        por_clave = {str(f["clave"]): f for f in vigentes_filas}

        entrantes: dict[str, dict[str, Any]] = {}
        claves_generadas = 0
        claves_conocidas = list(por_clave.keys())

        for registro in lectura.registros:
            fila: FilaUnidad = registro  # type: ignore[assignment]
            if fila.clave is not None:
                clave = str(fila.clave)
            else:
                clave = generar_clave_automatica("UNI", claves_conocidas)
                claves_conocidas.append(clave)
                claves_generadas += 1
            entrantes[clave] = {"nombre": fila.nombre}

        vigentes = {clave: {"nombre": f.get("nombre")} for clave, f in por_clave.items()}
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._unidades.crear(
                    {"clave": alta.clave, "nombre": alta.despues["nombre"]}
                )
                operaciones.append(
                    _operacion("unidad", nuevo_id, "insert", despues=dict(alta.despues))
                )
            for cambio in diff.cambios:
                fila_vigente = por_clave[cambio.clave]
                await self._unidades.actualizar(fila_vigente["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "unidad",
                        fila_vigente["id"],
                        "update",
                        antes=_recorte(fila_vigente, _CAMPOS_RESTAURABLES_UNIDAD),
                        despues=dict(cambio.despues),
                    )
                )
            for baja in diff.bajas:
                fila_vigente = por_clave[baja.clave]
                await self._unidades.actualizar(fila_vigente["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "unidad",
                        fila_vigente["id"],
                        "update",
                        antes=_recorte(fila_vigente, _CAMPOS_RESTAURABLES_UNIDAD),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={"claves_generadas": claves_generadas},
        )


class AplicadorContratistas:
    """Catálogo de contratistas (§8.3, §10.6).

    El contratista es la fuerza de trabajo: pone las cuadrillas con las que se
    ejecuta un frente. Además de su identidad, la fila trae los frentes que
    sabe hacer, y esos se resuelven aquí de **clave a id** —el cargador no
    tiene con qué— y se reemplazan enteros: uno que dejó de hacer
    instalaciones tiene que perder ese frente.

    Una clave de frente que no exista no tumba la fila: el contratista entra
    igual y la clave sale reportada. Perder el alta de quien está trabajando en
    la obra por un frente mal escrito sería desproporcionado.
    """

    def __init__(
        self,
        *,
        contratistas: RepositorioContratistas,
        frentes: RepositorioFrentes,
        cargas: RepositorioCargas,
        especialidades=None,
    ) -> None:
        self._contratistas = contratistas
        self._frentes = frentes
        self._cargas = cargas
        self._especialidades = especialidades

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._contratistas.listar(solo_activos=False)
        por_clave = {str(c["clave"]): c for c in vigentes_filas}

        catalogo_frentes = _CatalogoPorNombre(
            await self._frentes.listar(solo_activos=False),
            await self._cargas.mapeos("frente"),
        )
        oficios_vigentes = (
            await self._especialidades.listar(solo_activos=False)
            if self._especialidades is not None
            else []
        )
        catalogo_oficios = _CatalogoPorNombre(
            oficios_vigentes, await self._cargas.mapeos("especialidad")
        )
        claves_de_oficio = {str(f["clave"]).upper() for f in oficios_vigentes}

        entrantes: dict[str, dict[str, Any]] = {}
        frentes_de: dict[str, list[UUID]] = {}
        oficios_de: dict[str, list[UUID]] = {}
        sin_resolver: list[str] = []
        sin_oficio: list[str] = []
        aproximadas: list[str] = []
        oficios_creados: list[str] = []

        for registro in lectura.registros:
            fila: FilaContratista = registro  # type: ignore[assignment]
            clave = str(fila.clave)
            entrantes[clave] = {
                "razon_social": fila.razon_social,
                "rfc": fila.rfc,
                "contacto": fila.contacto,
                "telefono": fila.telefono,
                "email": fila.email,
            }
            frentes_de[clave] = await _resolver_todas(
                fila.frentes, catalogo_frentes, sin_resolver, aproximadas
            )
            oficios_de[clave] = await _resolver_todas(
                fila.especialidades,
                catalogo_oficios,
                sin_oficio,
                aproximadas,
                crear=(
                    self._especialidades.crear
                    if self._especialidades is not None and not dry_run
                    else None
                ),
                creadas=oficios_creados,
                tomadas=claves_de_oficio,
            )

        vigentes = {
            clave: _recorte(f, ("razon_social", "rfc", "contacto", "telefono", "email"))
            for clave, f in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._contratistas.crear(
                    {"clave": alta.clave, **alta.despues}
                )
                await self._contratistas.reemplazar_frentes(
                    nuevo_id, frentes_de.get(alta.clave, [])
                )
                await self._reemplazar_oficios(nuevo_id, oficios_de.get(alta.clave, []))
                operaciones.append(
                    _operacion("contratista", nuevo_id, "insert", despues=dict(alta.despues))
                )
            for cambio in diff.cambios:
                fila_vigente = por_clave[cambio.clave]
                await self._contratistas.actualizar(
                    fila_vigente["id"], dict(cambio.despues)
                )
                await self._contratistas.reemplazar_frentes(
                    fila_vigente["id"], frentes_de.get(cambio.clave, [])
                )
                await self._reemplazar_oficios(
                    fila_vigente["id"], oficios_de.get(cambio.clave, [])
                )
                operaciones.append(
                    _operacion(
                        "contratista",
                        fila_vigente["id"],
                        "update",
                        antes=_recorte(fila_vigente, _CAMPOS_RESTAURABLES_CONTRATISTA),
                        despues=dict(cambio.despues),
                    )
                )
            for baja in diff.bajas:
                fila_vigente = por_clave[baja.clave]
                await self._contratistas.actualizar(
                    fila_vigente["id"], {"estatus": _ESTATUS_BAJA}
                )
                operaciones.append(
                    _operacion(
                        "contratista",
                        fila_vigente["id"],
                        "update",
                        antes=_recorte(fila_vigente, _CAMPOS_RESTAURABLES_CONTRATISTA),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={
                "frentes_sin_resolver": sorted(set(sin_resolver)),
                "especialidades_sin_resolver": sorted(set(sin_oficio)),
                "especialidades_creadas": oficios_creados,
                # Las que empataron por parecido y no exactas. Se nombran para
                # que alguien las pueda revisar: `SUBCONTRATO` contra
                # `SUBCONTRATOS` es correcto, pero decidirlo en silencio no.
                "resueltas_por_parecido": sorted(set(aproximadas)),
            },
        )

    async def _reemplazar_oficios(
        self, contratista_id: UUID, ids: list[UUID]
    ) -> None:
        """Guarda el segundo eje, si el repositorio lo soporta.

        Opcional porque el puente nació en la 0047 y hay dobles de prueba que
        no lo implementan: un contratista sin oficios registrados sigue siendo
        un contratista válido, y romper la carga entera por eso no ayuda a
        nadie.
        """
        reemplazar = getattr(self._contratistas, "reemplazar_especialidades", None)
        if reemplazar is not None:
            await reemplazar(contratista_id, ids)


class AplicadorFamilias:
    """Catálogo base de familias (§3.5): identidad únicamente — clave y
    nombre. `parent_id`/`aplica_a`/`iva_aplica` quedan en su default; se
    ajustan a mano desde el catálogo (el archivo real no trae ninguno de
    los tres, §3.3: lo que no trae no se inventa)."""

    def __init__(self, *, familias: RepositorioFamilias, cargas: RepositorioCargas) -> None:
        self._familias = familias
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._familias.listar(solo_activos=False)
        por_clave = {str(f["clave"]): f for f in vigentes_filas}

        entrantes: dict[str, dict[str, Any]] = {}
        claves_generadas = 0
        claves_conocidas = list(por_clave.keys())

        for registro in lectura.registros:
            fila: FilaFamilia = registro  # type: ignore[assignment]
            if fila.clave is not None:
                clave = str(fila.clave)
            else:
                clave = generar_clave_automatica("FAM", claves_conocidas)
                claves_conocidas.append(clave)
                claves_generadas += 1
            entrantes[clave] = {"nombre": fila.nombre}

        vigentes = {clave: {"nombre": f.get("nombre")} for clave, f in por_clave.items()}
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._familias.crear(
                    {"clave": alta.clave, "nombre": alta.despues["nombre"]}
                )
                operaciones.append(
                    _operacion("familia", nuevo_id, "insert", despues=dict(alta.despues))
                )
            for cambio in diff.cambios:
                fila_vigente = por_clave[cambio.clave]
                await self._familias.actualizar(fila_vigente["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "familia",
                        fila_vigente["id"],
                        "update",
                        antes=_recorte(fila_vigente, _CAMPOS_RESTAURABLES_FAMILIA),
                        despues=dict(cambio.despues),
                    )
                )
            for baja in diff.bajas:
                fila_vigente = por_clave[baja.clave]
                await self._familias.actualizar(fila_vigente["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "familia",
                        fila_vigente["id"],
                        "update",
                        antes=_recorte(fila_vigente, _CAMPOS_RESTAURABLES_FAMILIA),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={"claves_generadas": claves_generadas},
        )


# --- Niveles y etapas de construcción (§10.1) -----------------------------
#
# Antes solo se sembraban de pasada cuando el árbol de presupuesto los
# referenciaba (`RepositorioNivelesEtapas.upsert_nivel`/`upsert_etapa`,
# primera carga define la descripción y ya). Estos dos son su propio
# cargador dueño del catálogo: sí actualizan la descripción en cada carga
# (§10.2, modo Actualizar), con diff y snapshot como cualquier otro.
#
# Ninguna de las dos tablas tiene `estatus` (migración 0005): sin baja
# lógica, un modo Reemplazar calcula `diff.bajas` igual —es el diff quien
# decide qué falta, no el aplicador— pero no hay nada que este aplicador
# pueda hacer con esas filas más que dejarlas como están. No se cuentan
# como "actualizadas": no se tocaron.


class AplicadorNiveles:
    """Catálogo base de niveles de construcción (§10.1): identidad
    únicamente — clave y descripción."""

    def __init__(self, *, niveles_etapas: RepositorioNivelesEtapas) -> None:
        self._niveles_etapas = niveles_etapas

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._niveles_etapas.listar_niveles()
        por_clave = {str(f["clave"]): f for f in vigentes_filas}

        entrantes: dict[str, dict[str, Any]] = {}
        claves_generadas = 0
        claves_conocidas = list(por_clave.keys())

        for registro in lectura.registros:
            fila: FilaNivel = registro  # type: ignore[assignment]
            if fila.clave is not None:
                clave = str(fila.clave)
            else:
                clave = generar_clave_automatica("NIV", claves_conocidas)
                claves_conocidas.append(clave)
                claves_generadas += 1
            entrantes[clave] = {"descripcion": fila.descripcion}

        vigentes = {
            clave: {"descripcion": f.get("descripcion")} for clave, f in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._niveles_etapas.crear_nivel(
                    {"clave": alta.clave, "descripcion": alta.despues["descripcion"]}
                )
                operaciones.append(
                    _operacion("nivel", nuevo_id, "insert", despues=dict(alta.despues))
                )
            for cambio in diff.cambios:
                fila_vigente = por_clave[cambio.clave]
                await self._niveles_etapas.actualizar_nivel(
                    fila_vigente["id"], dict(cambio.despues)
                )
                operaciones.append(
                    _operacion(
                        "nivel",
                        fila_vigente["id"],
                        "update",
                        antes=_recorte(fila_vigente, ("descripcion",)),
                        despues=dict(cambio.despues),
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={"claves_generadas": claves_generadas},
        )


class AplicadorEtapasConstructivas:
    """Catálogo base de etapas de construcción (§10.1): identidad
    clave, descripción y el **frente** al que pertenece la etapa (§8.3,
    migración 0045).

    ``nivel_id`` sigue sin resolverse aquí (ver
    `domain.cargadores.etapas_constructivas`): el archivo real no lo trae.

    El frente sí viene, y se resuelve por nombre contra el catálogo. Uno que no
    exista **se crea**: el archivo del cliente es la autoridad sobre su propio
    vocabulario de frentes, y sembrar una lista a mano ya salió mal una vez
    —los seis del §8.3 no eran los cuatro que esta constructora usa—."""

    def __init__(
        self,
        *,
        niveles_etapas: RepositorioNivelesEtapas,
        frentes: RepositorioFrentes | None = None,
        cargas: RepositorioCargas | None = None,
    ) -> None:
        self._niveles_etapas = niveles_etapas
        self._frentes = frentes
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        vigentes_filas = await self._niveles_etapas.listar_etapas()
        por_clave = {str(f["clave"]): f for f in vigentes_filas}

        entrantes: dict[str, dict[str, Any]] = {}
        etapas_por_frente: dict[str, list[str]] = {}
        claves_generadas = 0
        claves_conocidas = list(por_clave.keys())

        for registro in lectura.registros:
            fila: FilaEtapaConstructiva = registro  # type: ignore[assignment]
            if fila.clave is not None:
                clave = str(fila.clave)
            else:
                clave = generar_clave_automatica("ECO", claves_conocidas)
                claves_conocidas.append(clave)
                claves_generadas += 1
            entrantes[clave] = {"descripcion": fila.descripcion}
            if fila.frente:
                etapas_por_frente.setdefault(fila.frente, []).append(clave)

        vigentes = {
            clave: {"descripcion": f.get("descripcion")} for clave, f in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._niveles_etapas.crear_etapa(
                    {"clave": alta.clave, "descripcion": alta.despues["descripcion"]}
                )
                operaciones.append(
                    _operacion(
                        "etapa_constructiva", nuevo_id, "insert", despues=dict(alta.despues)
                    )
                )
            for cambio in diff.cambios:
                fila_vigente = por_clave[cambio.clave]
                await self._niveles_etapas.actualizar_etapa(
                    fila_vigente["id"], dict(cambio.despues)
                )
                operaciones.append(
                    _operacion(
                        "etapa_constructiva",
                        fila_vigente["id"],
                        "update",
                        antes=_recorte(fila_vigente, ("descripcion",)),
                        despues=dict(cambio.despues),
                    )
                )

        detalle: dict[str, Any] = {"claves_generadas": claves_generadas}
        if etapas_por_frente and self._frentes is not None:
            detalle["frentes"] = await _mapear_clasificacion(
                por_referencia=etapas_por_frente,
                catalogo=self._frentes,
                asignar=lambda destino, claves: (
                    self._niveles_etapas.asignar_frente_por_clave(
                        frente_id=destino, claves=claves
                    )
                ),
                crear_faltantes=True,
                dry_run=dry_run,
                mapeos=await self._cargas.mapeos("frente")
                if self._cargas is not None
                else None,
            )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle=detalle,
        )


# --- CPU / Conceptos (§10.6 `CABECERAS_CPU.xlsx`) -------------------------

_TIPO_INSUMO_POR_CATEGORIA: dict[CategoriaExplosion, TipoInsumo] = {
    CategoriaExplosion.MATERIAL: TipoInsumo.MATERIAL,
    CategoriaExplosion.MANO_OBRA: TipoInsumo.MANO_OBRA,
    CategoriaExplosion.DESTAJO: TipoInsumo.MANO_OBRA,
    CategoriaExplosion.SUBCONTRATO: TipoInsumo.SUBCONTRATO,
}
"""Tipo del insumo que se da de alta cuando un componente no cruza contra el
catálogo — de `AplicadorCPU` (`cpu.CATEGORIA_POR_TIPO`, nunca produce
`DESTAJO`) y de `AplicadorPresupuesto` (`_CATEGORIA_POR_TIPO_NODO`, nunca
produce `MANO_OBRA`): un componente de otra categoría no llega hasta aquí
en ninguno de los dos."""


class AplicadorCPU:
    """Catálogo de conceptos con su APU (§10.6, §7.3).

    Cada concepto del archivo se convierte en: el `concepto` (alta o
    actualización), su **composición** (`explosion`) sustituida completa, y una
    **versión nueva de CPU** cuyo precio sale de explotar esa composición
    (§7.3: el CPU se calcula, no se captura).

    Un componente cuyo insumo no está en el catálogo se da de alta solo, con
    lo mínimo que trae la fila (clave, descripción, tipo, costo — mismo
    criterio que unidad/familia, §8.7): un hueco silencioso daría un precio
    menor al real, y esta fila sí trae su propio P.U. para llenarlo, así
    que bloquear el concepto entero por un insumo nuevo es peor que darlo de
    alta. `CATEGORIA_POR_TIPO` (`domain.cargadores.cpu`) ya limita esto a
    material, mano de obra y subcontrato — un componente de otra categoría
    ni siquiera llega hasta aquí.
    """

    def __init__(
        self,
        *,
        conceptos: RepositorioConceptos,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        familias: RepositorioFamilias,
        cargas: RepositorioCargas,
    ) -> None:
        self._conceptos = conceptos
        self._insumos = insumos
        self._unidades = unidades
        self._familias = familias
        self._cargas = cargas

    async def aplicar(  # noqa: C901 — el flujo del §9.2 es lineal, no ramificado
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        conceptos_filas = await self._conceptos.listar(solo_activos=False)
        por_clave = {str(f["clave"]): f for f in conceptos_filas}

        insumos_filas = await self._insumos.listar(solo_activos=False)
        insumos_por_clave = {str(f["clave"]): f for f in insumos_filas}
        clave_de_insumo = {f["id"]: str(f["clave"]) for f in insumos_filas}
        id_insumo = {str(f["clave"]): f["id"] for f in insumos_filas}
        insumos = Homologador.desde(
            insumos_filas, mapeos=await self._cargas.mapeos("insumo")
        )
        costos_insumo = {
            str(f["clave"]): Decimal(
                str(f.get("costo_base_actualizado") or f.get("costo_base") or 0)
            )
            for f in insumos_filas
        }

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}
        # Sin ámbito propio de mano_obra/subcontrato en `familia.aplica_a`
        # (§10.1 solo define material/concepto): un insumo dado de alta desde
        # aquí comparte el mismo árbol que materiales (§8.7, mismo criterio
        # que `AplicadorManoObra`), no el de conceptos que se calcula abajo.
        familias_de_insumo_filas = await self._familias.listar(
            aplica_a="material", solo_activos=False
        )
        familias_de_insumo = Homologador.desde(
            familias_de_insumo_filas, mapeos=await self._cargas.mapeos("familia")
        )
        id_familia_de_insumo = {str(f["clave"]): f["id"] for f in familias_de_insumo_filas}
        familias_filas = await self._familias.listar(
            aplica_a="concepto", solo_activos=False
        )
        familias = Homologador.desde(
            familias_filas, mapeos=await self._cargas.mapeos("familia")
        )
        id_familia = {str(f["clave"]): f["id"] for f in familias_filas}

        pendientes: list[PendientePropuesto] = []
        errores: list[ErrorDeFila] = []
        entrantes: dict[str, dict[str, Any]] = {}
        planes: dict[str, dict[str, Any]] = {}
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevas_familias: dict[str, UUID | None] = {}
        # Dict propio, no compartido con `nuevas_familias`: esa es del árbol
        # de familias del CONCEPTO (aplica_a="concepto"); esta es del árbol
        # de familias del INSUMO que se da de alta solo (aplica_a="material",
        # `familias_de_insumo`). Comparten clave de texto pero son dos
        # catálogos distintos — mezclarlas haría que la primera creada
        # "prestara" su id a la otra sin que ninguna lo pida.
        nuevas_familias_insumo: dict[str, UUID | None] = {}
        nuevos_insumos: dict[str, UUID | None] = {}

        for registro in lectura.registros:
            bloque: ConceptoCargado = registro  # type: ignore[assignment]
            cabeza = bloque.encabezado

            componentes: list[Componente] = []
            filas_explosion: list[dict[str, Any]] = []
            incompleto = False

            for componente in bloque.componentes:
                clave_texto = str(componente.clave_insumo)
                # Si `clave_texto` cruza (directo o por mapeo), gana la clave
                # canónica del catálogo — igual que antes de este cambio—;
                # solo cuando no cruza (se va a dar de alta) `clave_insumo`
                # es el propio texto del archivo, que es lo único que hay.
                clave_insumo = insumos.resolver(clave_texto) or clave_texto

                async def _dar_de_alta_insumo(
                    _datos: dict[str, Any],
                    *,
                    _componente: ComponenteCargado = componente,
                    clave: str = clave_texto,
                ) -> UUID:
                    unidad_insumo_id = None
                    if _componente.unidad:
                        unidad_insumo_id = await _resolver_o_dar_de_alta(
                            _componente.unidad,
                            homologador=unidades,
                            id_por_clave=id_unidad,
                            creadas=nuevas_unidades,
                            crear=self._unidades.crear_o_existente,
                            dry_run=dry_run,
                        )
                    familia_insumo_id = None
                    if _componente.familia:
                        familia_insumo_id = await _resolver_o_dar_de_alta(
                            _componente.familia,
                            homologador=familias_de_insumo,
                            id_por_clave=id_familia_de_insumo,
                            creadas=nuevas_familias_insumo,
                            crear=self._familias.crear_o_existente,
                            dry_run=dry_run,
                        )
                    return await self._insumos.crear_o_existente(
                        {
                            "tipo": str(_TIPO_INSUMO_POR_CATEGORIA[_componente.categoria]),
                            "clave": clave,
                            "descripcion": _componente.descripcion or clave,
                            "unidad_id": unidad_insumo_id,
                            "familia_id": familia_insumo_id,
                            "costo_base": _componente.precio_unitario or Decimal(0),
                        }
                    )

                insumo_id = await _resolver_o_dar_de_alta_con_alerta(
                    clave_texto,
                    componente.descripcion,
                    homologador=insumos,
                    id_por_clave=id_insumo,
                    filas_por_clave=insumos_por_clave,
                    creadas=nuevos_insumos,
                    crear=_dar_de_alta_insumo,
                    entidad="insumo",
                    fila=componente.fila,
                    pendientes=pendientes,
                    dry_run=dry_run,
                )
                if clave_insumo not in insumos_por_clave:
                    # En `dry_run` sobre un insumo nuevo, `insumo_id` es
                    # `None` (§9.3: la vista previa no escribe) — igual se
                    # registra para que el `["id"]` de abajo no truene; nunca
                    # se lee de verdad porque eso solo pasa dentro de
                    # `if not dry_run:`.
                    insumos_por_clave[clave_insumo] = {"id": insumo_id}
                if clave_insumo not in costos_insumo:
                    costos_insumo[clave_insumo] = componente.precio_unitario or Decimal(0)
                try:
                    del_dominio = Componente(
                        categoria=componente.categoria,
                        cantidad=componente.cantidad,
                        clave_insumo=clave_insumo,
                        costo_unitario=componente.precio_unitario or None,
                        orden=len(componentes),
                    )
                except ErrorDeAPU as exc:
                    errores.append(
                        ErrorDeFila(
                            fila=componente.fila,
                            columna="cantidad",
                            valor=str(componente.cantidad),
                            motivo=str(exc),
                        )
                    )
                    incompleto = True
                    continue

                componentes.append(del_dominio)
                costo = (
                    del_dominio.costo_unitario
                    if del_dominio.costo_unitario is not None
                    else costos_insumo.get(clave_insumo, Decimal(0))
                )
                filas_explosion.append(
                    {
                        "tipo_hijo": str(TipoHijoExplosion.INSUMO),
                        "insumo_id": insumos_por_clave[clave_insumo]["id"],
                        "categoria": str(componente.categoria),
                        # El §10.6 da una sola columna E ("rendimiento =
                        # CANTIDAD"), así que las dos del esquema (§7.3)
                        # reciben el mismo número.
                        "cantidad": del_dominio.cantidad,
                        "rendimiento": del_dominio.cantidad,
                        "costo_unitario": costo,
                        "importe": del_dominio.cantidad * costo,
                        "orden": len(filas_explosion),
                    }
                )

            if incompleto:
                # Cargar el concepto sin uno de sus insumos publicaría un CPU
                # más barato que el real (§7.3). Se omite entero.
                continue

            actual = por_clave.get(bloque.llave, {})

            unidad_id = actual.get("unidad_id")
            if cabeza.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    cabeza.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear_o_existente,
                    dry_run=dry_run,
                )

            familia_id = actual.get("familia_id")
            if cabeza.familia:
                familia_id = await _resolver_o_dar_de_alta(
                    cabeza.familia,
                    homologador=familias,
                    id_por_clave=id_familia,
                    creadas=nuevas_familias,
                    crear=self._familias.crear_o_existente,
                    dry_run=dry_run,
                )

            try:
                precio = calcular_cpu(
                    bloque.llave,
                    composiciones={bloque.llave: componentes},
                    costos_insumo=costos_insumo,
                )
            except ErrorDeAPU as exc:
                errores.append(
                    ErrorDeFila(fila=cabeza.fila, columna="clave", valor=bloque.llave, motivo=str(exc))
                )
                continue

            if bloque.llave not in por_clave:
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.CPU_NUEVO,
                        entidad="concepto",
                        valor_origen=bloque.llave,
                        propuesta={
                            "descripcion": cabeza.descripcion,
                            "precio_unitario": str(precio.total.monto),
                            "componentes": len(componentes),
                        },
                        origen_ref=f"fila {cabeza.fila}",
                    )
                )

            entrantes[bloque.llave] = {
                "descripcion": cabeza.descripcion,
                "unidad_id": unidad_id,
                "familia_id": familia_id,
                "composicion": _firma_explosion(filas_explosion, clave_de_insumo),
            }
            planes[bloque.llave] = {
                "cabeza": cabeza,
                "filas_explosion": filas_explosion,
                "precio": precio,
            }

        vigentes: dict[str, dict[str, Any]] = {}
        for clave, vigente_fila in por_clave.items():
            # La composición solo se lee de los conceptos que el archivo toca:
            # para los demás el diff únicamente mira si están o no (bajas del
            # modo Reemplazar, §10.2), y explotar todo el catálogo para eso
            # sería una consulta por concepto sin necesidad.
            composicion = (
                _firma_explosion(
                    await self._conceptos.explosion_directa(vigente_fila["id"]),
                    clave_de_insumo,
                )
                if clave in entrantes
                else ""
            )
            vigentes[clave] = {
                "descripcion": vigente_fila.get("descripcion"),
                "unidad_id": vigente_fila.get("unidad_id"),
                "familia_id": vigente_fila.get("familia_id"),
                "composicion": composicion,
            }

        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for cambio in (*diff.altas, *diff.cambios):
                plan = planes[cambio.clave]
                fila = por_clave.get(cambio.clave)

                if fila is None:
                    concepto_id = await self._conceptos.crear(
                        {
                            "tipo": str(TipoConcepto.CONCEPTO),
                            "clave": cambio.clave,
                            "descripcion": cambio.despues["descripcion"],
                            "unidad_id": cambio.despues["unidad_id"],
                            "familia_id": cambio.despues["familia_id"],
                        }
                    )
                    operaciones.append(
                        _operacion(
                            "concepto",
                            concepto_id,
                            "insert",
                            despues={"clave": cambio.clave},
                        )
                    )
                else:
                    concepto_id = fila["id"]
                    await self._conceptos.actualizar(
                        concepto_id,
                        {
                            "descripcion": cambio.despues["descripcion"],
                            "unidad_id": cambio.despues["unidad_id"],
                            "familia_id": cambio.despues["familia_id"],
                        },
                    )
                    operaciones.append(
                        _operacion(
                            "concepto",
                            concepto_id,
                            "update",
                            antes=_recorte(
                                fila,
                                ("tipo", "descripcion", "unidad_id", "familia_id", "estatus"),
                            ),
                            despues=dict(cambio.despues),
                        )
                    )

                operaciones.extend(
                    await _publicar_cpu_de_concepto(
                        self._conceptos, concepto_id, plan["filas_explosion"], plan["precio"]
                    )
                )

            for baja in diff.bajas:
                fila = por_clave[baja.clave]
                # Baja lógica, igual que en materiales: `explosion`,
                # `actividad` y `presupuesto` referencian `concepto` y un
                # borrado se llevaría obra ya ejecutada (§10.2).
                await self._conceptos.actualizar(fila["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "concepto",
                        fila["id"],
                        "update",
                        antes=_recorte(
                            fila,
                            ("tipo", "descripcion", "unidad_id", "familia_id", "estatus"),
                        ),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            errores=tuple(errores),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={
                "unidades_creadas": len(nuevas_unidades),
                "familias_creadas": len(nuevas_familias),
                "familias_de_insumo_creadas": len(nuevas_familias_insumo),
                "insumos_creados": len(nuevos_insumos),
            },
        )


async def _publicar_cpu_de_concepto(
    conceptos: RepositorioConceptos,
    concepto_id: UUID,
    filas_explosion: list[dict[str, Any]],
    precio: PrecioUnitario,
) -> list[dict[str, Any]]:
    """Sustituye la composición y publica la versión nueva de CPU (§10.8).

    Compartida por `AplicadorCPU` y `AplicadorPresupuesto`: la única
    diferencia entre publicar el CPU de un concepto por el archivo de CPU o
    por el árbol de un prototipo es de dónde salió `filas_explosion` — el
    resto (guardar antes, sustituir, versionar) es idéntico.

    El orden importa y es el que la reversa deshace al revés: primero se
    guarda lo que se va a borrar de `explosion`, luego se retira el CPU
    vigente y se inserta el nuevo, y al final entran las filas nuevas de
    `explosion` atadas a ese CPU.
    """
    operaciones: list[dict[str, Any]] = []

    anteriores = await conceptos.explosion_directa(concepto_id)
    await conceptos.eliminar_explosion(concepto_id)
    for anterior in anteriores:
        operaciones.append(
            _operacion("explosion", anterior["id"], "delete", antes=dict(anterior))
        )

    versiones = await conceptos.versiones_cpu(concepto_id)
    vigentes_antes = {
        fila["id"]: dict(fila) for fila in versiones if bool(fila["vigente"])
    }
    nueva, retiradas = publicar_version(
        [_version_de_dominio(fila) for fila in versiones],
        precio,
        variante=None,
    )
    for identificador, fila in vigentes_antes.items():
        if int(fila["version"]) in retiradas:
            operaciones.append(
                _operacion(
                    "cpu",
                    identificador,
                    "update",
                    antes={
                        "precio_unitario": fila["precio_unitario"],
                        "precio_destajo": fila["precio_destajo"],
                        "vigente": True,
                    },
                    despues={"vigente": False},
                )
            )

    cpu_id = await conceptos.publicar_version_cpu(
        concepto_id,
        version=nueva.version,
        precio_unitario=nueva.precio.total.monto,
        precio_destajo=nueva.precio.destajo.monto,
        variante=None,
        retirar=list(retiradas),
    )
    operaciones.append(
        _operacion("cpu", cpu_id, "insert", despues={"version": nueva.version})
    )

    insertadas = await conceptos.agregar_explosion(
        concepto_id, cpu_id=cpu_id, filas=filas_explosion
    )
    for fila in insertadas:
        operaciones.append(_operacion("explosion", fila["id"], "insert"))

    return operaciones


def _version_de_dominio(fila: dict[str, Any]) -> VersionCPU:
    return VersionCPU(
        version=int(fila["version"]),
        precio=PrecioUnitario(
            total=Dinero(Decimal(str(fila["precio_unitario"]))),
            destajo=Dinero(Decimal(str(fila["precio_destajo"]))),
        ),
        vigente=bool(fila["vigente"]),
        variante=fila.get("variante"),
    )


def _firma_explosion(
    filas: list[dict[str, Any]], clave_de_insumo: dict[Any, str]
) -> str:
    """Composición como texto comparable, para saber si el APU cambió (§10.8).

    Se firma por **clave** de insumo y no por su id (§3.3): es la identidad
    estable entre el archivo y la base.
    """
    partes = []
    for fila in sorted(filas, key=lambda f: int(f.get("orden") or 0)):
        clave = clave_de_insumo.get(fila.get("insumo_id"), "")
        cantidad = Decimal(str(fila.get("cantidad") or 0)).normalize() + Decimal(0)
        costo = Decimal(str(fila.get("costo_unitario") or 0)).normalize() + Decimal(0)
        partes.append(f"{clave}:{fila.get('categoria')}:{cantidad}:{costo}")
    return "|".join(partes)


# --- Cuadrillas (§10.6 `CABECERAS_CUADRILLAS.xlsx`) -----------------------


class AplicadorCuadrillas:
    """Composición y PU de cuadrillas (§10.6, §7.3, §7.6).

    Para efectos de costo, una cuadrilla es un concepto cuya composición es
    100% mano de obra: cada integrante se modela como un `Componente`
    (`domain.catalogos.apu`) con ``categoria=MANO_OBRA``, así que
    `calcular_cpu` devuelve un `PrecioUnitario` donde destajo == total
    siempre — "lo que cobra la cuadrilla es el 100% de su costo". Cero
    matemática nueva: se reutiliza tal cual lo que ya prueba `AplicadorCPU`.

    Un integrante (``MOOP-...``) es el individuo que ejecuta la obra dentro
    de la cuadrilla (el grupo) — no el destajo de `AplicadorManoObra` ni
    un insumo de un CPU. Confirmado con el usuario: este catálogo de
    personal **nunca se ha cargado por ningún otro archivo**, así que un
    integrante que no cruza se da de alta solo, con lo mínimo (clave,
    descripción, ``tipo=mano_obra``) — mismo criterio que unidad/familia
    (§8.7): el riesgo de un individuo de más no es el de un concepto o un
    precio en conflicto, se corrige después con un alta/homologación.
    """

    def __init__(
        self,
        *,
        cuadrillas: RepositorioCuadrillas,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        cargas: RepositorioCargas,
    ) -> None:
        self._cuadrillas = cuadrillas
        self._insumos = insumos
        self._unidades = unidades
        self._cargas = cargas

    async def aplicar(  # noqa: C901 — el flujo del §9.2 es lineal, no ramificado
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        cuadrillas_filas = await self._cuadrillas.listar(solo_activos=False)
        por_clave = {str(f["clave"]): f for f in cuadrillas_filas}

        insumos_filas = await self._insumos.listar(solo_activos=False)
        clave_de_insumo = {f["id"]: str(f["clave"]) for f in insumos_filas}
        id_insumo = {str(f["clave"]): f["id"] for f in insumos_filas}
        insumos = Homologador.desde(
            insumos_filas, mapeos=await self._cargas.mapeos("insumo")
        )
        costos_insumo = {
            str(f["clave"]): Decimal(
                str(f.get("costo_base_actualizado") or f.get("costo_base") or 0)
            )
            for f in insumos_filas
        }

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}

        pendientes: list[PendientePropuesto] = []
        errores: list[ErrorDeFila] = []
        entrantes: dict[str, dict[str, Any]] = {}
        planes: dict[str, dict[str, Any]] = {}
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevos_insumos: dict[str, UUID | None] = {}

        for registro in lectura.registros:
            bloque: CuadrillaCargada = registro  # type: ignore[assignment]
            cabeza = bloque.encabezado

            componentes: list[Componente] = []
            filas_integrantes: list[dict[str, Any]] = []
            incompleto = False

            for integrante in bloque.componentes:
                clave_insumo = str(integrante.clave_insumo)

                async def _dar_de_alta_integrante(
                    _datos: dict[str, Any],
                    *,
                    clave: str = clave_insumo,
                    descripcion: str = integrante.descripcion or clave_insumo,
                ) -> UUID:
                    return await self._insumos.crear_o_existente(
                        {
                            "tipo": str(TipoInsumo.MANO_OBRA),
                            "clave": clave,
                            "descripcion": descripcion,
                        }
                    )

                insumo_id = await _resolver_o_dar_de_alta(
                    clave_insumo,
                    homologador=insumos,
                    id_por_clave=id_insumo,
                    creadas=nuevos_insumos,
                    crear=_dar_de_alta_integrante,
                    dry_run=dry_run,
                )

                try:
                    del_dominio = Componente(
                        categoria=CategoriaExplosion.MANO_OBRA,
                        cantidad=integrante.cantidad,
                        clave_insumo=clave_insumo,
                        costo_unitario=integrante.costo_unitario or None,
                        orden=len(componentes),
                    )
                except ErrorDeAPU as exc:
                    errores.append(
                        ErrorDeFila(
                            fila=integrante.fila,
                            columna="cantidad",
                            valor=str(integrante.cantidad),
                            motivo=str(exc),
                        )
                    )
                    incompleto = True
                    continue

                componentes.append(del_dominio)
                costo = (
                    del_dominio.costo_unitario
                    if del_dominio.costo_unitario is not None
                    else costos_insumo.get(clave_insumo, Decimal(0))
                )
                filas_integrantes.append(
                    {
                        "insumo_id": insumo_id,
                        "cantidad": del_dominio.cantidad,
                        "costo_unitario": costo,
                        "importe": del_dominio.cantidad * costo,
                        "orden": len(filas_integrantes),
                    }
                )

            if incompleto:
                # Mismo criterio que un concepto con un insumo faltante: un
                # PU de cuadrilla con un hueco sale más barato que el real
                # y ese precio se propagaría a cada destajo que la use.
                continue

            actual = por_clave.get(bloque.llave, {})

            unidad_id = actual.get("unidad_id")
            if cabeza.unidad:
                unidad_id = await _resolver_o_dar_de_alta(
                    cabeza.unidad,
                    homologador=unidades,
                    id_por_clave=id_unidad,
                    creadas=nuevas_unidades,
                    crear=self._unidades.crear_o_existente,
                    dry_run=dry_run,
                )

            try:
                precio = calcular_cpu(
                    bloque.llave,
                    composiciones={bloque.llave: componentes},
                    costos_insumo=costos_insumo,
                )
            except ErrorDeAPU as exc:
                errores.append(
                    ErrorDeFila(
                        fila=cabeza.fila, columna="clave", valor=bloque.llave, motivo=str(exc)
                    )
                )
                continue

            entrantes[bloque.llave] = {
                "nombre": cabeza.descripcion,
                "unidad_id": unidad_id,
                "composicion": _firma_cuadrilla(filas_integrantes, clave_de_insumo),
            }
            planes[bloque.llave] = {"filas_integrantes": filas_integrantes, "precio": precio}

        vigentes: dict[str, dict[str, Any]] = {}
        for clave, vigente_fila in por_clave.items():
            # La composición vigente solo se lee de las cuadrillas que el
            # archivo toca: para las demás el diff únicamente mira si están
            # o no (bajas del modo Reemplazar, §10.2).
            composicion = ""
            if clave in entrantes:
                version_vigente = next(
                    (
                        v
                        for v in await self._cuadrillas.versiones(vigente_fila["id"])
                        if v["vigente"]
                    ),
                    None,
                )
                if version_vigente is not None:
                    composicion = _firma_cuadrilla(
                        await self._cuadrillas.integrantes_de(version_vigente["id"]),
                        clave_de_insumo,
                    )
            vigentes[clave] = {
                "nombre": vigente_fila.get("nombre"),
                "unidad_id": vigente_fila.get("unidad_id"),
                "composicion": composicion,
            }

        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for cambio in (*diff.altas, *diff.cambios):
                plan = planes[cambio.clave]
                fila = por_clave.get(cambio.clave)

                if fila is None:
                    cuadrilla_id = await self._cuadrillas.crear(
                        {
                            "clave": cambio.clave,
                            "nombre": cambio.despues["nombre"],
                            "unidad_id": cambio.despues["unidad_id"],
                        }
                    )
                    operaciones.append(
                        _operacion(
                            "cuadrilla", cuadrilla_id, "insert", despues={"clave": cambio.clave}
                        )
                    )
                else:
                    cuadrilla_id = fila["id"]
                    cambios_cuadrilla = {
                        "nombre": cambio.despues["nombre"],
                        "unidad_id": cambio.despues["unidad_id"],
                    }
                    await self._cuadrillas.actualizar(cuadrilla_id, cambios_cuadrilla)
                    operaciones.append(
                        _operacion(
                            "cuadrilla",
                            cuadrilla_id,
                            "update",
                            antes=_recorte(fila, ("nombre", "unidad_id", "estatus")),
                            despues=cambios_cuadrilla,
                        )
                    )

                operaciones.extend(
                    await _publicar_version_de_cuadrilla(
                        self._cuadrillas, cuadrilla_id, plan["filas_integrantes"], plan["precio"]
                    )
                )

            for baja in diff.bajas:
                fila = por_clave[baja.clave]
                # Baja lógica, igual que insumo/concepto: no se toca el
                # historial de versiones, solo el estatus del catálogo.
                await self._cuadrillas.actualizar(fila["id"], {"estatus": _ESTATUS_BAJA})
                operaciones.append(
                    _operacion(
                        "cuadrilla",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, ("nombre", "unidad_id", "estatus")),
                        despues={"estatus": _ESTATUS_BAJA},
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            errores=tuple(errores),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios) + len(diff.bajas),
            omitidos=diff.omitidos + lectura.omitidos,
            detalle={
                "unidades_creadas": len(nuevas_unidades),
                "integrantes_creados": len(nuevos_insumos),
            },
        )


async def _publicar_version_de_cuadrilla(
    cuadrillas: RepositorioCuadrillas,
    cuadrilla_id: UUID,
    filas_integrantes: list[dict[str, Any]],
    precio: PrecioUnitario,
) -> list[dict[str, Any]]:
    """Publica la versión nueva de PU de una cuadrilla y su composición (§10.8).

    A diferencia de `_publicar_cpu_de_concepto`, no hay una fila "viva" de
    composición que sustituir: `cuadrilla_integrante.cuadrilla_version_id`
    no admite nulo, así que cada versión es dueña exclusiva de sus filas —
    basta con insertar las de la versión nueva; las de versiones anteriores
    quedan intactas, que es justo el historial que se pidió (§10.8).
    """
    operaciones: list[dict[str, Any]] = []

    versiones = await cuadrillas.versiones(cuadrilla_id)
    vigentes_antes = {f["id"]: dict(f) for f in versiones if bool(f["vigente"])}
    nueva, retiradas = publicar_version(
        [_version_de_cuadrilla(f) for f in versiones], precio, variante=None
    )
    for identificador, fila in vigentes_antes.items():
        if int(fila["version"]) in retiradas:
            operaciones.append(
                _operacion(
                    "cuadrilla_version",
                    identificador,
                    "update",
                    antes={"precio_unitario": fila["precio_unitario"], "vigente": True},
                    despues={"vigente": False},
                )
            )

    version_id = await cuadrillas.publicar_version(
        cuadrilla_id,
        version=nueva.version,
        precio_unitario=nueva.precio.total.monto,
        retirar=list(retiradas),
    )
    operaciones.append(
        _operacion("cuadrilla_version", version_id, "insert", despues={"version": nueva.version})
    )

    insertadas = await cuadrillas.agregar_integrantes(version_id, filas_integrantes)
    for fila in insertadas:
        operaciones.append(_operacion("cuadrilla_integrante", fila["id"], "insert"))

    return operaciones


def _version_de_cuadrilla(fila: dict[str, Any]) -> VersionCPU:
    # El destajo de una cuadrilla siempre es el 100% de su costo (§7.3): no
    # hay una columna `precio_destajo` propia que leer, a diferencia de `cpu`.
    return VersionCPU(
        version=int(fila["version"]),
        precio=PrecioUnitario(
            total=Dinero(Decimal(str(fila["precio_unitario"]))),
            destajo=Dinero(Decimal(str(fila["precio_unitario"]))),
        ),
        vigente=bool(fila["vigente"]),
        variante=None,
    )


def _firma_cuadrilla(filas: list[dict[str, Any]], clave_de_insumo: dict[Any, str]) -> str:
    """Composición de una cuadrilla como texto comparable (§10.8) — mismo
    criterio que `_firma_explosion`, sin `categoria`: todo integrante de una
    cuadrilla es mano de obra por definición."""
    partes = []
    for fila in sorted(filas, key=lambda f: int(f.get("orden") or 0)):
        clave = clave_de_insumo.get(fila.get("insumo_id"), "")
        cantidad = Decimal(str(fila.get("cantidad") or 0)).normalize() + Decimal(0)
        costo = Decimal(str(fila.get("costo_unitario") or 0)).normalize() + Decimal(0)
        partes.append(f"{clave}:{cantidad}:{costo}")
    return "|".join(partes)


# --- Movimientos de almacén (§10.6 `IMPORTAADOR_ALMACEN.xlsx`) ------------


class AplicadorAlmacen:
    """Movimientos de almacén (§10.6, §10.5, §7.7).

    Un archivo de almacén es un **libro de movimientos**, no un catálogo: sus
    renglones son altas y el §10.6 no le define clave de renglón. Por eso la
    idempotencia aquí es de **lote**: el mismo archivo no se aplica dos veces
    (hash, §10.8) y dentro del archivo se deduplica por la composición
    obra+material+fecha+motivo+cantidad+costo.

    Además baja la **valuación** del §10.5: `C/Último` de la fila más reciente
    de cada insumo pasa a `costo_ultimo` y a `costo_base_actualizado` —"el
    costo último más reciente (costo vigente)"—, con `origen = 'almacen'`.
    """

    def __init__(
        self,
        *,
        materiales: RepositorioMateriales,
        insumos: RepositorioInsumos,
        obras: RepositorioObras,
        contratistas: RepositorioContratistas,
        conceptos: RepositorioConceptos,
        familias: RepositorioFamilias,
        cargas: RepositorioCargas,
        tasa_iva: Decimal,
    ) -> None:
        self._materiales = materiales
        self._insumos = insumos
        self._obras = obras
        self._contratistas = contratistas
        self._conceptos = conceptos
        self._familias = familias
        self._cargas = cargas
        self._tasa_iva = tasa_iva

    async def aplicar(  # noqa: C901 — un cruce por catálogo, todos del §10.6
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        insumos_filas = await self._insumos.listar(solo_activos=False)
        insumos_por_clave = {str(f["clave"]): f for f in insumos_filas}
        insumos = Homologador.desde(
            insumos_filas, mapeos=await self._cargas.mapeos("insumo")
        )

        obras_filas = await self._obras.listar()
        obras_por_clave = {str(f["clave"]): f for f in obras_filas}
        obras = Homologador.desde(obras_filas, mapeos=await self._cargas.mapeos("obra"))

        motivos_filas = await self._materiales.listar_motivos(solo_activos=False)
        motivos_por_clave = {str(f["clave"]): f for f in motivos_filas}
        motivos = Homologador.desde(
            motivos_filas, mapeos=await self._cargas.mapeos("motivo_almacen")
        )

        contratistas_filas = await self._contratistas.listar(solo_activos=False)
        contratistas_por_clave = {str(f["clave"]): f for f in contratistas_filas}
        contratistas = Homologador.desde(
            contratistas_filas, mapeos=await self._cargas.mapeos("contratista")
        )

        conceptos_filas = await self._conceptos.listar(solo_activos=False)
        conceptos_por_clave = {str(f["clave"]): f for f in conceptos_filas}

        familias_por_id = {
            f["id"]: f for f in await self._familias.listar(solo_activos=False)
        }

        pendientes: list[PendientePropuesto] = []
        errores: list[ErrorDeFila] = []
        movimientos: list[tuple[FilaMovimiento, dict[str, Any]]] = []
        omitidos = lectura.omitidos
        importe_con_iva_total = Decimal(0)

        for registro in lectura.registros:
            movimiento: FilaMovimiento = registro  # type: ignore[assignment]

            clave_insumo = insumos.resolver(str(movimiento.clave_insumo))
            if clave_insumo is None:
                pendientes.append(
                    _pendiente_de_mapeo(
                        "insumo", str(movimiento.clave_insumo), movimiento.fila, critico=True
                    )
                )
                omitidos += 1
                continue

            clave_obra = obras.resolver(str(movimiento.clave_obra))
            if clave_obra is None:
                pendientes.append(
                    _pendiente_de_mapeo(
                        "obra", str(movimiento.clave_obra), movimiento.fila, critico=True
                    )
                )
                omitidos += 1
                continue

            clave_motivo = motivos.resolver(movimiento.motivo)
            if clave_motivo is None:
                # §10.5: "Motivo no catalogado -> bandeja de pendientes". Es
                # semilla editable (§8.7): el usuario lo agrega con su
                # signo/bucket y la carga se puede repetir.
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.MOTIVO_ALMACEN,
                        entidad="motivo_almacen",
                        valor_origen=movimiento.motivo,
                        propuesta={
                            "signo": 1 if movimiento.cantidad > 0 else -1,
                            "accion": (
                                "Dar de alta el motivo con su signo y bucket de "
                                "KPI (§10.5)."
                            ),
                        },
                        critico=True,
                        origen_ref=f"fila {movimiento.fila}",
                    )
                )
                omitidos += 1
                continue

            motivo = motivos_por_clave[clave_motivo]
            try:
                # El signo viene del archivo (§10.5); esto solo verifica que
                # no contradiga al motivo elegido — misma regla que la captura
                # manual de `POST /obras/{id}/salidas`.
                validar_signo_salida(movimiento.cantidad, int(motivo["signo"]))
            except ErrorDeMaterial as exc:
                errores.append(
                    ErrorDeFila(
                        fila=movimiento.fila,
                        columna="cantidad",
                        valor=str(movimiento.cantidad),
                        motivo=str(exc),
                    )
                )
                continue

            contratista_id = None
            if movimiento.contratista:
                clave_contratista = contratistas.resolver(movimiento.contratista)
                if clave_contratista is None:
                    pendientes.append(
                        _pendiente_de_mapeo(
                            "contratista",
                            movimiento.contratista,
                            movimiento.fila,
                            critico=False,
                        )
                    )
                else:
                    contratista_id = contratistas_por_clave[clave_contratista]["id"]

            concepto_id = None
            if movimiento.clave_concepto:
                fila_concepto = conceptos_por_clave.get(movimiento.clave_concepto)
                if fila_concepto is None:
                    pendientes.append(
                        _pendiente_de_mapeo(
                            "concepto",
                            movimiento.clave_concepto,
                            movimiento.fila,
                            critico=False,
                        )
                    )
                else:
                    concepto_id = fila_concepto["id"]

            insumo = insumos_por_clave[clave_insumo]
            familia = familias_por_id.get(insumo.get("familia_id"))
            aplica_iva = resolver_iva(
                iva_familia=bool(familia["iva_aplica"]) if familia else True,
                override_insumo=insumo.get("iva_aplica"),
            )
            importe_con_iva_total += importe_con_iva(
                movimiento.costo, aplica_iva=aplica_iva, tasa=self._tasa_iva
            )

            movimientos.append(
                (
                    movimiento,
                    {
                        "obra_id": obras_por_clave[clave_obra]["id"],
                        "insumo_id": insumo["id"],
                        "motivo_id": motivo["id"],
                        "concepto_id": concepto_id,
                        "contratista_id": contratista_id,
                        "carga_id": carga_id,
                        "fecha": movimiento.fecha,
                        "cantidad": movimiento.cantidad,
                        "costo": movimiento.costo,
                        "costo_ultimo": movimiento.costo_ultimo,
                        "almacen": movimiento.almacen,
                        "referencia": movimiento.clave_concepto,
                    },
                )
            )

        entrantes = {
            movimiento.llave: {"cantidad": movimiento.cantidad, "costo": movimiento.costo}
            for movimiento, _ in movimientos
        }
        # Contra `{}`: el §10.6 no da clave de renglón para este archivo, así
        # que no hay "vigente" con qué comparar fila a fila. La idempotencia
        # es de lote, por hash (§10.8).
        diff = diferenciar(vigentes={}, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for _, datos in movimientos:
                salida_id = await self._materiales.crear_salida(datos)
                operaciones.append(_operacion("salida_almacen", salida_id, "insert"))

            operaciones.extend(
                await self._valuar(movimientos, insumos_por_clave, insumos)
            )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            errores=tuple(errores),
            insertados=len(movimientos),
            actualizados=0,
            omitidos=omitidos,
            detalle={
                "importe_con_iva": str(importe_con_iva_total),
                "tasa_iva": str(self._tasa_iva),
            },
        )

    async def _valuar(
        self,
        movimientos: list[tuple[FilaMovimiento, dict[str, Any]]],
        insumos_por_clave: dict[str, dict[str, Any]],
        homologador: Homologador,
    ) -> list[dict[str, Any]]:
        """Baja `C/Último` al catálogo como costo vigente (§10.5).

        "El sistema calcula `costo_promedio_almacen` desde el costo último;
        `costo_base_actualizado` = el costo último **más reciente** (costo
        vigente)". Por eso gana la fila de **fecha mayor**, no la última del
        archivo: el orden del Excel no es cronológico.
        """
        ultimos: dict[str, tuple[object, Decimal]] = {}
        for movimiento, _ in movimientos:
            if movimiento.costo_ultimo is None:
                continue
            clave = homologador.resolver(str(movimiento.clave_insumo))
            if clave is None:
                continue
            previo = ultimos.get(clave)
            if previo is None or movimiento.fecha >= previo[0]:  # type: ignore[operator]
                ultimos[clave] = (movimiento.fecha, movimiento.costo_ultimo)

        operaciones: list[dict[str, Any]] = []
        for clave, (_, costo) in ultimos.items():
            insumo = insumos_por_clave[clave]
            if (
                insumo.get("costo_ultimo") == costo
                and insumo.get("costo_base_actualizado") == costo
                and insumo.get("origen") == "almacen"
            ):
                continue
            await self._insumos.actualizar(
                insumo["id"],
                {
                    "costo_ultimo": costo,
                    "costo_base_actualizado": costo,
                    "origen": "almacen",
                },
            )
            operaciones.append(
                _operacion(
                    "insumo",
                    insumo["id"],
                    "update",
                    antes=_recorte(insumo, _CAMPOS_RESTAURABLES_INSUMO),
                    despues={"costo_ultimo": costo, "origen": "almacen"},
                )
            )
        return operaciones


# --- Prototipos (extensión propia, no está en el §10.6) -------------------

_CAMPOS_PROTOTIPO = ("nombre", "m2", "niveles", "recamaras")
"""Campos que este cargador gobierna. `proyecto_id` y `clave` son la
identidad de la fila (§3.3): un renglón cuya clave ya existe **nunca**
reasigna su proyecto por carga, solo actualiza estos cuatro."""


class AplicadorPrototipos:
    """Prototipos — bulk-load de `POST /prototipos` (§7.2).

    Sin `Homologador`: el único cruce es el proyecto por su clave, y una
    clave que no existe exacto es un error de fila, no algo que adivinar
    (mismo criterio que "la clave manda" en materiales, §3.3).

    No soporta el modo Reemplazar: `prototipo` no tiene columna `estatus`,
    así que no hay baja lógica que ejecutar sobre lo que el archivo ya no
    trae.
    """

    def __init__(
        self,
        *,
        prototipos: RepositorioPrototipos,
        proyectos: RepositorioProyectos,
    ) -> None:
        self._prototipos = prototipos
        self._proyectos = proyectos

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        if modo is ModoCarga.REEMPLAZAR:
            raise ErrorDeProyecto(
                "Prototipos no soporta el modo Reemplazar: no tiene baja "
                "lógica (§10.2). Usa Actualizar o Acumular."
            )

        vigentes_filas = await self._prototipos.listar()
        por_clave = {str(f["clave"]): f for f in vigentes_filas}

        proyectos_filas = await self._proyectos.listar()
        proyecto_id_por_clave = {str(p["clave"]): p["id"] for p in proyectos_filas}

        errores: list[ErrorDeFila] = []
        entrantes: dict[str, dict[str, Any]] = {}
        proyecto_id_por_llave: dict[str, Any] = {}

        # La validación de dominio (`Prototipo.crear`) corre aquí, **antes**
        # del diff y sin importar `dry_run`: si se dejara para el commit, la
        # vista previa contaría una fila con `niveles=0` como alta válida y
        # el aplicar real la rechazaría — números distintos entre los dos,
        # que es justo lo que "el dry-run tiene que dar los mismos números
        # que el commit" (§9.3) prohíbe.
        for registro in lectura.registros:
            prototipo: FilaPrototipo = registro  # type: ignore[assignment]
            actual = por_clave.get(prototipo.llave, {})

            proyecto_id = proyecto_id_por_clave.get(prototipo.proyecto_clave)
            if proyecto_id is None and not actual:
                # Solo bloquea el alta: un renglón que ya existe se puede
                # actualizar aunque el archivo traiga un `proyecto_clave`
                # que ya no cruza (no se reasigna, ver `_CAMPOS_PROTOTIPO`).
                errores.append(
                    ErrorDeFila(
                        fila=prototipo.fila,
                        columna="proyecto_clave",
                        valor=prototipo.proyecto_clave,
                        motivo=(
                            f"proyecto_clave: no existe un proyecto con la "
                            f"clave {prototipo.proyecto_clave!r} (créalo primero "
                            f"en Creador de obra)."
                        ),
                    )
                )
                continue

            proyecto_id_efectivo = proyecto_id or actual.get("proyecto_id")
            try:
                dominio = Prototipo.crear(
                    proyecto_id=str(proyecto_id_efectivo),
                    clave=prototipo.llave,
                    nombre=prototipo.nombre,
                    m2=_o_vigente(prototipo.m2, actual, "m2"),
                    niveles=_o_vigente(prototipo.niveles, actual, "niveles"),
                    recamaras=_o_vigente(prototipo.recamaras, actual, "recamaras"),
                )
            except ErrorDeProyecto as exc:
                errores.append(ErrorDeFila(fila=prototipo.fila, motivo=str(exc)))
                continue

            proyecto_id_por_llave[prototipo.llave] = dominio.proyecto_id
            entrantes[prototipo.llave] = {
                "nombre": dominio.nombre,
                "m2": dominio.m2,
                "niveles": dominio.niveles,
                "recamaras": dominio.recamaras,
            }

        vigentes = {
            clave: {campo: fila.get(campo) for campo in _CAMPOS_PROTOTIPO}
            for clave, fila in por_clave.items()
        }
        diff = diferenciar(vigentes=vigentes, entrantes=entrantes, modo=modo)

        operaciones: list[dict[str, Any]] = []
        if not dry_run:
            for alta in diff.altas:
                nuevo_id = await self._prototipos.crear(
                    {
                        "proyecto_id": proyecto_id_por_llave[alta.clave],
                        "clave": alta.clave,
                        "nombre": alta.despues["nombre"],
                        "m2": alta.despues["m2"],
                        "niveles": alta.despues["niveles"],
                        "recamaras": alta.despues["recamaras"],
                    }
                )
                operaciones.append(
                    _operacion(
                        "prototipo", nuevo_id, "insert", despues=dict(alta.despues)
                    )
                )

            for cambio in diff.cambios:
                fila = por_clave[cambio.clave]
                await self._prototipos.actualizar(fila["id"], dict(cambio.despues))
                operaciones.append(
                    _operacion(
                        "prototipo",
                        fila["id"],
                        "update",
                        antes=_recorte(fila, _CAMPOS_PROTOTIPO),
                        despues=dict(cambio.despues),
                    )
                )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            errores=tuple(errores),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios),
            omitidos=diff.omitidos + lectura.omitidos,
        )


# --- Presupuesto jerárquico (extensión propia, no está en el §10.6) -------

_CATEGORIA_POR_TIPO_NODO: dict[TipoNodoPresupuesto, CategoriaExplosion] = {
    TipoNodoPresupuesto.MATERIAL: CategoriaExplosion.MATERIAL,
    TipoNodoPresupuesto.DESTAJO: CategoriaExplosion.DESTAJO,
    TipoNodoPresupuesto.SUBCONTRATO: CategoriaExplosion.SUBCONTRATO,
}


def _clave_catalogo_concepto(nodo: NodoLeido, arbol: ArbolPrototipoCargado) -> str:
    """La clave que identifica el concepto en el catálogo compartido.

    Un `CONCEPTO` real —el "Concepto CPU", el mismo universo que carga
    `AplicadorCPU` desde `CABECERAS_CPU.xlsx`— usa su propia clave de
    archivo tal cual (`EST-01`), sin modificar: es la misma clave única
    (`uq_concepto_clave`, por organización) que cualquier otro prototipo
    que la repita. Así el árbol de ingeniería por prototipo **reconoce**
    el concepto ya cargado por el catálogo de CPU en vez de crear uno
    nuevo por prototipo (decisión revertida: antes namespaceaba TODO nodo
    por igual — ver `_procesar_concepto` para qué hace con la clave una
    vez resuelta, y por qué el `CONCEPTO` real no pasa por el conflicto de
    ahí abajo).

    `CONCEPTO_AUXILIAR` y la etapa que colapsa en concepto
    (`es_etapa_con_componentes_directos`) **sí siguen namespaceados** por
    prototipo, sin cambio: su clave de archivo (`ACA-01080`, o la propia
    `ECO-00002` de la etapa) se repite idéntica en cada prototipo con una
    composición que legítimamente cambia de uno a otro —no son la misma
    identidad de catálogo aunque compartan clave de archivo—, así que
    compartir fila ahí generaría un `CONCEPTO_EN_CONFLICTO` falso en casi
    cada fila de ese tipo (bug real, ya cubierto por
    `test_etapa_colapsada_con_cantidades_distintas_no_es_conflicto`).
    """
    if nodo.tipo is TipoNodoPresupuesto.CONCEPTO:
        return nodo.clave
    return f"{nodo.clave}~{arbol.clave_prototipo}"


async def _precio_vigente_de_concepto(
    conceptos: RepositorioConceptos, concepto_id: UUID
) -> Decimal | None:
    """El precio total del CPU vigente (receta base, `variante=null`) de un
    concepto ya publicado, o `None` si el concepto existe en catálogo pero
    todavía no tiene ningún CPU —solo identidad, sembrado por "Catálogo de
    Conceptos" (§10.6) sin pasar todavía por "Conceptos CPU"—: ahí no hay
    nada vigente que referenciar."""
    for version in await conceptos.versiones_cpu(concepto_id):
        if bool(version["vigente"]) and version["variante"] is None:
            return Decimal(str(version["precio_unitario"]))
    return None


class AplicadorPresupuesto:
    """Árbol de un prototipo (nivel → etapa → concepto) y su presupuesto
    (§7.4, §7.3, extensión propia — no está en el §10.6).

    Puebla tres cosas que hasta hoy nadie escribía: el árbol WBS
    (`prototipo_nodo`), el catálogo compartido de niveles/etapas, y el
    presupuesto versionado del prototipo. El catálogo de conceptos/APU es el
    mismo de siempre (`concepto`/`explosion`/`cpu`, `variante=null`) — este
    aplicador reutiliza `_publicar_cpu_de_concepto`, la misma función que usa
    `AplicadorCPU`.

    **`CONCEPTO` real: el cargador es una guía, no la fuente de verdad.**
    Un `CONCEPTO` (`tipo=concepto`, "Concepto CPU") se busca por su propia
    clave en el catálogo compartido (`_clave_catalogo_concepto`). Si ya
    tiene un CPU vigente, la fila del archivo se ignora del todo —ni se
    procesan sus materiales, ni se compara composición— y la partida de
    este prototipo usa ese precio ya vigente tal cual: publicar una versión
    nueva de CPU es trabajo exclusivo del cargador "Conceptos CPU"
    (`AplicadorCPU`), este solo lo referencia. Si la clave no existe en el
    catálogo, o existe solo como identidad sin CPU todavía, el archivo SÍ
    es la fuente: se publica el CPU con la composición que trae esa fila
    (alta o primer CPU), sin pasar por conflicto —no hay nada vigente que
    pudiera pisarse.

    **`CONCEPTO_AUXILIAR` y etapa colapsada: conflicto de catálogo, no
    sobrescritura silenciosa.** Estos dos siguen namespaceados por
    prototipo (`_clave_catalogo_concepto`), sin cambio. Si la composición
    coincide con la vigente, se publica igual que siempre. Si difiere, el
    catálogo **se queda como estaba** —no se toca `concepto`/`explosion`/
    `cpu`— y se registra `TipoPendiente.CONCEPTO_EN_CONFLICTO` (no crítico)
    para que alguien lo resuelva a mano. La partida de presupuesto de este
    prototipo usa siempre el precio calculado de **su propia** composición,
    haya o no conflicto: nunca hereda en silencio el precio de otro
    prototipo por un conflicto no resuelto.

    **No hay `Homologador` de proyecto**: este cargador no da de alta
    prototipos (el archivo no trae proyecto, §7.2) — solo identifica por
    clave uno ya existente. Uno que no cruza es error de fila crítico; el
    resto del archivo sigue.
    """

    def __init__(
        self,
        *,
        conceptos: RepositorioConceptos,
        insumos: RepositorioInsumos,
        unidades: RepositorioUnidades,
        prototipos: RepositorioPrototipos,
        prototipo_nodos: RepositorioPrototipoNodo,
        niveles_etapas: RepositorioNivelesEtapas,
        presupuestos: RepositorioPresupuestos,
        cargas: RepositorioCargas,
    ) -> None:
        self._conceptos = conceptos
        self._insumos = insumos
        self._unidades = unidades
        self._prototipos = prototipos
        self._prototipo_nodos = prototipo_nodos
        self._niveles_etapas = niveles_etapas
        self._presupuestos = presupuestos
        self._cargas = cargas

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        if modo is ModoCarga.REEMPLAZAR:
            raise ErrorDeProyecto(
                "Presupuesto no soporta el modo Reemplazar: recargar ya "
                "sustituye el árbol del prototipo por una versión nueva "
                "(§10.2). Usa Actualizar."
            )

        prototipos_filas = await self._prototipos.listar()
        prototipo_por_clave = {str(f["clave"]): f for f in prototipos_filas}

        conceptos_filas = await self._conceptos.listar(solo_activos=False)
        catalogo_conceptos: dict[str, dict[str, Any]] = {
            str(f["clave"]): dict(f) for f in conceptos_filas
        }
        firma_cache: dict[str, str] = {}

        insumos_filas = await self._insumos.listar(solo_activos=False)
        insumos_por_clave = {str(f["clave"]): f for f in insumos_filas}
        clave_de_insumo = {f["id"]: str(f["clave"]) for f in insumos_filas}
        id_insumo = {str(f["clave"]): f["id"] for f in insumos_filas}
        insumos = Homologador.desde(
            insumos_filas, mapeos=await self._cargas.mapeos("insumo")
        )
        costos_insumo = {
            str(f["clave"]): Decimal(
                str(f.get("costo_base_actualizado") or f.get("costo_base") or 0)
            )
            for f in insumos_filas
        }

        unidades_filas = await self._unidades.listar(solo_activos=False)
        unidades = Homologador.desde(
            unidades_filas, mapeos=await self._cargas.mapeos("unidad")
        )
        id_unidad = {str(f["clave"]): f["id"] for f in unidades_filas}

        errores: list[ErrorDeFila] = []
        pendientes: list[PendientePropuesto] = []
        operaciones: list[dict[str, Any]] = []
        claves_nuevas: set[str] = set()
        claves_actualizadas: set[str] = set()
        contadores = {
            "prototipos_tocados": 0,
            "nodos_creados": 0,
            "nodos_actualizados": 0,
            "conceptos_en_conflicto": 0,
            "conceptos_omitidos": 0,
            "conceptos_sin_cambio": 0,
            "conceptos_referenciados": 0,
            "partidas": 0,
        }
        nuevas_unidades: dict[str, UUID | None] = {}
        nuevos_insumos: dict[str, UUID | None] = {}

        for registro in lectura.registros:
            arbol: ArbolPrototipoCargado = registro  # type: ignore[assignment]
            prototipo = prototipo_por_clave.get(arbol.clave_prototipo)
            if prototipo is None:
                errores.append(
                    ErrorDeFila(
                        fila=arbol.raiz.fila,
                        columna="clave_hijo",
                        valor=arbol.clave_prototipo,
                        motivo=(
                            f"El prototipo {arbol.clave_prototipo!r} no existe. "
                            f"Carga primero este prototipo con Cargas → "
                            f"Prototipos (§7.2)."
                        ),
                    )
                )
                continue

            contadores["prototipos_tocados"] += 1
            partidas: list[dict[str, Any]] = []
            # Capturado una vez por prototipo, antes de tocar nada: es el
            # `antes` que la reversa necesita por nodo (§10.8) — el `id` que
            # conserva un upsert no basta, hace falta el valor previo.
            # Por `(parent_id, clave)`, no solo clave: la misma clave puede
            # colgar de dos padres distintos dentro del mismo prototipo
            # (`uq_prototipo_nodo_posicion`, migración 0038) — indexar solo
            # por clave dejaría una de las dos ocurrencias sin su `anterior`.
            nodos_existentes = {
                (f["parent_id"], str(f["clave"])): dict(f)
                for f in await self._prototipo_nodos.por_prototipo(prototipo["id"])
                if f["clave"]
            }

            for hijo in arbol.hijos.get(arbol.raiz.fila, ()):
                await self._procesar_subarbol(
                    arbol=arbol,
                    nodo=hijo,
                    prototipo_id=prototipo["id"],
                    parent_id_db=None,
                    nivel_id_heredado=None,
                    dry_run=dry_run,
                    insumos=insumos,
                    insumos_por_clave=insumos_por_clave,
                    clave_de_insumo=clave_de_insumo,
                    id_insumo=id_insumo,
                    nuevos_insumos=nuevos_insumos,
                    costos_insumo=costos_insumo,
                    unidades=unidades,
                    id_unidad=id_unidad,
                    nuevas_unidades=nuevas_unidades,
                    catalogo_conceptos=catalogo_conceptos,
                    firma_cache=firma_cache,
                    nodos_existentes=nodos_existentes,
                    operaciones=operaciones,
                    partidas=partidas,
                    errores=errores,
                    pendientes=pendientes,
                    contadores=contadores,
                    claves_nuevas=claves_nuevas,
                    claves_actualizadas=claves_actualizadas,
                )

            if not dry_run and partidas:
                version = await self._presupuestos.crear_version(
                    prototipo["id"], origen="excel", carga_id=carga_id
                )
                if version.get("anterior_id") is not None:
                    # La versión que este `crear_version` acaba de retirar
                    # (`vigente=false`): sin registrar esta operación, la
                    # reversa no sabría devolverla a vigente (§10.8).
                    operaciones.append(
                        _operacion(
                            "presupuesto",
                            version["anterior_id"],
                            "update",
                            antes={"vigente": True},
                            despues={"vigente": False},
                        )
                    )
                operaciones.append(
                    _operacion(
                        "presupuesto",
                        version["id"],
                        "insert",
                        despues={"version": version["version"]},
                    )
                )
                insertadas = await self._presupuestos.agregar_partidas(
                    version["id"], partidas
                )
                for fila in insertadas:
                    operaciones.append(
                        _operacion("partida_presupuesto", fila["id"], "insert")
                    )
                monto_total = sum(
                    (Decimal(str(p["importe"])) for p in partidas), Decimal(0)
                )
                await self._presupuestos.actualizar_monto_total(version["id"], monto_total)

        # Diff sintético: este cargador no tiene un conjunto plano por clave
        # que diferenciar (es un árbol, no una lista), pero `hay_cambios`
        # sigue decidiendo si la carga genera versión propia (§10.8) — y las
        # claves de concepto tocadas son justo lo que ese resumen necesita
        # decir.
        diff = Diff(
            altas=tuple(Cambio(clave=c, despues={}) for c in sorted(claves_nuevas)),
            cambios=tuple(
                Cambio(clave=c, despues={}) for c in sorted(claves_actualizadas)
            ),
        )

        etapas_con_nivel = (
            0 if dry_run else await self._niveles_etapas.derivar_nivel_desde_arbol()
        )

        return Aplicacion(
            diff=diff,
            operaciones=tuple(operaciones),
            pendientes=tuple(pendientes),
            errores=tuple(errores),
            insertados=len(diff.altas),
            actualizados=len(diff.cambios),
            omitidos=(
                contadores["conceptos_omitidos"]
                + contadores["conceptos_sin_cambio"]
                + contadores["conceptos_referenciados"]
                + lectura.omitidos
            ),
            detalle={
                **contadores,
                "unidades_creadas": len(nuevas_unidades),
                "insumos_creados": len(nuevos_insumos),
                # El árbol que este cargador acaba de construir es lo único que
                # dice de qué nivel cuelga cada etapa: el catálogo del §10.1 no
                # lo trae. Se deriva aquí, al terminar, para que agrupar la obra
                # por nivel —como la mira el residente— funcione sin que nadie
                # tenga que acordarse de un paso aparte.
                "etapas_con_nivel_derivado": etapas_con_nivel,
            },
        )

    async def _procesar_subarbol(
        self,
        *,
        arbol: ArbolPrototipoCargado,
        nodo: NodoLeido,
        prototipo_id: UUID,
        parent_id_db: UUID | None,
        nivel_id_heredado: UUID | None,
        dry_run: bool,
        insumos: Homologador,
        insumos_por_clave: dict[str, dict[str, Any]],
        clave_de_insumo: dict[Any, str],
        id_insumo: dict[str, Any],
        nuevos_insumos: dict[str, UUID | None],
        costos_insumo: dict[str, Decimal],
        unidades: Homologador,
        id_unidad: dict[str, Any],
        nuevas_unidades: dict[str, UUID | None],
        catalogo_conceptos: dict[str, dict[str, Any]],
        firma_cache: dict[str, str],
        nodos_existentes: dict[tuple[UUID | None, str], dict[str, Any]],
        operaciones: list[dict[str, Any]],
        partidas: list[dict[str, Any]],
        errores: list[ErrorDeFila],
        pendientes: list[PendientePropuesto],
        contadores: dict[str, int],
        claves_nuevas: set[str],
        claves_actualizadas: set[str],
    ) -> None:
        """Un nodo del árbol leído → `prototipo_nodo` (+ catálogo, si aplica).

        `NIVEL`/`ETAPA` (que no colapsan en concepto, ver
        `es_etapa_con_componentes_directos`) recursan hacia sus hijos.
        `CONCEPTO`/`CONCEPTO_AUXILIAR` (o una etapa que colapsa) son hojas
        del árbol: sus hijos `MATERIAL`/`DESTAJO`/`SUBCONTRATO` no se
        convierten en `prototipo_nodo` — se consumen como la explosión del
        concepto.

        El alta/actualización se decide contra `nodos_existentes` **antes**
        de escribir, sin importar `dry_run`: es lo que hace que la vista
        previa cuente igual que el commit (§9.3).
        """
        es_concepto_efectivo = nodo.tipo in (
            TipoNodoPresupuesto.CONCEPTO,
            TipoNodoPresupuesto.CONCEPTO_AUXILIAR,
        ) or (
            nodo.tipo is TipoNodoPresupuesto.ETAPA
            and es_etapa_con_componentes_directos(arbol, nodo)
        )

        if es_concepto_efectivo:
            await self._procesar_concepto(
                arbol=arbol,
                nodo=nodo,
                prototipo_id=prototipo_id,
                parent_id_db=parent_id_db,
                dry_run=dry_run,
                insumos=insumos,
                insumos_por_clave=insumos_por_clave,
                clave_de_insumo=clave_de_insumo,
                id_insumo=id_insumo,
                nuevos_insumos=nuevos_insumos,
                costos_insumo=costos_insumo,
                unidades=unidades,
                id_unidad=id_unidad,
                nuevas_unidades=nuevas_unidades,
                catalogo_conceptos=catalogo_conceptos,
                firma_cache=firma_cache,
                nodos_existentes=nodos_existentes,
                operaciones=operaciones,
                partidas=partidas,
                errores=errores,
                pendientes=pendientes,
                contadores=contadores,
                claves_nuevas=claves_nuevas,
                claves_actualizadas=claves_actualizadas,
            )
            return

        anterior = nodos_existentes.get((parent_id_db, nodo.clave))
        es_alta = anterior is None
        contadores["nodos_creados" if es_alta else "nodos_actualizados"] += 1

        nivel_id_db = nivel_id_heredado
        etapa_id_db = None
        nodo_id: UUID | None = anterior["id"] if anterior else None

        if not dry_run:
            if nodo.tipo is TipoNodoPresupuesto.NIVEL:
                nivel_id_db = await self._niveles_etapas.upsert_nivel(
                    clave=nodo.clave, descripcion=nodo.descripcion, orden=nodo.indice or 0
                )
            elif nodo.tipo is TipoNodoPresupuesto.ETAPA:
                etapa_id_db = await self._niveles_etapas.upsert_etapa(
                    clave=nodo.clave,
                    descripcion=nodo.descripcion,
                    nivel_id=nivel_id_heredado,
                    orden=nodo.indice or 0,
                )

            nodo_id, _ = await self._prototipo_nodos.upsert(
                prototipo_id,
                clave=nodo.clave,
                datos={
                    "parent_id": parent_id_db,
                    "tipo": "nivel" if nodo.tipo is TipoNodoPresupuesto.NIVEL else "etapa",
                    "nombre": nodo.descripcion,
                    "nivel_id": nivel_id_db if nodo.tipo is TipoNodoPresupuesto.NIVEL else None,
                    "etapa_id": etapa_id_db,
                    "orden": nodo.indice or 0,
                    "cantidad": nodo.cantidad or 0,
                },
            )
            operaciones.append(
                _operacion(
                    "prototipo_nodo",
                    nodo_id,
                    "insert" if es_alta else "update",
                    antes=_recorte(
                        anterior,
                        ("parent_id", "tipo", "nombre", "concepto_id", "nivel_id", "etapa_id", "orden", "cantidad"),
                    )
                    if anterior
                    else None,
                    despues={"clave": nodo.clave, "nombre": nodo.descripcion},
                )
            )

        for hijo in arbol.hijos.get(nodo.fila, ()):
            await self._procesar_subarbol(
                arbol=arbol,
                nodo=hijo,
                prototipo_id=prototipo_id,
                parent_id_db=nodo_id,
                nivel_id_heredado=nivel_id_db,
                dry_run=dry_run,
                insumos=insumos,
                insumos_por_clave=insumos_por_clave,
                clave_de_insumo=clave_de_insumo,
                id_insumo=id_insumo,
                nuevos_insumos=nuevos_insumos,
                costos_insumo=costos_insumo,
                unidades=unidades,
                id_unidad=id_unidad,
                nuevas_unidades=nuevas_unidades,
                catalogo_conceptos=catalogo_conceptos,
                firma_cache=firma_cache,
                nodos_existentes=nodos_existentes,
                operaciones=operaciones,
                partidas=partidas,
                errores=errores,
                pendientes=pendientes,
                contadores=contadores,
                claves_nuevas=claves_nuevas,
                claves_actualizadas=claves_actualizadas,
            )

    async def _procesar_concepto(
        self,
        *,
        arbol: ArbolPrototipoCargado,
        nodo: NodoLeido,
        prototipo_id: UUID,
        parent_id_db: UUID | None,
        dry_run: bool,
        insumos: Homologador,
        insumos_por_clave: dict[str, dict[str, Any]],
        clave_de_insumo: dict[Any, str],
        id_insumo: dict[str, Any],
        nuevos_insumos: dict[str, UUID | None],
        costos_insumo: dict[str, Decimal],
        unidades: Homologador,
        id_unidad: dict[str, Any],
        nuevas_unidades: dict[str, UUID | None],
        catalogo_conceptos: dict[str, dict[str, Any]],
        firma_cache: dict[str, str],
        nodos_existentes: dict[tuple[UUID | None, str], dict[str, Any]],
        operaciones: list[dict[str, Any]],
        partidas: list[dict[str, Any]],
        errores: list[ErrorDeFila],
        pendientes: list[PendientePropuesto],
        contadores: dict[str, int],
        claves_nuevas: set[str],
        claves_actualizadas: set[str],
    ) -> None:
        """Un nodo CONCEPTO/CONCEPTO_AUXILIAR (o etapa-colapsada): arma su
        APU desde sus hijos, decide alta/actualiza/conflicto contra el
        catálogo, y registra su partida de presupuesto.

        Para `CONCEPTO` con CPU vigente ya publicado, ni siquiera llega a
        armar el APU: se resuelve antes, referenciando ese precio tal
        cual (ver docstring de la clase)."""
        clave_catalogo = _clave_catalogo_concepto(nodo, arbol)
        actual = catalogo_conceptos.get(clave_catalogo)

        # `actual["id"]` es `None` cuando `actual` es el alta de ESTE MISMO
        # archivo que un `dry_run` dejó sin id real (§9.3: la vista previa
        # no escribe) — típicamente otro prototipo de este mismo lote
        # introduciendo la misma clave nueva. Sin id no hay CPU que
        # consultar; se trata como conflicto/alta más abajo, no como
        # referencia (ver el `elif actual is None` de la rama namespaceada
        # para el mismo criterio).
        if (
            nodo.tipo is TipoNodoPresupuesto.CONCEPTO
            and actual is not None
            and actual.get("id") is not None
        ):
            precio_vigente = await _precio_vigente_de_concepto(self._conceptos, actual["id"])
            if precio_vigente is not None:
                contadores["conceptos_referenciados"] += 1
                await self._registrar_nodo_y_partida(
                    nodo=nodo,
                    concepto_id=actual["id"],
                    precio_unitario=precio_vigente,
                    parent_id_db=parent_id_db,
                    prototipo_id=prototipo_id,
                    dry_run=dry_run,
                    nodos_existentes=nodos_existentes,
                    operaciones=operaciones,
                    partidas=partidas,
                    contadores=contadores,
                )
                return

        componentes: list[Componente] = []
        filas_explosion: list[dict[str, Any]] = []
        incompleto = False

        for hijo in arbol.hijos.get(nodo.fila, ()):
            categoria = _CATEGORIA_POR_TIPO_NODO.get(hijo.tipo)
            if categoria is None:
                # No debería pasar: `construir_arboles` solo cuelga hojas de
                # tipo MATERIAL/DESTAJO/SUBCONTRATO de un concepto.
                continue

            clave_insumo = insumos.resolver(hijo.clave) or hijo.clave

            async def _dar_de_alta_insumo(
                _datos: dict[str, Any],
                *,
                _hijo: NodoLeido = hijo,
                _categoria: CategoriaExplosion = categoria,
                clave: str = hijo.clave,
            ) -> UUID:
                unidad_insumo_id = None
                if _hijo.unidad:
                    unidad_insumo_id = await _resolver_o_dar_de_alta(
                        _hijo.unidad,
                        homologador=unidades,
                        id_por_clave=id_unidad,
                        creadas=nuevas_unidades,
                        crear=self._unidades.crear_o_existente,
                        dry_run=dry_run,
                    )
                return await self._insumos.crear_o_existente(
                    {
                        "tipo": str(_TIPO_INSUMO_POR_CATEGORIA[_categoria]),
                        "clave": clave,
                        "descripcion": _hijo.descripcion or clave,
                        "unidad_id": unidad_insumo_id,
                        "costo_base": _hijo.precio_unitario or Decimal(0),
                    }
                )

            insumo_id = await _resolver_o_dar_de_alta_con_alerta(
                hijo.clave,
                hijo.descripcion,
                homologador=insumos,
                id_por_clave=id_insumo,
                filas_por_clave=insumos_por_clave,
                creadas=nuevos_insumos,
                crear=_dar_de_alta_insumo,
                entidad="insumo",
                fila=hijo.fila,
                pendientes=pendientes,
                dry_run=dry_run,
            )
            if clave_insumo not in insumos_por_clave:
                # En `dry_run` sobre un insumo nuevo, `insumo_id` es `None`
                # (§9.3): igual se registra para que el `["id"]` de abajo no
                # truene; solo se lee de verdad dentro de `if not dry_run:`.
                insumos_por_clave[clave_insumo] = {"id": insumo_id}
            if clave_insumo not in costos_insumo:
                costos_insumo[clave_insumo] = hijo.precio_unitario or Decimal(0)

            if hijo.cantidad is None:
                cantidad = Decimal(0)
            elif nodo.tipo in (
                TipoNodoPresupuesto.CONCEPTO,
                TipoNodoPresupuesto.CONCEPTO_AUXILIAR,
            ):
                # El árbol trae cantidades absolutas para este nodo del
                # prototipo, no ya el rendimiento por unidad (§7.3): dividir
                # entre lo que el propio concepto/auxiliar acumula es lo que
                # saca el PU real, comparable entre prototipos (§10.6).
                cantidad_padre = nodo.cantidad if nodo.cantidad else Decimal(1)
                cantidad = hijo.cantidad / cantidad_padre
            else:
                # Etapa colapsada: no tiene cantidad propia comparable (el
                # archivo la trae vacía) — su total ya es el de los hijos,
                # se usa tal cual.
                cantidad = hijo.cantidad
            try:
                del_dominio = Componente(
                    categoria=categoria,
                    cantidad=cantidad,
                    clave_insumo=clave_insumo,
                    costo_unitario=hijo.precio_unitario or None,
                    orden=len(componentes),
                )
            except ErrorDeAPU as exc:
                errores.append(
                    ErrorDeFila(
                        fila=hijo.fila,
                        columna="cantidad",
                        valor=str(hijo.cantidad),
                        motivo=str(exc),
                    )
                )
                incompleto = True
                continue

            componentes.append(del_dominio)
            costo = (
                del_dominio.costo_unitario
                if del_dominio.costo_unitario is not None
                else costos_insumo.get(clave_insumo, Decimal(0))
            )
            filas_explosion.append(
                {
                    "tipo_hijo": str(TipoHijoExplosion.INSUMO),
                    "insumo_id": insumos_por_clave[clave_insumo]["id"],
                    "categoria": str(categoria),
                    "cantidad": del_dominio.cantidad,
                    "rendimiento": del_dominio.cantidad,
                    "costo_unitario": costo,
                    "importe": del_dominio.cantidad * costo,
                    "orden": len(filas_explosion),
                }
            )

        if incompleto:
            # Un APU con un hueco daría un precio menor al real (§7.3, mismo
            # criterio que `AplicadorCPU`): el concepto se omite entero, y
            # con él su partida — no hay precio confiable que registrar.
            contadores["conceptos_omitidos"] += 1
            return

        try:
            precio = calcular_cpu(
                clave_catalogo,
                composiciones={clave_catalogo: componentes},
                costos_insumo=costos_insumo,
            )
        except ErrorDeAPU as exc:
            errores.append(
                ErrorDeFila(fila=nodo.fila, columna="clave_hijo", valor=nodo.clave, motivo=str(exc))
            )
            contadores["conceptos_omitidos"] += 1
            return

        unidad_id = actual.get("unidad_id") if actual else None
        if nodo.unidad:
            unidad_id = await _resolver_o_dar_de_alta(
                nodo.unidad,
                homologador=unidades,
                id_por_clave=id_unidad,
                creadas=nuevas_unidades,
                crear=self._unidades.crear_o_existente,
                dry_run=dry_run,
            )

        concepto_id: UUID | None = actual["id"] if actual else None

        if nodo.tipo is TipoNodoPresupuesto.CONCEPTO:
            # Sin CPU vigente que referenciar (si lo hubiera, ya se resolvió
            # arriba antes de procesar hijos): la clave no existe, o existe
            # solo como identidad sin CPU todavía (§10.6, "Catálogo de
            # Conceptos" sin pasar por "Conceptos CPU"). En ambos casos no
            # hay nada vigente que este archivo pudiera pisar — se publica
            # directo, sin el conflicto de la rama de abajo (esa es solo
            # para `CONCEPTO_AUXILIAR`/etapa colapsada, namespaceados).
            es_alta = actual is None
            if not dry_run:
                if es_alta:
                    concepto_id = await self._conceptos.crear(
                        {
                            "tipo": str(TipoConcepto.CONCEPTO),
                            "clave": clave_catalogo,
                            "descripcion": nodo.descripcion,
                            "unidad_id": unidad_id,
                            "familia_id": None,
                        }
                    )
                    operaciones.append(
                        _operacion(
                            "concepto", concepto_id, "insert", despues={"clave": clave_catalogo}
                        )
                    )
                assert concepto_id is not None  # noqa: S101 — alta lo asigna arriba; si no, ya existía
                operaciones.extend(
                    await _publicar_cpu_de_concepto(
                        self._conceptos, concepto_id, filas_explosion, precio
                    )
                )

            if es_alta:
                claves_nuevas.add(clave_catalogo)
                catalogo_conceptos[clave_catalogo] = {
                    "id": concepto_id,
                    "tipo": str(TipoConcepto.CONCEPTO),
                    "clave": clave_catalogo,
                    "descripcion": nodo.descripcion,
                    "unidad_id": unidad_id,
                    "familia_id": None,
                    "estatus": "activo",
                }
                # No se omite (§10.3): se da de alta igual, pero un humano
                # tiene que autorizarla — mismo `TipoPendiente` que ya usa
                # `AplicadorCPU` para esta misma situación (concepto que el
                # catálogo no conocía), ahora también desde el árbol de
                # prototipo.
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.CPU_NUEVO,
                        entidad="concepto",
                        valor_origen=clave_catalogo,
                        propuesta={
                            "descripcion": nodo.descripcion,
                            "precio_unitario": str(precio.total.monto),
                            "componentes": len(componentes),
                        },
                        origen_ref=f"fila {nodo.fila}",
                    )
                )
            else:
                # Ya existía como identidad: se le publica su primer CPU,
                # pero descripción/unidad siguen siendo las que trajo
                # "Catálogo de Conceptos" — esas no son de este cargador.
                claves_actualizadas.add(clave_catalogo)
        else:
            firma_nueva = _firma_explosion(filas_explosion, clave_de_insumo)

            diferente = False
            if actual is not None:
                firma_vigente = firma_cache.get(clave_catalogo)
                if firma_vigente is None:
                    # Sin firma en caché, `actual` solo puede venir del
                    # catálogo real (no de una simulación en dry_run de este
                    # mismo archivo — esa siempre deja firma en caché al
                    # procesar, línea de abajo): `concepto_id` es un id real.
                    assert concepto_id is not None  # noqa: S101
                    filas_previas = await self._conceptos.explosion_directa(concepto_id)
                    firma_vigente = _firma_explosion(filas_previas, clave_de_insumo)
                    firma_cache[clave_catalogo] = firma_vigente
                diferente = firma_vigente != firma_nueva

            conflicto = False
            if diferente and concepto_id is None:
                # `actual` es un alta de ESTE MISMO archivo que dry_run dejó
                # sin id real (no se llamó `crear()`, §9.3: la vista previa
                # no escribe). Sin fila en la base no hay
                # `otros_prototipos_con_partida_vigente` que consultar — pero
                # dos prototipos del mismo archivo proponiendo la primera
                # composición de una clave nueva y no coincidiendo entre sí
                # es exactamente el mismo desacuerdo que el conflicto real:
                # ninguno de los dos es "el vigente" todavía. Se resuelve
                # igual, sin tocar nada.
                conflicto = True
            elif diferente:
                assert concepto_id is not None  # noqa: S101 — cubierto arriba
                # Composición distinta a la vigente: ¿es un prototipo
                # DISTINTO el que ya depende de ella (conflicto real), o es
                # este mismo prototipo recargando una corrección
                # (actualización legítima, nadie más se queda con datos
                # viejos)? Las dos consultas son de solo lectura — se hacen
                # igual en dry_run, para que la vista previa cuente igual
                # que el commit (§9.3).
                otros = await self._presupuestos.otros_prototipos_con_partida_vigente(
                    concepto_id, excluir_prototipo_id=prototipo_id
                )
                si_mismo = await self._presupuestos.tiene_partida_vigente(
                    concepto_id, prototipo_id
                )
                # Si ni otro prototipo ni yo mismo tenemos una partida
                # vigente para este concepto, su composición vigente no vino
                # de ningún prototipo — vino del catálogo de CPU (§10.6), que
                # es quien manda ahí. Sobreescribirla en silencio le
                # quitaría al CPU su fuente de verdad; se trata igual que un
                # conflicto real.
                conflicto = bool(otros) or not si_mismo

            if conflicto:
                contadores["conceptos_en_conflicto"] += 1
                pendientes.append(
                    PendientePropuesto(
                        tipo=TipoPendiente.CONCEPTO_EN_CONFLICTO,
                        entidad="concepto",
                        valor_origen=clave_catalogo,
                        propuesta={
                            "prototipo": arbol.clave_prototipo,
                            "accion": (
                                "Composición distinta a la del catálogo; corrige a "
                                "mano o vuelve a cargar el prototipo correcto."
                            ),
                        },
                        critico=False,
                        origen_ref=f"fila {nodo.fila}",
                    )
                )
            elif actual is None:
                # Alta: clave nueva en el catálogo. Solo llega aquí
                # `CONCEPTO_AUXILIAR` o una etapa colapsada (`CONCEPTO` real
                # se resuelve arriba) — de ahí el default a `CONCEPTO` del
                # catálogo para la etapa, que nunca es auxiliar.
                tipo_concepto = (
                    TipoConcepto.AUXILIAR
                    if nodo.tipo is TipoNodoPresupuesto.CONCEPTO_AUXILIAR
                    else TipoConcepto.CONCEPTO
                )
                if not dry_run:
                    concepto_id = await self._conceptos.crear(
                        {
                            "tipo": str(tipo_concepto),
                            "clave": clave_catalogo,
                            "descripcion": nodo.descripcion,
                            "unidad_id": unidad_id,
                            "familia_id": None,
                        }
                    )
                    operaciones.append(
                        _operacion(
                            "concepto", concepto_id, "insert", despues={"clave": clave_catalogo}
                        )
                    )
                    operaciones.extend(
                        await _publicar_cpu_de_concepto(
                            self._conceptos, concepto_id, filas_explosion, precio
                        )
                    )

                claves_nuevas.add(clave_catalogo)
                catalogo_conceptos[clave_catalogo] = {
                    "id": concepto_id,
                    "tipo": str(tipo_concepto),
                    "clave": clave_catalogo,
                    "descripcion": nodo.descripcion,
                    "unidad_id": unidad_id,
                    "familia_id": None,
                    "estatus": "activo",
                }
                firma_cache[clave_catalogo] = firma_nueva
            elif diferente:
                # Composición distinta pero nadie más vigente depende de
                # ella: actualización legítima (típicamente este mismo
                # prototipo recargando una corrección), no conflicto — se
                # publica igual que un cambio en `AplicadorCPU`.
                assert actual is not None  # noqa: S101 — `diferente` implica `actual is not None`
                assert concepto_id is not None  # noqa: S101
                if not dry_run:
                    await self._conceptos.actualizar(
                        concepto_id,
                        {
                            "descripcion": nodo.descripcion,
                            "unidad_id": unidad_id,
                            "familia_id": actual.get("familia_id"),
                        },
                    )
                    operaciones.append(
                        _operacion(
                            "concepto",
                            concepto_id,
                            "update",
                            antes=_recorte(
                                actual,
                                ("tipo", "descripcion", "unidad_id", "familia_id", "estatus"),
                            ),
                            despues={"descripcion": nodo.descripcion, "unidad_id": unidad_id},
                        )
                    )
                    operaciones.extend(
                        await _publicar_cpu_de_concepto(
                            self._conceptos, concepto_id, filas_explosion, precio
                        )
                    )

                claves_actualizadas.add(clave_catalogo)
                catalogo_conceptos[clave_catalogo] = {
                    **actual,
                    "descripcion": nodo.descripcion,
                    "unidad_id": unidad_id,
                }
                firma_cache[clave_catalogo] = firma_nueva
            else:
                # Sin conflicto, ya existía, misma composición: "si es
                # idéntico, no crea versión" (§10.8) — no se toca
                # `concepto`/`explosion`/`cpu`. `catalogo_conceptos`/
                # `firma_cache` ya están correctos (vienen del propio
                # `actual`).
                contadores["conceptos_sin_cambio"] += 1

        await self._registrar_nodo_y_partida(
            nodo=nodo,
            concepto_id=concepto_id,
            precio_unitario=precio.total.monto,
            parent_id_db=parent_id_db,
            prototipo_id=prototipo_id,
            dry_run=dry_run,
            nodos_existentes=nodos_existentes,
            operaciones=operaciones,
            partidas=partidas,
            contadores=contadores,
        )

    async def _registrar_nodo_y_partida(
        self,
        *,
        nodo: NodoLeido,
        concepto_id: UUID | None,
        precio_unitario: Decimal,
        parent_id_db: UUID | None,
        prototipo_id: UUID,
        dry_run: bool,
        nodos_existentes: dict[tuple[UUID | None, str], dict[str, Any]],
        operaciones: list[dict[str, Any]],
        partidas: list[dict[str, Any]],
        contadores: dict[str, int],
    ) -> None:
        """Última parte de `_procesar_concepto`, común a sus tres salidas
        —referencia a un CPU vigente, alta/actualiza/conflicto namespaceado,
        o el nuevo alta/primer-CPU de un `CONCEPTO` real—: sube el nodo del
        árbol y su partida de presupuesto con el `concepto_id`/precio que ya
        se resolvió."""
        contadores["partidas"] += 1
        cantidad_partida = nodo.cantidad if nodo.cantidad is not None else Decimal(1)

        anterior_nodo = nodos_existentes.get((parent_id_db, nodo.clave))
        contadores["nodos_creados" if anterior_nodo is None else "nodos_actualizados"] += 1

        if dry_run:
            return

        nodo_id, _ = await self._prototipo_nodos.upsert(
            prototipo_id,
            clave=nodo.clave,
            datos={
                "parent_id": parent_id_db,
                "tipo": "concepto",
                "nombre": nodo.descripcion,
                "concepto_id": concepto_id,
                "orden": nodo.indice or 0,
                "cantidad": cantidad_partida,
            },
        )
        operaciones.append(
            _operacion(
                "prototipo_nodo",
                nodo_id,
                "insert" if anterior_nodo is None else "update",
                antes=_recorte(
                    anterior_nodo,
                    ("parent_id", "tipo", "nombre", "concepto_id", "nivel_id", "etapa_id", "orden", "cantidad"),
                )
                if anterior_nodo
                else None,
                despues={"clave": nodo.clave, "concepto_id": str(concepto_id)},
            )
        )
        partidas.append(
            {
                "concepto_id": concepto_id,
                "prototipo_nodo_id": nodo_id,
                "cantidad": cantidad_partida,
                "precio_unitario": precio_unitario,
                "importe": cantidad_partida * precio_unitario,
                "orden": nodo.indice or 0,
            }
        )


class AplicadorDePrototipos:
    """Despacha al aplicador que corresponde al **formato** del archivo.

    `TipoCarga.PROTOTIPOS` acepta dos archivos distintos —el alta plana y la
    ingeniería por prototipo (ver `CargadorPrototipos`)— porque para el
    usuario son la misma tarea: poblar prototipos. Cuál llegó lo dice lo que
    el lector entregó, no un segundo campo en la pantalla que hubiera que
    mantener en sincronía con el archivo.
    """

    def __init__(
        self, *, plano: AplicadorPrototipos, ingenieria: AplicadorPresupuesto
    ) -> None:
        self._plano = plano
        self._ingenieria = ingenieria

    async def aplicar(
        self,
        lectura: LecturaCarga,
        *,
        modo: ModoCarga,
        dry_run: bool,
        carga_id: UUID,
    ) -> Aplicacion:
        # Un archivo vacío o que no dejó ningún registro válido cae al plano:
        # da el mismo resultado (nada que aplicar) y evita una rama muerta.
        es_arbol = bool(lectura.registros) and isinstance(
            lectura.registros[0], ArbolPrototipoCargado
        )
        aplicador = self._ingenieria if es_arbol else self._plano
        return await aplicador.aplicar(
            lectura, modo=modo, dry_run=dry_run, carga_id=carga_id
        )
