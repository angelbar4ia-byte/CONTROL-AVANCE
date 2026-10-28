/**
 * El costo del concepto frente a su composición (entrega 6). Agregar o quitar una matriz cambia lo
 * que el catálogo calcula, pero no publica una versión nueva de costo: eso es una decisión (el costo
 * vigente es el que usan las obras que se generen). Aquí se avisa **cuando la edición movió el costo
 * calculado** y se deja publicar la versión nueva —la vigente queda en el histórico—. No se compara
 * calculado contra vigente a secas: un concepto de precio fijo (sin composición) siempre diferiría, y
 * publicarlo lo dejaría en cero. Tampoco toca las obras ya generadas: su precio se congeló al generarlas.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getObtenerCpuApiV1ConceptosConceptoIdCpuGetQueryKey,
  useObtenerCpuApiV1ConceptosConceptoIdCpuGet,
  usePublicarCpuApiV1ConceptosConceptoIdCpuPost,
} from '@/api/generado/catalogos/catalogos';
import { fmtMXN } from '@/lib/formato';

interface Props {
  readonly conceptoId: string;
  readonly conceptoClave: string;
}

export function CostoDelConcepto({ conceptoId, conceptoClave }: Props) {
  const queryClient = useQueryClient();
  const cpu = useObtenerCpuApiV1ConceptosConceptoIdCpuGet(conceptoId);
  const publicar = usePublicarCpuApiV1ConceptosConceptoIdCpuPost<ErrorApi>();
  const [mensaje, setMensaje] = useState<string | null>(null);

  const vigente = cpu.data?.vigente;
  const calculado = cpu.data?.calculado;
  // Lo calculado al abrir el panel (o al publicar): contra eso se mide lo que movió la edición.
  const base = useRef<string | null>(null);
  if (calculado && base.current === null) base.current = calculado.total;
  if (!vigente || !calculado) return null; // sin costo publicado no hay contra qué comparar
  const difiere = Number(calculado.total) !== Number(base.current);
  if (!difiere && !mensaje) return null;

  async function publicarNueva() {
    try {
      const r = await publicar.mutateAsync({ conceptoId, data: {} });
      base.current = calculado?.total ?? base.current;
      await queryClient.invalidateQueries({ queryKey: getObtenerCpuApiV1ConceptosConceptoIdCpuGetQueryKey(conceptoId) });
      setMensaje(`Costo de ${conceptoClave} publicado: versión ${r.version.version}.`);
    } catch (err) {
      setMensaje(err instanceof Error ? err.message : 'No se pudo publicar el costo.');
    }
  }

  return (
    <div role="status" className="arbol__costo text-xs" data-testid="costo-del-concepto">
      {difiere ? (
        <>
          <span>
            La composición movió el costo: calculado {fmtMXN(base.current)} → {fmtMXN(calculado.total)} (vigente{' '}
            {fmtMXN(vigente.precio.total)}).
          </span>{' '}
          <button type="button" className="btn btn--ghost btn--sm" disabled={publicar.isPending} onClick={() => void publicarNueva()}>
            Publicar versión nueva
          </button>
        </>
      ) : (
        <span>{mensaje}</span>
      )}
    </div>
  );
}
