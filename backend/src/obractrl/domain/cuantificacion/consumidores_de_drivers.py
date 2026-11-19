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

No hay precios ni destajos aquí. Datos puros.

Cómo se conecta `desperdicio_mamposteria` (F6, decidido y **sin ejecutar**)
---------------------------------------------------------------------------
El usuario decidió que el driver se conecta **cuando el sillar y el block sean elementos** de la biblioteca (hoy el sillar amarillo, 19 cm,
solo existe como concepto BAP-01010 y el block hueco no existe ni como concepto: ver `muro_ubicacion.MATERIALES_DE_MURO` y la regla F7 en
`conceptos_de_elemento`). Cuando exista el elemento de cada material, los pasos son, en este orden:

1. Crear el elemento con su concepto (regla F7, versión propuesta que autoriza Control de obra; sin precios) y ponerlo en
   `MATERIALES_DE_MURO[material]["elemento"]`: así la plantilla lo toma como mampostería implícita igual que EST-02010.
2. Que el cálculo del elemento lea `desperdicio_mamposteria` por `drivers_de_elementos` (valor vigente de la obra: petición > obra > defecto),
   **sin** tocar el tabique de 14 cm, cuyo desperdicio sigue en el elemento (M-105).
3. Registrar aquí un `Consumidor` (p. ej. `mamposteria_no_tabique`, `claves=("desperdicio_mamposteria",)`) y **quitar** el driver de
   `SIN_CONSUMIDOR_POR_AHORA`: `tests/api/test_drivers_conectados.py` falla a propósito si un driver gana consumidor sin salir de esa lista.
4. Que el cambio del valor del driver lo autorice Control de obra (F3), con su bitácora.

Mientras tanto no se aplica ningún desperdicio nuevo a la mampostería: no se inventan porcentajes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "CONSUMIDORES",
    "SIN_CONSUMIDOR_POR_AHORA",
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
        "(12 % de pieza y 5 % de mezcla, M-105). F6 (decidido, aún sin ejecutar): se conecta cuando el sillar y el block sean elementos; "
        "ver «Cómo se conecta desperdicio_mamposteria (F6)» arriba."
    ),
}
"""Drivers vigentes del catálogo que ningún cálculo lee todavía, con el motivo. La prueba falla si uno de ellos gana un consumidor
sin salir de esta lista (o si un driver pierde el suyo y no entra)."""


def consumidores_de(clave: str) -> tuple[Consumidor, ...]:
    """Los elementos y artefactos que leen el driver `clave` (vigente o constante)."""
    return tuple(c for c in CONSUMIDORES if clave in c.claves or clave in c.constantes)

