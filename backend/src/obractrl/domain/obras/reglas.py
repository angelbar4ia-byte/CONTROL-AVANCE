"""Reglas de la obra.

Spec §7.2 (Obra) · §2.1 (obra = lote/vivienda, unidad mínima de control) ·
§6 (avance) · §11.3 workflow A y D.

La obra es la unidad mínima de control: cuelga de un cluster, instancia un
prototipo y arrastra su propio avance. Dos invariantes la definen:

1. **Una obra sin prototipo es URBA** — espejo exacto del ``ck_obra_urba`` de
   `database/migrations/20260814000004_proyecto_y_obra.sql`. La urbanización
   no sale de un modelo de vivienda, así que es la única que puede ir sin
   `prototipo_id`.
2. **`entregada` congela la obra** (§11.3 D.3). Después del cierre de obra
   final no se mueve avance ni fechas: el hito ya se firmó.

El resto del estatus es **derivado del avance**, no capturado —mismo criterio
que el auto-estatus de la actividad (§6): la BD lo repite en
`app.actividad_recalcular` (la actividad) y en `app.obra_recalcular_avance`
(la obra, migración 0064: el móvil escribe directo a Postgres y ningún caso de
uso se entera) y el front lo refleja, pero la regla se define una sola vez,
aquí. `domain.obras.avance` es el cómo se agrega el avance de la obra.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11). Quién puede crear o editar
una obra es RBAC del borde (§11.2) reforzado por RLS (§12.4), no de esta
entidad.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from obractrl.domain.shared.diccionario import EstatusObra
from obractrl.domain.shared.valores import Avance, Clave

__all__ = [
    "ESTATUS_DERIVADOS",
    "ErrorDeObra",
    "Obra",
    "TransicionDeObraInvalida",
]


class ErrorDeObra(ValueError):
    """Invariante rota en los datos de una obra (§7.2)."""


class TransicionDeObraInvalida(ErrorDeObra):
    """Movimiento de estatus no permitido en el ciclo de la obra (§8.2)."""


ESTATUS_DERIVADOS: frozenset[EstatusObra] = frozenset(
    {
        EstatusObra.PENDIENTE,
        EstatusObra.INICIADA,
        EstatusObra.EN_PROCESO,
        EstatusObra.POR_ENTREGAR,
    }
)
"""Estatus que el avance puede fijar solo.

``entregada`` queda fuera a propósito: lo fija el cierre de obra final (§11.3
D), no el avance —igual que `EstatusActividad.es_automatico` deja fuera los
estatus de flujo (§6).
"""


@dataclass(slots=True)
class Obra:
    """Lote / vivienda: la unidad mínima de control (§2.1, §7.2)."""

    cluster_id: str
    clave: Clave
    prototipo_id: str | None = None
    residente_id: str | None = None
    estatus: EstatusObra = EstatusObra.PENDIENTE
    fecha_inicio: date | None = None
    fecha_fin: date | None = None
    avance: Avance = field(default_factory=Avance)
    m2: Decimal | None = None
    es_urba: bool = False

    @classmethod
    def crear(
        cls,
        *,
        cluster_id: str,
        clave: str,
        prototipo_id: str | None = None,
        residente_id: str | None = None,
        fecha_inicio: date | None = None,
        fecha_fin: date | None = None,
        m2: Decimal | None = None,
        es_urba: bool = False,
    ) -> Obra:
        """Alta de obra (§11.2 `POST /obras`, Control de obra)."""
        if not str(cluster_id).strip():
            raise ErrorDeObra("Toda obra pertenece a un cluster: falta 'cluster_id'.")

        try:
            clave_canonica = Clave(clave)
        except ValueError as exc:
            raise ErrorDeObra(str(exc)) from exc

        if prototipo_id is None and not es_urba:
            raise ErrorDeObra(
                "Una obra sin prototipo solo puede ser urbanización: marca "
                "'es_urba' o asigna un prototipo (§7.2)."
            )

        if m2 is not None and m2 <= 0:
            raise ErrorDeObra(f"Los m2 de la obra deben ser mayores que cero: {m2}.")

        obra = cls(
            cluster_id=str(cluster_id),
            clave=clave_canonica,
            prototipo_id=str(prototipo_id) if prototipo_id else None,
            residente_id=str(residente_id) if residente_id else None,
            m2=m2,
            es_urba=es_urba,
        )
        obra.programar_fechas(inicio=fecha_inicio, fin=fecha_fin)
        return obra

    # --- Invariantes transversales ---------------------------------------

    def _exigir_no_congelada(self, accion: str) -> None:
        """Tras el cierre de obra final la obra queda congelada (§11.3 D.3)."""
        if self.estatus is EstatusObra.ENTREGADA:
            raise TransicionDeObraInvalida(
                f"La obra {self.clave} está entregada y congelada: no se puede "
                f"{accion} (§11.3 D)."
            )

    @property
    def esta_congelada(self) -> bool:
        return self.estatus is EstatusObra.ENTREGADA

    # --- Edición (§11.2 `PATCH /obras/{id}`) ------------------------------

    def programar_fechas(
        self, *, inicio: date | None = None, fin: date | None = None
    ) -> None:
        """Fija el rango de la obra. `None` deja el valor actual sin tocar."""
        nuevo_inicio = inicio if inicio is not None else self.fecha_inicio
        nuevo_fin = fin if fin is not None else self.fecha_fin

        if nuevo_inicio is not None and nuevo_fin is not None and nuevo_fin < nuevo_inicio:
            raise ErrorDeObra(
                f"La fecha de fin ({nuevo_fin}) no puede ser anterior al inicio "
                f"({nuevo_inicio})."
            )

        self.fecha_inicio = nuevo_inicio
        self.fecha_fin = nuevo_fin

    def renombrar(self, clave: str) -> None:
        """Cambia la clave del lote (§10.1: CLUSTER + LOTE)."""
        self._exigir_no_congelada("cambiar la clave")
        try:
            self.clave = Clave(clave)
        except ValueError as exc:
            raise ErrorDeObra(str(exc)) from exc

    def redimensionar(self, m2: Decimal) -> None:
        """Corrige la superficie del lote."""
        self._exigir_no_congelada("cambiar los m2")
        if m2 <= 0:
            raise ErrorDeObra(f"Los m2 de la obra deben ser mayores que cero: {m2}.")
        self.m2 = m2

    def asignar_residente(self, residente_id: str | None) -> None:
        """Asigna (o libera) al residente responsable (§4: su alcance son sus obras)."""
        self._exigir_no_congelada("reasignar al residente")
        self.residente_id = str(residente_id) if residente_id else None

    # --- Ciclo de vida (§8.2) --------------------------------------------

    def iniciar(self, fecha: date) -> None:
        """Arranca la obra: `pendiente` → `iniciada` (§8.2)."""
        if self.estatus is not EstatusObra.PENDIENTE:
            raise TransicionDeObraInvalida(
                f"Solo una obra 'pendiente' se inicia; la obra {self.clave} está "
                f"en {self.estatus.value!r}."
            )
        self.estatus = EstatusObra.INICIADA
        self.programar_fechas(inicio=fecha)

    def sincronizar_avance(self, avance: Avance) -> None:
        """Refleja el avance de la obra y deriva su estatus (§6, §8.2).

        La regla es la misma que la del auto-estatus de la actividad: ``≥ 90%
        → por_entregar`` · ``> 0 → en_proceso``. Solo pisa los estatus derivados
        (`ESTATUS_DERIVADOS`): una obra entregada está congelada.
        """
        self._exigir_no_congelada("mover el avance")

        self.avance = avance
        if self.estatus not in ESTATUS_DERIVADOS:  # pragma: no cover - defensivo
            return

        if avance.esta_casi_listo:
            self.estatus = EstatusObra.POR_ENTREGAR
        elif avance.esta_iniciado:
            self.estatus = EstatusObra.EN_PROCESO
        elif self.estatus is not EstatusObra.INICIADA:
            self.estatus = EstatusObra.PENDIENTE

    def entregar(self, fecha: date) -> None:
        """Cierre de obra final (§11.3 D): la obra queda entregada y congelada.

        No se entrega una obra que nunca arrancó: el hito es la entrega del
        lote completo, con acta y evidencias (§6).
        """
        self._exigir_no_congelada("entregar de nuevo")
        if self.estatus is EstatusObra.PENDIENTE:
            raise TransicionDeObraInvalida(
                f"La obra {self.clave} nunca arrancó: no se puede entregar una "
                f"obra 'pendiente' (§11.3 D)."
            )
        self.estatus = EstatusObra.ENTREGADA
        self.programar_fechas(fin=fecha)

    # --- Generación desde prototipo (§11.3 A) ----------------------------

    def exigir_generable(self, *, ya_tiene_actividades: bool) -> str:
        """Valida que la obra pueda generarse y devuelve su `prototipo_id`.

        Tres razones para negarse (§11.3 A.2):
        * una obra **URBA sin prototipo** no tiene árbol WBS que recorrer;
        * una obra **entregada** está congelada;
        * una obra **que ya tiene actividades** se duplicaría —regenerar es
          una operación de reemplazo, no de alta, y hoy no existe.
        """
        self._exigir_no_congelada("generar actividades")

        if self.prototipo_id is None:
            raise TransicionDeObraInvalida(
                f"La obra {self.clave} no tiene prototipo (es urbanización): no "
                f"hay árbol de prototipo que recorrer (§11.3 A.2)."
            )

        if ya_tiene_actividades:
            raise TransicionDeObraInvalida(
                f"La obra {self.clave} ya tiene actividades generadas; volver a "
                f"generar las duplicaría (§11.3 A.2)."
            )

        return self.prototipo_id
