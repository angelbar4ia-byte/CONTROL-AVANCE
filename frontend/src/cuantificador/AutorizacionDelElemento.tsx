/**
 * Costos propone, Control de obra autoriza (plan de elementos de muro, fase I): el estado de autorización del elemento, su versión
 * y su historial. Un elemento nuevo que propone Costos se usa como provisional hasta que Control de obra lo autoriza; el cambio de
 * Costos sobre un elemento autorizado y la actualización de un APU esperan su autorización y no se aplican antes. Cada autorización
 * crea una versión con quién propuso, quién autorizó y cuándo. Los cambios de Control de obra no piden autorización.
 */

import type { ErrorApi } from '@/api/cliente';
import {
  getAutorizacionDelElementoApiV1ElementosParametricosElementoIdAutorizacionGetQueryKey as claveDeAutorizacion,
  getListarElementosParametricosApiV1ElementosParametricosGetQueryKey,
  useAutorizacionDelElementoApiV1ElementosParametricosElementoIdAutorizacionGet as useAutorizacion,
  useAutorizarElementoApiV1ElementosParametricosElementoIdAutorizarPost as useAutorizarElemento,
  useAutorizarRevisionApiV1RevisionesDeElementosRevisionIdAutorizarPost as useAutorizarRevision,
  useRechazarRevisionApiV1RevisionesDeElementosRevisionIdRechazarPost as useRechazarRevision,
} from '@/api/generado/elementos-parametricos/elementos-parametricos';
import { queryClient } from '@/app/queryClient';

interface Props {
  readonly elementoId: string;
  readonly clave: string;
  readonly puedeAutorizar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

const CLASE: Record<string, string> = { elemento: 'Elemento', concepto: 'Concepto nuevo', apu: 'APU' };
const ESTADO: Record<string, string> = { pendiente: 'Pendiente', autorizada: 'Autorizada', rechazada: 'Rechazada' };
const ROL: Record<string, string> = { costos: 'Costos', control_obra: 'Control de obra' };

const cuando = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' }) : '—');

export function AutorizacionDelElemento({ elementoId, clave, puedeAutorizar, onCambio, onError }: Props) {
  const consulta = useAutorizacion(elementoId);
  const autorizarElemento = useAutorizarElemento<ErrorApi>();
  const autorizarRevision = useAutorizarRevision<ErrorApi>();
  const rechazarRevision = useRechazarRevision<ErrorApi>();
  const datos = consulta.data;
  if (!datos) return null;

  const recargar = () => {
    void queryClient.invalidateQueries({ queryKey: claveDeAutorizacion(elementoId) });
    void queryClient.invalidateQueries({ queryKey: getListarElementosParametricosApiV1ElementosParametricosGetQueryKey() });
  };
  const pendientes = datos.versiones.filter((v) => v.estado === 'pendiente');

  async function autorizarAlta() {
    try {
      const r = await autorizarElemento.mutateAsync({ elementoId });
      recargar();
      onCambio(`${clave} autorizado: versión ${r.version}.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo autorizar el elemento.');
    }
  }
  async function autorizar(revisionId: string) {
    try {
      const r = await autorizarRevision.mutateAsync({ revisionId });
      recargar();
      void queryClient.invalidateQueries();
      onCambio(`${clave}: propuesta autorizada, versión ${r.version}.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo autorizar la propuesta.');
    }
  }
  async function rechazar(revisionId: string) {
    const motivo = window.prompt('¿Por qué se rechaza? (opcional)') ?? undefined;
    try {
      await rechazarRevision.mutateAsync({ revisionId, data: { motivo: motivo === '' ? null : motivo } });
      recargar();
      onCambio(`${clave}: propuesta rechazada.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo rechazar la propuesta.');
    }
  }

  return (
    <div role="group" aria-label={`Autorización de ${clave}`} data-autorizacion-del-elemento={clave} style={{ display: 'grid', gap: 4 }}>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className="text-xs text-mute">Autorización</span>
        {datos.estado === 'pendiente' ? (
          <span className="badge badge--warn" data-estado-de-autorizacion="pendiente">Nuevo, pendiente de autorizar: se usa como provisional</span>
        ) : (
          <span className="badge badge--ok" data-estado-de-autorizacion="autorizado">Autorizado</span>
        )}
        <span className="badge" data-version-del-elemento={datos.version ?? 0}>{datos.version === null ? 'sin versión' : `v${datos.version}`}</span>
        {datos.estado === 'pendiente' && puedeAutorizar && (
          <button type="button" className="btn btn--primary" disabled={autorizarElemento.isPending} onClick={() => void autorizarAlta()}>
            Autorizar y crear v1
          </button>
        )}
        {datos.estado === 'pendiente' && !puedeAutorizar && <span className="text-xs text-mute">Espera la autorización de Control de obra.</span>}
      </div>
      {pendientes.map((p) => (
        <div key={p.id} className="row text-xs" data-propuesta-pendiente={p.clase} style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="badge badge--warn">{CLASE[p.clase] ?? p.clase} · pendiente</span>
          <span>{p.concepto_clave ? `${p.concepto_clave}: ` : ''}{p.resumen}</span>
          <span className="text-mute">propuso {p.propuso_nombre ?? ROL[p.propuso_rol ?? ''] ?? '—'}</span>
          {puedeAutorizar ? (
            <>
              <button type="button" className="btn btn--primary" disabled={autorizarRevision.isPending} onClick={() => void autorizar(p.id)}>
                Autorizar
              </button>
              <button type="button" className="btn" disabled={rechazarRevision.isPending} onClick={() => void rechazar(p.id)}>
                Rechazar
              </button>
            </>
          ) : (
            <span className="text-mute">Espera la autorización de Control de obra.</span>
          )}
        </div>
      ))}
      <details>
        <summary className="text-xs">Versiones</summary>
        <table className="text-xs" aria-label={`Versiones de ${clave}`}>
          <thead>
            <tr><th>Versión</th><th>Qué</th><th>Estado</th><th>Cambio</th><th>Propuso</th><th>Autorizó</th><th>Cuándo</th></tr>
          </thead>
          <tbody>
            {datos.versiones.map((v) => (
              <tr key={v.id} data-version-de-elemento={v.version ?? 'pendiente'} data-estado={v.estado}>
                <td>{v.version === null ? '—' : `v${v.version}`}</td>
                <td>{CLASE[v.clase] ?? v.clase}{v.concepto_clave ? ` ${v.concepto_clave}` : ''}</td>
                <td>{ESTADO[v.estado] ?? v.estado}</td>
                <td>{v.resumen}{v.motivo ? ` (${v.motivo})` : ''}</td>
                <td>{v.propuso_nombre ?? ROL[v.propuso_rol ?? ''] ?? '—'}</td>
                <td>{v.decidio_nombre ?? ROL[v.decidio_rol ?? ''] ?? '—'}</td>
                <td>{cuando(v.decidido_en ?? v.propuesto_en)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
