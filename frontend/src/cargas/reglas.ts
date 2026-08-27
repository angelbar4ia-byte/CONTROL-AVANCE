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
  cpu: 'CPU (análisis de conceptos)',
  materiales: 'Materiales',
  mano_de_obra: 'Mano de obra / Destajos',
  subcontratos: 'Subcontratos',
  cuadrillas: 'Cuadrillas',
  contratistas: 'Contratistas',
  unidades: 'Unidades',
  familias: 'Familias',
  niveles: 'Niveles de construcción',
  etapas_constructivas: 'Etapas de construcción',
  presupuesto: 'Presupuesto (ingeniería por prototipo)',
  programa_base: 'Programa base',
  obras: 'Obras',
  almacen: 'Salidas de almacén',
  prototipos: 'Prototipos (alta masiva)',
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

export const TIPOS: readonly TipoCarga[] = Object.values(TipoCarga).filter(
  (tipo) => !TIPOS_CUBIERTOS_POR_OTRO.includes(tipo),
);
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
