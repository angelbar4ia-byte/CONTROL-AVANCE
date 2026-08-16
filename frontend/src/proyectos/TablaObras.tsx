/**
 * Lista plana de obras — lo que ven Residente y Supervisor.
 *
 * `GET /proyectos` y `GET /clusters` son de Control de obra y Super
 * intendente (§11.2), así que para el Residente ("Mis obras") y el
 * Supervisor ("Obras supervisadas", §5.1) no hay árbol que armar: se listan
 * las obras que `GET /obras` ya devolvió acotadas por RLS a su alcance (§4).
 */

import type { ObraRespuesta } from '@/api/generado/modelo';
import { colorAvance, fmtFecha, fmtNum, fmtPct } from '@/lib/formato';
import { etiquetaEstatusObra, tonoEstatusObra } from './reglas';

interface Props {
  readonly obras: readonly ObraRespuesta[];
  readonly cargando: boolean;
  readonly obraSeleccionada: string | null;
  readonly onSeleccionarObra: (obra: ObraRespuesta) => void;
}

export function TablaObras({ obras, cargando, obraSeleccionada, onSeleccionarObra }: Props) {
  return (
    <div className="table-wrap">
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Obra</th>
              <th>Estatus</th>
              <th>Avance</th>
              <th>Inicio</th>
              <th>Fin</th>
              <th className="is-num">m²</th>
              <th className="cell-actions">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {cargando ? (
              <tr>
                <td colSpan={7}>
                  <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                    Cargando…
                  </div>
                </td>
              </tr>
            ) : obras.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <div className="text-mute text-sm" style={{ padding: '24px 0' }}>
                    No hay obras en tu alcance con estos filtros.
                  </div>
                </td>
              </tr>
            ) : (
              obras.map((obra) => {
                const pct = Number(obra.avance_pct);
                const tono = colorAvance(pct);
                return (
                  <tr
                    key={obra.id}
                    style={
                      obra.id === obraSeleccionada ? { background: 'var(--c-elev)' } : undefined
                    }
                  >
                    <td className="is-key">{obra.clave}</td>
                    <td>
                      <span className={`badge badge--${tonoEstatusObra(obra.estatus)}`}>
                        {etiquetaEstatusObra(obra.estatus)}
                      </span>
                    </td>
                    <td>
                      <div className={`bar ${tono !== 'accent' ? `bar--${tono}` : ''}`}>
                        <div
                          className="bar__fill"
                          style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                        />
                      </div>
                      <div className="text-mute text-xs mono tnum mt-8">
                        {fmtPct(obra.avance_pct)}
                      </div>
                    </td>
                    <td>{fmtFecha(obra.fecha_inicio)}</td>
                    <td>{fmtFecha(obra.fecha_fin)}</td>
                    <td className="is-num">{fmtNum(obra.m2)}</td>
                    <td className="cell-actions">
                      <button
                        type="button"
                        className="btn btn--sm"
                        aria-haspopup="dialog"
                        onClick={() => onSeleccionarObra(obra)}
                      >
                        Detalle
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
