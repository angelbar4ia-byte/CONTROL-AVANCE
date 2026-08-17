/**
 * Traducción entre el formulario de alta de incidencia (todo `string`) y el
 * DTO del contrato (`AbrirIncidenciaPeticion`, §11.2; "DTOs en el borde" —
 * AGENTS.md).
 *
 * Puro y sin reglas de negocio. La única transformación con criterio es
 * `bloquea_actividades`: el contrato lo declara *"Solo válido con impacto
 * 'detiene' (§6)"*, así que mandarlo con otro impacto es un 422 seguro. Se
 * omite en vez de mandarlo — es formato del DTO, no una decisión de negocio:
 * quien decide si la incidencia detiene la obra sigue siendo el dominio.
 */

import type { AbrirIncidenciaPeticion, ImpactoIncidencia, TipoIncidencia } from '@/api/generado/modelo';

export interface FormularioIncidencia {
  readonly obraId: string;
  readonly tipo: TipoIncidencia;
  readonly impacto: ImpactoIncidencia;
  readonly titulo: string;
  readonly descripcion: string;
  readonly frenteId: string;
  readonly fechaLimite: string;
  /** Ids de actividad, uno por línea. Solo aplica con impacto `detiene`. */
  readonly bloqueaActividades: string;
}

export function formularioIncidenciaVacio(
  obraId: string,
  tipo: TipoIncidencia,
  impacto: ImpactoIncidencia,
): FormularioIncidencia {
  return {
    obraId,
    tipo,
    impacto,
    titulo: '',
    descripcion: '',
    frenteId: '',
    fechaLimite: '',
    bloqueaActividades: '',
  };
}

function textoOpcional(valor: string): string | undefined {
  const limpio = valor.trim();
  return limpio === '' ? undefined : limpio;
}

/** Una actividad por línea; se descartan líneas vacías y repetidas. */
export function actividadesBloqueadas(texto: string): readonly string[] {
  const ids: string[] = [];
  for (const linea of texto.split('\n')) {
    const id = linea.trim();
    if (id !== '' && !ids.includes(id)) ids.push(id);
  }
  return ids;
}

export function peticionDeIncidencia(
  formulario: FormularioIncidencia,
): AbrirIncidenciaPeticion {
  const bloquea = actividadesBloqueadas(formulario.bloqueaActividades);
  return {
    obra_id: formulario.obraId.trim(),
    tipo: formulario.tipo,
    impacto: formulario.impacto,
    titulo: formulario.titulo.trim(),
    descripcion: textoOpcional(formulario.descripcion),
    frente_id: textoOpcional(formulario.frenteId),
    fecha_limite: textoOpcional(formulario.fechaLimite),
    // El contrato solo acepta la lista con impacto 'detiene' (§6).
    bloquea_actividades:
      formulario.impacto === 'detiene' && bloquea.length > 0 ? [...bloquea] : undefined,
  };
}

/** Presencia de lo que el contrato marca obligatorio; el 422 es del backend. */
export function incidenciaCompleta(formulario: FormularioIncidencia): boolean {
  return formulario.obraId.trim() !== '' && formulario.titulo.trim() !== '';
}
