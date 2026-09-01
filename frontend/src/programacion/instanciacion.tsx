/**
 * Lo que comparten las dos formas de bajar un programa base a las obras
 * (§7.5, §11.2).
 *
 * Son la misma operación con distinto alcance —`InstanciarPrograma` sobre una
 * obra, `ReplicarPrograma` sobre las del prototipo— y por eso piden y reportan
 * lo mismo: la fecha de corte contra la que se mide el desfase, y los dos
 * huecos que el backend devuelve sin considerarlos errores (actividades sin
 * renglón en la plantilla y dependencias que no resolvieron).
 *
 * Vive aparte para que las dos pantallas no expliquen distinto lo mismo: si el
 * texto del hueco de plantilla se redactara dos veces, tarde o temprano una de
 * las dos diría otra cosa.
 */

interface PropsFechaCorte {
  /** Id del `<input>`: hay dos pantallas y una puede montar varias. */
  readonly id: string;
  readonly valor: string;
  readonly onCambio: (valor: string) => void;
}

/** Fecha contra la que se mide el desfase; vacío = hoy (§6). */
export function CampoFechaCorte({ id, valor, onCambio }: PropsFechaCorte) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        Fecha de corte (opcional)
      </label>
      <input
        id={id}
        className="input"
        type="date"
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
      />
      <div className="field__hint">
        Fecha contra la que se mide el desfase; vacío = hoy (§6).
      </div>
    </div>
  );
}

interface PropsHuecos {
  readonly sinItem: readonly string[];
  readonly refsNoResueltas: readonly string[];
  /** Prefijo para el caso masivo ("FRESNO 01: 3 actividades…"). */
  readonly prefijo?: string;
}

/**
 * Los dos huecos que deja una instanciación y que **no** son errores: el
 * programa base puede cubrir solo parte del árbol del prototipo, y el motor
 * ignora las dependencias que no apuntan a ninguna actividad de la obra (§6,
 * §7.5). Se reportan para que Control de obra complete la plantilla en vez de
 * que el hueco pase inadvertido.
 */
export function HuecosDeLaPlantilla({ sinItem, refsNoResueltas, prefijo }: PropsHuecos) {
  if (sinItem.length === 0 && refsNoResueltas.length === 0) return null;
  const marca = prefijo ? `${prefijo}: ` : '';

  return (
    <>
      {sinItem.length > 0 && (
        <div className="field__hint">
          {marca}
          <span className="mono tnum">{sinItem.length}</span> actividades sin renglón en
          el programa base: conservaron su programación anterior (§7.5).
        </div>
      )}
      {refsNoResueltas.length > 0 && (
        <div className="field__hint" style={{ color: 'var(--c-warn)' }}>
          {marca}
          <span className="mono tnum">{refsNoResueltas.length}</span> dependencias del
          programa base no corresponden a ninguna actividad de la obra; el motor las
          ignoró (§6).
        </div>
      )}
    </>
  );
}
