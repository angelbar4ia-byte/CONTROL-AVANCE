/**
 * Catálogo de motivos de almacén por la **ruta directa a Supabase** (§10.7).
 *
 * `motivo_almacen` es semilla editable (§8.7, §10.5) y está en la lista
 * blanca de `lib/supabase.ts`, así que se lee con supabase-js + RLS como
 * frontera —igual que unidades o familias— en vez de por la API: el contrato
 * no expone `GET /motivos-almacen` y `POST /obras/{id}/salidas` exige
 * `motivo_id`. Sin este catálogo el formulario de alta pediría pegar un UUID.
 *
 * La **escritura** de la salida sigue yendo por el backend (§10.7): esta ruta
 * es solo de lectura de catálogo.
 */

import { useQuery } from '@tanstack/react-query';

import { supabase } from '@/lib/supabase';

/** Fila de `motivo_almacen` (migración 0008). */
export interface MotivoAlmacen {
  readonly id: string;
  readonly clave: string;
  readonly descripcion: string;
  /** `-1` salida · `+1` entrada. Clasifica el bucket de KPI (§10.5). */
  readonly signo: number;
  readonly bucket: string;
}

export const CLAVE_CONSULTA_MOTIVOS = ['catalogo', 'motivo_almacen'] as const;

async function leerMotivos(): Promise<readonly MotivoAlmacen[]> {
  const { data, error } = await supabase
    .from('motivo_almacen')
    .select('id, clave, descripcion, signo, bucket')
    .eq('estatus', 'activo')
    .order('clave');

  if (error) throw new Error(error.message);
  return (data ?? []) as MotivoAlmacen[];
}

export function useMotivosAlmacen() {
  return useQuery({
    queryKey: CLAVE_CONSULTA_MOTIVOS,
    queryFn: leerMotivos,
    // Semilla editable pero de cambio raro: no vale la pena revalidar en
    // cada foco mientras se llena el formulario (§12.9).
    staleTime: 5 * 60 * 1000,
  });
}
