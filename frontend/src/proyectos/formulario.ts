/**
 * Traducción entre los campos de un formulario (siempre `string`) y los DTOs
 * del contrato (§11.2, "DTOs en el borde" — AGENTS.md).
 *
 * Todo lo de aquí es puro y sin reglas de negocio: normaliza vacíos a `null`,
 * arma el cuerpo de `POST /obras/bulk` y calcula el **diff** de un
 * `PATCH /obras/{id}` — mandar el objeto completo en un PATCH borraría la
 * distinción entre "no lo toques" (`undefined`) y "libéralo" (`null`), que el
 * contrato usa en `residente_id`.
 */

import type {
  ActualizarObraPeticion,
  CrearObraPeticion,
  ObraRespuesta,
} from '@/api/generado/modelo';

/** Texto de un input: vacío → `null` (el contrato usa `null`, no `''`). */
export function textoOpcional(valor: string): string | null {
  const limpio = valor.trim();
  return limpio === '' ? null : limpio;
}

/** Número de un input: vacío o no numérico → `null`. */
export function numeroOpcional(valor: string): number | null {
  const limpio = valor.trim();
  if (limpio === '') return null;
  const n = Number(limpio);
  return Number.isFinite(n) ? n : null;
}

/** Campos editables de una obra (§11.2 `PATCH /obras/{id}`). */
export interface FormularioObra {
  readonly clave: string;
  readonly residenteId: string;
  readonly fechaInicio: string;
  readonly fechaFin: string;
  readonly m2: string;
}

/** Vuelca una obra del servidor a los campos del formulario. */
export function formularioDeObra(obra: ObraRespuesta): FormularioObra {
  return {
    clave: obra.clave,
    residenteId: obra.residente_id ?? '',
    fechaInicio: obra.fecha_inicio ?? '',
    fechaFin: obra.fecha_fin ?? '',
    m2: obra.m2 ?? '',
  };
}

/**
 * Solo los campos que cambiaron respecto a la obra actual.
 *
 * `undefined` (campo ausente) = no lo toques · `null` = límpialo. Para
 * `residente_id` el contrato lo dice explícito: "manda `null` para liberar
 * la obra".
 */
export function cambiosDeObra(
  obra: ObraRespuesta,
  formulario: FormularioObra,
): ActualizarObraPeticion {
  const cambios: {
    -readonly [K in keyof ActualizarObraPeticion]: ActualizarObraPeticion[K];
  } = {};

  const clave = formulario.clave.trim();
  if (clave !== '' && clave !== obra.clave) cambios.clave = clave;

  const residenteId = textoOpcional(formulario.residenteId);
  if (residenteId !== (obra.residente_id ?? null)) cambios.residente_id = residenteId;

  const fechaInicio = textoOpcional(formulario.fechaInicio);
  if (fechaInicio !== (obra.fecha_inicio ?? null)) cambios.fecha_inicio = fechaInicio;

  const fechaFin = textoOpcional(formulario.fechaFin);
  if (fechaFin !== (obra.fecha_fin ?? null)) cambios.fecha_fin = fechaFin;

  const m2 = numeroOpcional(formulario.m2);
  const m2Actual = obra.m2 === null ? null : Number(obra.m2);
  if (m2 !== m2Actual) cambios.m2 = m2;

  return cambios;
}

export function hayCambios(cambios: ActualizarObraPeticion): boolean {
  return Object.keys(cambios).length > 0;
}

export interface ClavesLote {
  /** Claves en el orden capturado, sin vacíos ni repetidas. */
  readonly claves: readonly string[];
  /** Claves que venían más de una vez (se conserva la primera). */
  readonly duplicadas: readonly string[];
}

/**
 * Claves del alta masiva: una por línea (§11.2 `POST /obras/bulk`).
 *
 * El lote entra completo o no entra (así lo documenta el contrato), y una
 * clave repetida lo tumbaría entero por la unicidad de `clave` (§3.3), así
 * que se avisa antes de enviarlo.
 */
export function parsearClavesLote(texto: string): ClavesLote {
  const claves: string[] = [];
  const duplicadas: string[] = [];
  const vistas = new Set<string>();

  for (const linea of texto.split('\n')) {
    const clave = linea.trim();
    if (clave === '') continue;
    if (vistas.has(clave)) {
      if (!duplicadas.includes(clave)) duplicadas.push(clave);
      continue;
    }
    vistas.add(clave);
    claves.push(clave);
  }

  return { claves, duplicadas };
}

/** Arma el cuerpo del lote repitiendo los datos comunes en cada clave. */
export function obrasDelLote(
  comunes: Omit<CrearObraPeticion, 'clave'>,
  claves: readonly string[],
): readonly CrearObraPeticion[] {
  return claves.map((clave) => ({ ...comunes, clave }));
}
