/**
 * Cierres — bandeja de solicitudes de cierre de actividad (§4, §11.3 C).
 *
 * Pantalla compartida (§5.3): Supervisor y Control de obra la ven con el
 * mismo componente, pero cada uno solo puede accionar lo que le toca —
 * `validar ≠ autorizar` (§4):
 *   - Supervisor **autoriza** o rechaza una solicitud `solicitada`.
 *   - Control de obra **valida** (con comentario opcional) o rechaza una
 *     solicitud `autorizada`.
 *
 * Rutas: `/cierres` para ambos roles (`shell/navegacion.ts`).
 */

import { useState } from 'react';

import {
  useAutorizarCierreApiV1CierresCierreIdAutorizarPost,
  useListarCierresApiV1CierresGet,
  useRechazarCierreApiV1CierresCierreIdRechazarPost,
  useValidarCierreApiV1CierresCierreIdValidarPost,
} from '@/api/generado/cierres/cierres';
import type { CierreRespuesta, EstatusSolicitudCierre } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { accionesDisponibles, tonoEstatusCierre } from './reglas';

const TABS: readonly { readonly valor: EstatusSolicitudCierre | 'todas'; readonly etiqueta: string }[] = [
  { valor: 'todas', etiqueta: 'Todas' },
  { valor: 'solicitada', etiqueta: 'Solicitada' },
  { valor: 'autorizada', etiqueta: 'Autorizada' },
  { valor: 'validada', etiqueta: 'Validada' },
  { valor: 'rechazada', etiqueta: 'Rechazada' },
];

type Dialogo =
  | { readonly tipo: 'validar'; readonly cierre: CierreRespuesta }
  | { readonly tipo: 'rechazar'; readonly cierre: CierreRespuesta }
  | null;

function idCorto(id: string): string {
  return id.slice(0, 8);
}

export default function Cierres() {
  const { sesion } = useSesion();
  const [tab, setTab] = useState<EstatusSolicitudCierre | 'todas'>('todas');
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [texto, setTexto] = useState('');
  const [error, setError] = useState<string | null>(null);

  const consulta = useListarCierresApiV1CierresGet({
    estatus: tab === 'todas' ? undefined : tab,
  });

  const autorizar = useAutorizarCierreApiV1CierresCierreIdAutorizarPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  const validar = useValidarCierreApiV1CierresCierreIdValidarPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setDialogo(null);
        setTexto('');
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  const rechazar = useRechazarCierreApiV1CierresCierreIdRechazarPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setDialogo(null);
        setTexto('');
        void consulta.refetch();
      },
      onError: (err) => setError(err.message),
    },
  });

  if (!sesion) return null;
  const rol = sesion.rol;

  const filas = consulta.data ?? [];

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">
            {rol === 'control_obra' ? 'Control de obra' : 'Control supervisión'}
          </div>
          <h1 className="page__title">Cierres</h1>
          <div className="page__subtitle">
            {rol === 'control_obra'
              ? 'Valida y comenta las solicitudes autorizadas — no autoriza (§4).'
              : rol === 'supervisor'
                ? 'Autoriza o rechaza las solicitudes de cierre de tus obras.'
                : 'Bandeja de solicitudes de cierre.'}
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-8">
          <ErrorBanner mensaje={error} />
        </div>
      )}

      <div className="filterbar">
        <div className="tabs">
          {TABS.map((t) => (
            <button
              key={t.valor}
              type="button"
              className={`tabs__tab ${tab === t.valor ? 'is-active' : ''}`}
              onClick={() => setTab(t.valor)}
            >
              {t.etiqueta}
            </button>
          ))}
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Cierre</th>
                <th>Actividad</th>
                <th className="is-num">Cantidad</th>
                <th className="is-num">Monto</th>
                <th>Estatus</th>
                <th>Comentarios</th>
                <th className="cell-actions">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={7}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      No hay solicitudes en este filtro.
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((cierre) => {
                  const acciones = accionesDisponibles(rol, cierre.estatus);
                  return (
                    <tr key={cierre.id}>
                      <td className="is-key" title={cierre.id}>
                        {idCorto(cierre.id)}
                      </td>
                      <td className="is-key" title={cierre.actividad_id}>
                        {idCorto(cierre.actividad_id)}
                      </td>
                      <td className="is-num">{fmtNum(cierre.cantidad)}</td>
                      <td className="is-num">{fmtMXN(cierre.monto)}</td>
                      <td>
                        <span className={`badge badge--${tonoEstatusCierre(cierre.estatus)}`}>
                          {cierre.estatus}
                        </span>
                      </td>
                      <td className="text-mute">{cierre.comentarios ?? '—'}</td>
                      <td className="cell-actions">
                        <div className="row gap-4">
                          {acciones.includes('autorizar') && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              disabled={autorizar.isPending}
                              onClick={() => autorizar.mutate({ cierreId: cierre.id })}
                            >
                              Autorizar
                            </button>
                          )}
                          {acciones.includes('validar') && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              onClick={() => setDialogo({ tipo: 'validar', cierre })}
                            >
                              Validar
                            </button>
                          )}
                          {acciones.includes('rechazar') && (
                            <button
                              type="button"
                              className="btn btn--danger btn--sm"
                              onClick={() => setDialogo({ tipo: 'rechazar', cierre })}
                            >
                              Rechazar
                            </button>
                          )}
                          {acciones.length === 0 && <span className="text-faint text-sm">—</span>}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {dialogo?.tipo === 'validar' && (
        <Modal
          titulo="Validar cierre"
          onCerrar={() => {
            setDialogo(null);
            setTexto('');
          }}
        >
          <div className="sheet__body">
            <div className="field">
              <label className="field__label" htmlFor="comentario-validar">
                Comentario (opcional)
              </label>
              <textarea
                id="comentario-validar"
                className="textarea"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder="Control de obra valida y comenta — no autoriza (§4)."
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
              type="button"
              className="btn btn--accent"
              disabled={validar.isPending}
              onClick={() =>
                validar.mutate({
                  cierreId: dialogo.cierre.id,
                  data: { comentario: texto.trim() === '' ? undefined : texto },
                })
              }
            >
              {validar.isPending ? 'Validando…' : 'Confirmar validación'}
            </button>
          </div>
        </Modal>
      )}

      {dialogo?.tipo === 'rechazar' && (
        <Modal
          titulo="Rechazar solicitud de cierre"
          onCerrar={() => {
            setDialogo(null);
            setTexto('');
          }}
        >
          <div className="sheet__body">
            <div className="field">
              <label className="field__label" htmlFor="motivo-rechazo">
                Motivo (obligatorio)
              </label>
              <textarea
                id="motivo-rechazo"
                className="textarea"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                required
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
              type="button"
              className="btn btn--danger"
              disabled={rechazar.isPending || texto.trim() === ''}
              onClick={() =>
                rechazar.mutate({ cierreId: dialogo.cierre.id, data: { motivo: texto } })
              }
            >
              {rechazar.isPending ? 'Rechazando…' : 'Confirmar rechazo'}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
