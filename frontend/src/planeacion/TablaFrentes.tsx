/**
 * La matriz frente × periodo: cuántas cuadrillas pide cada frente (§8.3).
 *
 * Componente de presentación: recibe la demanda ya calculada y no decide nada
 * salvo cómo se ve (§12.11). La división vive en
 * `domain/planeacion/cuadrillas.py`.
 *
 * ## Por qué se enseñan cuadrillas y jornadas a la vez
 *
 * La cuadrilla es con lo que se contrata —"mándame tres"— y la jornada es de
 * dónde salió. Cuando una celda sorprende, el `title` trae las jornadas: sin
 * eso, un 2.3 en una semana corta y un 2.3 en una completa se leen igual y no
 * son lo mismo.
 *
 * ## Por qué no se redondea
 *
 * 2.3 cuadrillas significa que dos aprietan y tres sobran. Redondear aquí
 * escondería esa lectura justo donde se decide, así que se enseñan los dos
 * decimales que el dominio devuelve y quien contrata resuelve.
 */

import type { FrenteDeObraRespuesta } from '@/api/generado/modelo';
import { fmtNum } from '@/lib/formato';
import { claseDeCobertura, cobertura, esContratable, textoDeCobertura } from './reglas';

/** Ancho fijo por columna de periodo, como la rejilla del programa base. */
const ANCHO_PERIODO = 84;

export interface PeriodoDePlaneacion {
  readonly clave: string;
  readonly desde: string;
  readonly hasta: string;
  readonly etiqueta: string;
  readonly dias_habiles: number;
}

interface Props {
  readonly periodos: readonly PeriodoDePlaneacion[];
  readonly frentes: readonly FrenteDeObraRespuesta[];
  /** El rol planifica: con `false` la columna de contratar no se dibuja. */
  readonly puedeAsignar: boolean;
  readonly onAsignar: (frente: FrenteDeObraRespuesta) => void;
}

export function TablaFrentes({ periodos, frentes, puedeAsignar, onAsignar }: Props) {
  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table" style={{ minWidth: 'max-content' }}>
          <thead>
            <tr>
              <th style={{ minWidth: 90 }}>Frente</th>
              <th style={{ minWidth: 200 }}>Nombre</th>
              <th style={{ minWidth: 190 }}>Contratista</th>
              <th
                className="is-num"
                style={{ minWidth: 90 }}
                title="La semana más cargada. Es la cifra con la que se contrata."
              >
                Pico
              </th>
              <th
                className="is-num"
                style={{ minWidth: 90 }}
                title="Lo que se decidió, al lado de lo que el cálculo sugiere."
              >
                Planeadas
              </th>
              <th style={{ minWidth: 110 }}>Cobertura</th>
              {periodos.map((periodo) => (
                <th
                  key={periodo.clave}
                  className="is-num"
                  style={{ width: ANCHO_PERIODO, minWidth: ANCHO_PERIODO }}
                  title={`${periodo.desde} → ${periodo.hasta} · ${periodo.dias_habiles} día(s) hábil(es)`}
                >
                  {periodo.etiqueta}
                </th>
              ))}
              <th className="is-num" style={{ minWidth: 110 }}>
                Jornadas
              </th>
              {puedeAsignar && <th style={{ minWidth: 110 }} />}
            </tr>
          </thead>
          <tbody>
            {frentes.map((frente) => (
              <FilaFrente
                key={frente.frente_id || '__sin_frente__'}
                frente={frente}
                periodos={periodos}
                puedeAsignar={puedeAsignar}
                onAsignar={onAsignar}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilaFrente({
  frente,
  periodos,
  puedeAsignar,
  onAsignar,
}: {
  readonly frente: FrenteDeObraRespuesta;
  readonly periodos: readonly PeriodoDePlaneacion[];
  readonly puedeAsignar: boolean;
  readonly onAsignar: (frente: FrenteDeObraRespuesta) => void;
}) {
  const contratable = esContratable(frente.frente_id);
  const plan = frente.cuadrillas_plan ?? null;

  return (
    <tr>
      <td className="mono">{frente.frente_clave}</td>
      <td>
        {frente.frente_nombre}
        {!contratable && (
          <div className="field__hint">
            Etapas sin frente. Se mapean en <strong>Frentes de obra</strong>.
          </div>
        )}
      </td>
      <td>
        {frente.contratista_nombre ?? (
          <span className="text-mute">{contratable ? '—' : ''}</span>
        )}
      </td>
      <td className="is-num">{fmtNum(frente.pico_cuadrillas)}</td>
      <td className="is-num">
        {plan === null ? <span className="text-mute">—</span> : plan}
      </td>
      <td>
        {contratable && (
          <span className={claseDeCobertura(cobertura(frente.pico_cuadrillas, plan))}>
            {textoDeCobertura(frente.pico_cuadrillas, plan)}
          </span>
        )}
      </td>
      {periodos.map((periodo, i) => {
        const cuadrillas = frente.cuadrillas[i] ?? 0;
        const jornadas = frente.jornadas[i] ?? 0;
        return (
          <td
            key={periodo.clave}
            className="is-num"
            title={
              jornadas > 0
                ? `${fmtNum(jornadas)} jornada(s) ÷ ${periodo.dias_habiles} día(s) hábil(es)`
                : undefined
            }
          >
            {cuadrillas > 0 ? (
              fmtNum(cuadrillas)
            ) : (
              <span className="text-mute">·</span>
            )}
          </td>
        );
      })}
      <td className="is-num">{fmtNum(frente.total_jornadas)}</td>
      {puedeAsignar && (
        <td>
          {contratable && (
            <button
              type="button"
              className="btn btn--sm"
              onClick={() => onAsignar(frente)}
            >
              {frente.contratista_id ? 'Cambiar' : 'Asignar'}
            </button>
          )}
        </td>
      )}
    </tr>
  );
}
