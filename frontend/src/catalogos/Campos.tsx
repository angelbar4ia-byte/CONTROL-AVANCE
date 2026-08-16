/**
 * Campos de formulario del feature de catálogos (DESIGN_SYSTEM.md §4:
 * `.field`, `.input`, `.select`).
 *
 * Mismo patrón que `proyectos/Campos.tsx`: cada feature trae los suyos para
 * no acoplarse a otro módulo (AGENTS.md, "fronteras de módulo"). Los de aquí
 * agregan lo que los catálogos necesitan y proyectos no: la **casilla de
 * IVA** (§3.5) con su estado heredado, y el área de texto para los sinónimos
 * de unidad (§3.5, §10.3).
 *
 * Cero lógica: solo presentación y el amarre `label`/`id` para que todo sea
 * navegable con teclado y legible por lector de pantalla.
 */

interface PropsTexto {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: string;
  readonly onCambio: (valor: string) => void;
  readonly tipo?: 'text' | 'number';
  /** Números y claves van en mono con `tabular-nums` (§12.10). */
  readonly mono?: boolean;
  readonly requerido?: boolean;
  readonly marcador?: string;
  readonly pista?: string;
  readonly paso?: string;
  readonly minimo?: string;
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

interface PropsCheck {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: boolean;
  readonly onCambio: (valor: boolean) => void;
  readonly pista?: string;
}

/** Casilla simple (`iva_aplica` de familia, `incluir_inactivos`…). */
export function CampoCheck({ id, etiqueta, valor, onCambio, pista }: PropsCheck) {
  return (
    <div className="field">
      <label className="row gap-4" htmlFor={id} style={{ alignItems: 'center' }}>
        <input
          id={id}
          type="checkbox"
          checked={valor}
          onChange={(e) => onCambio(e.target.checked)}
        />
        <span className="text-sm">{etiqueta}</span>
      </label>
      {pista !== undefined && <div className="field__hint">{pista}</div>}
    </div>
  );
}

/**
 * IVA de un insumo: tres estados, no dos (§3.5).
 *
 * "Valor inicial derivado de la **familia**… **override por material**". Un
 * booleano no alcanza: hay que poder decir "heredo de mi familia" (`null` en
 * el contrato) además de "sí" y "no". Por eso es un `select` de tres
 * opciones y no una casilla.
 */
export function CampoIva({
  id,
  valor,
  onCambio,
  heredado,
}: {
  readonly id: string;
  /** `''` = hereda de la familia (el contrato manda `null`). */
  readonly valor: '' | 'si' | 'no';
  readonly onCambio: (valor: '' | 'si' | 'no') => void;
  /** Qué dice la familia elegida, para mostrar qué se hereda. */
  readonly heredado: boolean | null;
}) {
  const queHereda =
    heredado === null
      ? 'la familia todavía no lo define'
      : heredado
        ? 'la familia lo grava'
        : 'la familia está exenta';

  return (
    <CampoSelect
      id={id}
      etiqueta="IVA"
      valor={valor}
      onCambio={(nuevo) => onCambio(nuevo as '' | 'si' | 'no')}
      opciones={[
        { valor: 'si', etiqueta: 'Sí, lo grava (override)' },
        { valor: 'no', etiqueta: 'No, exento (override)' },
      ]}
      vacio={`Heredar de la familia — ${queHereda}`}
      pista="La tasa y las familias exentas son configurables y viven en BD (§3.5, §8.7)."
    />
  );
}

interface PropsArea {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: string;
  readonly onCambio: (valor: string) => void;
  readonly marcador?: string;
  readonly pista?: string;
  readonly filas?: number;
}

export function CampoArea({
  id,
  etiqueta,
  valor,
  onCambio,
  marcador,
  pista,
  filas = 3,
}: PropsArea) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>
        {etiqueta}
      </label>
      <textarea
        id={id}
        className="textarea"
        rows={filas}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        placeholder={marcador}
      />
      {pista !== undefined && <div className="field__hint">{pista}</div>}
    </div>
  );
}
