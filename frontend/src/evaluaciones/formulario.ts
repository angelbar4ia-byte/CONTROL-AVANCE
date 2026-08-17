/**
 * Traducción entre los formularios de evaluación (todo `string`) y los DTOs
 * del contrato (`CrearEvaluacionPeticion`, `AgregarRespuestasPeticion`;
 * §11.2 "Evaluación", "DTOs en el borde" — AGENTS.md).
 *
 * Puro y sin reglas: no decide si el rol puede crear ese nivel ni si el
 * sujeto aplica —el endpoint responde 422 (§11.3 H)— ni pondera el puntaje,
 * que es del dominio (§7.8, peso por criterio).
 */

import type {
  AgregarRespuestasPeticion,
  CrearEvaluacionPeticion,
  NivelEvaluacion,
  RespuestaItemInput,
  SujetoEvaluacion,
} from '@/api/generado/modelo';

export interface FormularioEvaluacion {
  readonly nivel: NivelEvaluacion;
  readonly sujetoTipo: SujetoEvaluacion;
  readonly sujetoId: string;
  readonly periodo: string;
  readonly obraId: string;
}

export function formularioEvaluacionVacio(
  nivel: NivelEvaluacion,
  periodo: string,
): FormularioEvaluacion {
  return { nivel, sujetoTipo: 'obra', sujetoId: '', periodo, obraId: '' };
}

function textoOpcional(valor: string): string | undefined {
  const limpio = valor.trim();
  return limpio === '' ? undefined : limpio;
}

export function peticionDeEvaluacion(
  formulario: FormularioEvaluacion,
): CrearEvaluacionPeticion {
  return {
    nivel: formulario.nivel,
    sujeto_tipo: formulario.sujetoTipo,
    sujeto_id: formulario.sujetoId.trim(),
    periodo: formulario.periodo.trim(),
    obra_id: textoOpcional(formulario.obraId),
  };
}

export function evaluacionCompleta(formulario: FormularioEvaluacion): boolean {
  return formulario.sujetoId.trim() !== '' && formulario.periodo.trim() !== '';
}

/**
 * Respuestas capturadas: `criterio_id → { valor, comentario }`. Los criterios
 * sin valor se omiten —el contrato exige al menos uno (`minItems: 1`)— y el
 * valor viaja como **string decimal**, como lo declara el contrato.
 */
export interface CapturaRespuesta {
  readonly valor: string;
  readonly comentario: string;
}

export function peticionDeRespuestas(
  capturas: ReadonlyMap<string, CapturaRespuesta>,
): AgregarRespuestasPeticion {
  const respuestas: RespuestaItemInput[] = [];
  for (const [criterioId, captura] of capturas) {
    const valor = captura.valor.trim();
    if (valor === '') continue;
    respuestas.push({
      criterio_id: criterioId,
      valor,
      comentario: textoOpcional(captura.comentario),
    });
  }
  return { respuestas };
}

export function hayRespuestas(capturas: ReadonlyMap<string, CapturaRespuesta>): boolean {
  return peticionDeRespuestas(capturas).respuestas.length > 0;
}

/**
 * Periodo por defecto en formato `YYYY-MM` (§7.8 acepta `'WWYY'` o
 * `'YYYY-MM'`). Se ofrece el mensual porque es el que se escribe sin pensar;
 * el campo es editable.
 */
export function periodoActual(ahora: Date = new Date()): string {
  const mes = String(ahora.getMonth() + 1).padStart(2, '0');
  return `${ahora.getFullYear()}-${mes}`;
}
