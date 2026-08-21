"""¿El contrato de hoy rompe a un cliente de ayer? (§12.12)

Spec §12.12 ("**Contrato compatible hacia atrás:** la API **no rompe**
clientes viejos — cambios **aditivos**, deprecación con ventana") · §11.2 ·
§12.8.

## Por qué existe

Desde la Fase 15 hay un cliente que **no se puede actualizar a voluntad**: la
app de Google Play. Entre que se publica una versión y que la instala el
último residente pasan días o semanas (§12.13), y en ese rato el servidor
tiene que seguir hablándole al binario viejo. La misma cosa vale para una
pestaña del navegador que alguien dejó abierta el viernes.

`verificar_contrato.py` responde *¿el contrato del repo coincide con el
código?*. Este responde la otra pregunta, que ninguna prueba hacía: *¿el
cambio es aditivo?*. Son distintas —se puede regenerar el contrato
correctamente y, con eso, romper a todos los clientes viejos a la vez—.

## Contra qué se compara

Contra `openapi/publicado.json`: el contrato de la versión **que está en
producción**. No es una copia redundante de `openapi.json`; es la línea base
que solo se mueve al liberar (`--publicar`, junto con el tag `vX.Y.Z` del
§12.12). Mientras no se mueva, todo cambio del contrato se mide contra lo que
los clientes de allá afuera realmente conocen.

## Qué se considurar romper

- Quitar una operación, o cambiarle el método.
- Volver **obligatorio** un parámetro o un campo del cuerpo que no lo era
  —incluido agregar uno nuevo obligatorio—: el cliente viejo no lo manda.
- Quitar un campo de una respuesta: el cliente viejo lo lee.
- Quitar un valor de un enum de respuesta o cambiar el tipo de un campo.

## Y qué NO se considera romper

- **Agregar** operaciones, campos opcionales o valores de enum. Es la
  definición de aditivo.
- Quitar un parámetro **opcional** de una petición: el cliente que lo mandaba
  sigue funcionando porque el servidor lo ignora.
- Quitar una operación **deprecada cuya ventana ya venció** (ver abajo). Es
  justo el mecanismo que el §12.12 pide: se anuncia, se espera, se quita.

## La ventana de deprecación

Una operación se marca con `deprecated: true` y con la fecha en que se podrá
retirar, en la extensión `x-sunset` (`YYYY-MM-DD`). Eso lo pone
`adapters/api/deprecacion.py`, que además manda las cabeceras `Deprecation` y
`Sunset` del RFC 8594 en cada respuesta —para que un cliente lo note sin leer
el contrato—.

Este script exige las dos cosas juntas: una operación deprecada **sin**
`x-sunset` es un error, porque una deprecación sin fecha nunca vence y se
queda para siempre. Y quitar una operación cuya fecha aún no llegó también es
un error, aunque estuviera deprecada: la ventana existe para cumplirse.

Uso:
    python scripts/verificar_compatibilidad.py             # verifica
    python scripts/verificar_compatibilidad.py --publicar  # mueve la línea base
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[2]
ACTUAL = RAIZ / "openapi" / "openapi.json"
PUBLICADO = RAIZ / "openapi" / "publicado.json"

METODOS = ("get", "post", "put", "patch", "delete")

MAX_HALLAZGOS = 40
"""Con cuarenta líneas ya se entiende qué se rompió; un volcado completo de un
contrato de ochenta rutas ahoga el log de CI (mismo criterio que
`verificar_contrato.py`)."""


def _cargar(ruta: Path) -> dict[str, Any]:
    if not ruta.exists():
        raise SystemExit(
            f"No existe {ruta.relative_to(RAIZ)}. Publica la línea base con:\n"
            "    python scripts/verificar_compatibilidad.py --publicar"
        )
    return json.loads(ruta.read_text(encoding="utf-8"))


def _operaciones(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """`{"GET /api/v1/obras": operación}` para todo el documento."""
    salida: dict[str, dict[str, Any]] = {}
    for ruta, item in doc.get("paths", {}).items():
        for metodo, operacion in item.items():
            if metodo in METODOS:
                salida[f"{metodo.upper()} {ruta}"] = operacion
    return salida


def _esquemas(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return doc.get("components", {}).get("schemas", {})


def _sunset(operacion: dict[str, Any]) -> date | None:
    crudo = operacion.get("x-sunset")
    if not isinstance(crudo, str):
        return None
    try:
        return date.fromisoformat(crudo)
    except ValueError:
        return None


def _parametros_obligatorios(operacion: dict[str, Any]) -> set[str]:
    return {
        f"{p.get('in')}:{p.get('name')}"
        for p in operacion.get("parameters", [])
        if p.get("required")
    }


def _cuerpo_obligatorio(
    operacion: dict[str, Any], esquemas: dict[str, Any]
) -> set[str]:
    """Campos `required` del cuerpo JSON, resolviendo un `$ref` de un nivel.

    Un nivel alcanza porque FastAPI genera exactamente esa forma: el
    `requestBody` apunta a un esquema de `components`. Si algún día anidara
    más, esto **no** inventa: devuelve vacío y no reporta un falso positivo.
    """
    contenido = (
        operacion.get("requestBody", {}).get("content", {}).get("application/json", {})
    )
    esquema = contenido.get("schema", {})
    if "$ref" in esquema:
        nombre = esquema["$ref"].rsplit("/", 1)[-1]
        esquema = esquemas.get(nombre, {})
    return set(esquema.get("required", []))


def _propiedades(esquema: dict[str, Any]) -> dict[str, Any]:
    propiedades = esquema.get("properties")
    return propiedades if isinstance(propiedades, dict) else {}


def _tipo(propiedad: Any) -> str | None:
    """Tipo declarado de una propiedad, si es simple.

    Un `anyOf` —lo que FastAPI genera para `str | None`— no se compara: su
    forma cambia por motivos que no rompen a nadie (agregar `null`, por
    ejemplo). Se comparan solo los tipos simples, donde `string` → `integer`
    sí rompe seguro.
    """
    if not isinstance(propiedad, dict):
        return None
    tipo = propiedad.get("type")
    return tipo if isinstance(tipo, str) else None


def comparar(viejo: dict[str, Any], nuevo: dict[str, Any]) -> list[str]:
    """Devuelve los cambios que rompen. Lista vacía = el cambio es aditivo."""
    fallos: list[str] = []
    hoy = date.today()

    ops_viejas = _operaciones(viejo)
    ops_nuevas = _operaciones(nuevo)
    esquemas_viejos = _esquemas(viejo)
    esquemas_nuevos = _esquemas(nuevo)

    # --- Operaciones que desaparecieron ---------------------------------
    for clave, operacion in ops_viejas.items():
        if clave in ops_nuevas:
            continue

        if not operacion.get("deprecated"):
            fallos.append(
                f"{clave}: se quitó sin deprecar. El §12.12 pide anunciarla "
                "primero (`deprecar(...)`) y retirarla después de su ventana."
            )
            continue

        sunset = _sunset(operacion)
        if sunset is None:
            fallos.append(
                f"{clave}: estaba deprecada pero sin `x-sunset`, así que su "
                "ventana nunca empezó a correr."
            )
        elif sunset > hoy:
            fallos.append(
                f"{clave}: su ventana de deprecación vence el {sunset} y hoy "
                f"es {hoy}. Todavía no se puede quitar."
            )

    # --- Deprecaciones sin fecha ----------------------------------------
    for clave, operacion in ops_nuevas.items():
        if operacion.get("deprecated") and _sunset(operacion) is None:
            fallos.append(
                f"{clave}: está deprecada sin `x-sunset`. Una deprecación sin "
                "fecha no vence nunca; usa `deprecar(desde=..., meses=...)`."
            )

    # --- Requisitos nuevos en la petición -------------------------------
    for clave, operacion in ops_nuevas.items():
        vieja = ops_viejas.get(clave)
        if vieja is None:
            continue  # operación nueva: aditiva por definición

        nuevos = _parametros_obligatorios(operacion) - _parametros_obligatorios(vieja)
        for parametro in sorted(nuevos):
            fallos.append(
                f"{clave}: el parámetro {parametro} pasó a obligatorio; el "
                "cliente viejo no lo manda."
            )

        cuerpo_nuevo = _cuerpo_obligatorio(operacion, esquemas_nuevos)
        cuerpo_viejo = _cuerpo_obligatorio(vieja, esquemas_viejos)
        for campo in sorted(cuerpo_nuevo - cuerpo_viejo):
            fallos.append(
                f"{clave}: el campo '{campo}' del cuerpo pasó a obligatorio; "
                "el cliente viejo no lo manda."
            )

    # --- Esquemas: lo que el cliente viejo lee --------------------------
    for nombre, esquema_viejo in esquemas_viejos.items():
        esquema_nuevo = esquemas_nuevos.get(nombre)
        if esquema_nuevo is None:
            # Un esquema puede desaparecer porque se renombró o porque dejó de
            # usarse; lo que importa es la operación que lo devolvía, y eso ya
            # se revisó arriba. Aquí no se reporta para no duplicar el fallo.
            continue

        viejas = _propiedades(esquema_viejo)
        nuevas = _propiedades(esquema_nuevo)

        for campo in sorted(set(viejas) - set(nuevas)):
            fallos.append(
                f"{nombre}.{campo}: se quitó del esquema; un cliente viejo "
                "puede estar leyéndolo."
            )

        for campo, propiedad in viejas.items():
            if campo not in nuevas:
                continue
            antes, ahora = _tipo(propiedad), _tipo(nuevas[campo])
            if antes and ahora and antes != ahora:
                fallos.append(
                    f"{nombre}.{campo}: cambió de {antes} a {ahora}."
                )

            perdidos = set(_enum(propiedad)) - set(_enum(nuevas[campo]))
            for valor in sorted(perdidos):
                fallos.append(
                    f"{nombre}.{campo}: se quitó el valor '{valor}' del enum."
                )

        # Un enum de nivel superior (los de `diccionario.py` salen así).
        perdidos = set(_enum(esquema_viejo)) - set(_enum(esquema_nuevo))
        for valor in sorted(perdidos):
            fallos.append(f"{nombre}: se quitó el valor '{valor}' del enum.")

    return fallos


def _enum(esquema: Any) -> list[str]:
    if not isinstance(esquema, dict):
        return []
    valores = esquema.get("enum")
    return [str(v) for v in valores] if isinstance(valores, list) else []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publicar",
        action="store_true",
        help="Mueve la línea base al contrato actual. Se hace al liberar (§12.12).",
    )
    args = parser.parse_args()

    actual = _cargar(ACTUAL)

    if args.publicar:
        PUBLICADO.write_text(
            json.dumps(actual, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"Línea base publicada: {PUBLICADO.relative_to(RAIZ)}")
        print(
            "Recuerda: esto declara que ESTE contrato es el que está en "
            "producción. Va en el commit del release, no antes."
        )
        return 0

    fallos = comparar(_cargar(PUBLICADO), actual)

    if not fallos:
        print("El contrato es compatible hacia atrás.")
        return 0

    print(f"El contrato ROMPE a los clientes publicados ({len(fallos)} hallazgos):\n")
    for linea in fallos[:MAX_HALLAZGOS]:
        print(f"  · {linea}")
    if len(fallos) > MAX_HALLAZGOS:
        print(f"  … y {len(fallos) - MAX_HALLAZGOS} más.")
    print(
        "\nSi el cambio es intencional y ya no hay clientes viejos, publica la "
        "línea base:\n    python scripts/verificar_compatibilidad.py --publicar"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
