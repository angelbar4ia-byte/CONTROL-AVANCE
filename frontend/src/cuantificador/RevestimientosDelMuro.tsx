/**
 * Los revestimientos de un muro (D-645, tanda 2): cada uno es **un concepto del catálogo, como un CPU** (con su precio y su
 * receta; por ejemplo Galarza), no una capa Sí/No. Se elige el concepto, la cara (interior o fachada) y la altura; luego se
 * dibuja el largo sobre el muro y la línea mide largo × altura en m². Aquí se listan los del muro y se agregan o quitan.
 */

import { useMemo, useState } from 'react';

import type { ActividadRespuesta, TrazoFeature } from '@/api/generado/modelo';
import { fmtNum } from '@/lib/formato';

import { CampoDecimal } from './CampoDecimal';
import { tipoDeMedicion } from './tipos';

export type CaraDeRevestimiento = 'interior' | 'fachada';

export interface RevestimientoPorColocar {
  readonly muroId: string;
  readonly actividadId: string;
  readonly clave: string;
  readonly cara: CaraDeRevestimiento;
  readonly alturaM: number;
}

const ALTURA_POR_DEFECTO_M = 2.6;
const NOMBRE_DE_CARA: Record<CaraDeRevestimiento, string> = { interior: 'Interior', fachada: 'Fachada' };

interface Props {
  readonly muroId: string;
  readonly trazos: readonly TrazoFeature[];
  readonly actividades: readonly ActividadRespuesta[];
  /** Hay un revestimiento esperando su largo (modo dibujar) y de qué muro es. */
  readonly colocando: RevestimientoPorColocar | null;
  readonly onColocar: (r: RevestimientoPorColocar | null) => void;
  readonly onQuitar: (trazoId: string) => void;
}

export function RevestimientosDelMuro({ muroId, trazos, actividades, colocando, onColocar, onQuitar }: Props) {
  const [abierto, setAbierto] = useState(false);
  const [actividadId, setActividadId] = useState('');
  const [cara, setCara] = useState<CaraDeRevestimiento>('fachada');
  const [altura, setAltura] = useState(ALTURA_POR_DEFECTO_M);

  // Un revestimiento se mide en m²: los conceptos de la obra que se miden por área.
  const candidatos = useMemo(
    () => actividades.filter((a) => a.concepto_id && tipoDeMedicion(a.unidad) === 'area'),
    [actividades],
  );
  const claveDe = (id: string | null | undefined) => actividades.find((a) => a.id === id)?.concepto_clave ?? 'concepto';
  const propios = trazos.filter((t) => t.properties.revestimiento_de === muroId);
  const elegida = candidatos.find((a) => a.id === actividadId);
  const listo = elegida !== undefined && altura > 0;
  const esteMuro = colocando?.muroId === muroId ? colocando : null;

  return (
    <div className="revestimientos-muro" role="group" aria-label="Revestimientos del muro">
      <div className="opciones__titulo">Revestimientos</div>
      {propios.length === 0 ? (
        <p className="text-mute text-xs">Sin revestimientos. Cada uno es un concepto del catálogo, con su largo y su altura.</p>
      ) : (
        <ul className="revestimientos-muro__lista">
          {propios.map((t) => {
            const enlace = t.properties.enlaces.find((e) => e.vigente);
            return (
              <li key={t.id as string} data-revestimiento={claveDe(enlace?.nodo_id)}>
                <span>
                  <b className="mono">{claveDe(enlace?.nodo_id)}</b> · {NOMBRE_DE_CARA[(t.properties.revestimiento_cara ?? 'fachada') as CaraDeRevestimiento]}
                </span>
                <span className="mono">{enlace ? `${fmtNum(enlace.cantidad)} m²` : '—'}</span>
                <button type="button" className="btn btn--ghost btn--sm" aria-label={`Quitar el revestimiento ${claveDe(enlace?.nodo_id)}`} onClick={() => onQuitar(t.id as string)}>
                  Quitar
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {esteMuro ? (
        <div className="revestimientos-muro__colocando" role="status">
          Dibuja el largo de <b>{esteMuro.clave}</b> ({NOMBRE_DE_CARA[esteMuro.cara].toLowerCase()}, {esteMuro.alturaM} m de alto) sobre el muro: dos clics.{' '}
          <button type="button" className="btn btn--ghost btn--sm" onClick={() => onColocar(null)}>
            Cancelar
          </button>
        </div>
      ) : !abierto ? (
        <button type="button" className="btn btn--sm" onClick={() => setAbierto(true)}>
          + Revestimiento
        </button>
      ) : (
        <div className="revestimientos-muro__alta" role="group" aria-label="Revestimiento nuevo">
          <label className="text-xs">
            Concepto del catálogo
            <select aria-label="Concepto del revestimiento" value={actividadId} onChange={(e) => setActividadId(e.target.value)}>
              <option value="">Elige un concepto…</option>
              {candidatos.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.concepto_clave} · {a.descripcion}
                </option>
              ))}
            </select>
          </label>
          {candidatos.length === 0 && (
            <p className="text-mute text-xs">No hay conceptos en m² en esta obra. Agrégalo como partida en la pestaña Árbol.</p>
          )}
          <div className="opciones__fila" role="group" aria-label="Cara del revestimiento">
            {(['interior', 'fachada'] as const).map((c) => (
              <button key={c} type="button" className={cara === c ? 'chip is-active' : 'chip'} aria-pressed={cara === c} onClick={() => setCara(c)}>
                {NOMBRE_DE_CARA[c]}
              </button>
            ))}
          </div>
          <label className="text-xs">
            Altura (m)
            <CampoDecimal etiqueta="Altura del revestimiento (m)" valor={altura} onValor={setAltura} />
          </label>
          <div className="row" style={{ gap: 6 }}>
            <button
              type="button"
              className="btn btn--sm"
              disabled={!listo}
              onClick={() => {
                if (!elegida) return;
                onColocar({ muroId, actividadId: elegida.id, clave: elegida.concepto_clave ?? 'revestimiento', cara, alturaM: altura });
                setAbierto(false);
              }}
            >
              Dibujar el largo
            </button>
            <button type="button" className="btn btn--ghost btn--sm" onClick={() => setAbierto(false)}>
              Cerrar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
