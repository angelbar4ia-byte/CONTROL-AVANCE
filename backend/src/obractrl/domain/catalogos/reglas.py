"""Reglas de los catálogos maestros.

Spec §7.3 (catálogos maestros y APU) · §10.1 (set compartido con Auditoría) ·
§3.3 (prioridad de CLAVE) · §3.5 (IVA por familia con override por material) ·
§8.7 (invariantes vs semilla editable).

Aquí viven las entidades de catálogo —`Unidad`, `Familia`, `Insumo`,
`Concepto`, `Contratista`— con sus invariantes de alta. El **APU** (explosión
y CPU) es lógica pesada y vive aparte, en `domain.catalogos.apu`, como
permite el §11.1 ("para los contextos con lógica pesada —APU/CPU y CPM— se
extraen entidades de dominio puras").

Dos cosas que este módulo **no** hace, a propósito:

- **No** valida los prefijos de clave (`EST`, `SUB`, `MOA`…, §10.1): son
  semilla editable (§8.7), así que el dominio los normaliza y los deja
  disponibles en `Clave.prefijo` para quien los contraste contra la lista
  viva de Configuración. Mismo criterio que `domain.proyectos.reglas.Prototipo`.
- **No** decide quién ve qué: el alcance por rol es frontera de la base
  (§12.4; los catálogos entran al bloque A de `rls_policies`, alcance de
  organización, escritura solo para `app.es_config()`).

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).

**`Material` no es una entidad propia:** el §7.3 lo define como
``Insumo`` con ``tipo = material``. `Insumo.es_material` es toda la
diferencia; duplicar la entidad duplicaría la clave única del catálogo y
rompería el §3.3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from obractrl.domain.shared.diccionario import TipoConcepto, TipoInsumo
from obractrl.domain.shared.valores import Clave

__all__ = [
    "AMBITOS_FAMILIA",
    "Concepto",
    "Contratista",
    "Cuadrilla",
    "ErrorDeCatalogo",
    "Familia",
    "Insumo",
    "Unidad",
    "resolver_iva",
]

AMBITOS_FAMILIA: frozenset[str] = frozenset({"material", "concepto"})
"""Ámbitos de un árbol de familias: "Familias (materiales / conceptos)" (§10.1)."""


class ErrorDeCatalogo(ValueError):
    """Invariante rota en un catálogo maestro (§7.3)."""


def _exigir_texto(valor: str, campo: str) -> str:
    limpio = " ".join(str(valor).split())
    if not limpio:
        raise ErrorDeCatalogo(f"El campo {campo!r} es obligatorio.")
    return limpio


def _opcional(valor: str | None) -> str | None:
    if valor is None:
        return None
    limpio = " ".join(str(valor).split())
    return limpio or None


def _exigir_clave(valor: str) -> Clave:
    """La clave es única por catálogo y es la que manda en todo cruce (§3.3)."""
    try:
        return Clave(valor)
    except ValueError as exc:
        raise ErrorDeCatalogo(str(exc)) from exc


def _exigir_no_negativo(valor: Decimal, campo: str) -> Decimal:
    if valor < 0:
        raise ErrorDeCatalogo(f"El campo {campo!r} no puede ser negativo: {valor}.")
    return valor


def _exigir_positivo(valor: Decimal, campo: str) -> Decimal:
    if valor <= 0:
        raise ErrorDeCatalogo(f"El campo {campo!r} debe ser mayor que cero: {valor}.")
    return valor


def _exigir_plazo(valor: int | None) -> int | None:
    """Plazo de entrega en días (§10.1, migración 0044).

    `None` se conserva: es "no se ha capturado", que no es lo mismo que cero
    —llega el mismo día—. Confundirlos haría que un insumo sin capturar
    ignorara la anticipación global en vez de heredarla.
    """
    if valor is None:
        return None
    if valor < 0:
        raise ErrorDeCatalogo(
            f"El plazo de entrega no puede ser negativo: {valor}. Pedir un "
            f"insumo despues de usarlo no es un plazo (§10.1)."
        )
    return int(valor)


def resolver_iva(*, iva_familia: bool, override_insumo: bool | None) -> bool:
    """IVA efectivo de un insumo (§3.5).

    "IVA por material (casilla en el catálogo de Materiales): valor inicial
    derivado de la **familia** (gravada → activada; Pétreos / Jardinería →
    desactivada); **override por material**" (§3.5).

    Por eso `insumo.iva_aplica` es *nullable* en el esquema: ``None`` no
    significa "no aplica", significa **hereda de la familia** — así lo dice el
    `comment on column insumo.iva_aplica` de la migración 0005. Un booleano
    explícito es el override y gana sobre la familia, incluso cuando lo que
    hace es reactivar el IVA de una familia exenta.

    La **tasa** (16%) no entra aquí: es configurable y se lee de BD (§8.7,
    `RepositorioConfiguracion`); esta función solo decide *si* aplica.
    """
    if override_insumo is None:
        return iva_familia
    return override_insumo


@dataclass(slots=True)
class Unidad:
    """Unidad de medida con sus sinónimos y factor (§7.3, §3.5).

    Semilla editable (§8.7): el código siembra las canónicas del §8.4 y el
    usuario extiende la lista desde Configuración. Los **sinónimos** son lo
    que permite que ``pza``, ``PZ`` y ``PIEZA`` crucen a la misma unidad al
    homologar (§10.3).
    """

    clave: Clave
    nombre: str
    sinonimos: tuple[str, ...] = ()
    factor: Decimal = Decimal(1)

    @classmethod
    def crear(
        cls,
        *,
        clave: str,
        nombre: str,
        sinonimos: list[str] | None = None,
        factor: Decimal = Decimal(1),
    ) -> Unidad:
        canonica = _exigir_clave(clave)
        # Los sinónimos se normalizan con la misma regla que la clave: si
        # `PZ` y ` pz ` cayeran distintos, el cruce por sinónimo fallaría
        # justo en el caso que existe para resolver (§10.3).
        vistos: dict[str, None] = {}
        for sinonimo in sinonimos or []:
            limpio = str(_exigir_clave(sinonimo))
            if limpio != str(canonica):
                vistos[limpio] = None
        return cls(
            clave=canonica,
            nombre=_exigir_texto(nombre, "nombre"),
            sinonimos=tuple(vistos),
            factor=_exigir_positivo(factor, "factor"),
        )


@dataclass(slots=True)
class Cuadrilla:
    """Grupo de trabajadores al que se asigna un destajo (§7.6, §10.6).

    Alta manual mínima (§11.2): clave, nombre y opcionalmente la unidad a la
    que refiere su PU (p.ej. "jor"). La composición y el precio versionado
    se cargan por archivo (`CABECERAS_CUADRILLAS.xlsx`, §10.6), no aquí.
    """

    clave: Clave
    nombre: str
    unidad_id: str | None = None

    @classmethod
    def crear(
        cls, *, clave: str, nombre: str, unidad_id: str | None = None
    ) -> Cuadrilla:
        return cls(
            clave=_exigir_clave(clave),
            nombre=_exigir_texto(nombre, "nombre"),
            unidad_id=_opcional(unidad_id),
        )


@dataclass(slots=True)
class Familia:
    """Nodo del árbol de familias (§7.3). En materiales define el IVA (§3.5)."""

    clave: Clave
    nombre: str
    parent_id: str | None = None
    aplica_a: str = "material"
    iva_aplica: bool = True

    @classmethod
    def crear(
        cls,
        *,
        clave: str,
        nombre: str,
        parent_id: str | None = None,
        aplica_a: str = "material",
        iva_aplica: bool = True,
    ) -> Familia:
        ambito = str(aplica_a).strip().lower()
        if ambito not in AMBITOS_FAMILIA:
            raise ErrorDeCatalogo(
                f"Ámbito de familia desconocido: {aplica_a!r}. Las familias son "
                f"de materiales o de conceptos (§10.1): "
                f"{', '.join(sorted(AMBITOS_FAMILIA))}."
            )
        return cls(
            clave=_exigir_clave(clave),
            nombre=_exigir_texto(nombre, "nombre"),
            parent_id=_opcional(parent_id),
            aplica_a=ambito,
            iva_aplica=iva_aplica,
        )


@dataclass(slots=True)
class Insumo:
    """Recurso base del APU (§7.3). ``Material`` = insumo con `tipo='material'`.

    `iva_aplica` es el **override** del valor de la familia y por eso admite
    ``None`` = heredar (§3.5). Resolverlo es trabajo de :func:`resolver_iva`,
    no del constructor: la familia no viaja con el insumo.
    """

    tipo: TipoInsumo
    clave: Clave
    descripcion: str
    unidad_id: str | None = None
    familia_id: str | None = None
    costo_base: Decimal = Decimal(0)
    iva_aplica: bool | None = None
    factor_conversion: Decimal = Decimal(1)
    dias_entrega: int | None = None
    """Plazo de entrega: con cuánta anticipación hay que pedirlo para tenerlo
    cuando el cronograma lo pide (§7.3, migración 0044). `None` = no se ha
    capturado y manda la anticipación global de quien consulta; cero es un
    dato —llega el mismo día—, no un hueco."""

    @classmethod
    def crear(
        cls,
        *,
        tipo: TipoInsumo | str,
        clave: str,
        descripcion: str,
        unidad_id: str | None = None,
        familia_id: str | None = None,
        costo_base: Decimal = Decimal(0),
        iva_aplica: bool | None = None,
        factor_conversion: Decimal = Decimal(1),
        dias_entrega: int | None = None,
    ) -> Insumo:
        try:
            tipo_canonico = TipoInsumo(tipo)
        except ValueError as exc:
            raise ErrorDeCatalogo(
                f"Tipo de insumo desconocido: {tipo!r}. Es un invariante del "
                f"§8.2; un valor fuera de la lista va a la bandeja de "
                f"pendientes (§10.3), no al catálogo."
            ) from exc

        return cls(
            tipo=tipo_canonico,
            clave=_exigir_clave(clave),
            descripcion=_exigir_texto(descripcion, "descripcion"),
            unidad_id=_opcional(unidad_id),
            familia_id=_opcional(familia_id),
            costo_base=_exigir_no_negativo(costo_base, "costo_base"),
            iva_aplica=iva_aplica,
            factor_conversion=_exigir_positivo(factor_conversion, "factor_conversion"),
            dias_entrega=_exigir_plazo(dias_entrega),
        )

    @property
    def es_material(self) -> bool:
        """`Material` = `Insumo` con `tipo = material` (§7.3): no hay tabla aparte."""
        return self.tipo is TipoInsumo.MATERIAL

    def iva_efectivo(self, *, iva_familia: bool) -> bool:
        """IVA que aplica a este insumo dado el de su familia (§3.5)."""
        return resolver_iva(iva_familia=iva_familia, override_insumo=self.iva_aplica)


@dataclass(slots=True)
class Concepto:
    """Partida de obra (§7.3). El `tipo` permite anidar auxiliares y matrices."""

    tipo: TipoConcepto
    clave: Clave
    descripcion: str
    unidad_id: str | None = None
    familia_id: str | None = None

    @classmethod
    def crear(
        cls,
        *,
        clave: str,
        descripcion: str,
        tipo: TipoConcepto | str = TipoConcepto.CONCEPTO,
        unidad_id: str | None = None,
        familia_id: str | None = None,
    ) -> Concepto:
        try:
            tipo_canonico = TipoConcepto(tipo)
        except ValueError as exc:
            raise ErrorDeCatalogo(
                f"Tipo de concepto desconocido: {tipo!r}. Es un invariante del "
                f"§8.2; un valor fuera de la lista va a la bandeja de "
                f"pendientes (§10.3), no al catálogo."
            ) from exc

        return cls(
            tipo=tipo_canonico,
            clave=_exigir_clave(clave),
            descripcion=_exigir_texto(descripcion, "descripcion"),
            unidad_id=_opcional(unidad_id),
            familia_id=_opcional(familia_id),
        )

    @property
    def es_anidable(self) -> bool:
        """Auxiliares y matrices son los conceptos que otros explotan (§7.3)."""
        return self.tipo in (TipoConcepto.AUXILIAR, TipoConcepto.MATRIZ)


@dataclass(slots=True)
class Contratista:
    """Contratista oficial del catálogo (§7.3, §10.1).

    Los alias con que aparece en archivos externos **no** viven aquí: son
    `mapeo` (§10.3), justo para no ensuciar la lista oficial.
    """

    clave: Clave
    razon_social: str
    rfc: str | None = None
    contacto: str | None = None
    telefono: str | None = None
    email: str | None = None
    calificacion: Decimal | None = None
    frentes: tuple[str, ...] = field(default=())

    @classmethod
    def crear(
        cls,
        *,
        clave: str,
        razon_social: str,
        rfc: str | None = None,
        contacto: str | None = None,
        telefono: str | None = None,
        email: str | None = None,
        calificacion: Decimal | None = None,
        frentes: list[str] | None = None,
    ) -> Contratista:
        if calificacion is not None and calificacion < 0:
            raise ErrorDeCatalogo(
                f"La calificación de un contratista no puede ser negativa: "
                f"{calificacion}."
            )
        return cls(
            clave=_exigir_clave(clave),
            razon_social=_exigir_texto(razon_social, "razon_social"),
            # El RFC se guarda en mayúsculas: es una clave fiscal, y el §3.3
            # exige que dos escrituras del mismo valor crucen igual.
            rfc=(_opcional(rfc) or "").upper() or None,
            contacto=_opcional(contacto),
            telefono=_opcional(telefono),
            email=(_opcional(email) or "").lower() or None,
            calificacion=calificacion,
            frentes=tuple(dict.fromkeys(frentes or [])),
        )
