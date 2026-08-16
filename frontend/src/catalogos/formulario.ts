/**
 * Traducción entre los campos de un formulario (siempre `string`) y los DTOs
 * del contrato (§11.2, "DTOs en el borde" — AGENTS.md).
 *
 * Mismo criterio que `proyectos/formulario.ts`: puro, sin reglas de negocio,
 * y normalizando vacíos a `null` porque el contrato distingue `null` de
 * ausente. En catálogos esa distinción es la que sostiene el §3.5: en
 * `iva_aplica`, `null` **no** es "no aplica", es "hereda de la familia".
 */

import type {
  CrearConceptoPeticion,
  CrearContratistaPeticion,
  CrearFamiliaPeticion,
  CrearInsumoPeticion,
  CrearMaterialPeticion,
  CrearUnidadPeticion,
  PublicarCPUPeticion,
  TipoConcepto,
  TipoInsumo,
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

/** `''` en el selector de IVA = heredar de la familia → `null` (§3.5). */
export type ValorIva = '' | 'si' | 'no';

export function ivaOpcional(valor: ValorIva): boolean | null {
  if (valor === '') return null;
  return valor === 'si';
}

/**
 * Sinónimos de unidad: uno por línea o separados por coma (§3.5, §10.3).
 *
 * El §3.5 pone el ejemplo (`pza→PZ`, `m2→M2`); son alias que cruzan a la
 * misma unidad. Se deduplican para no mandar dos veces el mismo alias.
 */
export function parsearSinonimos(texto: string): readonly string[] {
  const vistos = new Set<string>();
  const sinonimos: string[] = [];

  for (const bruto of texto.split(/[\n,]/)) {
    const sinonimo = bruto.trim();
    if (sinonimo === '' || vistos.has(sinonimo)) continue;
    vistos.add(sinonimo);
    sinonimos.push(sinonimo);
  }

  return sinonimos;
}

export interface FormularioUnidad {
  readonly clave: string;
  readonly nombre: string;
  readonly sinonimos: string;
  readonly factor: string;
}

export function peticionUnidad(formulario: FormularioUnidad): CrearUnidadPeticion {
  return {
    clave: formulario.clave.trim(),
    nombre: formulario.nombre.trim(),
    sinonimos: [...parsearSinonimos(formulario.sinonimos)],
    factor: numeroOpcional(formulario.factor) ?? undefined,
  };
}

export interface FormularioFamilia {
  readonly clave: string;
  readonly nombre: string;
  readonly parentId: string;
  /** `material` o `concepto` (§10.1). */
  readonly aplicaA: string;
  readonly ivaAplica: boolean;
}

export function peticionFamilia(formulario: FormularioFamilia): CrearFamiliaPeticion {
  return {
    clave: formulario.clave.trim(),
    nombre: formulario.nombre.trim(),
    parent_id: textoOpcional(formulario.parentId),
    aplica_a: formulario.aplicaA,
    iva_aplica: formulario.ivaAplica,
  };
}

export interface FormularioInsumo {
  readonly clave: string;
  readonly descripcion: string;
  readonly tipo: TipoInsumo;
  readonly unidadId: string;
  readonly familiaId: string;
  readonly costoBase: string;
  readonly iva: ValorIva;
  readonly factorConversion: string;
}

export function peticionInsumo(formulario: FormularioInsumo): CrearInsumoPeticion {
  return {
    clave: formulario.clave.trim(),
    descripcion: formulario.descripcion.trim(),
    tipo: formulario.tipo,
    unidad_id: textoOpcional(formulario.unidadId),
    familia_id: textoOpcional(formulario.familiaId),
    // `costo_base` y `factor_conversion` no aceptan `null` en el contrato:
    // se omiten cuando no se capturaron y el backend pone su default.
    costo_base: numeroOpcional(formulario.costoBase) ?? undefined,
    iva_aplica: ivaOpcional(formulario.iva),
    factor_conversion: numeroOpcional(formulario.factorConversion) ?? undefined,
  };
}

/**
 * Mismo formulario, ruta distinta: `POST /materiales` no lleva `tipo`
 * —"es siempre `material`" (§7.3, y así lo documenta el contrato)—.
 */
export function peticionMaterial(formulario: FormularioInsumo): CrearMaterialPeticion {
  return {
    clave: formulario.clave.trim(),
    descripcion: formulario.descripcion.trim(),
    unidad_id: textoOpcional(formulario.unidadId),
    familia_id: textoOpcional(formulario.familiaId),
    costo_base: numeroOpcional(formulario.costoBase) ?? undefined,
    iva_aplica: ivaOpcional(formulario.iva),
    factor_conversion: numeroOpcional(formulario.factorConversion) ?? undefined,
  };
}

export interface FormularioConcepto {
  readonly clave: string;
  readonly descripcion: string;
  readonly tipo: TipoConcepto;
  readonly unidadId: string;
  readonly familiaId: string;
}

export function peticionConcepto(formulario: FormularioConcepto): CrearConceptoPeticion {
  return {
    clave: formulario.clave.trim(),
    descripcion: formulario.descripcion.trim(),
    tipo: formulario.tipo,
    unidad_id: textoOpcional(formulario.unidadId),
    familia_id: textoOpcional(formulario.familiaId),
  };
}

export interface FormularioContratista {
  readonly clave: string;
  readonly razonSocial: string;
  readonly rfc: string;
  readonly contacto: string;
  readonly telefono: string;
  readonly email: string;
}

export function peticionContratista(
  formulario: FormularioContratista,
): CrearContratistaPeticion {
  return {
    clave: formulario.clave.trim(),
    razon_social: formulario.razonSocial.trim(),
    rfc: textoOpcional(formulario.rfc),
    contacto: textoOpcional(formulario.contacto),
    telefono: textoOpcional(formulario.telefono),
    email: textoOpcional(formulario.email),
  };
}

export interface FormularioVersionCPU {
  readonly variante: string;
  /** Vacío = que el backend lo calcule de la explosión (§7.3). */
  readonly precioUnitario: string;
  readonly precioDestajo: string;
}

/**
 * Cuerpo de `POST /conceptos/{id}/cpu`.
 *
 * El contrato dice que el precio explícito es la excepción: "si se omite —lo
 * normal—, el CPU se calcula de la explosión del concepto (§7.3)". Por eso
 * los dos campos se mandan solo cuando el usuario los capturó; un `0`
 * escrito a mano sí viaja, un campo vacío no.
 */
export function peticionVersionCPU(
  formulario: FormularioVersionCPU,
): PublicarCPUPeticion {
  return {
    variante: textoOpcional(formulario.variante),
    precio_unitario: numeroOpcional(formulario.precioUnitario),
    precio_destajo: numeroOpcional(formulario.precioDestajo),
  };
}

/**
 * ¿La captura pide un precio explícito a medias? El contrato acepta los dos
 * campos o ninguno; capturar solo el total dejaría el destajo sin definir y
 * el §7.3 exige el desglose (destajo ≤ total). Se avisa antes de enviar.
 */
export function precioIncompleto(formulario: FormularioVersionCPU): boolean {
  const total = formulario.precioUnitario.trim() !== '';
  const destajo = formulario.precioDestajo.trim() !== '';
  return total !== destajo;
}
