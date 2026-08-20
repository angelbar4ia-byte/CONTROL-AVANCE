/**
 * Reflejo en el front de las reglas del expediente (§7.9, §11.2).
 *
 * Sin lógica de negocio: etiquetas y la única pregunta que la pantalla
 * necesita responder sin ir al servidor —¿este rol sube documentos?—. La regla
 * de verdad vive en `domain/expediente/reglas.py` (`ROLES_QUE_SUBEN`) y RLS la
 * vuelve a imponer con la política de `expediente_doc`.
 */

import type { Rol } from '@/shell/navegacion';

const ETIQUETA_TIPO: Record<string, string> = {
  plano: 'Plano',
  contrato: 'Contrato',
  acta: 'Acta',
  evidencia: 'Evidencia',
  bitacora: 'Bitácora',
  otro: 'Otro',
};

/** Los seis del enum `tipo_expediente_doc` (migración 0002). */
export const TIPOS_DOC: readonly string[] = Object.keys(ETIQUETA_TIPO);

export function etiquetaTipoDoc(tipo: string): string {
  return ETIQUETA_TIPO[tipo] ?? tipo;
}

/**
 * ¿Este rol sube documentos al expediente? (§11.2)
 *
 * Control de obra y Super intendente. El residente y el supervisor lo **leen**
 * —el expediente es la memoria de la obra y todos la consultan—, pero lo que
 * entra en él lo decide quien responde por la obra.
 */
export function puedeSubirDocumentos(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}
