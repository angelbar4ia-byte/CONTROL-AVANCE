"""Dataset golden de la explosión de insumos y el precio unitario (§11.7, §7.3).

Es el cálculo con más consecuencias del sistema: de él salen el precio de cada
concepto, lo que se estima (§11.3 E) y el consumo teórico contra el que se
cruza el almacén (§10.5). Un error de redondeo aquí no se ve como un error: se
ve como una obra que costó un poco más.

## El árbol que se congela

Un muro de tabique con tres niveles de anidamiento: el concepto raíz usa un
auxiliar (mortero), que a su vez usa otro (cemento-arena). Es donde aparecen las
dos cosas que un caso plano no ejercita: la **cantidad acumulada** —el producto
del camino, no la de la fila— y el **costo de un concepto**, que es el resultado
de explotarlo y no un número capturado.
"""

from __future__ import annotations

from decimal import Decimal

from obractrl.domain.catalogos.apu import Componente, explotar
from obractrl.domain.shared.diccionario import CategoriaExplosion

# Costos del catálogo (§10.1) para los componentes que no traen PU propio.
COSTOS = {
    "CEM-GRIS": Decimal("4.85"),
    "ARENA": Decimal("310.50"),
    "AGUA": Decimal("22.00"),
    "TABIQUE": Decimal("7.35"),
    "ALBAÑIL": Decimal("612.40"),
    "AYUDANTE": Decimal("398.15"),
    "ANDAMIO": Decimal("85.00"),
}

COMPOSICIONES: dict[str, list[Componente]] = {
    "MURO-TAB": [
        Componente(
            categoria=CategoriaExplosion.MATERIAL,
            clave_insumo="TABIQUE",
            cantidad=Decimal("52.5"),
            orden=1,
        ),
        # Un auxiliar: su costo sale de explotarlo, no de un PU capturado.
        Componente(
            categoria=CategoriaExplosion.AUXILIAR,
            clave_concepto="MORTERO",
            cantidad=Decimal("0.032"),
            orden=2,
        ),
        Componente(
            categoria=CategoriaExplosion.MANO_OBRA,
            clave_insumo="ALBAÑIL",
            cantidad=Decimal("0.65"),
            orden=3,
        ),
        Componente(
            categoria=CategoriaExplosion.MANO_OBRA,
            clave_insumo="AYUDANTE",
            cantidad=Decimal("0.65"),
            orden=4,
        ),
        # Con PU propio: el declarado en el APU gana sobre el del catálogo.
        Componente(
            categoria=CategoriaExplosion.EQUIPO,
            clave_insumo="ANDAMIO",
            cantidad=Decimal("0.08"),
            costo_unitario=Decimal("92.50"),
            orden=5,
        ),
    ],
    "MORTERO": [
        Componente(
            categoria=CategoriaExplosion.AUXILIAR,
            clave_concepto="CEM-ARENA",
            cantidad=Decimal("1.0"),
            orden=1,
        ),
        Componente(
            categoria=CategoriaExplosion.MATERIAL,
            clave_insumo="AGUA",
            cantidad=Decimal("0.22"),
            orden=2,
        ),
        Componente(
            categoria=CategoriaExplosion.MANO_OBRA,
            clave_insumo="AYUDANTE",
            cantidad=Decimal("1.8"),
            orden=3,
        ),
    ],
    "CEM-ARENA": [
        Componente(
            categoria=CategoriaExplosion.MATERIAL,
            clave_insumo="CEM-GRIS",
            cantidad=Decimal("350"),
            orden=1,
        ),
        Componente(
            categoria=CategoriaExplosion.MATERIAL,
            clave_insumo="ARENA",
            cantidad=Decimal("1.05"),
            orden=2,
        ),
    ],
}


def _serializar(explosion) -> dict:
    return {
        "clave": explosion.clave,
        # `.monto`, no `str(Dinero)`: el `repr` del value object metería el
        # nombre de la clase en el golden, y entonces renombrarla se vería como
        # un cambio de precio.
        "precio": {
            "total": str(explosion.precio.total.monto),
            "destajo": str(explosion.precio.destajo.monto),
        },
        "lineas": [
            {
                "ruta": list(linea.ruta),
                "nivel": linea.nivel,
                "tipo_hijo": str(linea.tipo_hijo),
                "referencia": linea.referencia,
                "categoria": str(linea.categoria),
                "cantidad_unitaria": str(linea.cantidad_unitaria),
                "cantidad": str(linea.cantidad),
                "costo_unitario": str(linea.costo_unitario),
                "importe": str(linea.importe),
                "es_destajo": linea.es_destajo,
            }
            for linea in explosion.lineas
        ],
    }


def test_golden_muro_de_tabique(golden) -> None:
    """El árbol completo y el precio unitario resultante."""
    explosion = explotar(
        "MURO-TAB", composiciones=COMPOSICIONES, costos_insumo=COSTOS
    )
    golden("explosion_muro_tabique", _serializar(explosion))


def test_golden_auxiliar_suelto(golden) -> None:
    """El auxiliar por su cuenta.

    Se congela aparte porque es el que se cruza contra el almacén (§10.5): si el
    mortero cambia de precio, lo que hay que ver en el diff es este archivo y no
    doscientas líneas del muro entero.
    """
    explosion = explotar("MORTERO", composiciones=COMPOSICIONES, costos_insumo=COSTOS)
    golden("explosion_mortero", _serializar(explosion))


def test_un_concepto_sin_composicion_no_inventa_costo(golden) -> None:
    """Un concepto que no está en `composiciones` se toma como hoja sin desglose.

    Es el caso de un catálogo cargado a medias, y lo que importa es que dé cero
    en vez de tronar: una carga incompleta no puede tumbar la pantalla de CPU.
    """
    explosion = explotar("NO-EXISTE", composiciones=COMPOSICIONES, costos_insumo=COSTOS)
    golden("explosion_concepto_ausente", _serializar(explosion))
