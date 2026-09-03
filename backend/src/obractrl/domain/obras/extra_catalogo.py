"""Alta extra-catálogo: el trabajo que aparece cuando la obra se mueve.

Spec §11.2 (`POST /actividades` — alta extra-catálogo con OC, rol **R**) ·
§5.1 (el Residente trae «Extra-catálogo» en su sidebar) · §8.2 (el enum
`estatus_actividad` ya declara `extra_catalogo`).

## Por qué existe esta ruta

En una obra real siempre hay trabajo que no estaba en el prototipo: un muro que
había que demoler, una instalación que el proyecto no traía. Hasta ahora no
había dónde registrarlo, así que o se capturaba contra una actividad que no
correspondía —falseando su avance— o no se capturaba.

## La orden de cambio

El §11.2 la nombra una vez y no la define. Se interpreta como **orden de
cambio**: el documento que autoriza ejecutar algo fuera de catálogo. La regla
que se deriva es simple y no admite excepción: **no hay extra sin orden**.

Vive dos veces a propósito —aquí y como `ck_actividad_extra_con_oc` en la
migración 0026—: esta da un mensaje en español antes de tocar la base; la de la
base es la que **garantiza**, también para la ruta directa a Supabase (§10.7).

## Quién

Solo el Residente (§11.2 marca la `(R)`). Es quien está en la obra y ve
aparecer el trabajo; Control de obra y Supervisor lo revisan después por los
mismos caminos que todo lo demás —la Torre, el cierre, la estimación—.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.shared.diccionario import EstatusActividad, ModoPago, Rol

__all__ = [
    "ActividadExtra",
    "ErrorDeExtraCatalogo",
    "puede_dar_de_alta_extra",
]


class ErrorDeExtraCatalogo(ValueError):
    """Invariante rota en un alta extra-catálogo (§11.2).

    Lleva `campo` para que el borde lo mapee a un `problem+json` con la ruta
    del dato que falló, igual que `ErrorDeCaptura` (§11.2).
    """

    def __init__(self, mensaje: str, campo: str) -> None:
        super().__init__(mensaje)
        self.campo = campo


def puede_dar_de_alta_extra(rol: Rol) -> bool:
    """Solo el Residente (§11.2).

    No es una restricción de comodidad: quien da de alta un extra está
    afirmando que ese trabajo existe en la obra, y el único que puede afirmarlo
    es quien está ahí. Que después haya que estimarlo y cerrarlo es lo que pone
    a los otros roles a revisarlo.
    """
    return rol is Rol.RESIDENTE


@dataclass(frozen=True, slots=True)
class ActividadExtra:
    """Una actividad fuera de catálogo, ya validada (§11.2)."""

    obra_id: str
    descripcion: str
    orden_cambio: str
    cant_base: Decimal
    modo_pago: ModoPago
    precio_unitario: Decimal
    precio_destajo: Decimal
    concepto_id: str | None = None
    frente_id: str | None = None
    nivel_id: str | None = None
    """El **frente** donde cae este trabajo (§7.4): cimentación, planta baja.

    Sin él la actividad no aparece en ningún grupo de la pantalla del residente
    —que agrupa por nivel y etapa— y queda como trabajo huérfano que solo se ve
    filtrando por «fuera de catálogo». El trabajo existe en algún lado de la
    obra; decir dónde es parte de darlo de alta.
    """
    etapa_id: str | None = None
    """El **sub-frente**: la etapa dentro del nivel. Es la unidad con la que se
    reprograma, así que un extra sin ella no se puede mover con su grupo."""
    duracion_dias: Decimal = Decimal(1)

    @property
    def estatus(self) -> EstatusActividad:
        """Nace en `extra_catalogo` (§8.2).

        Es el equivalente de `programada` para una actividad extra, y el
        trigger de la 0026 la mueve a `en_proceso` en cuanto se le captura
        avance. Distinguirla desde el estatus es lo que permite listar «lo que
        di de alta y todavía no empieza».
        """
        return EstatusActividad.EXTRA_CATALOGO

    @classmethod
    def crear(
        cls,
        *,
        obra_id: str,
        descripcion: str,
        orden_cambio: str,
        cant_base: Decimal,
        rol: Rol,
        modo_pago: ModoPago = ModoPago.DESTAJO,
        precio_unitario: Decimal = Decimal(0),
        precio_destajo: Decimal = Decimal(0),
        concepto_id: str | None = None,
        frente_id: str | None = None,
        nivel_id: str | None = None,
        etapa_id: str | None = None,
        duracion_dias: Decimal = Decimal(1),
    ) -> ActividadExtra:
        if not puede_dar_de_alta_extra(rol):
            raise ErrorDeExtraCatalogo(
                f"Un {rol.value} no da de alta trabajo extra-catálogo; "
                f"lo hace el residente de la obra (§11.2).",
                campo="rol",
            )

        orden = " ".join(str(orden_cambio).split())
        if not orden:
            raise ErrorDeExtraCatalogo(
                "El trabajo extra necesita la orden de cambio que lo autoriza.",
                campo="orden_cambio",
            )

        texto = " ".join(str(descripcion).split())
        if not texto:
            raise ErrorDeExtraCatalogo(
                "Describe qué trabajo es: sin descripción, el extra no se puede "
                "revisar ni estimar.",
                campo="descripcion",
            )

        if cant_base <= 0:
            raise ErrorDeExtraCatalogo(
                f"La cantidad debe ser mayor que cero: {cant_base}.",
                campo="cant_base",
            )

        if precio_unitario < 0 or precio_destajo < 0:
            raise ErrorDeExtraCatalogo(
                "Los precios no pueden ser negativos.", campo="precio_unitario"
            )

        # Un extra sin precio no se puede estimar (§11.3 E), y una actividad que
        # no se puede estimar es trabajo que nadie va a cobrar. Se exige el
        # precio del modo de pago que se eligió, no los dos: un destajo no tiene
        # por qué traer precio unitario.
        if modo_pago is ModoPago.DESTAJO and precio_destajo <= 0:
            raise ErrorDeExtraCatalogo(
                "Un extra a destajo necesita su precio de destajo: si no, no se "
                "puede estimar y nadie lo cobra.",
                campo="precio_destajo",
            )
        if modo_pago is not ModoPago.DESTAJO and precio_unitario <= 0:
            raise ErrorDeExtraCatalogo(
                f"Un extra por {modo_pago.value} necesita su precio unitario: si "
                f"no, no se puede estimar y nadie lo cobra.",
                campo="precio_unitario",
            )

        if duracion_dias <= 0:
            raise ErrorDeExtraCatalogo(
                f"La duración debe ser mayor que cero: {duracion_dias}.",
                campo="duracion_dias",
            )

        return cls(
            obra_id=obra_id,
            descripcion=texto,
            orden_cambio=orden,
            cant_base=cant_base,
            modo_pago=modo_pago,
            precio_unitario=precio_unitario,
            precio_destajo=precio_destajo,
            concepto_id=concepto_id,
            frente_id=frente_id,
            nivel_id=nivel_id,
            etapa_id=etapa_id,
            duracion_dias=duracion_dias,
        )
