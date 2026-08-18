"""¿`openapi/openapi.json` coincide con lo que genera la app? (§12.2)

Orval genera los hooks del front y del móvil desde ese archivo. Un endpoint
cambiado sin regenerarlo **no rompe ninguna prueba** —el front sigue
compilando contra el contrato viejo— y se descubre en producción. Esto es lo
único que convierte "el front programa contra el contrato" en algo verificado.

Vive en un script y no dentro del YAML de CI a propósito: así se corre igual
en local (`python scripts/verificar_contrato.py`) que en CI, y el YAML no
carga con Python embebido —donde un escape mal puesto rompe el archivo entero
sin que nadie lo note hasta la corrida—.

Que el resultado sea reproducible depende de `backend/constraints.txt`: dos
versiones distintas de FastAPI generan contratos distintos sin que nadie haya
tocado un endpoint. Ver el encabezado de ese archivo.

Uso:
    python scripts/verificar_contrato.py            # verifica
    python scripts/verificar_contrato.py --escribir # regenera
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CONTRATO = RAIZ / "openapi" / "openapi.json"

MAX_LINEAS_DIFF = 200
"""Un diff completo de un contrato de 59 rutas ahoga el log de CI. Con las
primeras líneas basta para saber qué cambió y decidir."""


def generar() -> str:
    # Se importa aquí y no arriba para que `--help` funcione sin levantar la
    # app entera ni leer la configuración.
    from obractrl.main import crear_app

    return json.dumps(crear_app().openapi(), indent=2, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--escribir",
        action="store_true",
        help="Regenera el contrato en vez de solo verificarlo.",
    )
    args = parser.parse_args()

    generado = generar()

    if args.escribir:
        CONTRATO.write_text(generado, encoding="utf-8", newline="\n")
        print(f"Contrato regenerado: {CONTRATO.relative_to(RAIZ)}")
        print("Falta regenerar el cliente: cd frontend && npm run api:generar")
        return 0

    versionado = CONTRATO.read_text(encoding="utf-8")
    if generado.strip() == versionado.strip():
        print("Contrato al día.")
        return 0

    diff = difflib.unified_diff(
        versionado.splitlines(),
        generado.splitlines(),
        fromfile="openapi/openapi.json (versionado)",
        tofile="generado por la app",
        lineterm="",
        n=2,
    )
    # El diff y no solo el veredicto: sin él, "está desactualizado" obliga a
    # reproducir el entorno de CI para saber qué cambió.
    print("\n".join(list(diff)[:MAX_LINEAS_DIFF]))
    print(
        "\nopenapi.json está desactualizado.\n"
        "  1. cd backend && python scripts/verificar_contrato.py --escribir\n"
        "  2. cd frontend && npm run api:generar\n"
        "  3. commitear las dos cosas juntas (ver openapi/README.md).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
