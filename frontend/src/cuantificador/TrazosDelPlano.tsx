/**
 * Pestaña «Trazos» del panel izquierdo: todos los trazos del plano, agrupados por concepto, con
 * búsqueda. Un clic elige el trazo en el plano (igual que con la herramienta Seleccionar) y el
 * detalle de la derecha muestra sus enlaces.
 */

import { useMemo, useState } from 'react';

import type { TrazoFeature } from '@/api/generado/modelo';
import { agruparTrazos, type OpcionesDeLista } from './listaDeTrazos';

interface Props {
  readonly trazos: readonly TrazoFeature[];
  readonly elegidoId: string | null;
  readonly opciones: Omit<OpcionesDeLista, 'busqueda'>;
  readonly onElegir: (trazoId: string) => void;
}

export function TrazosDelPlano({ trazos, elegidoId, opciones, onElegir }: Props) {
  const [busqueda, setBusqueda] = useState('');
  const grupos = useMemo(
    () => agruparTrazos(trazos, { ...opciones, busqueda }),
    [trazos, opciones, busqueda],
  );

  return (
    <div className="trazos-plano">
      <input
        className="input"
        type="search"
        placeholder="Buscar trazo, concepto o medición"
        aria-label="Buscar trazo"
        value={busqueda}
        onChange={(e) => setBusqueda(e.target.value)}
        style={{ margin: 8, width: 'calc(100% - 16px)' }}
      />
      <div className="trazos-plano__lista" role="list" aria-label="Todos los trazos del plano">
        {grupos.length === 0 ? (
          <div className="text-mute text-sm" style={{ padding: 10 }}>
            {trazos.length === 0 ? 'Aún no hay trazos.' : 'Ningún trazo coincide.'}
          </div>
        ) : (
          grupos.map((grupo) => (
            <div key={grupo.claveDeGrupo ?? 'sin-enlace'}>
              <div className="trazos-plano__grupo">
                <span>{grupo.nombre}</span>
                <span className="text-mute">{grupo.trazos.length}</span>
              </div>
              {grupo.trazos.map((fila) => (
                <button
                  key={fila.id}
                  type="button"
                  role="listitem"
                  className={`trazos-plano__fila${fila.id === elegidoId ? ' is-activa' : ''}`}
                  aria-current={fila.id === elegidoId ? 'true' : undefined}
                  onClick={() => onElegir(fila.id)}
                >
                  <span
                    className="trazos-plano__color"
                    style={{ background: fila.color ?? 'var(--c-accent)' }}
                    aria-hidden
                  />
                  <span className="trazos-plano__nombre">
                    <b>{fila.titulo}</b>
                    <small>{fila.subtitulo}</small>
                  </span>
                  <span className="trazos-plano__cantidad mono">{fila.cantidad ?? ''}</span>
                </button>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
