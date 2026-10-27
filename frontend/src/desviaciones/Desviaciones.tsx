/**
 * Desviaciones de una obra, con o sin causa (cerebro MODELO.md §5g).
 *
 * El cuantificador escribe una desviación cuando lo medido en el plano se aparta
 * de la cantidad base. Aquí se ven y se les pone causa, siguiendo las reglas de
 * captura del cerebro:
 *
 *   1. la detección no depende de nadie: la desviación existe se declare o no;
 *   2. «sin causa» es un estado válido, con su propio porcentaje: se muestra, no
 *      se persigue ni se penaliza;
 *   3. la causa se agrega **después**, sin vencer, y se puede corregir;
 *   4. el vocabulario es controlado —no texto libre—: sin eso las desviaciones no
 *      se pueden agregar ni comparar.
 *
 * Los dos factores nunca se suman: una fila es de precio **o** de consumo.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCapturarCausaApiV1DesviacionesDesviacionIdCausaPut,
  useListarDesviacionesApiV1ObrasObraIdDesviacionesGet,
} from '@/api/generado/desviaciones/desviaciones';
import { useListarObrasApiV1ObrasGet } from '@/api/generado/obras/obras';
import type { CausaDesviacion, DesviacionRespuesta, ObraRespuesta } from '@/api/generado/modelo';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtFecha, fmtMXN, fmtNum, fmtPct } from '@/lib/formato';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { etiquetaCausa, etiquetaFactor, resumenDeCausas } from './reglas';

export default function Desviaciones() {
  const idempotente = useClavesPorRecurso();
  const [obraElegida, setObraElegida] = useState('');
  const [error, setError] = useState<string | null>(null);

  const obrasQ = useListarObrasApiV1ObrasGet<ObraRespuesta[], ErrorApi>({});
  const obras = obrasQ.data ?? [];
  const obraId = obraElegida !== '' ? obraElegida : (obras[0]?.id ?? '');

  const consulta = useListarDesviacionesApiV1ObrasObraIdDesviacionesGet<
    DesviacionRespuesta[],
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });

  const capturar = useCapturarCausaApiV1DesviacionesDesviacionIdCausaPut<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (e) => setError(e.message),
    },
    ...idempotente,
  });

  const filas = consulta.data ?? [];
  const resumen = resumenDeCausas(filas);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Comprobación</div>
          <h1 className="page__title">Desviaciones</h1>
          <div className="page__subtitle">
            Lo medido que se aparta de lo presupuestado. La desviación existe se declare o
            no su causa; la causa se agrega después, sin prisa, y se puede corregir.
          </div>
        </div>
      </div>

      <div className="filterbar">
        <div className="field" style={{ minWidth: 220 }}>
          <label className="field__label" htmlFor="desv-obra">
            Obra
          </label>
          <select
            id="desv-obra"
            className="select"
            value={obraId}
            onChange={(e) => setObraElegida(e.target.value)}
          >
            {obras.map((o) => (
              <option key={o.id} value={o.id}>
                {o.clave}
              </option>
            ))}
          </select>
        </div>
        {resumen.total > 0 && (
          <div className="text-sm text-mute" style={{ alignSelf: 'flex-end' }}>
            {resumen.total} desviaciones · {resumen.sinCausa} sin causa (
            {fmtPct(resumen.pctSinCausa)})
          </div>
        )}
      </div>

      {obrasQ.error && <ErrorBanner mensaje={obrasQ.error.message} />}
      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}
      {error && <ErrorBanner mensaje={error} />}

      {obraId === '' || consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          {obraId === '' ? 'Sin obras en tu alcance.' : 'Cargando…'}
        </div>
      ) : filas.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Sin desviaciones</div>
          <div className="empty-sub">
            Esta obra no tiene lo medido apartado de lo presupuestado.
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <div className="table-scroll">
            <table className="table" style={{ minWidth: 'max-content' }}>
              <thead>
                <tr>
                  <th style={{ minWidth: 110 }}>Detectada</th>
                  <th style={{ minWidth: 260 }}>Dónde</th>
                  <th>Factor</th>
                  <th className="is-num">Plan → Real</th>
                  <th className="is-num">Monto</th>
                  <th style={{ minWidth: 260 }}>Causa</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((f) => (
                  <tr key={f.id}>
                    <td className="text-xs">{fmtFecha(f.detectada_en)}</td>
                    <td>
                      <span className="mono">{f.nodo_clave ?? '—'}</span> {f.nodo_descripcion}
                      <div className="text-mute text-xs">
                        {f.tipo_nodo === 'insumo' ? 'Insumo' : 'Concepto'}
                      </div>
                    </td>
                    <td>
                      <span className="badge badge--outline">{etiquetaFactor(f.tipo)}</span>
                    </td>
                    <td className="is-num tnum">
                      {f.tipo === 'consumo'
                        ? `${fmtNum(f.cantidad_plan)} → ${fmtNum(f.cantidad_real)}`
                        : `${fmtMXN(f.precio_plan)} → ${fmtMXN(f.precio_real)}`}
                    </td>
                    <td className="is-num tnum">{fmtMXN(f.monto)}</td>
                    <td>
                      <select
                        className="select"
                        aria-label={`Causa de ${f.nodo_clave ?? 'la desviación'} (${etiquetaFactor(f.tipo)})`}
                        value={f.causa ?? ''}
                        disabled={capturar.isPending}
                        onChange={(e) => {
                          if (e.target.value === '') return;
                          capturar.mutate({
                            desviacionId: f.id,
                            data: { causa: e.target.value as CausaDesviacion },
                          });
                        }}
                      >
                        <option value="">Sin causa</option>
                        {f.causas_posibles.map((c) => (
                          <option key={c} value={c}>
                            {etiquetaCausa(c)}
                          </option>
                        ))}
                      </select>
                      {f.causa_capturada_por && (
                        <div className="text-mute text-xs">
                          {f.causa_capturada_por} · {fmtFecha(f.causa_capturada_en)}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
