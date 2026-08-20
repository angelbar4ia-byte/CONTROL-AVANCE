"""Cierre de obra final — workflow D (§11.3 D, §11.2, §6).

Es la culminación del sistema: se cierra la obra con la que se empezó. El
expediente técnico de la Fase 5 se construyó justamente para sostenerlo.

## Los tres pasos, y qué decide cada uno

1. **Abrir** (SI). Crea el `CierreObra` en `en_proceso` y **reúne pendientes**
   (§11.3 D.1). Abrir con pendientes está permitido y es el punto: convocar al
   equipo es lo que hace que los pendientes se resuelvan. Lo que no se puede es
   firmar con ellos.
2. **Participar** (cada rol). Residente entrega, Supervisor da su visto bueno,
   Control de obra responde por calidad y expediente, Super intendente firma.
   Uno por rol —lo impone `uq_cierre_obra_participacion`—: la participación es
   del rol, no de la persona.
3. **Cerrar**. Cuando participaron los cuatro **y** no queda ningún pendiente
   bloqueante, la obra pasa a `entregada` y queda congelada (§11.3 D.3).

## Qué bloquea y qué no

No todo pendiente impide cerrar, y confundirlos haría la ruta inservible:

· **Bloquean** — avance incompleto, actividades sin concluir, cierres de
  actividad esperando resolución, estimaciones sin validar. Todos significan
  lo mismo: hay trabajo o dinero sin resolver, y firmar la entrega los daría
  por buenos sin que nadie los haya mirado.
· **No bloquean** — incidencias abiertas de impacto menor, expediente sin
  documentos, evaluación final ausente. Son cosas que **deberían** estar y cuya
  falta hay que ver, pero que no describen trabajo sin terminar. Bloquear con
  ellas convertiría el cierre en un trámite imposible y enseñaría a saltárselo.

Una incidencia que **detiene** sí bloquea: no es un detalle de calidad, es la
obra parada.

Módulo puro: sin FastAPI, SQLModel ni RLS (§12.11).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from obractrl.domain.shared.diccionario import Rol

__all__ = [
    "ROLES_QUE_PARTICIPAN",
    "CierreDeObra",
    "ErrorDeCierreDeObra",
    "Pendiente",
    "evaluar_pendientes",
    "puede_abrir_cierre_de_obra",
]

ROLES_QUE_PARTICIPAN: tuple[Rol, ...] = (
    Rol.RESIDENTE,
    Rol.SUPERVISOR,
    Rol.CONTROL_OBRA,
    Rol.SUPER_INTENDENTE,
)
"""Los cuatro del §11.3 D.2. El cierre no es de nadie en particular: es el acta
en la que cada rol responde por su parte."""

APORTACION_POR_ROL: dict[Rol, str] = {
    Rol.RESIDENTE: "entrega",
    Rol.SUPERVISOR: "visto bueno",
    Rol.CONTROL_OBRA: "calidad y expediente",
    Rol.SUPER_INTENDENTE: "firma",
}
"""Qué aporta cada rol (§11.3 D.2). Se nombra para que la pantalla no tenga que
inventarlo y para que quede escrito de dónde sale."""


class ErrorDeCierreDeObra(ValueError):
    """Invariante rota en el cierre de obra (§11.3 D)."""


def puede_abrir_cierre_de_obra(rol: Rol) -> bool:
    """Solo el Super intendente (§11.2 marca la `(SI)`).

    Abrir el cierre convoca a los cuatro roles a firmar una entrega. Que lo
    dispare quien responde por la organización, y no quien ejecuta, es lo que
    impide que la obra se dé por entregada desde dentro.
    """
    return rol is Rol.SUPER_INTENDENTE


@dataclass(frozen=True, slots=True)
class Pendiente:
    """Algo que falta para poder firmar la entrega.

    `bloquea` es la única distinción que importa: los que bloquean impiden
    cerrar; los demás se muestran para que alguien los mire.
    """

    clave: str
    detalle: str
    bloquea: bool
    cuantos: int = 0


def evaluar_pendientes(estado: dict[str, object]) -> list[Pendiente]:
    """Traduce el estado de la obra a la lista de lo que falta (§11.3 D.1).

    Recibe un `dict` y no una entidad porque los datos vienen de cinco
    contextos distintos —avance, cierres, estimación, incidencias,
    expediente— y armarlos en un agregado aquí obligaría al dominio a conocer
    cinco formas. El repositorio los junta en una consulta; esta función solo
    decide qué significan.
    """

    def entero(clave: str) -> int:
        valor = estado.get(clave, 0)
        return int(valor) if isinstance(valor, (int, float, Decimal)) else 0

    avance = estado.get("avance_pct", 0)
    avance_pct = Decimal(str(avance)) if avance is not None else Decimal(0)

    pendientes: list[Pendiente] = []

    if avance_pct < Decimal(100):
        pendientes.append(
            Pendiente(
                clave="avance_incompleto",
                detalle=f"La obra va en {avance_pct} % de avance.",
                bloquea=True,
            )
        )

    sin_concluir = entero("actividades_sin_concluir")
    if sin_concluir > 0:
        pendientes.append(
            Pendiente(
                clave="actividades_sin_concluir",
                detalle=f"{sin_concluir} actividad(es) sin concluir.",
                bloquea=True,
                cuantos=sin_concluir,
            )
        )

    cierres = entero("cierres_pendientes")
    if cierres > 0:
        pendientes.append(
            Pendiente(
                clave="cierres_pendientes",
                detalle=(
                    f"{cierres} cierre(s) de actividad esperando autorización o "
                    f"validación (§11.3 C)."
                ),
                bloquea=True,
                cuantos=cierres,
            )
        )

    estimaciones = entero("estimaciones_sin_validar")
    if estimaciones > 0:
        pendientes.append(
            Pendiente(
                clave="estimaciones_sin_validar",
                detalle=(
                    f"{estimaciones} estimación(es) sin validar: hay dinero sin "
                    f"resolver (§11.3 E)."
                ),
                bloquea=True,
                cuantos=estimaciones,
            )
        )

    detienen = entero("incidencias_detienen")
    if detienen > 0:
        pendientes.append(
            Pendiente(
                clave="incidencias_detienen",
                detalle=f"{detienen} incidencia(s) tienen la obra detenida.",
                bloquea=True,
                cuantos=detienen,
            )
        )

    # --- De aquí para abajo, se informan pero no impiden firmar ---

    abiertas = entero("incidencias_abiertas") - detienen
    if abiertas > 0:
        pendientes.append(
            Pendiente(
                clave="incidencias_abiertas",
                detalle=f"{abiertas} incidencia(s) abiertas que no detienen la obra.",
                bloquea=False,
                cuantos=abiertas,
            )
        )

    if entero("documentos_expediente") == 0:
        pendientes.append(
            Pendiente(
                clave="expediente_vacio",
                detalle=(
                    "El expediente no tiene documentos: la obra se entregaría sin "
                    "acervo (§7.9)."
                ),
                bloquea=False,
            )
        )

    if entero("evaluaciones_finales") == 0:
        pendientes.append(
            Pendiente(
                clave="sin_evaluacion_final",
                detalle="No hay evaluación final de la obra (§11.3 H).",
                bloquea=False,
            )
        )

    return pendientes


@dataclass(slots=True)
class CierreDeObra:
    """El acta de entrega en curso (§11.3 D)."""

    obra_id: str
    participantes: frozenset[Rol] = frozenset()
    cerrada: bool = False

    @property
    def faltan_por_participar(self) -> tuple[Rol, ...]:
        return tuple(r for r in ROLES_QUE_PARTICIPAN if r not in self.participantes)

    @property
    def participaron_todos(self) -> bool:
        return not self.faltan_por_participar

    def registrar_participacion(self, rol: Rol) -> CierreDeObra:
        """Un rol registra su parte (§11.3 D.2).

        Devuelve un cierre nuevo en vez de mutar: así el caso de uso puede
        decidir si con esta participación ya se cierra, sin haber tocado nada.
        """
        if self.cerrada:
            raise ErrorDeCierreDeObra(
                "La obra ya está cerrada; no se puede volver a participar."
            )
        if rol not in ROLES_QUE_PARTICIPAN:
            raise ErrorDeCierreDeObra(f"El rol {rol.value} no participa en el cierre.")
        if rol in self.participantes:
            # No es un error de datos: es que ese rol ya firmó. Se distingue del
            # resto porque la pantalla puede querer decir "ya participaste" en
            # vez de "algo salió mal".
            raise ErrorDeCierreDeObra(
                f"El rol {rol.value} ya registró su participación en este cierre."
            )
        return CierreDeObra(
            obra_id=self.obra_id,
            participantes=self.participantes | {rol},
            cerrada=self.cerrada,
        )

    def exigir_que_se_pueda_cerrar(self, pendientes: list[Pendiente]) -> None:
        """¿Se puede firmar? (§11.3 D.3)

        Dos condiciones, y las dos tienen que decirse por separado en el error:
        quien lo lea necesita saber si le falta convocar o le falta resolver.
        """
        if not self.participaron_todos:
            faltan = ", ".join(r.value for r in self.faltan_por_participar)
            raise ErrorDeCierreDeObra(
                f"Faltan por participar: {faltan} (§11.3 D.2)."
            )

        bloqueantes = [p for p in pendientes if p.bloquea]
        if bloqueantes:
            detalle = " ".join(p.detalle for p in bloqueantes)
            raise ErrorDeCierreDeObra(
                f"La obra no se puede entregar todavía. {detalle}"
            )
