"""Quién usa cada driver del Paramétrico: el registro explícito de consumidores (Ola 4, «drivers conectados»).

La pestaña Paramétrico muestra, por cada driver, **«lo usan»**: la lista de elementos y artefactos cuyo cálculo lo lee. Esa lista sale
de este registro, no de un texto suelto. Una prueba (`tests/domain/test_consumidores_de_drivers.py`) lo mantiene honesto en los dos
sentidos: cambia cada driver, uno por uno, y comprueba que el resultado de cada consumidor cambia **si y solo si** el registro dice
que ese consumidor lo lee; y falla si un driver del catálogo no tiene ningún consumidor (salvo los que `SIN_CONSUMIDOR_POR_AHORA`
declara, con su motivo) o si el registro nombra un driver que no existe.

Dos formas de leer un driver:

- `claves`: el cálculo lee el valor **vigente de la obra** (petición > obra > defecto, ver `drivers_de_elementos`);
- `constantes`: el driver es **fijo** (no se edita por obra) y el cálculo lo sigue leyendo como constante del dominio, que debe ser
  igual al valor de partida del driver (`escarpio_minimo`, `corona_cimiento_cm` en el muro de cimentación de piedra).

La **fachada por bandas** (F1) NO lee ningún driver, a propósito: reparte los m² de cara exterior de los muros reales con las bandas de la
decisión del usuario (0 a 3.00, 3.00 a 4.20, resto), que son constantes del dominio (`fachada_por_bandas`), y con la altura de cada muro y su zona
de losa; no lee `altura_estandar` (el plano ya no la lee) ni ningún otro. `SIN_DRIVER_POR_DECISION` lo deja escrito y una prueba lo mantiene.
`escarpio_minimo` y `corona_cimiento_cm` siguen **inmutables** (F4: ni su valor ni su modo se proponen ni se cambian).

No hay precios ni destajos aquí. Datos puros.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "CONSUMIDORES",
    "SIN_CONSUMIDOR_POR_AHORA",
    "SIN_DRIVER_POR_DECISION",
    "Consumidor",
    "consumidores_de",
]

TipoDeConsumidor = Literal["elemento", "artefacto", "plano"]
DondeSeVerifica = Literal["backend", "frontend"]

_RECETA_DE_ACERO = (
    "traslape_armex_cm",
    "traslape_varilla_diametros",
    "puntas_inferior_diametros",
    "puntas_superior_diametros",
    "puntas_armex_cm",
    "tolerancia_corte_cm",
    "max_piezas_corte",
    "desperdicio_acero",
)


@dataclass(frozen=True, slots=True)
class Consumidor:
    id: str
    tipo: TipoDeConsumidor
    nombre: str
    claves: tuple[str, ...]
    """Los drivers cuyo valor vigente (de la obra) lee su cálculo."""
    constantes: tuple[str, ...] = ()
    """Los drivers fijos que lee como constante del dominio."""
    verificado_en: DondeSeVerifica = "backend"
    """Dónde lo prueba el repositorio: `backend` en `test_consumidores_de_drivers.py`; `frontend` en vitest (la vista previa es del cliente)."""


CONSUMIDORES: tuple[Consumidor, ...] = (
    Consumidor(
        "estructura", "elemento",
        "Castillos K-1…K-8, aparentes y columnas forjadas (biblioteca › Estructura)",
        (*_RECETA_DE_ACERO, "desperdicio_concreto", "altura_estandar"),
    ),
    Consumidor(
        "estructura_lineal", "elemento",
        "Trabes, contratrabes, nervaduras, zapata Z-1 y columna C-1 (biblioteca › Estructura)",
        (*_RECETA_DE_ACERO, "desperdicio_concreto"),
    ),
    Consumidor("receta_acero", "elemento", "Receta del acero (cálculo suelto de varillas, armex y anillos)", _RECETA_DE_ACERO),
    Consumidor(
        "baston", "elemento", "Bastón BA-1 (por longitud de trazo)",
        ("traslape_varilla_diametros", "tolerancia_corte_cm", "max_piezas_corte"),
    ),
    Consumidor(
        "cimentacion_de_piedra", "elemento", "Muro de cimentación de piedra CIM-01010", (),
        constantes=("escarpio_minimo", "corona_cimiento_cm"),
    ),
    Consumidor(
        "plantilla_colocar", "artefacto", "Colocar la plantilla de muro en el plano (reparto de los castillos estimados; el alto lo da el muro)", ("separacion_castillos",),
    ),
    Consumidor(
        "plantilla_vista_previa", "artefacto", "Vista previa de la plantilla de muro (el alto es el de la plantilla)", ("separacion_castillos",),
        verificado_en="frontend",
    ),
)

SIN_CONSUMIDOR_POR_AHORA: dict[str, str] = {
    "desperdicio_mamposteria": (
        "Se aplica a la mampostería de los materiales que no son el tabique de 14 cm (sillar, block…), que todavía no son elementos "
        "de la biblioteca. NO se aplica al tabique de 14 cm (EST-02010) ni a sus aparejos: su desperdicio va en el elemento "
        "(12 % de pieza y 5 % de mezcla, M-105)."
    ),
}
"""Drivers vigentes del catálogo que ningún cálculo lee todavía, con el motivo. La prueba falla si uno de ellos gana un consumidor
sin salir de esta lista (o si un driver pierde el suyo y no entra)."""


SIN_DRIVER_POR_DECISION: dict[str, str] = {
    "fachada_por_bandas": (
        "La fachada del plano por banda de altura (0 a 3.00, 3.00 a 4.20, resto; F1) sale de los muros, las zonas de losa y los puntos de nivel "
        "exterior del plano; las bandas son constantes de la decisión, no un driver."
    ),
}
"""Cálculos que, por decisión, NO leen ningún driver. Una prueba comprueba que cambiar cualquier driver no cambia su resultado."""


def consumidores_de(clave: str) -> tuple[Consumidor, ...]:
    """Los elementos y artefactos que leen el driver `clave` (vigente o constante)."""
    return tuple(c for c in CONSUMIDORES if clave in c.claves or clave in c.constantes)

