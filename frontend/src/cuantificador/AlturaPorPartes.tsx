/**
 * La altura de un muro: única, o por partes (D-627): «Muro» de 0 a 2.6 m, «Antepecho» de 2.6 a 3 m que no suma… Cada
 * parte dice desde dónde y hasta dónde llega y si suma a la cantidad. Lo comparten el panel de la herramienta Línea
 * (antes de trazar) y el detalle del trazo («Cómo cuenta para el concepto»).
 */

export interface ParteDeAltura {
  nombre: string;
  desde_m: number;
  hasta_m: number;
  suma: boolean;
}

interface Props {
  readonly partes: readonly ParteDeAltura[];
  /** La altura única, como se teclea: la primera parte nace con ella. */
  readonly alturaUnica: string;
  readonly onPartes: (partes: ParteDeAltura[]) => void;
}

const num = (t: unknown) => Number(String(t ?? '').replace(',', '.'));

export function AlturaPorPartes({ partes, alturaUnica, onPartes }: Props) {
  const cambiarUna = (i: number, cambio: Partial<ParteDeAltura>) =>
    onPartes(partes.map((x, j) => (j === i ? { ...x, ...cambio } : x)));
  const chip = (activo: boolean, etiqueta: string, alPulsar: () => void) => (
    <button type="button" className={activo ? 'chip is-active' : 'chip'} aria-pressed={activo} onClick={alPulsar}>
      {etiqueta}
    </button>
  );
  return (
    <>
      <div className="text-xs text-mute">Altura por partes</div>
      <div className="row" style={{ gap: 4 }} role="group" aria-label="Altura única o por partes">
        {chip(partes.length === 0, 'Altura única', () => onPartes([]))}
        {chip(partes.length > 0, 'Por partes', () =>
          onPartes([{ nombre: 'Muro', desde_m: 0, hasta_m: num(alturaUnica) || 2.6, suma: true }]),
        )}
      </div>
      {partes.map((p, i) => (
        <div key={i} className="row" style={{ gap: 4 }}>
          <input aria-label={`Nombre de la parte ${i + 1}`} style={{ width: 80 }} value={p.nombre} onChange={(e) => cambiarUna(i, { nombre: e.target.value })} />
          <input aria-label={`Desde (m) de la parte ${i + 1}`} inputMode="decimal" style={{ width: 48 }} value={String(p.desde_m)} onChange={(e) => cambiarUna(i, { desde_m: num(e.target.value) })} />
          <input aria-label={`Hasta (m) de la parte ${i + 1}`} inputMode="decimal" style={{ width: 48 }} value={String(p.hasta_m)} onChange={(e) => cambiarUna(i, { hasta_m: num(e.target.value) })} />
          <label className="text-xs" title="Suma a la cantidad">
            <input type="checkbox" checked={p.suma} onChange={(e) => cambiarUna(i, { suma: e.target.checked })} /> suma
          </label>
          <button type="button" className="btn btn--ghost btn--sm" aria-label={`Quitar la parte ${i + 1}`} onClick={() => onPartes(partes.filter((_, j) => j !== i))}>
            ×
          </button>
        </div>
      ))}
      {partes.length > 0 && (
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => {
            const ultima = partes[partes.length - 1]!;
            onPartes([...partes, { nombre: '', desde_m: ultima.hasta_m, hasta_m: ultima.hasta_m + 0.5, suma: true }]);
          }}
        >
          + Parte
        </button>
      )}
    </>
  );
}
