/**
 * Reflejo de UX del bloque "Catálogos · APU" (§7.3, §10.1, §11.2).
 *
 * Este módulo **no decide nada**. El alcance real lo impone RLS (§12.4), el
 * permiso real lo impone el RBAC del backend (`exigir_rol` en
 * `adapters/api/v1/catalogos.py`) y el costeo real lo calcula el dominio
 * (`domain/catalogos/apu.py`). Aquí solo se traduce el contrato a
 * presentación, para no ofrecer un botón que el servidor va a responder con
 * 403 ni pintar un dato sin etiqueta.
 *
 * El contrato (§11.2, bloque "Catálogos · APU") reparte así:
 *   - `GET/POST /unidades` · `/familias` · `/insumos` · `/conceptos` ·
 *     `/materiales` · `/contratistas` → **solo C**
 *   - `GET /conceptos/{id}/cpu` · `/explosion` → **C, SI**
 *   - `POST /conceptos/{id}/cpu` (nueva versión) → **solo C**
 */

import type { FamiliaRespuesta, InsumoRespuesta } from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';
import type { TonoBadge } from '@/lib/tonos';

/**
 * ¿Este rol administra los catálogos? — todo el bloque `GET/POST` de
 * catálogos es de Control de obra (§11.2).
 *
 * Es también quien edita la **semilla editable** (§8.7): unidades, familias
 * con su IVA y altas/bajas se administran desde Configuración, sin tocar
 * código.
 */
export function puedeAdministrarCatalogos(rol: Rol): boolean {
  return rol === 'control_obra';
}

/**
 * ¿Este rol consulta el APU? — `GET /conceptos/{id}/cpu` y `/explosion` son
 * (C, SI): el Super intendente ve el costeo aunque no edite el catálogo.
 */
export function puedeConsultarAPU(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}

/**
 * ¿Este rol publica una versión de CPU? — `POST /conceptos/{id}/cpu` es solo
 * de Control de obra (§11.2); el versionado es su responsabilidad (§10.8).
 */
export function puedePublicarCPU(rol: Rol): boolean {
  return rol === 'control_obra';
}

const ETIQUETA_TIPO_INSUMO: Record<string, string> = {
  material: 'Material',
  mano_obra: 'Mano de obra',
  equipo: 'Equipo',
  herramienta: 'Herramienta',
  subcontrato: 'Subcontrato',
};

/** Etiqueta legible de `insumo.tipo` (§7.3, invariante del §8.7). */
export function etiquetaTipoInsumo(tipo: string): string {
  return ETIQUETA_TIPO_INSUMO[tipo] ?? tipo;
}

const ETIQUETA_TIPO_CONCEPTO: Record<string, string> = {
  concepto: 'Concepto',
  auxiliar: 'Auxiliar',
  matriz: 'Matriz',
  basico: 'Básico',
};

/**
 * Etiqueta legible de `concepto.tipo` (§7.3). `auxiliar` y `matriz` son los
 * que otros conceptos anidan: por eso la explosión es un árbol.
 */
export function etiquetaTipoConcepto(tipo: string): string {
  return ETIQUETA_TIPO_CONCEPTO[tipo] ?? tipo;
}

const ETIQUETA_CATEGORIA: Record<string, string> = {
  material: 'Material',
  mano_obra: 'Mano de obra',
  equipo: 'Equipo',
  destajo: 'Destajo',
  subcontrato: 'Subcontrato',
  auxiliar: 'Auxiliar',
  matriz: 'Matriz',
};

/** Etiqueta legible de `explosion.categoria` (§7.3). */
export function etiquetaCategoria(categoria: string): string {
  return ETIQUETA_CATEGORIA[categoria] ?? categoria;
}

const TONO_CATEGORIA: Record<string, TonoBadge> = {
  material: 'info',
  mano_obra: 'accent',
  equipo: 'outline',
  destajo: 'accent',
  subcontrato: 'accent',
  auxiliar: 'warn',
  matriz: 'warn',
};

/**
 * Tono visual de una categoría de explosión.
 *
 * Mapeo de presentación, **no** la definición de qué es destajo: quién cobra
 * la cuadrilla lo decide el dominio (`CATEGORIAS_DE_DESTAJO` en
 * `domain/catalogos/apu.py`) y llega por línea en `es_destajo`. Aquí solo se
 * elige un color; agrupar los tonos de destajo bajo `accent` es una
 * coincidencia visual, no la regla.
 */
export function tonoCategoria(categoria: string): TonoBadge {
  return TONO_CATEGORIA[categoria] ?? 'outline';
}

const ETIQUETA_ESTATUS: Record<string, string> = {
  activo: 'Activo',
  inactivo: 'Inactivo',
};

/** Etiqueta de `estatus` de un registro de catálogo (baja lógica, §8.7). */
export function etiquetaEstatusCatalogo(estatus: string): string {
  return ETIQUETA_ESTATUS[estatus] ?? estatus;
}

const TONO_ESTATUS: Record<string, TonoBadge> = {
  activo: 'ok',
  inactivo: 'outline',
};

export function tonoEstatusCatalogo(estatus: string): TonoBadge {
  return TONO_ESTATUS[estatus] ?? 'outline';
}

/** De dónde salió el IVA que se está mostrando. */
export type OrigenIva = 'insumo' | 'familia' | 'sin_definir';

export interface IvaMostrado {
  /** `null` = ni el insumo ni su familia lo definen todavía. */
  readonly aplica: boolean | null;
  readonly origen: OrigenIva;
}

/**
 * IVA que aplica a un insumo, **tal como el backend lo dejó guardado** (§3.5).
 *
 * El §3.5 lo define así: "IVA por material (casilla en el catálogo de
 * Materiales): valor inicial derivado de la **familia** (gravada → activada;
 * Pétreos / Jardinería → desactivada); **override por material**". El
 * contrato lo repite en `CrearInsumoPeticion.iva_aplica`: "Nulo = hereda de
 * la familia".
 *
 * Esta función **no calcula impuestos**: no conoce la tasa (16% es
 * configurable y vive en BD, §8.7 caveat) ni qué familias están exentas.
 * Solo resuelve cuál de los dos valores que ya vinieron del servidor es el
 * que gobierna, para poder decir en la tabla si el insumo lleva override o
 * heredó de su familia. La autoridad sigue siendo el backend.
 */
export function ivaDelInsumo(
  insumo: Pick<InsumoRespuesta, 'iva_aplica'>,
  familia: Pick<FamiliaRespuesta, 'iva_aplica'> | undefined,
): IvaMostrado {
  const override = insumo.iva_aplica;
  if (override !== null && override !== undefined) {
    return { aplica: override, origen: 'insumo' };
  }

  const heredado = familia?.iva_aplica;
  if (heredado !== null && heredado !== undefined) {
    return { aplica: heredado, origen: 'familia' };
  }

  return { aplica: null, origen: 'sin_definir' };
}

const NOTA_ORIGEN_IVA: Record<OrigenIva, string> = {
  insumo: 'Override capturado en el insumo (§3.5).',
  familia: 'Heredado de la familia (§3.5).',
  sin_definir: 'Ni el insumo ni su familia lo definen; lo resuelve Configuración (§8.7).',
};

export function notaOrigenIva(origen: OrigenIva): string {
  return NOTA_ORIGEN_IVA[origen];
}
