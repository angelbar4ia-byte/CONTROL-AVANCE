/**
 * Cajón de detalle y edición de la programación de una actividad
 * (drill-down del §12.10; §11.2 `PATCH /actividades/{id}/programacion`).
 *
 * Muestra lo que el motor CPM dejó en la actividad —fechas tempranas y
 * tardías, holgura, desfase y si está en la ruta crítica (§6)— y, para los
 * roles que el contrato autoriza (S, C), deja ajustar fechas, duración,
 * frente y dependencias. El recálculo de la ruta va en la misma transacción
 * del backend: aquí no se recalcula nada.
 *
 * Se espera que el padre lo remonte con `key={fila.actividadId}`.
 */

import { useState, type FormEvent } from 'react';

import {
  useEditarProgramacionActividadApiV1ActividadesActividadIdProgramacionPatch,
  useProponerReprogramacionApiV1ActividadesActividadIdReprogramacionesPost,
} from '@/api/generado/programacion/programacion';
import type { FrenteRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { useSesion } from '@/app/sesion';
import { colorAvance, fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { useClavesPorRecurso } from '@/lib/idempotencia';
import { Sheet } from '@/lib/Sheet';
import { esFechaDeLoContratado, puedeProponerReprogramacion } from '@/reprogramaciones/reglas';
import { EditorDependencias } from './Dependencias';
import type { FilaGantt } from './filas';
import {
  cambiosDeProgramacion,
  dependeDeSiMisma,
  formularioDeFila,
  hayCambios,
  refsDesconocidas,
  soloFechas,
} from './formulario';
import {
  type AlcanceDeEdicion,
  etiquetaEstatusActividad,
  etiquetaTipoDependencia,
  etiquetaTono,
  tonoBadgeDeBarra,
  tonoBarra,
} from './reglas';

interface Props {
  readonly fila: FilaGantt;
  /** Resto de actividades de la obra, para elegir predecesoras por nombre. */
  readonly actividades: readonly FilaGantt[];
  readonly frentes: readonly FrenteRespuesta[];
  /** `PATCH /actividades/{id}/programacion`: (S, C) todo, (R) solo fechas — 0067. */
  readonly alcance: AlcanceDeEdicion;
  readonly onCerrar: () => void;
  /** El padre revalida el cronograma tras un ajuste. */
  readonly onAjustada: () => void;
}

export function PanelActividad({
  fila,
  actividades,
  frentes,
  alcance,
  onCerrar,
  onAjustada,
}: Props) {
  const [formulario, setFormulario] = useState(() => formularioDeFila(fila));
  const { sesion } = useSesion();
  const idempotente = useClavesPorRecurso();
  const [error, setError] = useState<{ mensaje: string; campo?: string; tipo?: string } | null>(
    null,
  );
  const [guardada, setGuardada] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [propuesta, setPropuesta] = useState(false);

  const ajustar = useEditarProgramacionActividadApiV1ActividadesActividadIdProgramacionPatch<
    ErrorApi
  >({
    mutation: {
      onSuccess: () => {
        setError(null);
        setGuardada(true);
        onAjustada();
      },
      onError: (err) => {
        setGuardada(false);
        setError({ mensaje: err.message, campo: err.campo, tipo: err.tipo });
      },
    },
  });

  // P-4: las fechas de lo contratado no se editan directo; se propone la nueva.
  const proponer = useProponerReprogramacionApiV1ActividadesActividadIdReprogramacionesPost<
    ErrorApi
  >({
    mutation: {
      onSuccess: () => {
        setError(null);
        setPropuesta(true);
        setMotivo('');
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo, tipo: err.tipo }),
    },
    ...idempotente,
  });

  const tono = tonoBarra(fila);
  const soloLasFechas = alcance === 'fechas';
  const cambios = soloLasFechas
    ? soloFechas(cambiosDeProgramacion(fila, formulario))
    : cambiosDeProgramacion(fila, formulario);
  const conocidas = new Set(actividades.map((otra) => otra.actividadId));
  const sueltas = refsDesconocidas(formulario.dependencias, conocidas);
  const autoreferencia = dependeDeSiMisma(fila.actividadId, formulario.dependencias);
  const avance = fila.avancePct;

  const opcionesPredecesoras = actividades
    .filter((otra) => otra.actividadId !== fila.actividadId)
    .map((otra) => ({ valor: otra.actividadId, etiqueta: otra.descripcion }));

  const contratada = esFechaDeLoContratado(error);
  const rol = sesion?.rol ?? null;

  function alProponer(evento: FormEvent) {
    evento.preventDefault();
    if (motivo.trim() === '' || proponer.isPending) return;
    proponer.mutate({
      actividadId: fila.actividadId,
      data: {
        motivo: motivo.trim(),
        fecha_inicio: cambios.fecha_inicio ?? null,
        fecha_termino: cambios.fecha_termino ?? null,
      },
    });
  }

  function alGuardar(evento: FormEvent) {
    evento.preventDefault();
    if (alcance === 'lectura' || autoreferencia || !hayCambios(cambios) || ajustar.isPending) return;
    ajustar.mutate({ actividadId: fila.actividadId, data: cambios });
  }

  return (
    <Sheet titulo={fila.descripcion} subtitulo={fila.actividadId} onCerrar={onCerrar}>
      <div className="sheet__body col gap-16">
        <div className="row gap-4" style={{ flexWrap: 'wrap' }}>
          <span className={`badge badge--${tonoBadgeDeBarra(tono)}`}>{etiquetaTono(tono)}</span>
          {fila.estatus !== null && (
            <span className="badge badge--outline">
              {etiquetaEstatusActividad(fila.estatus)}
            </span>
          )}
          {fila.bloqueada && (
            <span className="badge badge--danger">Bloqueada por incidencia</span>
          )}
        </div>

        <div>
          <div
            className={`bar ${colorAvance(avance) !== 'accent' ? `bar--${colorAvance(avance)}` : ''}`}
          >
            <div
              className="bar__fill"
              style={{ width: `${Math.min(100, Math.max(0, avance))}%` }}
            />
          </div>
          <div className="text-mute text-xs mono tnum mt-8">Avance {fmtPct(avance)}</div>
        </div>

        <div className="card">
          <div className="card__header">
            <div>
              <h3 className="card__title">Cálculo del motor</h3>
              <div className="card__sub">
                Lo determina el CPM del backend sobre el cronograma (§6); aquí solo se
                muestra.
              </div>
            </div>
          </div>
          <div className="card__body">
            <dl className="col gap-4" style={{ margin: 0 }}>
              <Dato etiqueta="Inicio temprano" valor={fmtFecha(fila.inicio)} />
              <Dato etiqueta="Fin temprano" valor={fmtFecha(fila.fin)} />
              <Dato etiqueta="Inicio tardío" valor={fmtFecha(fila.inicioTardio)} />
              <Dato etiqueta="Fin tardío" valor={fmtFecha(fila.finTardio)} />
              <Dato etiqueta="Duración (días)" valor={fmtNum(fila.duracionDias)} />
              <Dato etiqueta="Holgura (días)" valor={fmtNum(fila.holguraDias)} />
              <Dato etiqueta="Desfase (días)" valor={fmtNum(fila.desfaseDias)} />
              <Dato etiqueta="En ruta crítica" valor={fila.esCritica ? 'Sí' : 'No'} />
            </dl>
          </div>
        </div>

        {error && !contratada && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}

        {contratada && (
          <div className="card" role="alert">
            <div className="card__header">
              <div>
                <h3 className="card__title">Esta actividad está contratada</h3>
                <div className="card__sub">{error?.mensaje}</div>
              </div>
            </div>
            <form onSubmit={alProponer} className="card__body col gap-12">
              {puedeProponerReprogramacion(rol) ? (
                <>
                  <div className="field">
                    <label className="field__label" htmlFor="prog-motivo-reprogramacion">
                      Motivo de la reprogramación
                    </label>
                    <textarea
                      id="prog-motivo-reprogramacion"
                      className="input"
                      rows={2}
                      value={motivo}
                      onChange={(e) => setMotivo(e.target.value)}
                    />
                    <span className="field__hint">
                      Se propone con las fechas del formulario. La fecha no cambia hasta que
                      control de obra la valide y la realice.
                    </span>
                  </div>
                  <div className="row">
                    <button
                      type="submit"
                      className="btn btn--primary"
                      disabled={motivo.trim() === '' || proponer.isPending}
                    >
                      {proponer.isPending ? 'Proponiendo…' : 'Proponer reprogramación'}
                    </button>
                  </div>
                </>
              ) : (
                <div className="text-sm">
                  La reprogramación la propone el residente o el supervisor; tú la validas y la
                  realizas desde <strong>Reprogramaciones</strong>.
                </div>
              )}
            </form>
          </div>
        )}

        {propuesta && (
          <div role="status">
            <span className="badge badge--ok">
              Reprogramación propuesta · la fecha cambia cuando control de obra la realice
            </span>
          </div>
        )}

        {guardada && !ajustar.isPending && error === null && (
          <div role="status">
            <span className="badge badge--ok">Programación ajustada · ruta recalculada</span>
          </div>
        )}

        {alcance !== 'lectura' ? (
          <form onSubmit={alGuardar} className="card">
            <div className="card__header">
              <div>
                <h3 className="card__title">
                  {soloLasFechas ? 'Ajustar fechas' : 'Ajustar programación'}
                </h3>
                <div className="card__sub">
                  {soloLasFechas
                    ? 'Puedes corregir cuándo arrancó y cuándo terminó la partida. La duración, los vínculos y el frente los edita Control de obra. Queda registrado quién lo cambió.'
                    : 'Solo se envía lo que cambió. Dejar la lista de dependencias vacía deja la actividad sin predecesoras (§11.2). Queda registrado quién lo cambió.'}
                </div>
              </div>
            </div>
            <div className="card__body col gap-12">
              <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
                <div className="field" style={{ flex: 1, minWidth: 140 }}>
                  <label className="field__label" htmlFor="prog-inicio">
                    Inicio
                  </label>
                  <input
                    id="prog-inicio"
                    className="input"
                    type="date"
                    value={formulario.fechaInicio}
                    onChange={(e) =>
                      setFormulario((f) => ({ ...f, fechaInicio: e.target.value }))
                    }
                  />
                </div>
                <div className="field" style={{ flex: 1, minWidth: 140 }}>
                  <label className="field__label" htmlFor="prog-termino">
                    Término
                  </label>
                  <input
                    id="prog-termino"
                    className="input"
                    type="date"
                    value={formulario.fechaTermino}
                    onChange={(e) =>
                      setFormulario((f) => ({ ...f, fechaTermino: e.target.value }))
                    }
                  />
                </div>
                {!soloLasFechas && (
                  <div className="field" style={{ flex: 1, minWidth: 120 }}>
                    <label className="field__label" htmlFor="prog-duracion">
                      Duración (días)
                    </label>
                    <input
                      id="prog-duracion"
                      className="input input--mono"
                      type="number"
                      step="any"
                      min="0"
                      value={formulario.duracionDias}
                      onChange={(e) =>
                        setFormulario((f) => ({ ...f, duracionDias: e.target.value }))
                      }
                    />
                  </div>
                )}
              </div>

              {!soloLasFechas && (
              <div className="field">
                <label className="field__label" htmlFor="prog-frente">
                  Frente
                </label>
                <select
                  id="prog-frente"
                  className="select"
                  value={formulario.frenteId}
                  onChange={(e) => setFormulario((f) => ({ ...f, frenteId: e.target.value }))}
                >
                  <option value="">Sin frente</option>
                  {frentes.map((frente) => (
                    <option key={frente.id} value={frente.id}>
                      {frente.clave} · {frente.nombre}
                    </option>
                  ))}
                </select>
              </div>
              )}

              {!soloLasFechas && (
              <div className="col gap-4">
                <EditorDependencias
                  idBase="prog"
                  dependencias={formulario.dependencias}
                  onCambio={(dependencias) =>
                    setFormulario((f) => ({ ...f, dependencias }))
                  }
                  opciones={opcionesPredecesoras}
                  vacio="Sin predecesoras: la actividad puede arrancar el primer día del programa."
                />

                {autoreferencia && (
                  <div className="field__hint" style={{ color: 'var(--c-danger)' }}>
                    Una actividad no puede ser su propia predecesora: el motor lo rechaza como
                    ciclo (§6).
                  </div>
                )}

                {sueltas.length > 0 && !autoreferencia && (
                  <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
                    {sueltas.length} dependencia(s) apuntan a actividades que no están en este
                    cronograma; el motor las ignora al recalcular (§6).
                  </div>
                )}
              </div>
              )}

              <div className="row">
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={autoreferencia || !hayCambios(cambios) || ajustar.isPending}
                >
                  {ajustar.isPending ? 'Recalculando…' : 'Guardar y recalcular'}
                </button>
              </div>
            </div>
          </form>
        ) : (
          <div className="card">
            <div className="card__header">
              <h3 className="card__title">Dependencias</h3>
            </div>
            <div className="card__body col gap-4">
              {fila.dependencias.length === 0 ? (
                <div className="text-mute text-sm">Sin predecesoras.</div>
              ) : (
                fila.dependencias.map((dependencia) => (
                  <div key={dependencia.ref} className="text-sm">
                    <span className="mono">
                      {actividades.find((otra) => otra.actividadId === dependencia.ref)
                        ?.descripcion ?? dependencia.ref}
                    </span>{' '}
                    <span className="text-mute">
                      · {etiquetaTipoDependencia(dependencia.tipo)}
                      {(dependencia.lag_dias ?? 0) !== 0 &&
                        ` · lag ${fmtNum(dependencia.lag_dias)} d`}
                    </span>
                  </div>
                ))
              )}
              <div className="field__hint">
                Ajustar la programación es de Control de obra y Supervisor (§11.2); las
                fechas, también del Residente.
              </div>
            </div>
          </div>
        )}
      </div>
    </Sheet>
  );
}

function Dato({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  return (
    <div className="row" style={{ justifyContent: 'space-between', gap: 12 }}>
      <dt className="text-mute text-sm">{etiqueta}</dt>
      <dd className="text-sm mono tnum" style={{ margin: 0, textAlign: 'right' }}>
        {valor}
      </dd>
    </div>
  );
}
