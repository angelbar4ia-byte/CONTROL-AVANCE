/**
 * Cómo cuenta un muro (cerebro D-627): una línea medida en m² suma largo × altura × caras. La altura es una o va
 * **por partes** (cada parte de «desde» a «hasta», y puede no sumar: un cerramiento cuenta para la altura pero no
 * para el aplanado); las caras son una (interior o exterior) o dos. El servidor rehace el factor del enlace y los
 * vanos descuentan por las mismas caras. Sin botón de guardar: cada cambio se aplica.
 */

import { useEffect, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getVerMuroApiV1TrazosTrazoIdMuroGetQueryKey,
  useFijarMuroApiV1TrazosTrazoIdMuroPut,
  useVerMuroApiV1TrazosTrazoIdMuroGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import { queryClient } from '@/app/queryClient';

import { ALTURA_POR_DEFECTO_M } from './trazoPeticion';

interface Parte {
  nombre: string;
  desde: string;
  hasta: string;
  suma: boolean;
}

interface Props {
  readonly trazoId: string;
  readonly puedeEditar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

const num = (t: string) => Number(t.replace(',', '.'));

/** La altura que suma: la de las partes que suman, o la altura única. */
export function alturaQueSuma(partes: readonly Parte[] | null, altura: string): number {
  if (partes && partes.length > 0) {
    return partes.reduce((s, p) => (p.suma ? s + Math.max(num(p.hasta) - num(p.desde), 0) : s), 0);
  }
  return num(altura);
}

export function MuroDelTrazo({ trazoId, puedeEditar, onCambio, onError }: Props) {
  const muro = useVerMuroApiV1TrazosTrazoIdMuroGet(trazoId);
  const fijar = useFijarMuroApiV1TrazosTrazoIdMuroPut<ErrorApi>();
  const [altura, setAltura] = useState(String(ALTURA_POR_DEFECTO_M));
  const [caras, setCaras] = useState<1 | 2>(2);
  const [cara, setCara] = useState<'interior' | 'exterior'>('interior');
  const [partes, setPartes] = useState<Parte[] | null>(null);

  useEffect(() => {
    const m = muro.data;
    if (!m) return;
    setAltura(m.altura_m != null ? String(Number(m.altura_m)) : String(ALTURA_POR_DEFECTO_M));
    setCaras(m.caras === 1 ? 1 : 2);
    setCara(m.cara === 'exterior' ? 'exterior' : 'interior');
    setPartes(
      m.partes
        ? m.partes.map((p) => ({ nombre: p.nombre ?? '', desde: String(Number(p.desde_m)), hasta: String(Number(p.hasta_m)), suma: p.suma ?? true }))
        : null,
    );
  }, [muro.data]);

  const efectiva = alturaQueSuma(partes, altura);
  const partesValidas = partes === null || partes.every((p) => num(p.desde) >= 0 && num(p.hasta) > num(p.desde));
  const valido = partesValidas && efectiva > 0 && efectiva * caras !== 1;

  async function aplicar(sig: { altura?: string; caras?: 1 | 2; cara?: 'interior' | 'exterior'; partes?: Parte[] | null }) {
    const a = sig.altura ?? altura;
    const c = sig.caras ?? caras;
    const k = sig.cara ?? cara;
    const p = sig.partes === undefined ? partes : sig.partes;
    if (!(alturaQueSuma(p, a) > 0)) return;
    try {
      await fijar.mutateAsync({
        trazoId,
        data: {
          caras: c,
          ...(c === 1 ? { cara: k } : {}),
          ...(p && p.length > 0
            ? { partes: p.map((x) => ({ nombre: x.nombre, desde_m: num(x.desde), hasta_m: num(x.hasta), suma: x.suma })) }
            : { altura_m: num(a) }),
        },
      });
      void queryClient.invalidateQueries({ queryKey: getVerMuroApiV1TrazosTrazoIdMuroGetQueryKey(trazoId) });
      onCambio(`Muro: ${alturaQueSuma(p, a).toFixed(2)} m × ${c} ${c === 1 ? 'cara' : 'caras'}.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar cómo cuenta el muro.');
    }
  }

  const nuevaParte = (): Parte => ({ nombre: '', desde: partes && partes.length ? partes[partes.length - 1]!.hasta : '0', hasta: '', suma: true });

  return (
    <div role="group" aria-label="Cómo cuenta el muro" style={{ display: 'grid', gap: 4 }}>
      <div className="text-xs text-mute">Muro · altura × caras (m²)</div>
      <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
        {([1, 2] as const).map((n) => (
          <button
            key={n}
            type="button"
            className={caras === n ? 'btn btn--sm btn--primary' : 'btn btn--sm'}
            aria-pressed={caras === n}
            disabled={!puedeEditar || fijar.isPending}
            onClick={() => void aplicar({ caras: n })}
          >
            {n === 1 ? '1 cara' : '2 caras'}
          </button>
        ))}
        {caras === 1 &&
          (['interior', 'exterior'] as const).map((k) => (
            <button
              key={k}
              type="button"
              className={cara === k ? 'btn btn--sm btn--primary' : 'btn btn--sm'}
              aria-pressed={cara === k}
              disabled={!puedeEditar || fijar.isPending}
              onClick={() => void aplicar({ cara: k })}
            >
              {k === 'interior' ? 'Interior' : 'Exterior'}
            </button>
          ))}
      </div>
      <div className="row" style={{ gap: 4, flexWrap: 'wrap' }}>
        <button
          type="button"
          className={partes === null ? 'btn btn--sm btn--primary' : 'btn btn--sm'}
          aria-pressed={partes === null}
          disabled={!puedeEditar || fijar.isPending}
          onClick={() => {
            setPartes(null);
            void aplicar({ partes: null });
          }}
        >
          Altura única
        </button>
        <button
          type="button"
          className={partes !== null ? 'btn btn--sm btn--primary' : 'btn btn--sm'}
          aria-pressed={partes !== null}
          disabled={!puedeEditar || fijar.isPending}
          onClick={() => setPartes([{ nombre: 'Muro', desde: '0', hasta: altura, suma: true }])}
        >
          Por partes
        </button>
      </div>
      {partes === null ? (
        <label className="text-xs">
          Altura (m){' '}
          <input
            aria-label="Altura del muro (m)"
            inputMode="decimal"
            style={{ width: 56 }}
            value={altura}
            disabled={!puedeEditar}
            onChange={(e) => setAltura(e.target.value)}
            onBlur={() => valido && void aplicar({})}
          />
        </label>
      ) : (
        <div style={{ display: 'grid', gap: 2 }}>
          {partes.map((p, i) => (
            <div key={i} className="row" style={{ gap: 4 }}>
              <input aria-label={`Nombre de la parte ${i + 1}`} style={{ width: 80 }} value={p.nombre} disabled={!puedeEditar}
                onChange={(e) => setPartes(partes.map((x, j) => (j === i ? { ...x, nombre: e.target.value } : x)))} />
              <input aria-label={`Desde (m) de la parte ${i + 1}`} inputMode="decimal" style={{ width: 44 }} value={p.desde} disabled={!puedeEditar}
                onChange={(e) => setPartes(partes.map((x, j) => (j === i ? { ...x, desde: e.target.value } : x)))} />
              <input aria-label={`Hasta (m) de la parte ${i + 1}`} inputMode="decimal" style={{ width: 44 }} value={p.hasta} disabled={!puedeEditar}
                onChange={(e) => setPartes(partes.map((x, j) => (j === i ? { ...x, hasta: e.target.value } : x)))}
                onBlur={() => valido && void aplicar({})} />
              <label className="text-xs" title="Suma a la cantidad">
                <input type="checkbox" checked={p.suma} disabled={!puedeEditar}
                  onChange={(e) => {
                    const sig = partes.map((x, j) => (j === i ? { ...x, suma: e.target.checked } : x));
                    setPartes(sig);
                    void aplicar({ partes: sig });
                  }} />
                suma
              </label>
              {puedeEditar && (
                <button type="button" className="btn btn--ghost btn--sm" aria-label={`Quitar la parte ${i + 1}`}
                  onClick={() => {
                    const sig = partes.filter((_, j) => j !== i);
                    setPartes(sig.length ? sig : null);
                    void aplicar({ partes: sig.length ? sig : null });
                  }}>
                  ×
                </button>
              )}
            </div>
          ))}
          {puedeEditar && (
            <button type="button" className="btn btn--sm" onClick={() => setPartes([...partes, nuevaParte()])}>
              + Parte
            </button>
          )}
        </div>
      )}
      <div className="text-xs text-mute">
        Suma {Number.isFinite(efectiva) ? efectiva.toFixed(2) : '—'} m × {caras} = factor {Number.isFinite(efectiva) ? (efectiva * caras).toFixed(2) : '—'}
        {!valido && ' · revisa las medidas'}
      </div>
    </div>
  );
}
