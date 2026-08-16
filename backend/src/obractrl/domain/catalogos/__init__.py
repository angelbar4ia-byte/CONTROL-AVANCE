"""Contexto de dominio: Catálogos · APU (§11.1).

Dos módulos:

- `reglas` — entidades de catálogo (`Unidad`, `Familia`, `Insumo`,
  `Concepto`, `Contratista`) y la regla de IVA del §3.5.
- `apu` — explosión recursiva y CPU con desglose de destajo (§7.3).

`PrecioUnitario`, el value object del §11.1, **no se redefine aquí**: vive en
`domain.shared.valores` junto a `Dinero`, `Cantidad` y `Avance`, porque lo
consumen también la estimación (§6, modo de pago) y la generación de obra
(§11.3 A). El §8.7 pide que los invariantes vivan una sola vez en el núcleo
compartido; se reexporta para que el contexto lo tenga a mano.
"""

from __future__ import annotations

from obractrl.domain.shared.valores import PrecioUnitario

__all__ = ["PrecioUnitario"]
