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
 *
 * ## Por qué el renglón se abre
 *
 * Un frente entero es demasiado grueso para contratar: en la obra real OBRA
 * concentra el 90% de las jornadas, y nadie contrata "noventa por ciento de la
 * obra". Abierto se ve de qué oficios está hecho —albañilería, acabados,
 * estructura— y cada uno ya es algo que se le pide a alguien. La suma de los
 * oficios es el frente, así que las dos lecturas nunca se contradicen.
 */

import { ChevronDown, ChevronRight } from 'lucide-react';

import type {
  FrenteDeObraRespuesta,
  OficioDeFrenteRespuesta,
} from '@/api/generado/modelo';
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
  /** Frentes con el desglose por oficio abierto. */
  readonly abiertos?: ReadonlySet<string>;
  readonly onAlternar?: (frenteId: string) => void;
}

export function TablaFrentes({
  periodos,
  frentes,
  puedeAsignar,
  onAsignar,
  abiertos,
  onAlternar,
}: Props) {
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
            {frentes.map((frente) => {
              const clave = frente.frente_id || SIN_FRENTE_KEY;
              const oficios = frente.oficios ?? [];
              const abierto = abiertos?.has(clave) ?? false;
              return (
                <FilaFrente
                  key={clave}
                  frente={frente}
                  periodos={periodos}
                  puedeAsignar={puedeAsignar}
                  onAsignar={onAsignar}
                  oficios={oficios}
                  abierto={abierto}
                  onAlternar={onAlternar ? () => onAlternar(clave) : undefined}
                />
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const SIN_FRENTE_KEY = '__sin_frente__';

function FilaFrente({
  frente,
  periodos,
  puedeAsignar,
  onAsignar,
  oficios,
  abierto,
  onAlternar,
}: {
  readonly frente: FrenteDeObraRespuesta;
  readonly periodos: readonly PeriodoDePlaneacion[];
  readonly puedeAsignar: boolean;
  readonly onAsignar: (frente: FrenteDeObraRespuesta) => void;
  readonly oficios: readonly OficioDeFrenteRespuesta[];
  readonly abierto: boolean;
  readonly onAlternar?: () => void;
}) {
  const contratable = esContratable(frente.frente_id);
  const plan = frente.cuadrillas_plan ?? null;
  // Un solo oficio no es un desglose: abrirlo repetiría el renglón de arriba.
  const hayDesglose = oficios.length > 1 && onAlternar !== undefined;

  return (
    <>
    <tr>
      <td className="mono">
        {hayDesglose ? (
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            aria-expanded={abierto}
            aria-label={`Oficios de ${frente.frente_nombre}`}
            onClick={onAlternar}
          >
            {abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}{' '}
            {frente.frente_clave}
          </button>
        ) : (
          frente.frente_clave
        )}
      </td>
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
    {abierto &&
      oficios.map((oficio) => (
        <FilaOficio
          key={`${frente.frente_id}-${oficio.especialidad_id || 'sin'}`}
          oficio={oficio}
          periodos={periodos}
          puedeAsignar={puedeAsignar}
        />
      ))}
    </>
  );
}

function FilaOficio({
  oficio,
  periodos,
  puedeAsignar,
}: {
  readonly oficio: OficioDeFrenteRespuesta;
  readonly periodos: readonly PeriodoDePlaneacion[];
  readonly puedeAsignar: boolean;
}) {
  return (
    // Fondo del panel para que el desglose se lea como parte del renglón de
    // arriba y no como otro frente. Mismo recurso que el desglose de insumos.
    <tr style={{ background: 'var(--c-panel-2)' }}>
      <td className="mono text-mute" style={{ paddingLeft: 28 }}>
        {oficio.clave}
      </td>
      <td className="text-mute">{oficio.nombre}</td>
      <td />
      <td className="is-num text-mute">{fmtNum(oficio.pico_cuadrillas)}</td>
      <td />
      <td />
      {periodos.map((periodo, i) => {
        const cuadrillas = oficio.cuadrillas[i] ?? 0;
        const jornadas = oficio.jornadas[i] ?? 0;
        return (
          <td
            key={periodo.clave}
            className="is-num text-mute"
            title={
              jornadas > 0
                ? `${fmtNum(jornadas)} jornada(s) ÷ ${periodo.dias_habiles} día(s) hábil(es)`
                : undefined
            }
          >
            {cuadrillas > 0 ? fmtNum(cuadrillas) : <span className="text-mute">·</span>}
          </td>
        );
      })}
      <td className="is-num text-mute">{fmtNum(oficio.total_jornadas)}</td>
      {puedeAsignar && <td />}
    </tr>
  );
}
