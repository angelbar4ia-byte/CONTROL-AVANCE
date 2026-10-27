/**
 * Cotización al cliente de lo que la obra modificó (migración 0084; cerebro D-531 a D-533, D-546;
 * B-123). *Antes de un control de cambio se hace un presupuesto al cliente del cambio o adicional.*
 *
 * Dos modos de precio: **por diferencia** (lo que entra menos lo que sale, entre el factor 0.7) y
 * **por m²** (una ampliación, a 17,000 el m²). Si no coinciden no se corrige solo: se dice. Control
 * de obra cotiza y registra la respuesta del cliente, que se da una sola vez.
 */

import { useRef, useState } from 'react';

import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import {
  getCotizacionesDeLaObraApiV1ObrasObraIdCotizacionesGetQueryKey,
  useCotizacionesDeLaObraApiV1ObrasObraIdCotizacionesGet,
  useCotizarLoModificadoApiV1ObrasObraIdCotizacionesPost,
  useResponderCotizacionApiV1CotizacionesCotizacionIdRespuestaPost,
} from '@/api/generado/partes/partes';
import { queryClient } from '@/app/queryClient';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtFecha, fmtMXN } from '@/lib/formato';

const ETIQUETA_ESTADO: Record<string, string> = {
  enviada: 'Enviada',
  aceptada: 'Aceptada',
  rechazada: 'Rechazada',
};

export default function Cotizaciones({ obraId, puedeCotizar }: { obraId: string; puedeCotizar: boolean }) {
  const [metodo, setMetodo] = useState<'por_diferencia' | 'por_m2'>('por_diferencia');
  const [m2, setM2] = useState('');
  const [error, setError] = useState<string | null>(null);
  const clave = useRef(claveDeIdempotencia());
  const lista = useCotizacionesDeLaObraApiV1ObrasObraIdCotizacionesGet(obraId);

  const refrescar = () =>
    void queryClient.invalidateQueries({
      queryKey: getCotizacionesDeLaObraApiV1ObrasObraIdCotizacionesGetQueryKey(obraId),
    });
  const cotizar = useCotizarLoModificadoApiV1ObrasObraIdCotizacionesPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        refrescar();
      },
      onError: (e) => setError(e.message),
    },
    request: { headers: () => ({ 'Idempotency-Key': clave.current }) },
  });
  const responder = useResponderCotizacionApiV1CotizacionesCotizacionIdRespuestaPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        refrescar();
      },
      onError: (e) => setError(e.message),
    },
    request: { headers: () => ({ 'Idempotency-Key': claveDeIdempotencia() }) },
  });

  const faltaM2 = metodo === 'por_m2' && !(Number(m2) > 0);

  return (
    <section aria-label="Cotización al cliente" className="mt-16">
      <h2 className="text-sm" style={{ margin: '16px 0 8px' }}>
        Cotización al cliente
      </h2>
      <div className="text-xs text-mute mb-8">
        Antes de un control de cambio se presupuesta al cliente lo que cambió. Por diferencia: lo que entra menos
        lo que sale, entre 0.7. Por m²: una ampliación a 17,000 el m².
      </div>
      {error && <ErrorBanner mensaje={error} />}

      {puedeCotizar && (
        <form
          aria-label="Cotizar lo modificado"
          className="row gap-8 mb-8"
          style={{ alignItems: 'flex-end', flexWrap: 'wrap' }}
          onSubmit={(e) => {
            e.preventDefault();
            clave.current = claveDeIdempotencia();
            cotizar.mutate({
              obraId,
              data: { metodo_precio: metodo, m2_ampliacion: metodo === 'por_m2' ? m2 : null },
            });
          }}
        >
          <div className="field">
            <label className="field__label" htmlFor="cot-metodo">
              Cómo se cobra
            </label>
            <select
              id="cot-metodo"
              className="select"
              value={metodo}
              onChange={(e) => setMetodo(e.target.value as 'por_diferencia' | 'por_m2')}
            >
              <option value="por_diferencia">Por diferencia (algo específico)</option>
              <option value="por_m2">Por m² (una ampliación)</option>
            </select>
          </div>
          {metodo === 'por_m2' && (
            <div className="field">
              <label className="field__label" htmlFor="cot-m2">
                m² de la ampliación
              </label>
              <input
                id="cot-m2"
                className="input"
                type="number"
                min="0"
                step="any"
                value={m2}
                onChange={(e) => setM2(e.target.value)}
              />
            </div>
          )}
          <button type="submit" className="btn btn--sm btn--primary" disabled={faltaM2 || cotizar.isPending}>
            Cotizar lo modificado
          </button>
        </form>
      )}

      {(lista.data ?? []).length === 0 ? (
        <div className="text-mute text-sm">Todavía no se ha cotizado nada al cliente.</div>
      ) : (
        <ul aria-label="Cotizaciones" className="text-sm" style={{ margin: 0, padding: 0, listStyle: 'none' }}>
          {(lista.data ?? []).map((c) => (
            <li key={c.id} style={{ marginBottom: 8 }}>
              <strong className="mono">{c.folio}</strong>{' '}
              <span className={`badge badge--${c.estado === 'aceptada' ? 'ok' : c.estado === 'rechazada' ? 'danger' : 'info'}`}>
                {ETIQUETA_ESTADO[c.estado] ?? c.estado}
              </span>{' '}
              · {c.metodo_precio === 'por_m2' ? 'Por m²' : 'Por diferencia'} · <strong>{fmtMXN(Number(c.precio))}</strong>
              <span className="text-xs text-mute">
                {' '}
                · entra {fmtMXN(Number(c.costo_entra))}, sale {fmtMXN(Number(c.costo_sale))} a costo directo ·{' '}
                {fmtFecha(c.creada_en)}
              </span>
              {c.por_m2_coincide_con_la_diferencia === false && (
                <div className="text-xs" role="note">
                  Por m² ({fmtMXN(Number(c.precio_por_m2))}) no coincide con la diferencia (
                  {fmtMXN(Number(c.precio_por_diferencia))}): no se corrige solo, alguien lo resuelve.
                </div>
              )}
              {c.estado === 'enviada' && puedeCotizar && (
                <span className="row gap-4" style={{ display: 'inline-flex', marginLeft: 8 }}>
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => responder.mutate({ cotizacionId: c.id, data: { aceptada: true } })}
                  >
                    El cliente aceptó
                  </button>
                  <button
                    type="button"
                    className="btn btn--sm"
                    onClick={() => responder.mutate({ cotizacionId: c.id, data: { aceptada: false } })}
                  >
                    El cliente rechazó
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
