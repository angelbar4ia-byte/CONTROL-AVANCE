/**
 * Editor de precedencias (`DependenciaDTO`, §7.5).
 *
 * Lo comparten el ajuste de una actividad (`PATCH
 * /actividades/{id}/programacion`) y el alta de un programa base (`POST
 * /programas-base`), que usan el mismo DTO con distinto significado de `ref`:
 * en una actividad es el id de la actividad predecesora, en un programa base
 * el `prototipo_nodo_id` de la predecesora. Por eso el `ref` se captura con
 * un `select` cuando hay catálogo que ofrecer (`opciones`) y con un campo de
 * texto cuando no lo hay.
 *
 * Cero reglas: no valida ciclos ni ordena nada. El motor rechaza el
 * cronograma inválido con 422 sin escribir (§6, §7.5).
 */

import type { FormularioDependencia } from './formulario';
import { etiquetaTipoDependencia, TIPOS_DEPENDENCIA } from './reglas';

/** Predecesora elegible: el valor es la `ref` que viaja en el DTO. */
export interface OpcionRef {
  readonly valor: string;
  readonly etiqueta: string;
}

interface Props {
  readonly idBase: string;
  readonly dependencias: readonly FormularioDependencia[];
  readonly onCambio: (dependencias: readonly FormularioDependencia[]) => void;
  /** Predecesoras elegibles; sin ellas el `ref` se captura como texto. */
  readonly opciones?: readonly OpcionRef[];
  /** Texto bajo el título cuando no hay ninguna predecesora. */
  readonly vacio: string;
  readonly pistaRef?: string;
}

export function EditorDependencias({
  idBase,
  dependencias,
  onCambio,
  opciones,
  vacio,
  pistaRef,
}: Props) {
  function actualizar(indice: number, parcial: Partial<FormularioDependencia>) {
    onCambio(
      dependencias.map((dependencia, i) =>
        i === indice ? { ...dependencia, ...parcial } : dependencia,
      ),
    );
  }

  return (
    <div className="col gap-4">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="field__label">Dependencias</span>
        <button
          type="button"
          className="btn btn--sm"
          onClick={() => onCambio([...dependencias, { ref: '', tipo: 'FS', lagDias: '0' }])}
        >
          Agregar predecesora
        </button>
      </div>

      {dependencias.length === 0 && <div className="field__hint">{vacio}</div>}

      {dependencias.map((dependencia, indice) => (
        <div
          key={`${idBase}-dep-${indice}`}
          className="row gap-4"
          style={{ flexWrap: 'wrap', alignItems: 'flex-end' }}
        >
          <div className="field" style={{ flex: 2, minWidth: 200 }}>
            <label className="field__label" htmlFor={`${idBase}-dep-ref-${indice}`}>
              Predecesora
            </label>
            {opciones === undefined ? (
              <input
                id={`${idBase}-dep-ref-${indice}`}
                className="input input--mono"
                value={dependencia.ref}
                onChange={(e) => actualizar(indice, { ref: e.target.value })}
                placeholder="uuid de la predecesora"
              />
            ) : (
              <select
                id={`${idBase}-dep-ref-${indice}`}
                className="select"
                value={dependencia.ref}
                onChange={(e) => actualizar(indice, { ref: e.target.value })}
              >
                <option value="">Elegir…</option>
                {/* Una `ref` fuera del catálogo (versión anterior del
                    programa) se conserva como opción para no borrarla al
                    abrir el editor. */}
                {dependencia.ref !== '' &&
                  !opciones.some((opcion) => opcion.valor === dependencia.ref) && (
                    <option value={dependencia.ref}>{dependencia.ref}</option>
                  )}
                {opciones.map((opcion) => (
                  <option key={opcion.valor} value={opcion.valor}>
                    {opcion.etiqueta}
                  </option>
                ))}
              </select>
            )}
            {pistaRef !== undefined && indice === 0 && (
              <div className="field__hint">{pistaRef}</div>
            )}
          </div>

          <div className="field" style={{ flex: 1, minWidth: 130 }}>
            <label className="field__label" htmlFor={`${idBase}-dep-tipo-${indice}`}>
              Tipo
            </label>
            <select
              id={`${idBase}-dep-tipo-${indice}`}
              className="select"
              value={dependencia.tipo}
              onChange={(e) => actualizar(indice, { tipo: e.target.value })}
            >
              {TIPOS_DEPENDENCIA.map((tipo) => (
                <option key={tipo} value={tipo}>
                  {etiquetaTipoDependencia(tipo)}
                </option>
              ))}
            </select>
          </div>

          <div className="field" style={{ flex: 1, minWidth: 90 }}>
            <label className="field__label" htmlFor={`${idBase}-dep-lag-${indice}`}>
              Lag (días)
            </label>
            <input
              id={`${idBase}-dep-lag-${indice}`}
              className="input input--mono"
              type="number"
              step="any"
              value={dependencia.lagDias}
              onChange={(e) => actualizar(indice, { lagDias: e.target.value })}
            />
          </div>

          <button
            type="button"
            className="btn btn--ghost btn--sm"
            aria-label={`Quitar predecesora ${indice + 1}`}
            onClick={() => onCambio(dependencias.filter((_, i) => i !== indice))}
          >
            Quitar
          </button>
        </div>
      ))}
    </div>
  );
}
