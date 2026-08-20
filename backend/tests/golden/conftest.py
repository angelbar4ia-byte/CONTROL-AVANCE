"""Arnés de los datasets golden (§11.7).

## Qué es un golden y en qué se distingue de una prueba normal

Una prueba normal afirma una regla: «exceder la cantidad programada rechaza la
captura». Un golden afirma un **resultado completo**: dado este cronograma
exacto, el motor devuelve estas fechas exactas. No comprueba que el cálculo sea
correcto —eso lo hacen las pruebas de dominio— sino que **no cambie sin que
alguien lo decida**.

Su valor está en el diff. Cuando alguien toca el motor de CPM y una holgura pasa
de 2 a 0, lo que aparece en la revisión es esa línea, no «una prueba en rojo».
Sin esto, una regresión de cálculo se ve como un número raro en una pantalla
tres semanas después.

## Cómo se actualiza uno

Con `--actualizar-golden`. **Nunca por reflejo**: si el resultado cambió, la
pregunta es si el cambio es el que se quería. Regenerar para que el CI se ponga
verde convierte el golden en un registro de lo último que pasó, que es
exactamente lo contrario de lo que es.

Los archivos viven en `tests/golden/datos/` y se versionan: el diff es el
producto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

DIRECTORIO = Path(__file__).parent / "datos"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--actualizar-golden",
        action="store_true",
        default=False,
        help=(
            "Reescribe los datasets golden con el resultado actual. Úsalo solo "
            "cuando el cambio de resultado sea el que se quería."
        ),
    )


@pytest.fixture
def golden(request: pytest.FixtureRequest):
    """Compara un resultado contra su golden, o lo crea si no existe.

    Que un golden ausente se cree en vez de fallar es deliberado: escribir a
    mano un JSON de doscientas líneas invita a copiar la salida sin mirarla, que
    es peor. Lo que hace falta es **revisar el archivo nuevo en el diff**, y para
    eso tiene que existir.
    """
    actualizar = bool(request.config.getoption("--actualizar-golden"))

    def comparar(nombre: str, resultado: Any) -> None:
        archivo = DIRECTORIO / f"{nombre}.json"
        DIRECTORIO.mkdir(parents=True, exist_ok=True)

        # `sort_keys` + `indent`: el archivo tiene que ser estable entre
        # corridas y legible en un diff. Un JSON de una línea con las claves en
        # orden de inserción haría que cualquier cambio se viera como "todo
        # cambió".
        texto = json.dumps(resultado, indent=2, ensure_ascii=False, sort_keys=True)

        if actualizar or not archivo.exists():
            archivo.write_text(texto + "\n", encoding="utf-8")
            if not actualizar:
                pytest.skip(
                    f"Golden creado: {archivo.name}. Revísalo en el diff y vuelve "
                    f"a correr."
                )
            return

        esperado = archivo.read_text(encoding="utf-8").strip()
        assert texto == esperado, (
            f"El resultado cambió respecto de {archivo.name}.\n\n"
            f"Si el cambio es el que querías, corre con `--actualizar-golden` y "
            f"revisa el diff. Si no, acabas de encontrar una regresión."
        )

    return comparar
