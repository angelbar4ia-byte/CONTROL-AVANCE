/**
 * La pestaña «Trabajos» del cuantificador: los destajos de la receta de cada concepto de la obra, con
 * su cuadrilla y su rendimiento. Puro: recibe lo que trae el servidor y lo que ya se midió.
 *
 * - La **cantidad del concepto** es lo medido en el plano; si aún no hay medición, lo presupuestado.
 * - La **cantidad del destajo** es la del concepto × el factor (unidades del destajo por unidad del
 *   concepto).
 * - La **cuadrilla es capacidad**: el rendimiento dice cuánto hace en un día. Manda el **teórico** (la
 *   semilla, editable); si no hay, el **calculado** (costo de la cuadrilla ÷ precio del destajo). El
 *   precio del destajo no cambia aunque cambie la cuadrilla.
 * - Duración = cantidad del destajo ÷ capacidad por día; jornales = costo de la jornada × días.
 */

import type { TrabajoDeObraRespuesta } from '@/api/generado/modelo';

export interface CantidadDelConcepto {
  readonly valor: number;
  readonly fuente: 'medida en el plano' | 'presupuestada';
}

export interface CalculoDeTrabajo {
  readonly cantidadDelConcepto: CantidadDelConcepto;
  readonly cantidad: number;
  readonly importe: number;
  /** Unidades del destajo que la cuadrilla hace en un día; `null` si no hay cuadrilla o rendimiento. */
  readonly capacidadPorDia: number | null;
  /** `'teórico'` o `'calculado'`: de dónde sale la capacidad. */
  readonly origenDeLaCapacidad: 'teórico' | 'calculado' | null;
  readonly dias: number | null;
  readonly jornales: number | null;
  /** Importe − jornales: lo que sobra del destajo después de pagar a la cuadrilla. */
  readonly diferencia: number | null;
}

export interface GrupoDeTrabajos {
  readonly actividadId: string;
  readonly conceptoClave: string;
  readonly conceptoNombre: string;
  readonly conceptoUnidad: string | null;
  readonly cantidadDelConcepto: CantidadDelConcepto;
  readonly trabajos: readonly TrabajoConCalculo[];
}

export interface TrabajoConCalculo {
  readonly trabajo: TrabajoDeObraRespuesta;
  readonly calculo: CalculoDeTrabajo;
}

const num = (v: string | number | null | undefined): number | null => {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};

/** Lo medido manda; sin medición (o en cero), lo presupuestado. */
export function cantidadDelConcepto(
  medida: string | number | null | undefined,
  presupuestada: string | number | null | undefined,
): CantidadDelConcepto {
  const m = num(medida);
  if (m !== null && m > 0) return { valor: m, fuente: 'medida en el plano' };
  return { valor: num(presupuestada) ?? 0, fuente: 'presupuestada' };
}

export function calcularTrabajo(
  trabajo: TrabajoDeObraRespuesta,
  cantidadConcepto: CantidadDelConcepto,
): CalculoDeTrabajo {
  const factor = num(trabajo.factor) ?? 0;
  const precio = num(trabajo.precio) ?? 0;
  const cantidad = cantidadConcepto.valor * factor;

  const teorico = num(trabajo.rendimiento_teorico);
  const calculado = num(trabajo.rendimiento_calculado);
  const capacidad = teorico !== null && teorico > 0 ? teorico : calculado !== null && calculado > 0 ? calculado : null;
  const origen: CalculoDeTrabajo['origenDeLaCapacidad'] =
    capacidad === null ? null : teorico !== null && teorico > 0 ? 'teórico' : 'calculado';

  const dias = capacidad !== null ? cantidad / capacidad : null;
  const costoJornada = num(trabajo.costo_cuadrilla);
  const jornales = dias !== null && costoJornada !== null ? costoJornada * dias : null;
  const importe = cantidad * precio;

  return {
    cantidadDelConcepto: cantidadConcepto,
    cantidad,
    importe,
    capacidadPorDia: capacidad,
    origenDeLaCapacidad: origen,
    dias,
    jornales,
    diferencia: jornales !== null ? importe - jornales : null,
  };
}

export interface OpcionesDeTrabajos {
  /** Lo medido de cada actividad (de la cuantificación), por id de actividad. */
  readonly medidaPorActividad: ReadonlyMap<string, string | number | null | undefined>;
  readonly busqueda?: string;
}

/** Los trabajos agrupados por concepto, en orden de clave, con su cálculo; filtrados por texto. */
export function agruparTrabajos(
  trabajos: readonly TrabajoDeObraRespuesta[],
  opciones: OpcionesDeTrabajos,
): readonly GrupoDeTrabajos[] {
  const consulta = (opciones.busqueda ?? '').trim().toLowerCase();
  const grupos = new Map<string, GrupoDeTrabajos & { trabajos: TrabajoConCalculo[] }>();

  for (const t of trabajos) {
    const concepto = cantidadDelConcepto(opciones.medidaPorActividad.get(t.actividad_id), t.cantidad_presupuestada);
    const clave = t.concepto_clave ?? '—';
    const nombre = t.concepto_descripcion ?? clave;
    const texto = [t.clave, t.descripcion, clave, nombre, t.cuadrilla_nombre].filter(Boolean).join(' ').toLowerCase();
    if (consulta !== '' && !texto.includes(consulta)) continue;

    const grupo = grupos.get(t.actividad_id) ?? {
      actividadId: t.actividad_id,
      conceptoClave: clave,
      conceptoNombre: nombre,
      conceptoUnidad: t.concepto_unidad ?? null,
      cantidadDelConcepto: concepto,
      trabajos: [],
    };
    grupo.trabajos.push({ trabajo: t, calculo: calcularTrabajo(t, concepto) });
    grupos.set(t.actividad_id, grupo);
  }
  return [...grupos.values()].sort((a, b) => a.conceptoClave.localeCompare(b.conceptoClave, 'es', { numeric: true }));
}
