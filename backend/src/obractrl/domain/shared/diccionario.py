"""Diccionario canónico — invariantes del dominio.

Spec §8 (diccionario) · §8.2 (enumeraciones) · §8.7 (invariantes vs semilla).

Estos son los **invariantes**: valores que no cambian sin un cambio real de
lógica. Agregar uno es trabajo de programador y exige migración en
``database/migrations/0002_enums_canonicos.sql``, que es su espejo.

Lo que el negocio extiende solo —unidades, familias, frentes, motivos de
almacén, umbrales— **no vive aquí**: es semilla editable que se carga de BD
(ver ``configurables.py``).

Módulo sin dependencias: el dominio no conoce FastAPI, SQLModel ni RLS.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "ALIAS_ENCABEZADOS",
    "PREFIJOS",
    "BucketAlmacen",
    "CategoriaExplosion",
    "ClaseNodo",
    "EstatusActividad",
    "EstatusCarga",
    "EstatusCierreObra",
    "EstatusEstimacion",
    "EstatusIncidencia",
    "EstatusObra",
    "EstatusProceso",
    "EstatusSolicitudCierre",
    "ImpactoIncidencia",
    "ModoCarga",
    "ModoPago",
    "NivelEvaluacion",
    "Rol",
    "SujetoEvaluacion",
    "TipoCarga",
    "TipoConcepto",
    "TipoExpedienteDoc",
    "TipoHijoExplosion",
    "TipoIncidencia",
    "TipoInsumo",
    "TipoSemana",
]


class _Canonico(StrEnum):
    """Enum de cadena: su valor es exactamente el del enum de Postgres.

    ``StrEnum`` hace que el miembro *sea* su cadena, así que se puede pasar
    directo a una consulta o serializar sin ``.value``.
    """


# --- Identidad y permisos (§4) ------------------------------------------


class Rol(_Canonico):
    RESIDENTE = "residente"
    SUPERVISOR = "supervisor"
    CONTROL_OBRA = "control_obra"
    SUPER_INTENDENTE = "super_intendente"

    @property
    def puede_configurar(self) -> bool:
        """Configuración y catálogos son de Control y Super intendente (§5.1)."""
        return self in (Rol.CONTROL_OBRA, Rol.SUPER_INTENDENTE)

    @property
    def puede_autorizar_cierre(self) -> bool:
        """El Supervisor **autoriza**; nadie más (§4)."""
        return self is Rol.SUPERVISOR

    @property
    def puede_validar_cierre(self) -> bool:
        """Control de obra **valida y comenta**, no autoriza (§4)."""
        return self is Rol.CONTROL_OBRA


# --- Proyecto y obra (§7.2) ---------------------------------------------


class EstatusObra(_Canonico):
    PENDIENTE = "pendiente"
    INICIADA = "iniciada"
    EN_PROCESO = "en_proceso"
    CASI_LISTA = "casi_lista"
    ENTREGADA = "entregada"


class ClaseNodo(_Canonico):
    """Rol del nodo en el árbol WBS. Columna ``CLASE`` del archivo (§10.6)."""

    ETAPA = "etapa"
    NIVEL = "nivel"
    CONCEPTO = "concepto"


# --- Catálogos y APU (§7.3) ---------------------------------------------


class TipoInsumo(_Canonico):
    MATERIAL = "material"
    MANO_OBRA = "mano_obra"
    EQUIPO = "equipo"
    HERRAMIENTA = "herramienta"


class TipoConcepto(_Canonico):
    CONCEPTO = "concepto"
    AUXILIAR = "auxiliar"
    MATRIZ = "matriz"
    BASICO = "basico"


class CategoriaExplosion(_Canonico):
    MATERIAL = "material"
    MANO_OBRA = "mano_obra"
    EQUIPO = "equipo"
    DESTAJO = "destajo"
    SUBCONTRATO = "subcontrato"
    AUXILIAR = "auxiliar"
    MATRIZ = "matriz"


class TipoHijoExplosion(_Canonico):
    INSUMO = "insumo"
    CONCEPTO = "concepto"


# --- Ejecución (§7.6) ----------------------------------------------------


class EstatusActividad(_Canonico):
    PROGRAMADA = "programada"
    EN_PROCESO = "en_proceso"
    CASI = "casi"
    PENDIENTE_CIERRE = "pendiente_cierre"
    CONCLUIDA = "concluida"
    RETRASADA = "retrasada"
    EXTRA_CATALOGO = "extra_catalogo"

    @property
    def es_automatico(self) -> bool:
        """Estatus que el motor de avance puede fijar solo (§6).

        Los de flujo (``pendiente_cierre``, ``concluida``…) los fija el caso
        de uso correspondiente y el auto-estatus no los pisa.
        """
        return self in (
            EstatusActividad.PROGRAMADA,
            EstatusActividad.EN_PROCESO,
            EstatusActividad.CASI,
        )


class ModoPago(_Canonico):
    """``actividad.modo_pago`` y ``estimacion.modo`` comparten valores (§8.2)."""

    DESTAJO = "destajo"
    CONCEPTO = "concepto"
    SUBCONTRATO = "subcontrato"


class EstatusEstimacion(_Canonico):
    BORRADOR = "borrador"
    ENVIADA = "enviada"
    VALIDADA = "validada"


# --- Control y flujos (§7.8) --------------------------------------------


class TipoIncidencia(_Canonico):
    FALTA_MATERIAL = "falta_material"
    ERROR_EJECUCION = "error_ejecucion"
    CAMBIO_CLIENTE = "cambio_cliente"
    PROYECTO_INDEF = "proyecto_indef"
    RETRABAJO = "retrabajo"
    DETALLE = "detalle"


class ImpactoIncidencia(_Canonico):
    DETALLE = "detalle"
    RETRASO = "retraso"
    DETIENE = "detiene"

    @property
    def afecta_programa(self) -> bool:
        """``detalle`` no afecta el programa; ``retraso`` y ``detiene`` sí (§6)."""
        return self is not ImpactoIncidencia.DETALLE

    @property
    def bloquea(self) -> bool:
        return self is ImpactoIncidencia.DETIENE


class EstatusIncidencia(_Canonico):
    ABIERTA = "abierta"
    PROGRAMADA = "programada"
    EN_ATENCION = "en_atencion"
    CIERRE_SOLICITADO = "cierre_solicitado"
    CERRADA = "cerrada"
    RECHAZADA = "rechazada"


class EstatusSolicitudCierre(_Canonico):
    SOLICITADA = "solicitada"
    AUTORIZADA = "autorizada"
    VALIDADA = "validada"
    RECHAZADA = "rechazada"


class EstatusCierreObra(_Canonico):
    EN_PROCESO = "en_proceso"
    CERRADA = "cerrada"


class SujetoEvaluacion(_Canonico):
    OBRA = "obra"
    RESIDENTE = "residente"
    CONTRATISTA = "contratista"


class NivelEvaluacion(_Canonico):
    AUTO = "auto"
    CONTROL = "control"
    FINAL = "final"


# --- Soporte y cargas (§7.9, §9) ----------------------------------------


class TipoExpedienteDoc(_Canonico):
    PLANO = "plano"
    CONTRATO = "contrato"
    ACTA = "acta"
    EVIDENCIA = "evidencia"
    BITACORA = "bitacora"
    OTRO = "otro"


class EstatusProceso(_Canonico):
    """Etapas de un proceso de mejora (§7.9 `Proceso`).

    **Este enum no está en el §8.2 y aquí se decide.** El §7.9 le da a
    `Proceso` un campo `estatus` y lo describe como "mejora de procesos", sin
    fijar valores; la migración 0010 lo dejó como `text` con default
    `propuesto`, sin `CHECK`.

    Se fija aquí y **no** como tipo de Postgres a propósito. Un enum de la base
    es un invariante: cambiarlo cuesta una migración con `down` probado
    (§12.12). Estos cuatro valores son una convención de tablero que una
    organización podría querer distinta —"piloto" en vez de "en_curso"— y el
    §8.7 llama a eso semilla editable, no invariante. Mientras el spec no los
    fije, el borde valida contra esta lista y la columna sigue siendo `text`:
    ampliarla es cambiar este enum, no migrar la base.
    """

    PROPUESTO = "propuesto"
    """Alguien lo levantó. Es el default de la columna."""

    EN_CURSO = "en_curso"
    """Se está probando en obra."""

    ADOPTADO = "adoptado"
    """Quedó como la forma de trabajar."""

    DESCARTADO = "descartado"
    """Se probó y no sirvió. Se conserva: saber qué no funcionó es la mitad
    del valor de un tablero de mejora."""


class TipoCarga(_Canonico):
    CATALOGO_CONCEPTOS = "catalogo_conceptos"
    MATERIALES = "materiales"
    CONTRATISTAS = "contratistas"
    UNIDADES = "unidades"
    FAMILIAS = "familias"
    PRESUPUESTO = "presupuesto"
    PROGRAMA_BASE = "programa_base"
    OBRAS = "obras"

    ALMACEN = "almacen"
    """Movimientos de almacén — `IMPORTAADOR_ALMACEN.xlsx` (§10.6).

    El §10.6 define este archivo como parte del contrato de cargadores, pero
    la lista de `carga_datos.tipo` del §8.2 no le dio valor: sin él una carga
    de almacén no se podría registrar como lote reversible (§10.8). Agregarlo
    es el "trabajo de programador" que el §8.7 prevé para un invariante, y su
    espejo en la base es
    `database/migrations/20260814000019_carga_de_almacen.sql`.
    """


class EstatusCarga(_Canonico):
    PENDIENTE = "pendiente"
    VALIDANDO = "validando"
    PREVISUALIZADO = "previsualizado"
    APLICADO = "aplicado"
    ERROR = "error"


class ModoCarga(_Canonico):
    """Modos de carga (§10.2)."""

    ACTUALIZAR = "actualizar"
    """Default: deduplica por clave, actualiza existentes, agrega nuevos."""

    ACUMULAR = "acumular"
    """Solo agrega nuevos, sin tocar lo actual."""

    REEMPLAZAR = "reemplazar"
    """Sustituye todo el conjunto. Exige confirmación."""


class TipoSemana(_Canonico):
    ORDINARIA = "ordinaria"
    """Lunes a domingo (§3.1)."""

    OBRA = "obra"
    """Jueves a miércoles; 5 días laborales (§3.1). Default de ObraCtrl."""


class BucketAlmacen(_Canonico):
    INGRESOS = "ingresos"
    SALIDAS = "salidas"
    AJUSTES = "ajustes"
    IMPORTE_TOTAL = "importe_total"


# --- Prefijos de clave (§10.1) ------------------------------------------

PREFIJOS: dict[str, str] = {
    "concepto": "EST",
    "subcontrato": "SUB",
    "servicio": "SER",
    "mano_obra": "MOA",
    "mano_obra_subcontrato": "MOS",
    "nivel": "NIV",
    "etapa": "ECO",
    "prototipo": "CAS",
}
"""Prefijo canónico por tipo de registro. Semilla editable (§8.7)."""


# --- Mapa de sinónimos para los cargadores (§8.6) ------------------------

ALIAS_ENCABEZADOS: dict[str, str] = {
    # clave
    "codigo": "clave",
    "code": "clave",
    "clave": "clave",
    "no.": "clave",
    "no": "clave",
    "num": "clave",
    "# parte": "clave",
    # descripcion
    "descripcion": "descripcion",
    "concepto": "descripcion",
    "partida": "descripcion",
    "parte": "descripcion",
    # unidad
    "u": "unidad",
    "um": "unidad",
    "unidad": "unidad",
    "unidad de medida": "unidad",
    # precio
    "p.u.": "precio_unitario",
    "pu": "precio_unitario",
    "precio unitario": "precio_unitario",
    "costo unitario": "precio_unitario",
    # cantidad
    "cant": "cantidad",
    "cant.": "cantidad",
    "cantidad": "cantidad",
    "volumen": "cantidad",
    "vol.": "cantidad",
    "vol": "cantidad",
    # importe
    "importe": "importe",
    "total": "importe",
    "subtotal": "importe",
    # rendimiento
    "rend.": "rendimiento",
    "rend": "rendimiento",
    "rendimiento": "rendimiento",
    # familia / tipo
    "familia": "familia",
    "clase": "familia",
    "tipo": "tipo",
}
"""Alias de encabezado externo → nombre canónico (§8.6).

Las llaves están normalizadas: minúsculas y sin espacios sobrantes.
Úsese vía :func:`obractrl.domain.shared.normalizacion.canonizar_encabezado`,
que aplica la misma normalización a la entrada.
"""
