"""La plantilla de muro, el artefacto (plan de elementos de muro, Ola 4A; M-1, M-4, M-14, M-19, Q9).

Una **plantilla** describe un muro completo: su tipo (confinado, con_cadena, tabique), material, ubicación (caras A y B), las
partes de altura y las **instancias de elementos** que lleva (castillos, cadenas y el muro de tabique de la lane 3C), cada una
enlazada a los conceptos del elemento. El Cuantificador solo elige la plantilla de cada trazo.

- **Por validar → validada** (M-19): toda plantilla nace «por validar» y cualquier cambio la deja así. Control de obra la valida
  contra la matriz de los conceptos de sus elementos (`validar_contra_matriz`): cada parte que toma un concepto debe existir en su
  matriz y no puede quedar tomada dos veces. Lo que no cuadra se avisa como *alerta por revisar* y se acepta con casilla; lo que
  impide validar *bloquea*: un elemento que ya no existe, una parte **sin concepto del catálogo** (C3) o un material de mampostería sin
  concepto (block hueco, cantera rosa: por capturar, no se inventa uno).
- **Versiones** (Q9): al cambiar una plantilla **ya validada** nace una versión nueva y los trazos ya medidos conservan la anterior
  (apuntan a su fila). Una plantilla aún por validar se edita en el lugar.
- **El castillo depende de la plantilla** y no del tipo «con cadena»: un castillo se coloca en el plano si la plantilla del muro
  es de «muros y cadena» (`admite_castillos_a_mano`): el castillo a mano elige cualquier K del catálogo; si la plantilla lleva castillos
  *ubicados* (`admite_castillos_ubicados`) también se pueden colocar de una vez por separación o extremos.

Nada de esto inventa precios ni destajos. Funciones puras, sin base de datos.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from obractrl.domain.cuantificacion.clasificacion_de_elementos import (
    CATEGORIAS,
    POSICIONES_DE_MURO,
    posiciones_permitidas,
    validar_posicion,
)
from obractrl.domain.cuantificacion.colocacion_de_plantilla import REGLAS_DE_CASTILLO
from obractrl.domain.cuantificacion.elementos_parametricos import (
    ErrorDeElementoParametrico,
)
from obractrl.domain.cuantificacion.muro_tipo import (
    CASTILLO_MODO_POR_TIPO,
    acabado_normalizado,
    tipo_valido,
)
from obractrl.domain.cuantificacion.muro_ubicacion import (
    MATERIALES_DE_MURO,
    caras_de_ubicacion,
    material_valido,
    ubicacion_resultante,
    ubicacion_valida,
    validar_partes_con_caras,
)
from obractrl.domain.cuantificacion.prototipos_de_muro import (
    validar_prototipo_y_planta,
)
from obractrl.domain.cuantificacion.reglas import ErrorDeCuantificacion

__all__ = [
    "CLASES_DE_ELEMENTO",
    "ESTADOS_DE_VALIDACION",
    "ROLES_QUE_EDITAN",
    "ROLES_QUE_VALIDAN",
    "Alerta",
    "ConceptoDelElemento",
    "ElementoParaValidar",
    "ErrorDePlantillaDeMuro",
    "InfoDeElemento",
    "admite_castillos_a_mano",
    "admite_castillos_ubicados",
    "alertas_del_material",
    "cambia_la_plantilla",
    "clase_de_elemento",
    "normalizar_plantilla",
    "puede_validar",
    "requiere_version_nueva",
    "validar_contra_matriz",
    "validar_que_edita",
    "validar_que_valida",
]

ESTADOS_DE_VALIDACION = ("por_validar", "validada")
CLASES_DE_ELEMENTO = ("castillo", "cadena", "muro")
MODOS_DE_CASTILLO = ("estimado", "ubicado")
ROLES_QUE_EDITAN = ("costos", "control_obra")
ROLES_QUE_VALIDAN = ("control_obra",)


class ErrorDePlantillaDeMuro(ErrorDeCuantificacion):
    """La plantilla no vale o no se puede validar."""


def validar_que_edita(rol: str) -> None:
    """Costos y Control de obra editan plantillas (M-15); residente y supervisor las ven en solo lectura."""
    if rol not in ROLES_QUE_EDITAN:
        raise ErrorDePlantillaDeMuro("Solo Costos y Control de obra editan las plantillas de muro.")


def validar_que_valida(rol: str) -> None:
    """Solo Control de obra valida una plantilla."""
    if rol not in ROLES_QUE_VALIDAN:
        raise ErrorDePlantillaDeMuro("Solo Control de obra valida las plantillas de muro.")


# --- Qué elementos entran en un muro ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class InfoDeElemento:
    """Un elemento ya resuelto por clave: del catálogo paramétrico (castillo, cadena) o de la biblioteca (muro de tabique)."""

    ref: str
    nombre: str
    clase: str
    categoria: str | None = None
    subcategoria: str | None = None
    provisional: bool = False


def clase_de_elemento(categoria: str, subcategoria: str) -> str | None:
    """Qué papel juega en un muro un elemento paramétrico de esa categoría: ``castillo`` (castillos), ``cadena`` (cadenas y
    dalas) o `None` si no se coloca en un muro (trabes, zapatas, losas, columnas forjadas…)."""
    for c in CATEGORIAS:
        if c["clave"] != categoria:
            continue
        sub = next((s for s in c["subcategorias"] if s["clave"] == subcategoria), None)
        if sub is None or not sub["en_muro"]:
            return None
        if categoria == "castillos":
            return "castillo"
        if categoria in ("cadenas", "dalas"):
            return "cadena"
    return None


def _decimal(valor: Any, que: str, *, minimo_exclusivo: bool = False) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        d = Decimal(str(valor))
    except Exception as e:  # noqa: BLE001 - cualquier cosa que no sea un número
        raise ErrorDePlantillaDeMuro(f"{que} debe ser un número.") from e
    if (d <= 0) if minimo_exclusivo else (d < 0):
        raise ErrorDePlantillaDeMuro(f"{que} debe ser mayor que cero." if minimo_exclusivo else f"{que} no puede ser negativo.")
    return d


def _regla_del_castillo(uid: str, modo: str, e: Mapping[str, Any]) -> dict[str, Any]:
    """La regla con que un castillo cuenta sus piezas (M-4): «cada separación y extremos» (`separacion`, con su separación o la del driver
    de la obra), «solo extremos» (`extremos`), «por ml» (piezas por metro lineal de muro) o «total» (los metros de castillo de un prototipo
    repartidos por m² de muro, con su base). Un castillo ubicado en el plano solo admite separación o extremos: sus piezas son enteras."""
    sep = _decimal(e.get("sep_m"), f"La separación de {uid}", minimo_exclusivo=True)
    regla = str(e.get("regla") or "")
    if not regla:
        regla = "separacion" if sep is not None else ("extremos" if modo == "ubicado" else "separacion")
    if regla not in REGLAS_DE_CASTILLO:
        raise ErrorDePlantillaDeMuro(f"La regla de {uid} es una de {', '.join(REGLAS_DE_CASTILLO)} (no «{regla}»).")
    if modo == "ubicado" and regla in ("por_ml", "total"):
        raise ErrorDePlantillaDeMuro(
            f"{uid} se coloca en el plano (muro con cadena): cuenta por separación o por extremos; «por ml» y «total» son para los castillos estimados."
        )
    salida: dict[str, Any] = {"regla": regla, "sep_m": None, "piezas_por_ml": None, "total_m": None, "base_m2": None}
    if regla == "separacion":
        salida["sep_m"] = str(sep) if sep is not None else None
    elif regla == "por_ml":
        por_ml = _decimal(e.get("piezas_por_ml"), f"Las piezas por ml de {uid}", minimo_exclusivo=True)
        if por_ml is None:
            raise ErrorDePlantillaDeMuro(f"{uid} cuenta «por ml»: di cuántas piezas lleva cada metro lineal de muro.")
        salida["piezas_por_ml"] = str(por_ml)
    elif regla == "total":
        total = _decimal(e.get("total_m"), f"Los metros de {uid}", minimo_exclusivo=True)
        base = _decimal(e.get("base_m2"), f"Los m² de muro de la base de {uid}", minimo_exclusivo=True)
        if total is None or base is None:
            raise ErrorDePlantillaDeMuro(f"{uid} cuenta por «total»: di los metros de castillo y los m² de muro sobre los que se reparten.")
        salida["total_m"], salida["base_m2"] = str(total), str(base)
    return salida


def _instancias(tipo: str, entradas: Sequence[Mapping[str, Any]], info: Mapping[str, InfoDeElemento]) -> list[dict[str, Any]]:
    salida: list[dict[str, Any]] = []
    usados: set[str] = set()
    modo_del_tipo = CASTILLO_MODO_POR_TIPO[tipo]
    for e in entradas:
        ref = str(e.get("ref") or "").strip()
        if not ref:
            raise ErrorDePlantillaDeMuro("Cada elemento de la plantilla lleva la clave del elemento (ref).")
        el = info.get(ref)
        if el is None:
            raise ErrorDePlantillaDeMuro(f"El elemento {ref} no existe en el catálogo o no se coloca en un muro.")
        if el.clase not in CLASES_DE_ELEMENTO:
            raise ErrorDePlantillaDeMuro(f"El elemento {ref} no se coloca en un muro.")
        if tipo == "tabique" and el.clase in ("castillo", "cadena"):
            raise ErrorDePlantillaDeMuro(f"Un muro de tabique no lleva castillos ni cadenas (quita {ref} o cambia el tipo).")
        uid = str(e.get("uid") or "").strip()
        if not uid:
            uid, n = ref, 2
            while uid in usados:
                uid, n = f"{ref}#{n}", n + 1
        if uid in usados:
            raise ErrorDePlantillaDeMuro(f"El identificador {uid} se repite en la plantilla.")
        usados.add(uid)
        item: dict[str, Any] = {"uid": uid, "ref": ref, "clase": el.clase, "modo": None, "sep_m": None, "posicion": None, "z_m": "0"}
        origen = " ".join(str(e.get("origen") or "").split())
        if origen:
            if len(origen) > 300:
                raise ErrorDePlantillaDeMuro(f"El origen de {uid} no puede pasar de 300 caracteres.")
            item["origen"] = origen
        z = _decimal(e.get("z_m"), f"El arranque de {uid}")
        item["z_m"] = str(z if z is not None else Decimal(0))
        if el.clase == "castillo":
            modo = e.get("modo") or modo_del_tipo
            if modo not in MODOS_DE_CASTILLO:
                raise ErrorDePlantillaDeMuro(f"El modo de un castillo es {' o '.join(MODOS_DE_CASTILLO)} (no «{modo}»).")
            if modo != modo_del_tipo:
                raise ErrorDePlantillaDeMuro(
                    f"En un muro «{tipo}» los castillos son {modo_del_tipo}s, no {modo}s: cambia el tipo del muro (M-4)."
                )
            item["modo"] = modo
            item.update(_regla_del_castillo(uid, modo, e))
        elif el.clase == "cadena":
            assert el.categoria is not None and el.subcategoria is not None
            posicion = e.get("posicion")
            if posicion is None:
                permitidas = posiciones_permitidas(el.categoria, el.subcategoria)
                posicion = permitidas[0] if permitidas else POSICIONES_DE_MURO[1]
            try:
                validar_posicion(el.categoria, el.subcategoria, str(posicion))
            except ErrorDeElementoParametrico as err:
                raise ErrorDePlantillaDeMuro(str(err)) from err
            item["posicion"] = str(posicion)
        else:  # el muro de tabique
            if any(x["clase"] == "muro" for x in salida):
                raise ErrorDePlantillaDeMuro("Una plantilla lleva un solo elemento de muro (el de la mampostería).")
        salida.append(item)
    return salida


def normalizar_plantilla(entrada: Mapping[str, Any], elementos: Mapping[str, InfoDeElemento]) -> dict[str, Any]:
    """Revisa una plantilla y la devuelve completa: nombre, tipo, material, ubicación, altura, partes con sus caras, elementos con
    su clase y modo, y acabado. `elementos` son los elementos de la entrada ya resueltos por clave. La ubicación pasa a
    ``personalizada`` si alguna parte trae una cara distinta de la que fija la ubicación."""
    nombre = str(entrada.get("nombre") or "").strip()
    if not 1 <= len(nombre) <= 80:
        raise ErrorDePlantillaDeMuro("El nombre de la plantilla lleva entre 1 y 80 caracteres.")
    tipo = tipo_valido(entrada.get("tipo"))
    if tipo is None:
        raise ErrorDePlantillaDeMuro("La plantilla lleva su tipo de muro.")
    material = material_valido(str(entrada.get("material") or ""))
    ubicacion = ubicacion_valida(str(entrada.get("ubicacion") or ""))
    altura = _decimal(entrada.get("altura_m"), "La altura", minimo_exclusivo=True)
    partes_crudas = list(entrada.get("partes") or [])
    partes = validar_partes_con_caras(partes_crudas)
    # Las partes que no traen caras las toman de la ubicación; las que traen caras distintas la vuelven personalizada.
    ubicacion = ubicacion_resultante(ubicacion, partes)
    if ubicacion != "personalizada":
        for p in partes:
            if p["cara_a"] is None and p["cara_b"] is None:
                p["cara_a"], p["cara_b"] = caras_de_ubicacion(ubicacion, p["rol"]) or (None, None)
    instancias = _instancias(tipo, list(entrada.get("elementos") or []), elementos)
    prototipo, planta = validar_prototipo_y_planta(entrada.get("prototipo"), entrada.get("planta"))
    if prototipo is not None and tipo != "confinado":
        raise ErrorDePlantillaDeMuro(
            "La plantilla de un prototipo es de muro confinado: propone los castillos cuando no hay plano estructural."
        )
    notas = str(entrada.get("notas") or "").strip() or None
    if notas is not None and len(notas) > 6000:
        raise ErrorDePlantillaDeMuro("Las notas de la plantilla no pueden pasar de 6000 caracteres.")
    return {
        "nombre": nombre,
        "tipo": tipo,
        "material": material,
        "ubicacion": ubicacion,
        "altura_m": str(altura) if altura is not None else None,
        "partes": partes,
        "elementos": instancias,
        "acabado": acabado_normalizado(entrada.get("acabado")),
        "prototipo": prototipo,
        "planta": planta,
        "notas": notas,
        "por_confirmar": bool(entrada.get("por_confirmar") or False),
    }


def admite_castillos_a_mano(tipo: str | None) -> bool:
    """¿Se colocan castillos a mano en un muro con esta plantilla? Sí en la de «muros y cadena» (muro con cadena), con o sin castillos propios:
    cuando hay plano estructural los castillos reales se siembran uno por uno en el plano, cada uno de su tipo K. El muro confinado los estima."""
    return tipo == "con_cadena"


def admite_castillos_ubicados(elementos: Iterable[Mapping[str, Any]]) -> bool:
    """¿La plantilla lleva un castillo que se coloca en el plano? Así el castillo deja de depender de «muro con cadena»."""
    return any(e.get("clase") == "castillo" and e.get("modo") == "ubicado" for e in elementos)


# --- Cambios y versiones ----------------------------------------------------------------------------------------------

_CAMPOS_QUE_CUENTAN = (
    "nombre", "tipo", "material", "ubicacion", "altura_m", "partes", "elementos", "acabado", "prototipo", "planta", "notas", "por_confirmar",
)


def _plano(v: Any) -> Any:
    if isinstance(v, Mapping):
        return {k: _plano(x) for k, x in sorted(v.items())}
    if isinstance(v, (list, tuple)):
        return [_plano(x) for x in v]
    if isinstance(v, Decimal):
        return str(v.normalize())
    if isinstance(v, str):
        try:
            return str(Decimal(v).normalize()) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else v
        except Exception:  # noqa: BLE001
            return v
    return v


def cambia_la_plantilla(antes: Mapping[str, Any], despues: Mapping[str, Any]) -> bool:
    """¿La plantilla nueva es distinta de la guardada? Solo cuentan el nombre, el tipo, el material, la ubicación, la altura, las
    partes, los elementos, el acabado, el prototipo y la planta, las notas y si los datos están por confirmar."""
    return any(_plano(antes.get(c)) != _plano(despues.get(c)) for c in _CAMPOS_QUE_CUENTAN)


def requiere_version_nueva(validacion: str) -> bool:
    """Q9: cambiar una plantilla ya validada crea la versión siguiente (los trazos medidos conservan la anterior); una por validar se
    edita en el lugar."""
    if validacion not in ESTADOS_DE_VALIDACION:
        raise ErrorDePlantillaDeMuro(f"La validación es {' o '.join(ESTADOS_DE_VALIDACION)}.")
    return validacion == "validada"


# --- Validación contra la matriz de los conceptos ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConceptoDelElemento:
    """Un concepto que paga una o varias partes del elemento, con su matriz (los insumos de su composición expandida)."""

    clave: str
    toma: frozenset[str]
    estado: str = "autorizado"
    """``autorizado`` (del catálogo), ``propuesto`` (concepto nuevo sin autorizar) o ``sin_matriz`` (del catálogo, pero la base no trae su composición)."""
    contexto: tuple[int | None, int | None, str | None, Decimal | None] = (None, None, None, None)
    matriz: frozenset[str] | None = None
    """Claves de insumo de la matriz del concepto; `None` si el concepto no tiene composición que revisar (uno propuesto)."""


@dataclass(frozen=True, slots=True)
class ElementoParaValidar:
    uid: str
    ref: str
    nombre: str
    clase: str
    partes: Mapping[str, frozenset[str]] = field(default_factory=dict)
    """Cada parte de la receta y los insumos que el elemento eligió para ella (vacío = aún no eligió)."""
    conceptos: Sequence[ConceptoDelElemento] = ()
    provisional: bool = False
    implicito: bool = False
    """El muro que sale del material de la plantilla (tabique rojo → EST-02010, sillar amarillo → BAP-01010) y no se colocó a mano."""


@dataclass(frozen=True, slots=True)
class Alerta:
    nivel: str  # "bloquea" | "alerta"
    codigo: str
    uid: str
    ref: str
    mensaje: str
    parte: str | None = None
    concepto: str | None = None


_ETIQUETAS = {"concreto": "el concreto", "acero": "el acero", "estribos": "los estribos", "alambre": "el alambre", "cimbra": "la cimbra", "muro": "la mampostería"}


def validar_contra_matriz(elementos: Iterable[ElementoParaValidar]) -> list[Alerta]:
    """Lo que no cuadra entre los elementos de la plantilla y la matriz de sus conceptos (M-19). Nunca corrige: avisa.

    - ``sin_concepto`` (**bloquea**, C3): una parte de la receta no la toma ningún concepto (o el elemento no tiene conceptos).
    - ``parte_doble``: dos conceptos toman la misma parte en el mismo contexto (sin ser escalones de una escalera).
    - ``parte_fuera_de_matriz``: el concepto toma una parte cuyo insumo no está en su matriz del catálogo (por revisar).
    - ``concepto_propuesto`` y ``elemento_provisional``: aún no los autoriza Control de obra, así que no hay matriz firme.
    """
    alertas: list[Alerta] = []
    for e in elementos:
        base = {"uid": e.uid, "ref": e.ref}
        if e.provisional:
            alertas.append(Alerta("alerta", "elemento_provisional", mensaje=f"{e.nombre} aún no está autorizado (provisional).", **base))
        for c in e.conceptos:
            if c.estado == "propuesto":
                alertas.append(
                    Alerta("alerta", "concepto_propuesto", concepto=c.clave, mensaje=f"El concepto {c.clave} de {e.nombre} es propuesto: no tiene matriz del catálogo que revisar.", **base)
                )
            elif c.estado == "sin_matriz":
                alertas.append(
                    Alerta("alerta", "concepto_sin_matriz", concepto=c.clave, mensaje=f"El concepto {c.clave} de {e.nombre} no tiene composición (matriz) en la base: no se puede revisar.", **base)
                )
        if not e.conceptos:
            alertas.append(Alerta("bloquea", "sin_concepto", mensaje=f"{e.nombre} no tiene ningún concepto que lo pague.", **base))
            continue
        for parte, insumos in e.partes.items():
            toman = [c for c in e.conceptos if parte in c.toma]
            etiqueta = _ETIQUETAS.get(parte, parte)
            if not toman:
                alertas.append(Alerta("bloquea", "sin_concepto", parte=parte, mensaje=f"{etiqueta.capitalize()} de {e.nombre} no lo toma ningún concepto.", **base))
                continue
            por_contexto: dict[tuple[Any, ...], list[str]] = {}
            for c in toman:
                por_contexto.setdefault(c.contexto, []).append(c.clave)
            for claves in por_contexto.values():
                if len(claves) > 1:
                    alertas.append(
                        Alerta("alerta", "parte_doble", parte=parte, mensaje=f"{etiqueta.capitalize()} de {e.nombre} lo toman dos conceptos a la vez: {', '.join(claves)}.", **base)
                    )
            for c in toman:
                if c.matriz is None or not insumos:
                    continue
                if not {i.upper() for i in insumos} & {i.upper() for i in c.matriz}:
                    alertas.append(
                        Alerta(
                            "alerta", "parte_fuera_de_matriz", parte=parte, concepto=c.clave,
                            mensaje=f"{c.clave} toma {etiqueta} de {e.nombre}, pero ninguno de sus insumos ({', '.join(sorted(insumos))}) está en su matriz: por revisar.",
                            **base,
                        )
                    )
    return alertas


def alertas_del_material(material: str, *, lleva_muro_propio: bool) -> list[Alerta]:
    """La mampostería de la plantilla (su material) también es una parte que necesita concepto (C3, F7).

    - El material con elemento de la biblioteca (tabique rojo → EST-02010, sillar amarillo → BAP-01010) se revisa como cualquier elemento: aquí no avisa.
    - ``material_sin_concepto`` (**bloquea**): el catálogo no tiene concepto para ese material (block hueco, cantera rosa): queda por
      capturar y no se inventa uno; la plantilla no se valida hasta que haya concepto (o el muro se coloque con un elemento de la biblioteca).
    - ``material_sin_elemento`` (alerta): el catálogo tiene concepto pero el material aún no es un elemento de la biblioteca (regla F7: si se
      crea el elemento se crea también su concepto); se acepta con casilla. Hoy ningún material con concepto está en ese caso: el sillar
      amarillo (BAP-01010, 19 cm) ya es un elemento, y la alerta queda para un material que gane concepto antes que elemento.
    Si la plantilla ya lleva un elemento de muro propio, el material no necesita uno."""
    if lleva_muro_propio:
        return []
    datos = MATERIALES_DE_MURO[material_valido(material)]
    if datos["elemento"]:
        return []
    base = {"uid": f"material:{material}", "ref": material}
    if datos["concepto"] is None:
        return [
            Alerta(
                "bloquea", "material_sin_concepto",
                mensaje=f"{datos['nombre']} no tiene concepto en el catálogo (por capturar): la mampostería queda sin concepto y no se puede validar.",
                **base,
            )
        ]
    return [
        Alerta(
            "alerta", "material_sin_elemento", concepto=str(datos["concepto"]),
            mensaje=f"{datos['nombre']} tiene el concepto {datos['concepto']} en el catálogo, pero aún no es un elemento de la biblioteca: no hay matriz que revisar.",
            **base,
        )
    ]


def puede_validar(alertas: Iterable[Alerta]) -> bool:
    """Una plantilla se valida si no hay alertas que bloqueen. Las alertas por revisar no impiden validar, pero Control de obra debe
    aceptarlas expresamente."""
    return not any(a.nivel == "bloquea" for a in alertas)

