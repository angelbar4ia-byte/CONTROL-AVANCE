/**
 * Los vanos colocados en el plano, en la pestaña Elementos: puertas, ventanas, cancel, arcos y pasos con su clave, su
 * muro y lo que descuentan. Un clic elige el vano en el plano y abre su detalle («Elemento colocado»).
 */

import type { VanoEnPlanoRespuesta } from '@/api/generado/modelo';

import { TIPOS_DE_VANO, type TipoDeVano } from './vanos';

interface Props {
  readonly vanos: readonly VanoEnPlanoRespuesta[];
  readonly elegidoId: string | null;
  readonly nombreDelMuro: (trazoId: string) => string;
  readonly onElegir: (id: string) => void;
}

export function VanosDelPlano({ vanos, elegidoId, nombreDelMuro, onElegir }: Props) {
  return (
    <section aria-label="Vanos colocados" className="col gap-4">
      <div className="text-xs text-mute">Vanos colocados · {vanos.length}</div>
      {vanos.length === 0 && <div className="text-mute text-xs">Sin vanos en este plano. Con la herramienta Vano, un clic sobre un muro.</div>}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 2 }}>
        {vanos.map((v) => {
          const tipo = (v.tipo in TIPOS_DE_VANO ? v.tipo : 'puerta') as TipoDeVano;
          return (
            <li key={v.id}>
              <button
                type="button"
                className={v.id === elegidoId ? 'chip is-active' : 'chip'}
                aria-pressed={v.id === elegidoId}
                data-vano-lista={v.clave}
                style={{ width: '100%', justifyContent: 'space-between' }}
                onClick={() => onElegir(v.id)}
              >
                <span className="mono">
                  {v.piezas > 1 ? `${v.piezas}× ` : ''}
                  {v.clave}
                </span>
                <span className="text-mute text-xs">
                  {TIPOS_DE_VANO[tipo].nombre} · {nombreDelMuro(v.trazo_id)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
