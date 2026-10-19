/**
 * Reflejo de UX del catálogo de ensambles paramétricos (skill
 * `erp-parametrico`, §11.2).
 *
 * Este módulo **no decide nada**. El permiso real lo impone el RBAC del
 * backend (`exigir_rol` en `adapters/api/v1/ensambles.py`), el alcance lo
 * impone RLS (§12.4), y los números —costo, destajo, cantidades acumuladas,
 * la clasificación de cada renglón al regenerar— los calcula el dominio
 * (`domain/catalogos/ensamble.py`). Aquí solo se traduce el contrato a
 * presentación: no se ofrece un botón que el servidor va a responder con 403
 * y no se pinta un estado sin explicar qué hay que hacer con él.
 *
 * El contrato reparte así:
 *   - `GET /ensambles` · `/{id}` · `/renglones` · `/cohorte` · `/explosion`
 *     → **C, SI**
 *   - `POST /ensambles` (Extracción) · `POST /ensambles/{id}/generar`
 *     → **solo C**
 */

import type { RenglonEnsamblePeticion } from '@/api/generado/modelo';
import { EstadoRenglonGenerado, OrigenCantidadEnsamble } from '@/api/generado/modelo';
import type { Rol } from '@/shell/navegacion';
import type { TonoBadge } from '@/lib/tonos';

/** ¿Este rol consulta ensambles? — leer es (C, SI), igual que el CPU de APU. */
export function puedeConsultarEnsambles(rol: Rol): boolean {
  return rol === 'control_obra' || rol === 'super_intendente';
}

/** ¿Este rol crea (Extracción) o genera/regenera? — solo Control de obra. */
export function puedeEscribirEnsambles(rol: Rol): boolean {
  return rol === 'control_obra';
}

const ETIQUETA_ORIGEN: Record<string, string> = {
  [OrigenCantidadEnsamble.heredada_concepto]: 'Heredada del concepto',
  [OrigenCantidadEnsamble.heredada_destajo]: 'Heredada de un destajo',
  [OrigenCantidadEnsamble.manual]: 'Manual',
};

/** Etiqueta de `origen` (skill §2: "heredar es mejor que capturar"). */
export function etiquetaOrigen(origen: string): string {
  return ETIQUETA_ORIGEN[origen] ?? origen;
}

export const OPCIONES_ORIGEN: readonly { readonly valor: string; readonly etiqueta: string }[] = [
  OrigenCantidadEnsamble.heredada_concepto,
  OrigenCantidadEnsamble.heredada_destajo,
  OrigenCantidadEnsamble.manual,
].map((valor) => ({ valor, etiqueta: etiquetaOrigen(valor) }));

const ETIQUETA_ESTADO: Record<string, string> = {
  [EstadoRenglonGenerado.nuevo]: 'Nuevo',
  [EstadoRenglonGenerado.actualizado]: 'Actualizado',
  [EstadoRenglonGenerado.desvinculado]: 'Editado a mano',
  [EstadoRenglonGenerado.conflicto]: 'Ya existía capturado',
  [EstadoRenglonGenerado.sobra]: 'Ya no está en la receta',
};

/** Etiqueta del estado de un renglón tras generar (skill §6). */
export function etiquetaEstadoRenglon(estado: string): string {
  return ETIQUETA_ESTADO[estado] ?? estado;
}

/**
 * Solo `nuevo` y `actualizado` se escriben sin preguntar; los otros tres
 * nunca se aplican solos y piden una decisión (skill §8, regla 11), así que
 * se pintan como alerta y no como éxito.
 */
export function tonoEstadoRenglon(estado: string): TonoBadge {
  if (estado === EstadoRenglonGenerado.nuevo || estado === EstadoRenglonGenerado.actualizado) {
    return 'ok';
  }
  return estado === EstadoRenglonGenerado.sobra ? 'warn' : 'danger';
}

const EXPLICACION_ESTADO: Record<string, string> = {
  [EstadoRenglonGenerado.desvinculado]:
    'Alguien editó esta partida a mano después de generarla: no se tocó. Compara lo que tiene hoy con lo que el ensamble pide ahora.',
  [EstadoRenglonGenerado.conflicto]:
    'Ya hay una partida capturada a mano para este concepto dentro de la instancia, que nunca generó este ensamble: no se sabe si es la misma cosa, así que no se tocó.',
  [EstadoRenglonGenerado.sobra]:
    'La partida existe pero el ensamble ya no incluye este concepto. Nada se borra solo: queda en el presupuesto hasta que decidas.',
};

/** Qué pasó y qué hay que hacer con un renglón pendiente (skill §6). */
export function explicacionEstado(estado: string): string {
  return EXPLICACION_ESTADO[estado] ?? '';
}

/**
 * Tasa y dispersión viajan siempre juntas (skill §5.7, regla 9): "un precio
 * paramétrico sin su dispersión es un número disfrazado de certeza". Si una
 * de las dos falta, no se muestra ninguna como dato firme.
 */
export function tasaPublicada(tasa: string | null | undefined, dispersion: string | null | undefined): boolean {
  return tasa != null && dispersion != null;
}

/**
 * El factor es cuántas veces entra el ensamble completo (skill §6): un número
 * positivo. Se valida solo para no pedirle al servidor una explosión que no
 * tiene sentido; el cálculo con él es del backend.
 */
export function factorValido(factor: string): boolean {
  const numero = Number(factor);
  return factor.trim() !== '' && Number.isFinite(numero) && numero > 0;
}

export interface FormularioRenglon {
  /** `'concepto'` o `'sub_ensamble'`: exactamente uno de los dos (skill §0). */
  readonly tipo: 'concepto' | 'sub_ensamble';
  readonly clave: string;
  readonly cantidad: string;
  readonly origen: string;
}

export const RENGLON_VACIO: FormularioRenglon = {
  tipo: 'concepto',
  clave: '',
  cantidad: '',
  origen: OrigenCantidadEnsamble.heredada_concepto,
};

/** Un renglón se puede enviar con clave y una cantidad positiva. */
export function renglonCompleto(renglon: FormularioRenglon): boolean {
  const cantidad = Number(renglon.cantidad);
  return renglon.clave.trim() !== '' && Number.isFinite(cantidad) && cantidad > 0;
}

/**
 * Del formulario al contrato. El orden es la posición en la lista; el backend
 * valida concepto XOR sub-ensamble y que la clave exista (§3.3), aquí solo se
 * arma el cuerpo.
 */
export function peticionRenglon(renglon: FormularioRenglon, orden: number): RenglonEnsamblePeticion {
  const clave = renglon.clave.trim();
  return {
    cantidad: renglon.cantidad,
    origen: renglon.origen as RenglonEnsamblePeticion['origen'],
    clave_concepto: renglon.tipo === 'concepto' ? clave : null,
    clave_sub_ensamble: renglon.tipo === 'sub_ensamble' ? clave : null,
    orden,
  };
}
