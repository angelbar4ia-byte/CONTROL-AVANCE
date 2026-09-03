/**
 * Reflejo en el front del alta extra-catálogo (§11.2).
 *
 * Sin lógica de negocio: qué campo de precio corresponde a cada modo de pago y
 * cuándo el formulario está completo. Las reglas de verdad viven en
 * `domain/obras/extra_catalogo.py` y en el `CHECK` de la migración 0026.
 */

import { ModoPago } from '@/api/generado/modelo';

export interface FormularioExtra {
  readonly descripcion: string;
  readonly ordenCambio: string;
  readonly cantBase: string;
  readonly modoPago: ModoPago;
  /** Un solo campo: cuál se manda lo decide `campoDePrecio`. */
  readonly precio: string;
  readonly duracionDias: string;
}

const ETIQUETA_MODO: Record<string, string> = {
  destajo: 'Destajo',
  concepto: 'Por concepto',
  subcontrato: 'Subcontrato',
};

export function etiquetaModoPago(modo: string): string {
  return ETIQUETA_MODO[modo] ?? modo;
}

/**
 * Qué precio pide cada modo de pago (§7.3).
 *
 * El dominio exige **el del modo elegido y solo ese**: un trabajo por concepto
 * no tiene por qué traer precio de destajo, y pedir los dos obligaría a
 * inventar un número. Por eso el formulario tiene un único campo de precio y
 * cambia de nombre.
 */
export function campoDePrecio(modo: ModoPago): 'precio_destajo' | 'precio_unitario' {
  return modo === ModoPago.destajo ? 'precio_destajo' : 'precio_unitario';
}

function positivo(valor: string): boolean {
  const numero = Number(valor);
  return Number.isFinite(numero) && numero > 0;
}

/**
 * ¿Se puede enviar?
 *
 * Refleja lo que el backend va a exigir, para no mandar una petición que ya se
 * sabe que falla: descripción, orden de cambio, cantidad positiva y precio
 * positivo. El servidor lo vuelve a comprobar — esto es UX, no validación.
 */
export function extraCompleto(formulario: FormularioExtra): boolean {
  return (
    formulario.descripcion.trim() !== '' &&
    formulario.ordenCambio.trim() !== '' &&
    positivo(formulario.cantBase) &&
    positivo(formulario.precio)
  );
}

// --- Las dos cosas que el jefe de obra distingue (§11.3) ------------------

import type { ActividadRespuesta } from '@/api/generado/modelo';
import { TipoControlCambio } from '@/api/generado/modelo';

/**
 * Dos nombres para dos cosas, y no eran sinónimos.
 *
 * El jefe de obra las separó: *"fuera de catálogo son actividades que no están
 * en el catálogo, y extra de catálogo son las que solicita el residente cuando
 * se termina el umbral"*.
 *
 * Confundirlas tiene consecuencia: una la da de alta el residente porque vio
 * aparecer el trabajo, y la otra necesita que Control autorice más cantidad.
 * Presentarlas en la misma lista haría que se pidieran por el camino
 * equivocado.
 */
export type PestanaExtra = 'fuera' | 'extra' | 'solicitudes';

export const PESTANAS_EXTRA: readonly {
  readonly clave: PestanaExtra;
  readonly etiqueta: string;
  readonly ayuda: string;
}[] = [
  {
    clave: 'fuera',
    etiqueta: 'Fuera de catálogo',
    ayuda: 'Trabajo que no está en el catálogo. Lo das de alta con su precio.',
  },
  {
    clave: 'extra',
    etiqueta: 'Extra de catálogo',
    ayuda: 'Más cantidad de algo que ya está, cuando se agota el umbral.',
  },
  {
    clave: 'solicitudes',
    etiqueta: 'Mis solicitudes',
    ayuda: 'Lo que pediste a Control y en qué quedó.',
  },
];

/**
 * ¿Cuánto le queda a esta actividad antes de necesitar autorización? (§6)
 *
 * Espejo de `techo_de` en `domain.obras.control_cambio` y del CHECK
 * `ck_actividad_programada_vs_base`. Vive aquí solo para avisar **mientras el
 * residente escribe**, no para decidir: la decisión es del servidor.
 */
export function techoDe(actividad: ActividadRespuesta): number {
  const autorizada = actividad.cant_autorizada;
  if (autorizada !== null && autorizada !== undefined) return Number(autorizada);
  const tolerancia = Number(actividad.tolerancia_pct ?? 20);
  return Number(actividad.cant_base) * (1 + tolerancia / 100);
}

/** Lo que todavía se puede programar sin pedirle nada a nadie. */
export function margenDe(actividad: ActividadRespuesta): number {
  return Math.max(0, techoDe(actividad) - Number(actividad.cant_programada));
}

/**
 * ¿Esta actividad ya agotó su umbral?
 *
 * Es la lista de "por esto tengo que pedir": sin margen, subir la cantidad
 * pasa por Control. Se muestran también las que están cerca —el umbral no
 * avisa antes de agotarse y descubrirlo el día que se necesita es tarde.
 */
export function sinMargen(actividad: ActividadRespuesta): boolean {
  return margenDe(actividad) <= 0;
}

const ETIQUETA_TIPO_CAMBIO: Record<string, string> = {
  extra_catalogo: 'Más cantidad',
  fuera_catalogo: 'Fuera de catálogo',
  sustitucion: 'Sustitución',
  alta_catalogo: 'Alta de catálogo',
};

export function etiquetaTipoCambio(tipo: string): string {
  return ETIQUETA_TIPO_CAMBIO[tipo] ?? tipo;
}

const TONO_ESTATUS_CAMBIO: Record<string, string> = {
  solicitado: 'warn',
  autorizado: 'ok',
  rechazado: 'danger',
};

export function tonoEstatusCambio(estatus: string): string {
  return TONO_ESTATUS_CAMBIO[estatus] ?? 'outline';
}

/** Los tipos que el residente puede pedir desde esta pantalla. */
export const TIPOS_SOLICITABLES: readonly TipoControlCambio[] = [
  TipoControlCambio.extra_catalogo,
  TipoControlCambio.fuera_catalogo,
  TipoControlCambio.sustitucion,
  TipoControlCambio.alta_catalogo,
];
