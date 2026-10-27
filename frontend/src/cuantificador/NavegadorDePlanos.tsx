/**
 * El navegador de planos: la lista de los planos de la obra, para abrir uno de un clic.
 *
 * Es la segunda pestaña del panel del presupuesto. Cada plano dice cuántos trazos lleva, cuántos de
 * ellos quedaron por revisar (se hicieron sobre una versión anterior) y si está calibrado. Los
 * planos que comparten nombre son versiones del mismo plano: se agrupan, con la más nueva arriba.
 */

import { Ruler, Upload } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { PlanoDetalleRespuesta } from '@/api/generado/modelo';
import { fmtFecha } from '@/lib/formato';

interface Props {
  readonly planos: readonly PlanoDetalleRespuesta[];
  readonly cargando: boolean;
  readonly activoId: string;
  readonly onElegir: (planoId: string) => void;
  readonly onSubir: () => void;
}

const norm = (t: string) => t.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

export function NavegadorDePlanos({ planos, cargando, activoId, onElegir, onSubir }: Props) {
  const [busqueda, setBusqueda] = useState('');

  const grupos = useMemo(() => {
    const q = norm(busqueda.trim());
    const porNombre = new Map<string, PlanoDetalleRespuesta[]>();
    for (const p of planos) {
      if (q !== '' && !norm(p.nombre).includes(q)) continue;
      porNombre.set(p.nombre, [...(porNombre.get(p.nombre) ?? []), p]);
    }
    return [...porNombre.entries()]
      .sort(([a], [b]) => a.localeCompare(b, 'es', { numeric: true }))
      .map(([nombre, versiones]) => ({
        nombre,
        versiones: [...versiones].sort((a, b) => b.version - a.version),
      }));
  }, [planos, busqueda]);

  return (
    <div className="planos">
      <div className="arbol__herramientas">
        <input
          className="input arbol__buscar"
          type="search"
          placeholder="Buscar plano"
          aria-label="Buscar un plano"
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
        />
        <button type="button" className="btn-icono" aria-label="Subir plano" title="Subir plano" onClick={onSubir}>
          <Upload size={15} aria-hidden />
        </button>
      </div>

      {cargando ? (
        <div className="text-mute text-sm" style={{ padding: 10 }}>
          Cargando planos…
        </div>
      ) : planos.length === 0 ? (
        <div className="text-mute text-sm" style={{ padding: 10 }}>
          Esta obra no tiene planos. Sube uno para empezar a trazar.
        </div>
      ) : grupos.length === 0 ? (
        <div className="text-mute text-sm" style={{ padding: 10 }}>
          Ningún plano coincide con «{busqueda}».
        </div>
      ) : (
        <ul className="planos__lista" aria-label="Planos de la obra">
          {grupos.map((g) => (
            <li key={g.nombre} className="planos__grupo">
              {g.versiones.length > 1 && (
                <div className="planos__nombre">
                  {g.nombre}
                  <span className="arbol__cuenta"> · {g.versiones.length} versiones</span>
                </div>
              )}
              <ul>
                {g.versiones.map((p, i) => {
                  const activo = p.id === activoId;
                  const calibrado = p.escala_m_por_unidad != null;
                  return (
                    <li key={p.id}>
                      <button
                        type="button"
                        className={activo ? 'planos__plano is-activo' : 'planos__plano'}
                        aria-current={activo ? 'true' : undefined}
                        onClick={() => onElegir(p.id)}
                      >
                        <span className="planos__titulo">
                          {g.versiones.length > 1 ? `Versión ${p.version}` : p.nombre}
                          {g.versiones.length > 1 && i === 0 && <span className="badge badge--outline">Vigente</span>}
                          {g.versiones.length === 1 && <span className="arbol__cuenta"> · v{p.version}</span>}
                        </span>
                        <span className="planos__datos">
                          <span title="Trazos de este plano">
                            {p.n_trazos} {p.n_trazos === 1 ? 'trazo' : 'trazos'}
                          </span>
                          {p.n_trazos_por_revisar > 0 && (
                            <span className="badge badge--warn">{p.n_trazos_por_revisar} por revisar</span>
                          )}
                          <span
                            className={calibrado ? 'planos__escala is-ok' : 'planos__escala is-sin'}
                            title={
                              calibrado
                                ? `Calibrado: 1 unidad = ${Number(p.escala_m_por_unidad).toPrecision(4)} m`
                                : 'Sin calibrar: las cantidades están en unidades de plano'
                            }
                          >
                            <Ruler size={12} aria-hidden />
                            {calibrado ? 'Calibrado' : 'Sin calibrar'}
                          </span>
                          <span className="arbol__cuenta">{fmtFecha(p.created_at)}</span>
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
