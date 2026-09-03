/**
 * Detalle de una incidencia y sus acciones del workflow F (§11.3 F, §7.8).
 *
 * Patrón de drill-down del sistema de diseño: la bandeja se queda a la
 * izquierda y el detalle abre en el cajón derecho (DESIGN_SYSTEM.md §5.4).
 *
 * ## Limitación conocida: historial de eventos
 *
 * `IncidenciaEvento` existe en el modelo (§7.8) y la tabla está en la
 * migración 0009, pero el contrato **no publica ninguna lectura**: no hay
 * `GET /incidencias/{id}` ni `GET /incidencias/{id}/eventos`, y
 * `IncidenciaRespuesta` no trae los eventos. Tampoco se puede leer directo
 * de Supabase: `incidencia_evento` es dato operativo, no catálogo, y la
 * ruta directa del §10.7 está reservada a catálogos (la lista blanca de
 * `lib/supabase.ts` no lo incluye).
 *
 * Por eso lo que se muestra aquí como historial es el **avance por la
 * escalera del workflow F** derivado del `estatus` vigente —dónde está la
 * incidencia y qué pasos ya quedaron atrás—, y la escritura de eventos sí
 * funciona (`POST /incidencias/{id}/eventos`). Cuando el backend publique la
 * lectura de `IncidenciaEvento`, este bloque debe cambiarse por la lista real
 * de `fecha · usuario · acción · comentario`.
 */

import { useState } from 'react';

import {
  useCerrarIncidenciaApiV1IncidenciasIncidenciaIdCerrarPost,
  useProgramarIncidenciaApiV1IncidenciasIncidenciaIdPatch,
  useRechazarIncidenciaApiV1IncidenciasIncidenciaIdRechazarPost,
  useRegistrarEventoIncidenciaApiV1IncidenciasIncidenciaIdEventosPost,
} from '@/api/generado/incidencias/incidencias';
import type { IncidenciaRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { fmtFecha } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import {
  ESTATUS_DE_ACCION,
  accionesDisponiblesIncidencia,
  descripcionImpacto,
  detieneObra,
  estaRechazada,
  etapasFlujoF,
  etiquetaEstatus,
  etiquetaImpacto,
  etiquetaTipo,
  tonoEstatusIncidencia,
  tonoImpacto,
} from './reglas';

interface Props {
  readonly incidencia: IncidenciaRespuesta;
  readonly onCerrar: () => void;
  readonly onCambio: () => void;
}

export function PanelIncidencia({ incidencia, onCerrar, onCambio }: Props) {
  const { sesion } = useSesion();
  const [asignadaA, setAsignadaA] = useState('');
  const [comentario, setComentario] = useState('');
  const [motivo, setMotivo] = useState('');
  const [error, setError] = useState<string | null>(null);

  const manejo = {
    onSuccess: () => {
      setError(null);
      setComentario('');
      setMotivo('');
      setAsignadaA('');
      onCambio();
    },
    onError: (err: ErrorApi) => setError(err.message),
  };

  const programar = useProgramarIncidenciaApiV1IncidenciasIncidenciaIdPatch<ErrorApi>({
    mutation: manejo,
  });
  const registrarEvento =
    useRegistrarEventoIncidenciaApiV1IncidenciasIncidenciaIdEventosPost<ErrorApi>({
      mutation: manejo,
    });
  const cerrar = useCerrarIncidenciaApiV1IncidenciasIncidenciaIdCerrarPost<ErrorApi>({
    mutation: manejo,
  });
  const rechazar = useRechazarIncidenciaApiV1IncidenciasIncidenciaIdRechazarPost<ErrorApi>({
    mutation: manejo,
  });

  if (!sesion) return null;

  const acciones = accionesDisponiblesIncidencia(sesion.rol, incidencia.estatus);
  const detiene = detieneObra(incidencia.impacto);
  const rechazada = estaRechazada(incidencia.estatus);
  const etapas = etapasFlujoF(incidencia.estatus);
  const trabajando =
    programar.isPending || registrarEvento.isPending || cerrar.isPending || rechazar.isPending;

  return (
    <Sheet
      titulo={incidencia.titulo}
      subtitulo={`${incidencia.id.slice(0, 8)} · ${etiquetaTipo(incidencia.tipo)}`}
      onCerrar={onCerrar}
    >
      <div className="sheet__body col gap-16">
        {error && <ErrorBanner mensaje={error} />}

        {detiene && (
          <div
            className="text-sm"
            role="alert"
            style={{
              color: 'var(--c-danger)',
              background: 'var(--c-danger-soft)',
              border: '1px solid var(--c-danger)',
              borderRadius: 'var(--r-md)',
              padding: '8px 12px',
            }}
          >
            <strong>Impacto «detiene»: frena la obra.</strong> {descripcionImpacto('detiene')}
            {incidencia.bloquea_actividades.length > 0 && (
              <div className="text-xs mt-8">
                {incidencia.bloquea_actividades.length} actividad(es) bloqueada(s):{' '}
                <span className="mono">
                  {incidencia.bloquea_claves && incidencia.bloquea_claves.length > 0
                    ? incidencia.bloquea_claves.join(' · ')
                    : incidencia.bloquea_actividades.map((id) => id.slice(0, 8)).join(' · ')}
                </span>
              </div>
            )}
          </div>
        )}

        <div className="row gap-12">
          <span className={`badge badge--${tonoEstatusIncidencia(incidencia.estatus)}`}>
            {etiquetaEstatus(incidencia.estatus)}
          </span>
          <span className={`badge badge--${tonoImpacto(incidencia.impacto)}`}>
            Impacto: {etiquetaImpacto(incidencia.impacto)}
          </span>
        </div>

        {incidencia.descripcion && <p className="text-sm text-soft">{incidencia.descripcion}</p>}

        <div className="card">
          <div className="card__header">
            <div className="card__title">Flujo</div>
            <div className="card__sub">Workflow F (§11.3)</div>
          </div>
          <div className="card__body col gap-4">
            {rechazada ? (
              <div className="badge badge--danger">
                Rechazada — salió del flujo (§11.3 F.4)
              </div>
            ) : (
              <ol className="col gap-4" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {etapas.map((etapa) => (
                  <li key={etapa.estatus} className="row gap-12">
                    <span
                      aria-hidden="true"
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: etapa.alcanzada ? 'var(--c-accent)' : 'var(--c-line-strong)',
                        flex: '0 0 auto',
                      }}
                    />
                    <span
                      className={etapa.actual ? 'text-sm' : 'text-sm text-mute'}
                      style={etapa.actual ? { fontWeight: 600 } : undefined}
                    >
                      {etapa.etiqueta}
                      {etapa.actual && <span className="text-xs text-mute"> · aquí</span>}
                    </span>
                  </li>
                ))}
              </ol>
            )}
            <div className="field__hint mt-8">
              El contrato todavía no publica la lectura de <code>IncidenciaEvento</code>{' '}
              (§7.8): esto refleja el estatus vigente, no la bitácora de
              <code> fecha · usuario · acción · comentario</code>.
            </div>
          </div>
        </div>

        <dl className="col gap-4 text-sm" style={{ margin: 0 }}>
          <Dato
            etiqueta="Obra"
            valor={incidencia.obra_clave ?? incidencia.obra_id.slice(0, 8)}
            mono={!incidencia.obra_clave}
          />
          <Dato
            etiqueta="Frente"
            valor={
              incidencia.nivel_descripcion
                ? `${incidencia.nivel_clave} · ${incidencia.nivel_descripcion}`
                : '—'
            }
          />
          <Dato
            etiqueta="Sub-frente"
            valor={
              incidencia.etapa_descripcion
                ? `${incidencia.etapa_clave} · ${incidencia.etapa_descripcion}`
                : '—'
            }
          />
          <Dato
            etiqueta="A quién se le compra"
            valor={incidencia.frente_id?.slice(0, 8) ?? '—'}
            mono
          />
          <Dato etiqueta="Creada por" valor={incidencia.creada_por?.slice(0, 8) ?? '—'} mono />
          <Dato etiqueta="Asignada a" valor={incidencia.asignada_a?.slice(0, 8) ?? '—'} mono />
          <Dato etiqueta="Fecha límite" valor={fmtFecha(incidencia.fecha_limite)} />
          <Dato etiqueta="Evidencias" valor={String(incidencia.evidencias.length)} mono />
        </dl>

        {acciones.includes('programar') && (
          <div className="field">
            <label className="field__label" htmlFor="incidencia-asignada">
              Programar: asignar a (id de usuario)
            </label>
            <input
              id="incidencia-asignada"
              className="input input--mono"
              placeholder="uuid del usuario"
              value={asignadaA}
              onChange={(e) => setAsignadaA(e.target.value)}
            />
            <div className="field__hint">
              El contrato no expone <code>GET /usuarios</code>, así que el id se captura a
              mano; cuando exista, este campo debe volverse un selector.
            </div>
          </div>
        )}

        {(acciones.includes('atender') ||
          acciones.includes('solicitar_cierre') ||
          acciones.includes('cerrar')) && (
          <div className="field">
            <label className="field__label" htmlFor="incidencia-comentario">
              Comentario (opcional)
            </label>
            <textarea
              id="incidencia-comentario"
              className="textarea"
              value={comentario}
              onChange={(e) => setComentario(e.target.value)}
            />
          </div>
        )}

        {acciones.includes('rechazar') && (
          <div className="field">
            <label className="field__label" htmlFor="incidencia-motivo">
              Motivo de rechazo (obligatorio para rechazar)
            </label>
            <textarea
              id="incidencia-motivo"
              className="textarea"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
            />
          </div>
        )}
      </div>

      <div className="sheet__footer">
        {acciones.length === 0 && (
          <span className="text-mute text-sm">
            Tu rol no tiene acciones pendientes sobre esta incidencia (§4, §11.2).
          </span>
        )}

        {acciones.includes('programar') && (
          <button
            type="button"
            className="btn btn--accent"
            disabled={trabajando || asignadaA.trim() === ''}
            onClick={() =>
              programar.mutate({
                incidenciaId: incidencia.id,
                data: { asignada_a: asignadaA.trim() },
              })
            }
          >
            Programar
          </button>
        )}

        {acciones.includes('atender') && (
          <button
            type="button"
            className="btn btn--accent"
            disabled={trabajando}
            onClick={() =>
              registrarEvento.mutate({
                incidenciaId: incidencia.id,
                data: {
                  accion: 'atender',
                  estatus_nuevo: ESTATUS_DE_ACCION.atender,
                  comentario: comentario.trim() === '' ? undefined : comentario,
                },
              })
            }
          >
            Atender
          </button>
        )}

        {acciones.includes('solicitar_cierre') && (
          <button
            type="button"
            className="btn btn--accent"
            disabled={trabajando}
            onClick={() =>
              registrarEvento.mutate({
                incidenciaId: incidencia.id,
                data: {
                  accion: 'solicitar_cierre',
                  estatus_nuevo: ESTATUS_DE_ACCION.solicitar_cierre,
                  comentario: comentario.trim() === '' ? undefined : comentario,
                },
              })
            }
          >
            Solicitar cierre
          </button>
        )}

        {acciones.includes('cerrar') && (
          <button
            type="button"
            className="btn btn--primary"
            disabled={trabajando}
            onClick={() =>
              cerrar.mutate({
                incidenciaId: incidencia.id,
                data: { comentario: comentario.trim() === '' ? undefined : comentario },
              })
            }
          >
            Cerrar
          </button>
        )}

        {acciones.includes('rechazar') && (
          <button
            type="button"
            className="btn btn--danger"
            disabled={trabajando || motivo.trim() === ''}
            onClick={() =>
              rechazar.mutate({ incidenciaId: incidencia.id, data: { motivo: motivo.trim() } })
            }
          >
            Rechazar
          </button>
        )}
      </div>
    </Sheet>
  );
}

function Dato({
  etiqueta,
  valor,
  mono = false,
}: {
  readonly etiqueta: string;
  readonly valor: string;
  readonly mono?: boolean;
}) {
  return (
    <div className="row gap-12">
      <dt className="text-mute" style={{ minWidth: 110 }}>
        {etiqueta}
      </dt>
      <dd className={mono ? 'mono' : ''} style={{ margin: 0 }}>
        {valor}
      </dd>
    </div>
  );
}
