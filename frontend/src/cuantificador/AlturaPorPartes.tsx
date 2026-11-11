/**
 * La altura de un muro: única, o por partes (D-627): «Muro» de 0 a 2.6 m, «Antepecho» de 2.6 a 3 m que no suma… Cada
 * parte dice desde dónde y hasta dónde llega y si suma a la cantidad. Lo comparten el panel de la herramienta Línea
 * (antes de trazar) y el detalle del trazo («Cómo cuenta para el concepto»).
 */

import { CampoDecimal } from './CampoDecimal';

export interface ParteDeAltura {
  nombre: string;
  desde_m: number;
  hasta_m: number;
  suma: boolean;
}

interface Props {
  readonly partes: readonly ParteDeAltura[];
  /** La altura única, como se teclea (ya no siembra las partes: nacen precargadas). */
  readonly alturaUnica?: string;
  readonly onPartes: (partes: ParteDeAltura[]) => void;
}

/** Las partes con que nace «Por partes»: un muro de casa con su cerramiento y su enrase (se editan o se quitan). */
export const PARTES_PRECARGADAS: readonly ParteDeAltura[] = [
  { nombre: 'Media altura', desde_m: 0, hasta_m: 1.2, suma: true },
  { nombre: 'Hasta cerramiento', desde_m: 1.2, hasta_m: 2.3, suma: true },
  { nombre: 'Cerramiento', desde_m: 2.3, hasta_m: 2.5, suma: false },
  { nombre: 'Enrase', desde_m: 2.5, hasta_m: 3, suma: true },
];


export function AlturaPorPartes({ partes, onPartes }: Props) {
  const cambiarUna = (i: number, cambio: Partial<ParteDeAltura>) =>
    onPartes(partes.map((x, j) => (j === i ? { ...x, ...cambio } : x)));
  const chip = (activo: boolean, etiqueta: string, alPulsar: () => void) => (
    <button type="button" className={activo ? 'chip is-active' : 'chip'} aria-pressed={activo} onClick={alPulsar}>
      {etiqueta}
    </button>
  );
  return (
    <div className="alturas">
      <div className="alturas__titulo">Altura por partes</div>
      <div className="alturas__modo" role="group" aria-label="Altura única o por partes">
        {chip(partes.length === 0, 'Altura única', () => onPartes([]))}
        {chip(partes.length > 0, 'Por partes', () => onPartes(PARTES_PRECARGADAS.map((p) => ({ ...p }))))}
      </div>
      {partes.map((p, i) => (
        <div key={i} className="alturas__fila">
          <input aria-label={`Nombre de la parte ${i + 1}`} className="alturas__nombre" value={p.nombre} onChange={(e) => cambiarUna(i, { nombre: e.target.value })} />
          <CampoDecimal etiqueta={`Desde (m) de la parte ${i + 1}`} className="alturas__medida" valor={p.desde_m} onValor={(n) => cambiarUna(i, { desde_m: n })} />
          <CampoDecimal etiqueta={`Hasta (m) de la parte ${i + 1}`} className="alturas__medida" valor={p.hasta_m} onValor={(n) => cambiarUna(i, { hasta_m: n })} />
          <label className="alturas__suma" title="Suma a la cantidad">
            <input type="checkbox" checked={p.suma} onChange={(e) => cambiarUna(i, { suma: e.target.checked })} /> suma
          </label>
          <button type="button" className="btn btn--icon alturas__quitar" aria-label={`Quitar la parte ${i + 1}`} onClick={() => onPartes(partes.filter((_, j) => j !== i))}>
            ×
          </button>
        </div>
      ))}
      {partes.length > 0 && (
        <button
          type="button"
          className="alturas__agregar"
          onClick={() => {
            const ultima = partes[partes.length - 1]!;
            onPartes([...partes, { nombre: '', desde_m: ultima.hasta_m, hasta_m: ultima.hasta_m + 0.5, suma: true }]);
          }}
        >
          + Parte
        </button>
      )}
    </div>
  );
}
