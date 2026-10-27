/**
 * Reprogramar lo asignado — las fechas asignadas no se mueven solas
 * (migración 0072; cerebro D-533, P-4).
 *
 * Una actividad asignada a un contratista no admite que se le mueva la fecha directo:
 * el residente o el supervisor **proponen** la fecha nueva (desde la programación) y
 * una cadena la acepta —el supervisor **revisa** lo del residente, control de obra
 * **valida** y **realiza**—. Al realizarse se mueve la fecha, queda el rastro en la
 * bitácora del programa y se avisa a los demás: si propuso el residente, al supervisor y a
 * control; si propuso el supervisor, al residente y a control.
 *
 * Control de obra también puede **observar**: dejar una nota al residente y al supervisor
 * sin mover la cadena, en cualquier estatus.
 *
 * Esta pantalla es la bandeja de esa cadena: cada reprogramación de la obra, lo que se
 * movió y quién ha intervenido, con la acción que le toca a cada rol.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getReprogramacionesDeLaObraApiV1ObrasObraIdReprogramacionesGetQueryKey,
  useAplicarReprogramacionApiV1ReprogramacionesReprogramacionIdAplicarPost,
  useObservarReprogramacionApiV1ReprogramacionesReprogramacionIdObservacionesPost,
  useRechazarReprogramacionApiV1ReprogramacionesReprogramacionIdRechazarPost,
  useReprogramacionesDeLaObraApiV1ObrasObraIdReprogramacionesGet,
  useRevisarReprogramacionApiV1ReprogramacionesReprogramacionIdRevisarPost,
  useValidarReprogramacionApiV1ReprogramacionesReprogramacionIdValidarPost,
} from '@/api/generado/programacion/programacion';
import type { ReprogramacionDeObraRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';
import { useSesion } from '@/app/sesion';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtFecha } from '@/lib/formato';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { Modal } from '@/lib/Modal';
import { SelectorObra } from '@/lib/SelectorObra';
import {
  accionesDeReprogramacion,
  etiquetaEstatusDeReprogramacion,
  puedeObservar,
  quienSigue,
  tonoEstatusDeReprogramacion,
} from './reglas';

export default function Reprogramaciones() {
  const { sesion } = useSesion();
  const idempotente = useClavesPorRecurso();
  const [obraId, setObraId] = useState('');
  const [rechazando, setRechazando] = useState<ReprogramacionDeObraRespuesta | null>(null);
  const [observando, setObservando] = useState<ReprogramacionDeObraRespuesta | null>(null);
  const [motivo, setMotivo] = useState('');
  const [observacion, setObservacion] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  const consulta = useReprogramacionesDeLaObraApiV1ObrasObraIdReprogramacionesGet<
    ReprogramacionDeObraRespuesta[],
    ErrorApi
  >(obraId, { query: { enabled: obraId !== '' } });

  const alExito = (mensaje: string) => () => {
    setError(null);
    setRechazando(null);
    setObservando(null);
    setMotivo('');
    setObservacion('');
    setAviso(mensaje);
    void queryClient.invalidateQueries({
      queryKey: getReprogramacionesDeLaObraApiV1ObrasObraIdReprogramacionesGetQueryKey(obraId),
    });
  };
  const opciones = (mensaje: string) => ({
    mutation: { onSuccess: alExito(mensaje), onError: (e: ErrorApi) => setError(e.message) },
    ...idempotente,
  });
  const revisar = useRevisarReprogramacionApiV1ReprogramacionesReprogramacionIdRevisarPost<ErrorApi>(
    opciones('Reprogramación revisada: sigue la validación de control de obra.'),
  );
  const validar = useValidarReprogramacionApiV1ReprogramacionesReprogramacionIdValidarPost<ErrorApi>(
    opciones('Reprogramación validada: control de obra puede realizarla.'),
  );
  const aplicar = useAplicarReprogramacionApiV1ReprogramacionesReprogramacionIdAplicarPost<ErrorApi>(
    opciones('Reprogramación realizada: la fecha se movió y se avisó a los demás.'),
  );
  const rechazar = useRechazarReprogramacionApiV1ReprogramacionesReprogramacionIdRechazarPost<ErrorApi>(
    opciones('Reprogramación rechazada.'),
  );

  const observar = useObservarReprogramacionApiV1ReprogramacionesReprogramacionIdObservacionesPost<ErrorApi>(
    opciones('Observación enviada al residente y al supervisor.'),
  );

  if (!sesion) return null;
  const rol = sesion.rol;
  const filas = consulta.data ?? [];
  const pendientes = filas.filter((f) => accionesDeReprogramacion(rol, f.estatus).length > 0).length;
  const ocupado = revisar.isPending || validar.isPending || aplicar.isPending;

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Programa</div>
          <h1 className="page__title">Reprogramaciones</h1>
          <div className="page__subtitle">
            Las fechas de lo <strong>asignado</strong> no se mueven solas: el residente o el
            supervisor proponen la fecha nueva; el supervisor revisa, y control de obra valida y
            realiza. Se propone desde la programación de la actividad.
          </div>
        </div>
      </div>

      {error && (
        <div className="mb-8">
          <ErrorBanner mensaje={error} />
        </div>
      )}
      {consulta.error && <ErrorBanner mensaje={consulta.error.message} />}
      {aviso && (
        <div className="text-sm mb-8" role="status">
          {aviso}
        </div>
      )}

      <div className="filterbar">
        <div style={{ minWidth: 260 }}>
          <SelectorObra
            id="reprogramacion-obra"
            etiqueta="Obra"
            valor={obraId}
            onCambio={(id) => {
              setObraId(id);
              setAviso(null);
            }}
          />
        </div>
        {pendientes > 0 && (
          <div className="text-sm" style={{ alignSelf: 'flex-end' }} role="status">
            <span className="badge badge--warn">
              {pendientes} {pendientes === 1 ? 'espera tu paso' : 'esperan tu paso'}
            </span>
          </div>
        )}
      </div>

      {obraId === '' ? (
        <div className="empty">
          <div className="empty-title">Elige una obra</div>
          <div className="empty-sub">Las reprogramaciones son de las actividades de una obra.</div>
        </div>
      ) : consulta.isLoading ? (
        <div className="text-mute text-sm" style={{ padding: 24 }}>
          Cargando…
        </div>
      ) : filas.length === 0 ? (
        <div className="empty">
          <div className="empty-title">Sin reprogramaciones</div>
          <div className="empty-sub">
            Ninguna actividad asignada de esta obra ha movido su fecha.
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <div className="table-scroll">
            <table className="table" style={{ minWidth: 'max-content' }}>
              <thead>
                <tr>
                  <th style={{ minWidth: 260 }}>Actividad</th>
                  <th style={{ minWidth: 150 }}>Contratista</th>
                  <th style={{ minWidth: 200 }}>Inicio</th>
                  <th style={{ minWidth: 200 }}>Término</th>
                  <th style={{ minWidth: 240 }}>Motivo</th>
                  <th style={{ minWidth: 220 }}>Cadena</th>
                  <th className="cell-actions" style={{ minWidth: 240 }} />
                </tr>
              </thead>
              <tbody>
                {filas.map((f) => {
                  const acciones = accionesDeReprogramacion(rol, f.estatus);
                  const siguiente = quienSigue(f);
                  const observaciones = f.observaciones ?? [];
                  return (
                    <tr key={f.id}>
                      <td>
                        <span className="mono">{f.concepto_clave ?? '—'}</span>{' '}
                        {f.actividad ?? '—'}
                      </td>
                      <td>{f.contratista ?? '—'}</td>
                      <td className="tnum">
                        <Cambio antes={f.fecha_inicio_anterior} despues={f.fecha_inicio} />
                      </td>
                      <td className="tnum">
                        <Cambio antes={f.fecha_termino_anterior} despues={f.fecha_termino} />
                      </td>
                      <td className="text-sm">{f.motivo}</td>
                      <td>
                        <span
                          className={`badge badge--${tonoEstatusDeReprogramacion(f.estatus)}`}
                        >
                          {etiquetaEstatusDeReprogramacion(f.estatus)}
                        </span>
                        <ul className="text-mute text-xs" style={{ margin: '4px 0 0', padding: 0, listStyle: 'none' }}>
                          <li>
                            Propone: {f.propuesta_por_nombre ?? '—'} · {fmtFecha(f.propuesta_en)}
                          </li>
                          {f.revisada_por_nombre && <li>Revisa: {f.revisada_por_nombre}</li>}
                          {f.validada_por_nombre && <li>Valida: {f.validada_por_nombre}</li>}
                          {f.aplicada_por_nombre && (
                            <li>
                              Realiza: {f.aplicada_por_nombre}
                              {f.aplicada_en ? ` · ${fmtFecha(f.aplicada_en)}` : ''}
                            </li>
                          )}
                          {f.rechazada_por_nombre && (
                            <li>
                              Rechaza: {f.rechazada_por_nombre}
                              {f.motivo_rechazo ? ` — ${f.motivo_rechazo}` : ''}
                            </li>
                          )}
                        </ul>
                        {siguiente && <div className="text-mute text-xs">{siguiente}</div>}
                        {observaciones.length > 0 && (
                          <ul
                            className="text-xs"
                            aria-label="Observaciones"
                            style={{ margin: '6px 0 0', padding: 0, listStyle: 'none' }}
                          >
                            {observaciones.map((o) => (
                              <li key={o.id}>
                                <strong>{o.usuario_nombre ?? 'Control de obra'}</strong>
                                <span className="text-mute"> · {fmtFecha(o.creada_en)}</span>
                                <div>{o.texto}</div>
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td className="cell-actions">
                        <div className="row gap-4">
                          {acciones.includes('revisar') && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              disabled={ocupado}
                              onClick={() => revisar.mutate({ reprogramacionId: f.id })}
                            >
                              Revisar
                            </button>
                          )}
                          {acciones.includes('validar') && (
                            <button
                              type="button"
                              className="btn btn--accent btn--sm"
                              disabled={ocupado}
                              onClick={() => validar.mutate({ reprogramacionId: f.id })}
                            >
                              Validar
                            </button>
                          )}
                          {acciones.includes('aplicar') && (
                            <button
                              type="button"
                              className="btn btn--primary btn--sm"
                              disabled={ocupado}
                              onClick={() => aplicar.mutate({ reprogramacionId: f.id })}
                            >
                              Realizar
                            </button>
                          )}
                          {acciones.includes('rechazar') && (
                            <button
                              type="button"
                              className="btn btn--sm"
                              onClick={() => setRechazando(f)}
                            >
                              Rechazar
                            </button>
                          )}
                          {puedeObservar(rol) && (
                            <button
                              type="button"
                              className="btn btn--sm"
                              onClick={() => setObservando(f)}
                            >
                              Observar
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

      {observando && (
        <Modal
          titulo="Observación para el residente y el supervisor"
          onCerrar={() => {
            setObservando(null);
            setObservacion('');
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (observacion.trim() !== '') {
                observar.mutate({
                  reprogramacionId: observando.id,
                  data: { texto: observacion.trim() },
                });
              }
            }}
          >
            <div className="sheet__body col gap-12">
              <p className="text-sm">
                <span className="mono">{observando.concepto_clave}</span> {observando.actividad}
              </p>
              <p className="text-mute text-sm">
                No mueve la cadena ni la fecha: es una nota. Les llega al residente y al
                supervisor de la obra por correo y en la app.
              </p>
              <div className="field">
                <label className="field__label" htmlFor="reprogramacion-observacion">
                  Observación
                </label>
                <textarea
                  id="reprogramacion-observacion"
                  className="input"
                  rows={3}
                  value={observacion}
                  onChange={(e) => setObservacion(e.target.value)}
                />
              </div>
            </div>
            <div className="sheet__footer">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setObservando(null);
                  setObservacion('');
                }}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={observacion.trim() === '' || observar.isPending}
              >
                Enviar observación
              </button>
            </div>
          </form>
        </Modal>
      )}

      {rechazando && (
        <Modal
          titulo="Rechazar la reprogramación"
          onCerrar={() => {
            setRechazando(null);
            setMotivo('');
          }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (motivo.trim() !== '') {
                rechazar.mutate({
                  reprogramacionId: rechazando.id,
                  data: { motivo: motivo.trim() },
                });
              }
            }}
          >
            <div className="sheet__body col gap-12">
              <p className="text-sm">
                <span className="mono">{rechazando.concepto_clave}</span> {rechazando.actividad}
              </p>
              <p className="text-mute text-sm">
                La fecha no se mueve. Quien propuso ve el motivo y puede proponer otra.
              </p>
              <div className="field">
                <label className="field__label" htmlFor="reprogramacion-motivo-rechazo">
                  Motivo
                </label>
                <textarea
                  id="reprogramacion-motivo-rechazo"
                  className="input"
                  rows={3}
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                />
              </div>
            </div>
            <div className="sheet__footer">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setRechazando(null);
                  setMotivo('');
                }}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={motivo.trim() === '' || rechazar.isPending}
              >
                Rechazar
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}

/** «antes → después» cuando la fecha se mueve; solo la vigente cuando no se toca. */
function Cambio({
  antes,
  despues,
}: {
  readonly antes: string | null | undefined;
  readonly despues: string | null | undefined;
}) {
  if (!despues) return <span className="text-mute">{fmtFecha(antes)} · sin cambio</span>;
  return (
    <span>
      <span className="text-mute">{fmtFecha(antes)}</span> → <strong>{fmtFecha(despues)}</strong>
    </span>
  );
}
