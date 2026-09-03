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
  /** El nivel (§7.4): dónde en la obra. Distinto de `frenteId` (tipo de
   * contratación). Se deriva de "va junto a esta actividad" o de la primera
   * actividad bloqueada; el formulario no ofrece un select aparte porque el
   * residente ya sabe con qué actividad está la incidencia, no con qué nivel. */
  readonly nivelId: string;
  readonly etapaId: string;
  readonly fechaLimite: string;
  /** Ids de actividad elegidos en el multi-select. Solo aplica con impacto
   * `detiene`; antes era un textarea donde se pegaba un id por línea. */
  readonly bloqueaActividades: readonly string[];
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
    nivelId: '',
    etapaId: '',
    fechaLimite: '',
    bloqueaActividades: [],
  };
}

function textoOpcional(valor: string): string | undefined {
  const limpio = valor.trim();
  return limpio === '' ? undefined : limpio;
}

export function peticionDeIncidencia(
  formulario: FormularioIncidencia,
): AbrirIncidenciaPeticion {
  return {
    obra_id: formulario.obraId.trim(),
    tipo: formulario.tipo,
    impacto: formulario.impacto,
    titulo: formulario.titulo.trim(),
    descripcion: textoOpcional(formulario.descripcion),
    frente_id: textoOpcional(formulario.frenteId),
    nivel_id: textoOpcional(formulario.nivelId),
    etapa_id: textoOpcional(formulario.etapaId),
    fecha_limite: textoOpcional(formulario.fechaLimite),
    // El contrato solo acepta la lista con impacto 'detiene' (§6).
    bloquea_actividades:
      formulario.impacto === 'detiene' && formulario.bloqueaActividades.length > 0
        ? [...formulario.bloqueaActividades]
        : undefined,
  };
}

/** Presencia de lo que el contrato marca obligatorio; el 422 es del backend. */
export function incidenciaCompleta(formulario: FormularioIncidencia): boolean {
  return formulario.obraId.trim() !== '' && formulario.titulo.trim() !== '';
}
