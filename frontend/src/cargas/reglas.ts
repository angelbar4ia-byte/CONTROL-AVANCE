/**
 * Reflejo en el front de las reglas de carga del §10.
 *
 * Spec §10.2 (tres modos y vista previa) · §10.3 (bandeja de pendientes) ·
 * §10.6 (cabeceras reales) · §10.8 (versionado y reversa).
 *
 * Sin lógica de negocio: etiquetas, tonos y las dos preguntas que la pantalla
 * necesita responder sin ir al servidor —¿esta carga se puede revertir?, ¿este
 * resultado se puede aplicar?—. Quién puede cargar es RBAC del backend
 * (Control de obra, §5.1) reforzado por RLS.
 */

import { ModoCarga, TipoCarga } from '@/api/generado/modelo';
import type { LoteRespuesta } from '@/api/generado/modelo';

const ETIQUETA_TIPO: Record<string, string> = {
  catalogo_conceptos: 'Catálogo de conceptos',
  conceptos_auxiliares: 'Conceptos auxiliares',
  cpu: 'Análisis de básicos conceptos',
  materiales: 'Materiales',
  fletes: 'Catálogo de fletes',
  mano_de_obra: 'Catálogo de mano de obra (puestos y cuadrillas)',
  subcontratos: 'Subcontratos',
  cuadrillas: 'Cuadrillas',
  semilla_cuadrilla_rendimiento: 'Semilla de cuadrillas y rendimientos',
  contratistas: 'Contratistas',
  unidades: 'Unidades',
  familias: 'Familias',
  niveles: 'Niveles de construcción',
  etapas_constructivas: 'Etapas de construcción',
  presupuesto: 'Presupuesto (ingeniería por prototipo)',
  programa_base: 'Programa base',
  obras: 'Obras',
  almacen: 'Salidas de almacén',
  prototipos: 'Presupuesto y prototipos (catálogo de presupuesto)',
  trabajos: 'Catálogo de trabajos (destajo/subcontrato)',
  ingenieria_lote: 'Ingeniería del lote',
};

const TIPOS_CUBIERTOS_POR_OTRO: readonly string[] = ['presupuesto'];
/**
 * Tipos que el backend sigue aceptando pero que **no** se ofrecen aparte en
 * la pantalla, porque otro los cubre.
 *
 * `presupuesto` es el árbol de ingeniería por prototipo, y "Prototipos (alta
 * masiva)" ya reconoce ese archivo además del alta plana: cuál es cuál lo
 * decide el propio `.xlsx` por sus encabezados, no el usuario. Ofrecer los
 * dos obligaría a acertarle al desplegable antes de subir, que es justo el
 * error que se quiso quitar.
 */

/**
 * Orden en que se suben los archivos de OPUS: cada paso solo necesita lo que
 * ya cargaron los anteriores. Los primeros once son el arranque del catálogo;
 * siguen los que dependen de una obra o de un proyecto; al final, los tipos
 * que el servidor acepta pero ya no son parte del camino normal.
 *
 * - Semilla de cuadrillas: liga cada destajo (trabajos) con su cuadrilla
 *   (catálogo de mano de obra); falla si falta alguno.
 * - Presupuesto y prototipos: arma el árbol de conceptos del que cuelga el
 *   análisis de básicos (su `clave_padre` debe existir).
 * - Análisis de básicos: lleva materiales, trabajos y cuadrillas ya cargados.
 */
const ORDEN_DE_CARGA: readonly string[] = [
  'unidades',
  'familias',
  'niveles',
  'etapas_constructivas',
  'materiales',
  'fletes',
  'trabajos',
  'mano_de_obra',
  'semilla_cuadrilla_rendimiento',
  'prototipos',
  'cpu',
  'contratistas',
  'programa_base',
  'obras',
  'ingenieria_lote',
  'almacen',
];

/** Lo que debe estar cargado antes de subir cada tipo (texto de ayuda). */
const REQUIERE_ANTES: Record<string, string> = {
  semilla_cuadrilla_rendimiento: 'Catálogo de trabajos y catálogo de mano de obra.',
  prototipos: 'Nada: es el árbol de conceptos del que cuelga el análisis de básicos.',
  cpu: 'Presupuesto y prototipos, materiales, fletes, trabajos y catálogo de mano de obra.',
};

export function requiereAntes(tipo: string): string | null {
  return REQUIERE_ANTES[tipo] ?? null;
}

function posicion(tipo: string): number {
  const i = ORDEN_DE_CARGA.indexOf(tipo);
  return i === -1 ? ORDEN_DE_CARGA.length : i;
}

export const TIPOS: readonly TipoCarga[] = Object.values(TipoCarga)
  .filter((tipo) => !TIPOS_CUBIERTOS_POR_OTRO.includes(tipo))
  .sort((a, b) => posicion(a) - posicion(b));

/** «5. Materiales»: el número es el paso en que se sube; sin número, fuera del camino normal. */
export function etiquetaConPaso(tipo: string): string {
  const i = ORDEN_DE_CARGA.indexOf(tipo);
  return i === -1 ? `Otros · ${etiquetaTipo(tipo)}` : `${i + 1}. ${etiquetaTipo(tipo)}`;
}
export const MODOS: readonly ModoCarga[] = Object.values(ModoCarga);

export function etiquetaTipo(tipo: string): string {
  return ETIQUETA_TIPO[tipo] ?? tipo;
}

const DESCRIPCION_MODO: Record<string, string> = {
  actualizar:
    'Inserta lo nuevo y actualiza lo que cambió. Lo que no viene en el archivo se queda como está.',
  acumular: 'Suma al valor existente en vez de reemplazarlo. Para movimientos, no para catálogos.',
  reemplazar:
    'La versión nueva sustituye a la vigente por completo: lo que no venga en el archivo deja de estar.',
};

export function descripcionModo(modo: string): string {
  return DESCRIPCION_MODO[modo] ?? '';
}

export function etiquetaModo(modo: string): string {
  return modo.charAt(0).toUpperCase() + modo.slice(1);
}

/** El modo que borra: la pantalla lo advierte antes de dejarlo aplicar. */
export function modoDestructivo(modo: string): boolean {
  return modo === 'reemplazar';
}

// Los valores literales son los de `EstatusCarga` (backend): "aplicado",
// "previsualizado", "error" — no "aplicada"/"vista_previa"/"con_errores".
// `estatus: string` en el contrato (sin enum) hace que TypeScript no
// pueda avisar de un typo aquí; nada lo iba a atrapar salvo leerlo dos
// veces contra el dominio real.
const TONO_ESTATUS: Record<string, string> = {
  aplicado: 'ok',
  previsualizado: 'info',
  error: 'danger',
};

export function tonoEstatus(estatus: string): string {
  return TONO_ESTATUS[estatus] ?? 'neutral';
}

export function etiquetaEstatus(estatus: string): string {
  return estatus.replaceAll('_', ' ');
}

const ETIQUETA_TIPO_PENDIENTE: Record<string, string> = {
  mapeo_no_reconocido: 'Alias sin homologar',
  cpu_nuevo: 'Concepto nuevo',
  unidad: 'Unidad desconocida',
  iva: 'IVA sin resolver',
  fila_no_parseada: 'Fila fuera de formato',
  motivo_almacen: 'Motivo de almacén no catalogado',
  concepto_en_conflicto: 'Composición en conflicto',
  descripcion_distinta: 'Descripción distinta al catálogo',
  wbs_inconsistente: 'WBS no coincide',
};

/** Etiqueta legible de `pendiente.tipo` (§10.3). */
export function etiquetaTipoPendiente(tipo: string): string {
  return ETIQUETA_TIPO_PENDIENTE[tipo] ?? etiquetaEstatus(tipo);
}

/**
 * ¿Este lote se puede revertir? (§10.8)
 *
 * Solo una carga **aplicada** y **no revertida ya**. Una vista previa no
 * escribió nada y una revertida no tiene qué deshacer; ofrecer el botón en
 * esos casos sería prometer una operación que responde 409.
 */
export function seePuedeRevertir(lote: LoteRespuesta): boolean {
  return lote.estatus === 'aplicado' && !lote.revertida;
}

/**
 * ¿Este lote se puede borrar del historial? (§10.8)
 *
 * Una vista previa (o una carga que falló) nunca escribió nada: no hay
 * riesgo en borrar su registro. Una carga aplicada solo se puede borrar
 * **después** de revertirla — borrar el snapshot sin deshacer sus cambios
 * dejaría el catálogo modificado y sin ninguna forma de revertirlo.
 */
export function sePuedeEliminar(lote: LoteRespuesta): boolean {
  return lote.estatus !== 'aplicado' || lote.revertida;
}

/**
 * Un resumen legible del lote, para la fila de la tabla.
 *
 * `resumen` viaja como `dict` en el contrato —lo escribe el caso de uso con la
 * forma del §9.4— así que aquí se estrecha a los cuatro números que la
 * pantalla muestra, tolerando que falte cualquiera.
 */
export interface ResumenDeLote {
  readonly filas: number;
  readonly insertados: number;
  readonly actualizados: number;
  readonly omitidos: number;
}

export function resumenDe(lote: LoteRespuesta): ResumenDeLote {
  const crudo = (lote.resumen ?? {}) as Record<string, unknown>;
  const numero = (clave: string): number => {
    const valor = crudo[clave];
    return typeof valor === 'number' ? valor : 0;
  };
  return {
    filas: numero('filas'),
    insertados: numero('insertados'),
    actualizados: numero('actualizados'),
    omitidos: numero('omitidos'),
  };
}

/**
 * Qué tipos de carga ofrece la pantalla a cada rol. Costos prepara la ingeniería y también la
 * sube (D-581), pero solo esa: las demás cargas son de Control de obra. El servidor lo impone.
 */
export function tiposParaRol(rol: string | null | undefined): readonly TipoCarga[] {
  return rol === 'costos' ? TIPOS.filter((t) => t === TipoCarga.ingenieria_lote) : TIPOS;
}
