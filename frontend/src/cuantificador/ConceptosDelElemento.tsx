/**
 * Los conceptos que toman una parte de la receta de un elemento paramétrico (cerebro D-630): «Habilitado de acero de
 * K-1» toma acero, estribos y alambre; «Colado de K-1» toma concreto y cimbra; un castillo puede contarse en piezas o
 * en metros. Se muestra lo que cada concepto toma por unidad suya. Sin botón de guardar: cada cambio se aplica.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useListarConceptosApiV1ConceptosGet } from '@/api/generado/catalogos/catalogos';
import {
  getConceptosDelElementoApiV1ElementosParametricosElementoIdConceptosGetQueryKey,
  useConceptosDelElementoApiV1ElementosParametricosElementoIdConceptosGet,
  useDejarDeTomarDelElementoApiV1ElementosParametricosElementoIdConceptosConceptoIdDelete,
  useTomarDelElementoApiV1ElementosParametricosElementoIdConceptosConceptoIdPut,
} from '@/api/generado/elementos-parametricos/elementos-parametricos';
import { queryClient } from '@/app/queryClient';

const MATERIALES = [
  ['concreto', 'Concreto'],
  ['acero', 'Acero'],
  ['estribos', 'Estribos'],
  ['alambre', 'Alambre'],
  ['cimbra', 'Cimbra'],
] as const;

type Material = (typeof MATERIALES)[number][0];

interface Props {
  readonly elementoId: string;
  readonly clave: string;
  /** Las unidades en que se puede contar un concepto de este tipo de elemento. */
  readonly unidades: readonly ('pza' | 'ml' | 'm²')[];
  readonly puedeDefinir: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

const num = (n: number) => (Math.abs(n) >= 100 ? n.toFixed(1) : Math.abs(n) >= 1 ? n.toFixed(2) : n.toFixed(3));

export function ConceptosDelElemento({ elementoId, clave, unidades, puedeDefinir, onCambio, onError }: Props) {
  const lista = useConceptosDelElementoApiV1ElementosParametricosElementoIdConceptosGet(elementoId);
  const catalogo = useListarConceptosApiV1ConceptosGet(undefined, { query: { enabled: puedeDefinir, staleTime: 60_000 } });
  const tomar = useTomarDelElementoApiV1ElementosParametricosElementoIdConceptosConceptoIdPut<ErrorApi>();
  const dejar = useDejarDeTomarDelElementoApiV1ElementosParametricosElementoIdConceptosConceptoIdDelete<ErrorApi>();
  const [nuevo, setNuevo] = useState('');

  const recargar = () =>
    void queryClient.invalidateQueries({
      queryKey: getConceptosDelElementoApiV1ElementosParametricosElementoIdConceptosGetQueryKey(elementoId),
    });
  const fallo = (err: unknown) => onError(err instanceof Error ? err.message : 'No se pudo cambiar el concepto.');

  async function guardar(conceptoId: string, unidad: 'pza' | 'ml' | 'm²', toma: Record<string, boolean>) {
    try {
      await tomar.mutateAsync({ elementoId, conceptoId, data: { unidad, toma } });
      recargar();
      onCambio(`${clave}: concepto actualizado.`);
    } catch (err) {
      fallo(err);
    }
  }

  const tomados = lista.data ?? [];
  const yaTomados = new Set(tomados.map((c) => c.concepto_id));

  return (
    <div role="group" aria-label={`Conceptos que toman de ${clave}`} style={{ display: 'grid', gap: 4 }}>
      <div className="text-xs text-mute">Conceptos que toman de este elemento</div>
      {tomados.length === 0 && <div className="text-mute text-xs">Ninguno todavía.</div>}
      {tomados.map((c) => (
        <div key={c.concepto_id} data-toma={c.clave} style={{ display: 'grid', gap: 2 }}>
          <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
            <span className="mono text-xs">{c.clave}</span>
            <span className="text-xs">{c.descripcion}</span>
            <select
              aria-label={`Unidad de ${c.clave}`}
              value={c.unidad}
              disabled={!puedeDefinir || tomar.isPending}
              onChange={(e) => void guardar(c.concepto_id, e.target.value as 'pza' | 'ml' | 'm²', c.toma)}
            >
              {unidades.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
            {puedeDefinir && (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                aria-label={`Quitar ${c.clave}`}
                onClick={() =>
                  void dejar
                    .mutateAsync({ elementoId, conceptoId: c.concepto_id })
                    .then(() => {
                      recargar();
                      onCambio(`${c.clave} ya no toma de ${clave}.`);
                    })
                    .catch(fallo)
                }
              >
                Quitar
              </button>
            )}
          </div>
          <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
            {MATERIALES.map(([m, rotulo]) => (
              <label key={m} className="text-xs">
                <input
                  type="checkbox"
                  checked={Boolean(c.toma[m])}
                  disabled={!puedeDefinir || tomar.isPending}
                  onChange={(e) => {
                    const siguiente: Record<string, boolean> = { ...c.toma, [m as Material]: e.target.checked };
                    void guardar(c.concepto_id, c.unidad as 'pza' | 'ml' | 'm²', siguiente);
                  }}
                />{' '}
                {rotulo}
              </label>
            ))}
          </div>
          <div className="text-xs text-mute">
            Por {c.unidad}:{' '}
            {MATERIALES.filter(([m]) => c.por_unidad[m])
              .map(([m, rotulo]) => `${rotulo.toLowerCase()} ${num(c.por_unidad[m]!.cantidad)} ${c.por_unidad[m]!.unidad}`)
              .join(' · ') || 'no toma materiales'}
          </div>
        </div>
      ))}
      {puedeDefinir && (
        <div className="arbol-edicion__alta" role="group" aria-label={`Un concepto toma de ${clave}`}>
          <select aria-label={`Concepto que toma de ${clave}`} value={nuevo} onChange={(e) => setNuevo(e.target.value)}>
            <option value="">Elige un concepto…</option>
            {(catalogo.data ?? [])
              .filter((c) => !yaTomados.has(c.id))
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.clave} · {c.descripcion}
                </option>
              ))}
          </select>
          <button
            type="button"
            className="btn btn--sm"
            disabled={nuevo === '' || tomar.isPending}
            onClick={() =>
              void guardar(nuevo, unidades[0]!, { concreto: true }).then(() => setNuevo(''))
            }
          >
            Agregar
          </button>
        </div>
      )}
    </div>
  );
}
