/**
 * Cierre de frentes — el segundo candado del cierre (migración 0071; D-515/D-522).
 *
 * El cierre tiene dos candados: **por frente** y, si se requiere, por actividad; el
 * segundo cierra todo el lote. Un frente es un nivel constructivo —cimentación,
 * planta baja, azotea—. El residente **solicita** su cierre al 90 % de avance, el
 * supervisor **aprueba** y control de obra **valida**; rechaza el supervisor o
 * control, con motivo. Cerrado el frente, el residente ya no registra avance ahí
 * (D-516).
 *
 * El frente que llega al 90 % **avisa** (`frente_listo_para_cierre`); no se cierra
 * solo: el cierre pregunta, no impide.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getFrentesDeLaObraApiV1ObrasObraIdCierresFrenteGetQueryKey,
  useAprobarCierreDeFrenteApiV1CierresFrenteCierreIdAprobarPost,
  useFrentesDeLaObraApiV1ObrasObraIdCierresFrenteGet,
  useRechazarCierreDeFrenteApiV1CierresFrenteCierreIdRechazarPost,
  useSolicitarCierreDeFrenteApiV1ObrasObraIdCierresFrentePost,
  useValidarCierreDeFrenteApiV1CierresFrenteCierreIdValidarPost,
} from '@/api/generado/cierres/cierres';
import type { FrenteParaCierreRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { colorAvance, fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { Modal } from '@/lib/Modal';
import { SelectorObra } from '@/lib/SelectorObra';
import { accionesDeFrente, etiquetaEstatusDeFrente, tonoEstatusDeFrente } from './reglas';

type Dialogo =
  | { readonly tipo: 'validar'; readonly frente: FrenteParaCierreRespuesta }
  | { readonly tipo: 'rechazar'; readonly frente: FrenteParaCierreRespuesta }
  | null;

export default function CierresDeFrente() {
  const { sesion } = useSesion();
  const idempotente = useClavesPorRecurso();
  const [obraId, setObraId] = useState('');
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [texto, setTexto] = useState('');
  const [error, setError] = useState<string | null>(null);

  const consulta = useFrentesDeLaObraApiV1ObrasObraIdCierresFrenteGet<
    FrenteParaCierreRespuesta[],
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });

  const alExito = () => {
    setError(null);
    setDialogo(null);
    setTexto('');
    void queryClient.invalidateQueries({
      queryKey: getFrentesDeLaObraApiV1ObrasObraIdCierresFrenteGetQueryKey(obraId),
    });
  };
  const opciones = {
    mutation: { onSuccess: alExito, onError: (e: ErrorApi) => setError(e.message) },
    ...idempotente,
  };
  const solicitar = useSolicitarCierreDeFrenteApiV1ObrasObraIdCierresFrentePost<ErrorApi>(opciones);
  const aprobar = useAprobarCierreDeFrenteApiV1CierresFrenteCierreIdAprobarPost<ErrorApi>(opciones);
  const validar = useValidarCierreDeFrenteApiV1CierresFrenteCierreIdValidarPost<ErrorApi>(opciones);
  const rechazar = useRechazarCierreDeFrenteApiV1CierresFrenteCierreIdRechazarPost<ErrorApi>(opciones);

  if (!sesion) return null;
  const rol = sesion.rol;
  const frentes = consulta.data ?? [];
  const listos = frentes.filter((f) => f.listo_para_cierre).length;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Cierre</div>
          <h1 className="page__title">Cierre de frentes</h1>
          <div className="page__subtitle">
            El frente es el nivel constructivo. El residente solicita su cierre al{' '}
            <strong>90 %</strong>, el supervisor aprueba y control de obra valida. Cerrado el
            frente, el residente ya no registra avance ahí.
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-8">
          <ErrorBanner mensaje={error} />
        </div>
      )}
      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}

      <div className="filterbar">
        <div style={{ minWidth: 260 }}>
          <SelectorObra id="cierre-frente-obra" etiqueta="Obra" valor={obraId} onCambio={setObraId} />
        </div>
        {listos > 0 && (
          <div className="text-sm" style={{ alignSelf: 'flex-end' }} role="status">
            <span className="badge badge--warn">
              {listos} {listos === 1 ? 'frente listo' : 'frentes listos'} para cierre
            </span>
          </div>
        )}
      </div>

      {obraId === '' ? (
        <div className="empty">
          <div className="empty-title">Elige una obra</div>
          <div className="empty-sub">Los frentes son los niveles de una obra.</div>
        </div>
      ) : consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Cargando…
        </div>
      ) : frentes.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Sin frentes</div>
          <div className="empty-sub">
            La obra todavía no tiene actividades con nivel: falta generarla.
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <div className="table-scroll">
            <table className="table" style={{ minWidth: 'max-content' }}>
              <thead>
                <tr>
                  <th style={{ minWidth: 100 }}>Frente</th>
                  <th style={{ minWidth: 200 }}>Descripción</th>
                  <th className="is-num">Actividades</th>
                  <th style={{ minWidth: 150 }}>Avance</th>
                  <th style={{ minWidth: 200 }}>Estado del cierre</th>
                  <th className="cell-actions" style={{ minWidth: 220 }} />
                </tr>
              </thead>
              <tbody>
                {frentes.map((f) => {
                  const acciones = accionesDeFrente(rol, f);
                  const pct = Number(f.avance_pct);
                  return (
                    <tr key={f.nivel_id}>
                      <td className="mono">{f.clave}</td>
                      <td>{f.descripcion ?? '—'}</td>
                      <td className="is-num tnum">{fmtNum(f.n_actividades)}</td>
                      <td>
                        <div className="row gap-4" style={{ alignItems: 'center' }}>
                          <div
                            className={`bar ${colorAvance(pct) !== 'accent' ? `bar--${colorAvance(pct)}` : ''}`}
                            style={{ flex: 1, minWidth: 60 }}
                          >
                            <div
                              className="bar__fill"
                              style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                            />
                          </div>
                          <span className="text-xs tnum">{fmtPct(f.avance_pct)}</span>
                        </div>
                      </td>
                      <td>
                        <span className={`badge badge--${tonoEstatusDeFrente(f.cierre_estatus)}`}>
                          {etiquetaEstatusDeFrente(f.cierre_estatus)}
                        </span>
                        {f.listo_para_cierre && (
                          <span
                            className="badge badge--warn"
                            title="Llegó al umbral y no se ha solicitado su cierre. Avisa, no cierra."
                          >
                            listo para cierre
                          </span>
                        )}
                        {f.cierre_estatus === 'rechazado' && f.cierre_comentarios && (
                          <div className="text-mute text-xs">{f.cierre_comentarios}</div>
                        )}
                        {f.cierre_estatus === 'validado' && f.validado_en && (
                          <div className="text-mute text-xs">{fmtFecha(f.validado_en)}</div>
                        )}
                      </td>
                      <td className="cell-actions">
                        <div className="row gap-4">
                          {acciones.includes('solicitar') && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              disabled={solicitar.isPending}
                              onClick={() =>
                                solicitar.mutate({ obraId, data: { nivel_id: f.nivel_id } })
                              }
                            >
                              Solicitar cierre
                            </button>
                          )}
                          {acciones.includes('aprobar') && f.cierre_id && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              disabled={aprobar.isPending}
                              onClick={() => aprobar.mutate({ cierreId: f.cierre_id as string })}
                            >
                              Aprobar
                            </button>
                          )}
                          {acciones.includes('validar') && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              onClick={() => setDialogo({ tipo: 'validar', frente: f })}
                            >
                              Validar
                            </button>
                          )}
                          {acciones.includes('rechazar') && (
                            <button
                              type="button"
                              className="btn btn--sm"
                              onClick={() => setDialogo({ tipo: 'rechazar', frente: f })}
                            >
                              Rechazar
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {dialogo && dialogo.frente.cierre_id && (
        <Modal
          titulo={dialogo.tipo === 'validar' ? 'Validar el cierre del frente' : 'Rechazar el cierre del frente'}
          onCerrar={() => {
            setDialogo(null);
            setTexto('');
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const cierreId = dialogo.frente.cierre_id as string;
              if (dialogo.tipo === 'validar') {
                validar.mutate({ cierreId, data: { comentario: texto.trim() || null } });
              } else if (texto.trim() !== '') {
                rechazar.mutate({ cierreId, data: { motivo: texto.trim() } });
              }
            }}
          >
            <div className="sheet__body col gap-12">
              <p className="text-sm">
                Frente <span className="mono">{dialogo.frente.clave}</span> ·{' '}
                {dialogo.frente.descripcion}
              </p>
              <p className="text-mute text-sm">
                {dialogo.tipo === 'validar'
                  ? 'Al validar, el frente queda cerrado: el residente ya no registra avance ahí.'
                  : 'El residente ve el motivo y puede volver a solicitar cuando lo corrija.'}
              </p>
              <div className="field">
                <label className="field__label" htmlFor="cierre-frente-texto">
                  {dialogo.tipo === 'validar' ? 'Comentario (opcional)' : 'Motivo'}
                </label>
                <textarea
                  id="cierre-frente-texto"
                  className="input"
                  rows={3}
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                />
              </div>
            </div>
            <div className="sheet__footer">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setDialogo(null);
                  setTexto('');
                }}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={
                  (dialogo.tipo === 'rechazar' && texto.trim() === '') ||
                  validar.isPending ||
                  rechazar.isPending
                }
              >
                {dialogo.tipo === 'validar' ? 'Validar' : 'Rechazar'}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
