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
