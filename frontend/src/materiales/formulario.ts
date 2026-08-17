/**
 * Traducción entre el formulario de salida de almacén (todo `string`) y el
 * DTO del contrato (`RegistrarSalidaPeticion`, §11.2 "Materiales";
 * "DTOs en el borde" — AGENTS.md).
 *
 * Puro y sin reglas: no decide si el signo de la cantidad concuerda con el
 * del motivo (eso lo resuelve el backend con un 409, §10.5) ni si el costo
 * lleva IVA (los costos van **sin IVA**, §10.6, y el backend lo agrega según
 * la `Clase` del material, §3.5).
 */

import type { RegistrarSalidaPeticion } from '@/api/generado/modelo';

export interface FormularioSalida {
  readonly insumoId: string;
  readonly motivoId: string;
  readonly cantidad: string;
  readonly costo: string;
  readonly fecha: string;
  readonly conceptoId: string;
  readonly contratistaId: string;
}

export function formularioSalidaVacio(fecha: string): FormularioSalida {
  return {
    insumoId: '',
    motivoId: '',
    cantidad: '',
    costo: '',
    fecha,
    conceptoId: '',
    contratistaId: '',
  };
}

function textoOpcional(valor: string): string | undefined {
  const limpio = valor.trim();
  return limpio === '' ? undefined : limpio;
}

/**
 * Cantidad y costo viajan como **string decimal**: el contrato los declara
 * con el patrón numérico de Pydantic (`Decimal`), y convertirlos a `number`
 * aquí perdería precisión en importes largos (§7 "Importes en DECIMAL").
 */
export function peticionDeSalida(formulario: FormularioSalida): RegistrarSalidaPeticion {
  return {
    insumo_id: formulario.insumoId.trim(),
    motivo_id: formulario.motivoId.trim(),
    cantidad: formulario.cantidad.trim(),
    costo: formulario.costo.trim() === '' ? '0' : formulario.costo.trim(),
    fecha: formulario.fecha,
    concepto_id: textoOpcional(formulario.conceptoId),
    contratista_id: textoOpcional(formulario.contratistaId),
  };
}

/**
 * ¿Están los campos que el contrato marca obligatorios?
 *
 * Solo verifica presencia —no rangos ni signos—: el 422/409 del endpoint es
 * quien decide si el movimiento es válido (§11.2).
 */
export function salidaCompleta(formulario: FormularioSalida): boolean {
  return (
    formulario.insumoId.trim() !== '' &&
    formulario.motivoId.trim() !== '' &&
    formulario.cantidad.trim() !== '' &&
    formulario.fecha.trim() !== ''
  );
}

/** Fecha de hoy en `YYYY-MM-DD` local, como la espera el contrato (`date`). */
export function hoyISO(ahora: Date = new Date()): string {
  const mes = String(ahora.getMonth() + 1).padStart(2, '0');
  const dia = String(ahora.getDate()).padStart(2, '0');
  return `${ahora.getFullYear()}-${mes}-${dia}`;
}
