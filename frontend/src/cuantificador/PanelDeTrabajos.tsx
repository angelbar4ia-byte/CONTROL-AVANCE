/**
 * Pestaña «Trabajos» del panel izquierdo: los destajos de cada concepto de la obra y, de cada uno, su
 * cuadrilla con su rendimiento; y debajo las cuadrillas (capacidad). Un clic elige un destajo o una
 * cuadrilla y la columna derecha muestra su detalle y lo deja editar (Control de obra).
 *
 * La cuadrilla es **capacidad**: dice cuánto hace en un día. No es el costo del concepto, y el precio
 * del destajo no cambia aunque cambie la cuadrilla.
 */

import { useMemo, useState } from 'react';

import type { TrabajoDeObraRespuesta } from '@/api/generado/modelo';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { agruparTrabajos } from './trabajos';

export type TrabajoElegido =
  | { readonly tipo: 'destajo'; readonly actividadId: string; readonly insumoId: string }
  | { readonly tipo: 'cuadrilla'; readonly id: string };

export interface CuadrillaDeLaObra {
  readonly id: string;
  readonly nombre: string;
  readonly costoJornada: number | null;
  /** Claves de los destajos de esta obra que trabajan con ella. */
  readonly trabajaEn: readonly string[];
}

/** Las cuadrillas que aparecen en los trabajos de la obra, con lo que cuestan y dónde trabajan. */
export function cuadrillasDeLosTrabajos(trabajos: readonly TrabajoDeObraRespuesta[]): readonly CuadrillaDeLaObra[] {
  const por = new Map<string, { nombre: string; costo: number | null; en: Set<string> }>();
  for (const t of trabajos) {
    if (!t.cuadrilla_id) continue;
    const entrada = por.get(t.cuadrilla_id) ?? {
      nombre: t.cuadrilla_nombre ?? t.cuadrilla_clave ?? 'Cuadrilla',
      costo: t.costo_cuadrilla != null ? Number(t.costo_cuadrilla) : null,
      en: new Set<string>(),
    };
    entrada.en.add(t.clave);
    por.set(t.cuadrilla_id, entrada);
  }
  return [...por.entries()]
    .map(([id, e]) => ({ id, nombre: e.nombre, costoJornada: e.costo, trabajaEn: [...e.en].sort() }))
    .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
}

interface Props {
  readonly trabajos: readonly TrabajoDeObraRespuesta[];
  readonly medidaPorActividad: ReadonlyMap<string, string | number | null | undefined>;
  readonly elegido: TrabajoElegido | null;
  readonly cargando: boolean;
  readonly onElegir: (elegido: TrabajoElegido) => void;
}

export function PanelDeTrabajos({ trabajos, medidaPorActividad, elegido, cargando, onElegir }: Props) {
  const [busqueda, setBusqueda] = useState('');
  const [abiertos, setAbiertos] = useState<ReadonlySet<string>>(new Set());
  const grupos = useMemo(
    () => agruparTrabajos(trabajos, { medidaPorActividad, busqueda }),
    [trabajos, medidaPorActividad, busqueda],
  );
  const cuadrillas = useMemo(() => cuadrillasDeLosTrabajos(trabajos), [trabajos]);

  function alternar(clave: string) {
    setAbiertos((actual) => {
      const siguiente = new Set(actual);
      if (siguiente.has(clave)) siguiente.delete(clave);
      else siguiente.add(clave);
      return siguiente;
    });
  }

  return (
    <div className="trabajos-panel">
      <p className="text-mute text-xs" style={{ margin: '6px 8px' }}>
        Aquí van los <b>trabajos</b>: los destajos de cada concepto y, en cada uno, su cuadrilla con su
        rendimiento. La cantidad sale del concepto: lo medido en el plano o, si aún no hay, lo
        presupuestado.
      </p>
      <input
        className="input"
        type="search"
        placeholder="Buscar destajo, concepto o cuadrilla…"
        aria-label="Buscar destajo"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
        style={{ margin: '4px 8px 8px', width: 'calc(100% - 16px)' }}
      />
      <div className="trabajos-panel__lista" role="list" aria-label="Destajos y cuadrillas">
        {cargando ? (
          <div className="text-mute text-sm" style={{ padding: 10 }}>Cargando…</div>
        ) : grupos.length === 0 ? (
          <div className="text-mute text-sm" style={{ padding: 10 }}>
            {trabajos.length === 0
              ? 'Los conceptos de esta obra no traen destajos en su receta.'
              : 'Ningún destajo coincide.'}
          </div>
        ) : (
          grupos.map((grupo) => (
            <div key={grupo.actividadId}>
              <div className="trazos-plano__grupo">
                <span title={grupo.conceptoNombre}>
                  <span className="mono">{grupo.conceptoClave}</span> {grupo.conceptoNombre}
                </span>
                <span className="text-mute mono">
                  {fmtNum(grupo.cantidadDelConcepto.valor)} {grupo.conceptoUnidad ?? ''}
                </span>
              </div>
              {grupo.trabajos.map(({ trabajo: t, calculo: c }) => {
                const clave = `${t.actividad_id}:${t.insumo_id}`;
                const abierto = abiertos.has(clave);
                const activo = elegido?.tipo === 'destajo' && elegido.actividadId === t.actividad_id && elegido.insumoId === t.insumo_id;
                return (
                  <div key={clave} role="listitem" className="trabajos-panel__trabajo">
                    <button
                      type="button"
                      className={`trazos-plano__fila trabajos-panel__fila${activo ? ' is-activa' : ''}`}
                      aria-expanded={abierto}
                      aria-current={activo ? 'true' : undefined}
                      onClick={() => {
                        onElegir({ tipo: 'destajo', actividadId: t.actividad_id, insumoId: t.insumo_id });
                        alternar(clave);
                      }}
                    >
                      <span aria-hidden>{abierto ? '▾' : '▸'}</span>
                      <span className="trazos-plano__nombre">
                        <b>
                          <span className="mono">{t.clave}</span> {t.descripcion}
                        </b>
                        <small>
                          {fmtNum(c.cantidad)} {t.unidad ?? ''} × {fmtMXN(t.precio)}
                          {c.dias !== null ? ` · ${fmtNum(c.dias)} días` : ''}
                        </small>
                      </span>
                      <span className="trazos-plano__cantidad mono">{fmtMXN(c.importe)}</span>
                    </button>
                    {abierto && (
                      <div className="trabajos-panel__cuadrilla">
                        {t.cuadrilla_id ? (
                          <>
                            {t.cuadrilla_nombre} · {c.capacidadPorDia !== null ? `${fmtNum(c.capacidadPorDia)} ${t.unidad ?? ''}/día` : 'sin rendimiento'}{' '}
                            <span className="text-mute">({c.origenDeLaCapacidad ?? 'sin dato'})</span>
                          </>
                        ) : (
                          <span className="text-mute">Sin cuadrilla</span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ))
        )}

        {cuadrillas.length > 0 && (
          <div>
            <div className="trazos-plano__grupo">
              <span>Cuadrillas (capacidad)</span>
              <span className="text-mute">{cuadrillas.length}</span>
            </div>
            {cuadrillas.map((q) => {
              const activo = elegido?.tipo === 'cuadrilla' && elegido.id === q.id;
              return (
                <div key={q.id} role="listitem">
                  <button
                    type="button"
                    className={`trazos-plano__fila trabajos-panel__fila${activo ? ' is-activa' : ''}`}
                    aria-current={activo ? 'true' : undefined}
                    onClick={() => onElegir({ tipo: 'cuadrilla', id: q.id })}
                  >
                    <span aria-hidden>·</span>
                    <span className="trazos-plano__nombre">
                      <b>{q.nombre}</b>
                      <small>
                        {q.costoJornada !== null ? `${fmtMXN(q.costoJornada)}/día` : 'costo por día sin capturar'} · {q.trabajaEn.length}{' '}
                        {q.trabajaEn.length === 1 ? 'destajo' : 'destajos'}
                      </small>
                    </span>
                    <span />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
