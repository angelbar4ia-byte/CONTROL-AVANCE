/**
 * Evaluaciones — bandeja de los tres niveles (§6, §7.8, §11.3 workflow H).
 *
 * Pantalla compartida (§5.3): la misma ruta `/evaluaciones` que cada sidebar
 * etiqueta distinto —«Autoevaluación» (R), «Evaluaciones» (C), «Evaluaciones
 * finales» (SI)— (§5.1, `shell/navegacion.ts`). Lo que cambia por rol es el
 * nivel que puede crear (§11.3 H) y el alcance, que RLS ya resolvió (§12.4).
 *
 * El Supervisor no tiene entrada de evaluaciones en su sidebar y el workflow
 * H no le asigna nivel, así que ve la bandeja sin el botón de alta.
 */

import { useState } from 'react';

import { useListarEvaluacionesApiV1EvaluacionesGet } from '@/api/generado/evaluaciones/evaluaciones';
import {
  NivelEvaluacion,
  SujetoEvaluacion,
  type EvaluacionRespuesta,
} from '@/api/generado/modelo';
import { useSesion } from '@/app/sesion';
import { fmtNum } from '@/lib/formato';
import { AltaEvaluacion } from './AltaEvaluacion';
import { PanelEvaluacion } from './PanelEvaluacion';
import {
  descripcionNivel,
  etiquetaNivel,
  etiquetaSujeto,
  nivelDelRol,
  tonoNivel,
  tonoPuntaje,
} from './reglas';

const TITULO_POR_ROL: Record<string, string> = {
  residente: 'Autoevaluación',
  control_obra: 'Evaluaciones',
  super_intendente: 'Evaluaciones finales',
  supervisor: 'Evaluaciones',
};

export default function Evaluaciones() {
  const { sesion } = useSesion();
  const [nivel, setNivel] = useState<NivelEvaluacion | 'todos'>('todos');
  const [sujeto, setSujeto] = useState<SujetoEvaluacion | 'todos'>('todos');
  const [abriendoAlta, setAbriendoAlta] = useState(false);
  const [seleccionada, setSeleccionada] = useState<EvaluacionRespuesta | null>(null);

  const consulta = useListarEvaluacionesApiV1EvaluacionesGet({
    nivel: nivel === 'todos' ? undefined : nivel,
    sujeto_tipo: sujeto === 'todos' ? undefined : sujeto,
  });

  if (!sesion) return null;

  const nivelPropio = nivelDelRol(sesion.rol);
  const filas = consulta.data ?? [];

  // El contrato no publica `GET /evaluaciones/{id}`: tras responder se
  // recarga la bandeja y el cajón se recupera de la lista.
  const abierta =
    seleccionada === null ? null : (filas.find((e) => e.id === seleccionada.id) ?? seleccionada);

  return (
    <div className="page">
      <div className="page__header">
        <div className="page__titlewrap">
          <div className="page__eyebrow mono">Reportes</div>
          <h1 className="page__title">{TITULO_POR_ROL[sesion.rol] ?? 'Evaluaciones'}</h1>
          <div className="page__subtitle">
            Tres niveles (§11.3 H): auto (Residente) → control (Control de obra)
            → final (Super intendente). Sujetos: obra, residente y contratista,
            con criterios configurables por sujeto (§6).
          </div>
        </div>
        {nivelPropio !== null && (
          <div className="page__actions">
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setAbriendoAlta(true)}
            >
              Nueva {etiquetaNivel(nivelPropio).toLowerCase()}
            </button>
          </div>
        )}
      </div>

      {nivelPropio !== null && (
        <div className="field__hint mb-8">{descripcionNivel(nivelPropio)}</div>
      )}

      <div className="filterbar">
        <div className="tabs">
          <button
            type="button"
            className={`tabs__tab ${nivel === 'todos' ? 'is-active' : ''}`}
            onClick={() => setNivel('todos')}
          >
            Todos los niveles
          </button>
          {Object.values(NivelEvaluacion).map((n) => (
            <button
              key={n}
              type="button"
              className={`tabs__tab ${nivel === n ? 'is-active' : ''}`}
              onClick={() => setNivel(n)}
            >
              {etiquetaNivel(n)}
            </button>
          ))}
        </div>
        <div className="field" style={{ minWidth: 180 }}>
          <label className="field__label" htmlFor="evaluaciones-sujeto">
            Sujeto
          </label>
          <select
            id="evaluaciones-sujeto"
            className="select"
            value={sujeto}
            onChange={(e) => setSujeto(e.target.value as SujetoEvaluacion | 'todos')}
          >
            <option value="todos">Todos</option>
            {Object.values(SujetoEvaluacion).map((s) => (
              <option key={s} value={s}>
                {etiquetaSujeto(s)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="table-wrap">
        <div className="table-scroll">
          <table className="table">
            <thead>
              <tr>
                <th>Evaluación</th>
                <th>Nivel</th>
                <th>Sujeto</th>
                <th>Periodo</th>
                <th>Obra</th>
                <th className="is-num">Puntaje</th>
                <th className="is-num">Respuestas</th>
                <th className="cell-actions">Detalle</th>
              </tr>
            </thead>
            <tbody>
              {consulta.isLoading ? (
                <tr>
                  <td colSpan={8}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      Cargando…
                    </div>
                  </td>
                </tr>
              ) : filas.length === 0 ? (
                <tr>
                  <td colSpan={8}>
                    <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                      No hay evaluaciones en este filtro.
                    </div>
                  </td>
                </tr>
              ) : (
                filas.map((evaluacion) => (
                  <tr key={evaluacion.id}>
                    <td className="is-key" title={evaluacion.id}>
                      {evaluacion.id.slice(0, 8)}
                    </td>
                    <td>
                      <span className={`badge badge--${tonoNivel(evaluacion.nivel)}`}>
                        {etiquetaNivel(evaluacion.nivel)}
                      </span>
                    </td>
                    <td>
                      {etiquetaSujeto(evaluacion.sujeto_tipo)}
                      <span className="text-xs text-mute mono">
                        {' '}
                        {evaluacion.sujeto_id.slice(0, 8)}
                      </span>
                    </td>
                    <td className="mono">{evaluacion.periodo}</td>
                    <td className="is-key">{evaluacion.obra_id?.slice(0, 8) ?? '—'}</td>
                    <td className="is-num">
                      <span className={`badge badge--${tonoPuntaje(evaluacion.puntaje)}`}>
                        {fmtNum(evaluacion.puntaje)}
                      </span>
                    </td>
                    <td className="is-num">{evaluacion.respuestas?.length ?? 0}</td>
                    <td className="cell-actions">
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() => setSeleccionada(evaluacion)}
                      >
                        Abrir
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {abriendoAlta && nivelPropio !== null && (
        <AltaEvaluacion
          nivel={nivelPropio}
          usuarioId={sesion.usuarioId}
          onCerrar={() => setAbriendoAlta(false)}
          onCreada={() => {
            setAbriendoAlta(false);
            void consulta.refetch();
          }}
        />
      )}

      {abierta && (
        <PanelEvaluacion
          evaluacion={abierta}
          onCerrar={() => setSeleccionada(null)}
          onRespondida={() => void consulta.refetch()}
        />
      )}
    </div>
  );
}
