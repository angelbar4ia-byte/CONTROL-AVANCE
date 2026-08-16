/**
 * Campos de formulario del feature (DESIGN_SYSTEM.md §4: `.field`, `.input`,
 * `.select`).
 *
 * Los formularios de alta de proyecto, cluster, prototipo y obra piden los
 * mismos campos una y otra vez; esto los centraliza para que la etiqueta
 * siempre quede asociada al control (`htmlFor`/`id`) y para no repetir el
 * marcado en cinco archivos. Cero lógica: solo presentación.
 */

interface PropsTexto {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: string;
  readonly onCambio: (valor: string) => void;
  readonly tipo?: 'text' | 'number' | 'date';
  /** Números y claves van en mono con `tabular-nums` (§12.10). */
  readonly mono?: boolean;
  readonly requerido?: boolean;
  readonly marcador?: string;
  readonly pista?: string;
  readonly paso?: string;
  readonly minimo?: string;
  readonly deshabilitado?: boolean;
}

export function CampoTexto({
  id,
  etiqueta,
  valor,
  onCambio,
  tipo = 'text',
  mono = false,
  requerido = false,
  marcador,
  pista,
  paso,
  minimo,
  deshabilitado = false,
}: PropsTexto) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {etiqueta}
        {requerido && <span aria-hidden> *</span>}
      </label>
      <input
        id={id}
        className={mono ? 'input input--mono' : 'input'}
        type={tipo}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        required={requerido}
        placeholder={marcador}
        step={paso}
        min={minimo}
        disabled={deshabilitado}
      />
      {pista !== undefined && <div className="field__hint">{pista}</div>}
    </div>
  );
}

export interface Opcion {
  readonly valor: string;
  readonly etiqueta: string;
}

interface PropsSelect {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: string;
  readonly onCambio: (valor: string) => void;
  readonly opciones: readonly Opcion[];
  /** Texto de la opción vacía; omítelo para no ofrecerla. */
  readonly vacio?: string;
  readonly requerido?: boolean;
  readonly pista?: string;
  readonly deshabilitado?: boolean;
}

export function CampoSelect({
  id,
  etiqueta,
  valor,
  onCambio,
  opciones,
  vacio,
  requerido = false,
  pista,
  deshabilitado = false,
}: PropsSelect) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {etiqueta}
        {requerido && <span aria-hidden> *</span>}
      </label>
      <select
        id={id}
        className="select"
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        required={requerido}
        disabled={deshabilitado}
      >
        {vacio !== undefined && <option value="">{vacio}</option>}
        {opciones.map((opcion) => (
          <option key={opcion.valor} value={opcion.valor}>
            {opcion.etiqueta}
          </option>
        ))}
      </select>
      {pista !== undefined && <div className="field__hint">{pista}</div>}
    </div>
  );
}
