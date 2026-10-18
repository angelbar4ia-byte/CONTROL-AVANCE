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
    "CausaDesviacion",
    "ClaseNodo",
    "EstatusActividad",
    "EstatusCarga",
    "EstatusCierreObra",
    "EstatusEstimacion",
    "EstatusIncidencia",
    "EstatusObra",
    "EstatusProceso",
    "EstatusSolicitudCierre",
    "FuenteTrazo",
    "ImpactoIncidencia",
    "MedidaCuantificacion",
    "ModoCantidad",
    "ModoCarga",
    "ModoPago",
    "NivelEvaluacion",
    "Rol",
    "SujetoEvaluacion",
    "TipoCarga",
    "TipoConcepto",
    "TipoDesviacion",
    "TipoExpedienteDoc",
    "TipoHijoExplosion",
    "TipoIncidencia",
    "TipoInsumo",
    "TipoNodoCuantificacion",
    "TipoNodoDesviacion",
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
    POR_ENTREGAR = "por_entregar"
    ENTREGADA = "entregada"


class ClaseNodo(_Canonico):
    """Rol del nodo en el árbol WBS. Columna ``CLASE`` del archivo (§10.6)."""

    ETAPA = "etapa"
    NIVEL = "nivel"
    CONCEPTO = "concepto"
    AGRUPADOR = "agrupador"
    """Nivel intermedio del export nativo de OPUS entre la etapa y el
    concepto (§7.4, migración 0051): agrupa varios conceptos reales bajo
    un subtotal propio sin ser él mismo un concepto de catálogo."""


class ModoCantidad(_Canonico):
    """De dónde sale `prototipo_nodo.cantidad` (cerebro MODELO.md §1/
    HALLAZGO 12, §7.1; migraciones 0055 y 0060). Nunca lo hereda el padre
    de sus hijos — es por nodo."""

    CAPTURADA = "capturada"
    """Alguien la tipeó: presupuesto a mano, sin ingeniería ni trazo."""

    CARGADA = "cargada"
    """Vino de una ingeniería importada (reversión por destajo, §11.9):
    la cantidad real de esa obra, ya reconstruida al importar."""

    HEREDADA = "heredada"
    """Se copió de un presupuesto de referencia sin recalcular nada — el
    paramétrico nace así, o una obra que clona su prototipo tal cual."""

    MEDIDA = "medida"
    """La produjo el cuantificador: un trazo sobre el plano de esta obra
    en particular (migración 0057)."""

    ESTIMADA = "estimada"
    """El motor paramétrico la calculó para esta obra (tasa aprendida ×
    el divisor de esta obra, migración 0060) — a diferencia de `heredada`,
    aquí sí hubo un cálculo nuevo, no una copia."""


# --- Catálogos y APU (§7.3) ---------------------------------------------


class TipoInsumo(_Canonico):
    MATERIAL = "material"
    MANO_OBRA = "mano_obra"
    EQUIPO = "equipo"
    HERRAMIENTA = "herramienta"
    SUBCONTRATO = "subcontrato"


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
    TRABAJO = "trabajo"
    """Mano de obra contratada (`Tipo=Contrato`, matriz nativa de OPUS,
    `ANALISIS_DE_BASICOS_CONCEPTOS.csv`, migración 0052): el genérico, sin
    distinguir `DESTAJO` de `SUBCONTRATO` por sí mismo — el cerebro
    prohíbe adivinar esa clase por el prefijo de la clave (cita fallos
    reales de hacerlo).

    `CATALOGO_DE_TRABAJOS.csv` (export nativo de OPUS, §cabeceras.
    TRABAJOS_OPUS) sí trae esa distinción fila por fila: cuando quien
    carga la matriz lo cruza y pasa el resultado como ``clase_trabajo`` a
    `domain.cargadores.cpu.agrupar_conceptos`, la fila se carga con la
    categoría precisa (`DESTAJO`/`SUBCONTRATO`) y no por este genérico.
    Sin ese cruce —o para una clave que no está en el catálogo—, la fila
    se queda aquí y se marca con el pendiente no crítico `TipoPendiente.
    TRABAJO_SIN_CLASE` para reclasificar a mano
    (`domain.cargadores.cpu._agrupar_conceptos_matriz`)."""

    FLETE = "flete"
    """Transporte de material (`Tipo=Flete`, misma matriz nativa de OPUS,
    migración 0052): categoría propia e inequívoca, sin el problema de
    `TRABAJO` — el cerebro ya la tiene así, sin ambigüedad que resolver,
    por eso no lleva pendiente."""


class TipoHijoExplosion(_Canonico):
    INSUMO = "insumo"
    CONCEPTO = "concepto"


# --- Desviación (cerebro MODELO.md §5g, CONOCIMIENTO.md §13.6) ----------


class TipoNodoDesviacion(_Canonico):
    """El nodo donde se detecta una `Desviacion`: insumo XOR concepto.

    Mismo patrón que `TipoHijoExplosion` (migración 0005, `ck_explosion_hijo`)
    aplicado a `desviacion` (migración 0054, `ck_desviacion_nodo`): otro
    enum, porque es otra entidad con otra semántica, aunque el par de
    columnas se repita.
    """

    INSUMO = "insumo"
    CONCEPTO = "concepto"


class TipoDesviacion(_Canonico):
    """Los dos factores de la fórmula de CONOCIMIENTO.md §13.6, nunca
    sumados en una sola fila::

        desviación = (precio_real - precio_plan) * cantidad_real   # precio
                   + (cantidad_real - cantidad_plan) * precio_plan  # consumo

    "Separarlos importa porque responden distintas personas. 'Pagamos más'
    es de compras; 'usamos más' es de obra" (§13.6).
    """

    PRECIO = "precio"
    CONSUMO = "consumo"


class CausaDesviacion(_Canonico):
    """Vocabulario controlado de "Causas por categoría" (CONOCIMIENTO.md
    §13.6, tabla de líneas 8693-8699): "vocabulario controlado, no texto
    libre — si no, las desviaciones no se pueden agregar ni comparar".

    Cuál de estas aplica a una fila de `Desviacion` depende del tipo del
    insumo/concepto detectado (material · mano_de_obra · herramienta ·
    maquinaria · contratos) y de `TipoDesviacion` (precio/consumo) de esa
    misma fila. La base no restringe esa combinación —el enum es plano,
    con los ~20 valores de las cinco categorías juntos—: decidir cuál
    aplica es trabajo del dominio/aplicación, no un CHECK de Postgres
    (MODELO.md §5g: "cuál aplica ... lo decide el dominio").

    **No confundir con `domain.desviacion.CausaRaiz`** (las nueve causas de
    §13.6 que deciden SI el hallazgo es una `Desviacion`): confundir esos dos
    vocabularios fue exactamente el error D-343 que el propio cerebro
    corrigió en D-347 (MODELO.md §5g).
    """

    # material · precio
    MERCADO = "mercado"
    VOLUMEN = "volumen"
    PROVEEDOR_DISTINTO = "proveedor_distinto"
    CAMBIO_DE_PRESENTACION = "cambio_de_presentacion"

    # material · consumo
    DESPERDICIO_MAYOR_AL_TEORICO = "desperdicio_mayor_al_teorico"
    MERMA_POR_DANO_CLIMA_O_ROBO = "merma_por_dano_clima_o_robo"
    SUSTITUCION_POR_EQUIVALENTE = "sustitucion_por_equivalente"
    """Sustitución por un equivalente del mismo grupo funcional (§13.6,
    cita el grupo funcional; D-342 del cerebro)."""

    # mano_de_obra · precio
    RENEGOCIACION = "renegociacion"
    URGENCIA = "urgencia"
    ALZA_DE_TABULADOR = "alza_de_tabulador"

    # mano_de_obra · consumo
    RENDIMIENTO_REAL_DISTINTO = "rendimiento_real_distinto"
    """Rendimiento real distinto al teórico (§13.6, cita §6.2)."""
    RETRABAJO = "retrabajo"
    TRABAJO_FUERA_DE_ALCANCE = "trabajo_fuera_de_alcance"

    # herramienta · precio
    TARIFA_DISTINTA = "tarifa_distinta"

    # herramienta · consumo
    DIAS_REALES_DE_RENTA = "dias_reales_de_renta"
    EQUIPO_PARADO = "equipo_parado"
    """Costo sin producción (§13.6, literal)."""

    # maquinaria · precio
    TARIFA = "tarifa"
    COMBUSTIBLE = "combustible"

    # maquinaria · consumo
    HORAS_EFECTIVAS_CONTRA_FACTURADAS = "horas_efectivas_contra_facturadas"

    # contratos · consumo
    VOLUMEN_REALMENTE_EJECUTADO = "volumen_realmente_ejecutado"


# --- Cuantificador (cerebro MODELO.md §1b) ------------------------------


class FuenteTrazo(_Canonico):
    """De qué archivo salió el trazo (TRAZO.fuente, migración 0057).

    Determina la precedencia al reemplazar un enlace (IFC > DWG > PDF) —
    esa comparación es trabajo de quien llama a `ReemplazarEnlace`, nunca
    un CHECK de esta tabla ni una regla automática (MODELO.md §1b: "depende
    de que quien traza reemplace el enlace a mano").
    """

    PDF = "pdf"
    DWG = "dwg"
    IFC = "ifc"


class MedidaCuantificacion(_Canonico):
    """Qué métrica del trazo alimenta la cantidad (ENLACE_CUANTIFICACION.
    medida, MODELO.md §1b). `AREA`/`PERIMETRO`/`LONGITUD` se calculan en
    SQL con `ST_Area`/`ST_Perimeter`/`ST_Length` sobre la geometría
    (§12.11: el dominio nunca toca PostGIS); `CONTEO` no es una función de
    PostGIS, es "este trazo cuenta como una instancia".
    """

    AREA = "area"
    PERIMETRO = "perimetro"
    LONGITUD = "longitud"
    CONTEO = "conteo"


class TipoNodoCuantificacion(_Canonico):
    """A qué mitad del NODO de cerebro apunta un `ENLACE_CUANTIFICACION`
    (migración 0057): `ACTIVIDAD` (instancia por obra, presupuesto ya
    congelado) o `PROTOTIPO_NODO` (plantilla de un prototipo "diseño_nuevo"
    de un solo uso). Mismo patrón que `TipoNodoDesviacion` aplicado a otra
    entidad con otra semántica.
    """

    ACTIVIDAD = "actividad"
    PROTOTIPO_NODO = "prototipo_nodo"


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
    """`CABECERAS_CONCEPTOS.xlsx` (§8.7): catálogo base de identidad de
    conceptos — clave, descripción, unidad, nada más. No es CPU: la
    composición del concepto vive en `CPU`, más abajo (antes compartían
    este mismo tipo)."""

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

    PROTOTIPOS = "prototipos"
    """Varios prototipos a la vez, en vez de darlos de alta uno a uno
    (§7.2). A diferencia de `ALMACEN`, el §10.6 no describe este archivo:
    es una extensión nueva del catálogo de cargadores. Espejo en la base:
    `database/migrations/20260814000029_carga_de_prototipos.sql`.
    """

    MANO_DE_OBRA = "mano_de_obra"
    """`CABECERAS_MANO_DE_OBRA.xlsx` (hoja `DESTAJOS`, §10.6): "clave,
    clave_usuario, descripción, unidad, cuadrilla, rendimiento_teórico/
    real, costo_unitario, familia". Alimenta el catálogo de insumos con
    `tipo=mano_obra` — hasta ahora solo `MATERIALES` lo hacía. Espejo en la
    base: `database/migrations/20260814000031_carga_de_mano_de_obra.sql`.
    """

    CUADRILLAS = "cuadrillas"
    """`CABECERAS_CUADRILLAS.xlsx` (§10.6): composición y PU de una
    cuadrilla — fila cabecera (`Clave = Clave cuadrilla`) + filas
    integrante (insumo, cantidad, costo). `MANO_DE_OBRA` da de alta la
    cuadrilla sola con clave+nombre; este archivo es el que carga su
    precio, con historial versionado (§10.8) como el CPU de un concepto.
    Espejo en la base:
    `database/migrations/20260814000032_cargador_de_cuadrillas.sql`.
    """

    SUBCONTRATOS = "subcontratos"
    """`catalogo_de_SUBCONTRATOS.xlsx` (§10.6): mismas cabeceras que
    `MANO_DE_OBRA`, `TIPO=Subcontrato`, claves `SUB-xxxxx`. Alimenta el
    catálogo de insumos con `tipo=subcontrato`. Espejo en la base:
    `database/migrations/20260814000034_carga_de_subcontratos.sql`.
    """

    CPU = "cpu"
    """`CABECERAS_CPU.xlsx`, hoja `EXPORTADOR` (§10.6): el análisis/
    composición de un concepto (qué materiales, mano de obra y subcontrato
    lleva, con qué cantidad y costo). Antes compartía tipo con
    `CATALOGO_CONCEPTOS`; se separan porque catálogo = identidad (clave,
    descripción, unidad) y CPU = composición son cosas distintas (§8.7).
    Espejo en la base: `database/migrations/20260814000035_carga_de_cpu.sql`.
    """

    CONCEPTOS_AUXILIARES = "conceptos_auxiliares"
    """`CABECERAS_CONCEPTOS_AUXILIARES.xlsx` (§8.7): catálogo base de
    identidad de conceptos auxiliares — clave, descripción, unidad. Mismo
    contrato que `CATALOGO_CONCEPTOS`, mismo `concepto` de destino, pero
    `tipo=auxiliar` (§7.3) en vez de `tipo=concepto`."""

    NIVELES = "niveles"
    """`CATALOGO_DE_NIVELES.xlsx` (§10.1): catálogo base de identidad de
    niveles de construcción — clave, descripción. Antes solo se sembraba
    solo, de pasada, cuando el árbol de presupuesto lo referenciaba
    (`RepositorioNivelesEtapas.upsert_nivel`); este es su propio cargador."""

    ETAPAS_CONSTRUCTIVAS = "etapas_constructivas"
    """`CATALOGO_DE_ETAPAS_DE_CONSTRUCCION.xlsx` (§10.1): catálogo base de
    identidad de etapas de construcción — clave, descripción. Mismo
    criterio que `NIVELES`."""

    TRABAJOS = "trabajos"
    """`CATALOGO_DE_TRABAJOS.csv`, export nativo de OPUS (§cabeceras.
    TRABAJOS_OPUS): 259 destajos y 6 subcontratos en un solo archivo,
    distinguidos fila por fila (`mano_de_obra.clase_de_trabajo`), no por
    archivo como `MANO_DE_OBRA`/`SUBCONTRATOS`. Es el único tipo de carga
    cuyo archivo real mezcla dos `TipoInsumo` distintos fila por fila, y
    por eso tiene su propio aplicador (`AplicadorTrabajos`) en vez de
    reusar `AplicadorManoObra` —que fija su `TipoInsumo` una sola vez por
    archivo completo (constructor), no por fila—. Espejo en la base:
    `database/migrations/20260814000053_carga_de_trabajos.sql`.
    """

    INGENIERIA_LOTE = "ingenieria_lote"
    """Ingeniería del lote, estructura `COMPLETA` (cerebro CONOCIMIENTO.md
    §11.8): un archivo sin encabezados, por cimentación/etapa, de lo que se
    planeó comprar/usar en una obra real. Su `AplicadorIngenieriaLote`
    (extensión propia) es el único que necesita contexto fuera del archivo
    —`obra_id` y, en el camino "diseño_nuevo", `prototipo_base_id`— porque
    la identidad del lote nunca se adivina del nombre del archivo
    (§11.4/§11.5: "el nombre dice la estructura, nunca la identidad").
    Espejo en la base:
    `database/migrations/20260814000056_carga_de_ingenieria_lote.sql`.
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
    # clave de unidad: el archivo real de materiales/mano de obra trae esta
    # columna aparte de "unidad" (el texto) — es el código del catálogo de
    # Unidades (§3.3), no una descripción más.
    "clave unidad": "clave_unidad",
    "clave de unidad": "clave_unidad",
    "clave_unidad": "clave_unidad",
    "cve unidad": "clave_unidad",
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
