/**
 * Las propuestas por revisar: trazos que una herramienta automática encontró (el conteo por plantilla,
 * el takeoff) y que **no suman nada** hasta que alguien los acepta. Todas vienen elegidas; un clic en una
 * propuesta del plano la descarta o la vuelve a elegir. Se aceptan las elegidas (pasan a medir su
 * concepto) o se rechazan (se borran sin haber sumado).
 */

import { Check, X } from 'lucide-react';

interface Props {
  /** Cuántas propuestas hay en el plano, y cuántas están elegidas. */
  readonly total: number;
  readonly elegidas: number;
  /** Para qué concepto se propusieron (por si hay de varios). */
  readonly resumen: readonly { readonly concepto: string; readonly n: number; readonly origen: string }[];
  readonly trabajando: boolean;
  readonly onAceptar: () => void;
  readonly onRechazar: () => void;
  readonly onElegirTodas: () => void;
}

const NOMBRE_DE_ORIGEN: Readonly<Record<string, string>> = {
  conteo_auto: 'conteo por plantilla',
  takeoff: 'takeoff automático',
};

export function PanelDePropuestas({ total, elegidas, resumen, trabajando, onAceptar, onRechazar, onElegirTodas }: Props) {
  return (
    <section className="opciones propuestas" aria-label="Propuestas por revisar">
      <div className="opciones__titulo">Propuestas por revisar</div>
      <ul className="propuestas__resumen text-xs">
        {resumen.map((r) => (
          <li key={`${r.concepto}-${r.origen}`}>
            <strong>{r.n}</strong> para <span className="mono">{r.concepto}</span> · {NOMBRE_DE_ORIGEN[r.origen] ?? r.origen}
          </li>
        ))}
      </ul>
      <p className="text-mute text-xs">
        <strong>No suman nada</strong> hasta que las aceptes. Un clic en una propuesta del plano la descarta o la vuelve a
        elegir.
      </p>
      <div className="opciones__fila">
        <button type="button" className="btn btn--accent btn--sm" disabled={elegidas === 0 || trabajando} onClick={onAceptar}>
          <Check size={13} aria-hidden /> Aceptar {elegidas}
        </button>
        <button type="button" className="btn btn--sm" disabled={elegidas === 0 || trabajando} onClick={onRechazar}>
          <X size={13} aria-hidden /> Rechazar {elegidas}
        </button>
        {elegidas < total && (
          <button type="button" className="btn btn--ghost btn--sm" onClick={onElegirTodas}>
            Elegir las {total}
          </button>
        )}
      </div>
    </section>
  );
}
