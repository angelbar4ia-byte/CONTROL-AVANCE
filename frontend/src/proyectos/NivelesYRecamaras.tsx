/**
 * Las celdas «Niveles» y «Recámaras» de un prototipo, editables en la tabla.
 *
 * Los niveles son las plantas del prototipo (planta baja y alta; el roof garden
 * no cuenta): 1 o 2. El catálogo de presupuesto crea los prototipos sin ninguno
 * de los dos (D-614) y aquí se llenan. Quién puede editar lo impone el servidor
 * (Control de obra y Super intendente); esta pantalla solo no ofrece el control
 * a quien no puede.
 */

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useEditarPrototipoApiV1PrototiposPrototipoIdPatch } from '@/api/generado/proyectos/proyectos';
import type { EditarPrototipoPeticion, PrototipoRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';

interface Props {
  readonly prototipo: Pick<PrototipoRespuesta, 'id' | 'clave' | 'niveles' | 'recamaras'>;
  readonly editable: boolean;
}

export function CeldasNivelesYRecamaras({ prototipo, editable }: Props) {
  // Solo lectura: sin hooks, así la tabla se pinta también fuera de un proveedor de consultas.
  if (!editable) {
    return (
      <>
        <td className="is-num tnum">{prototipo.niveles ?? '—'}</td>
        <td className="is-num tnum">{prototipo.recamaras ?? '—'}</td>
      </>
    );
  }
  return <CeldasEditables prototipo={prototipo} />;
}

function CeldasEditables({ prototipo }: Pick<Props, 'prototipo'>) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [recamaras, setRecamaras] = useState<string | null>(null);

  const editar = useEditarPrototipoApiV1PrototiposPrototipoIdPatch<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        setRecamaras(null);
        void queryClient.invalidateQueries({
          predicate: (consulta) => {
            const primera = consulta.queryKey[0];
            return typeof primera === 'string' && primera.includes('/api/v1/prototipos');
          },
        });
      },
      onError: (err) => {
        setRecamaras(null);
        setError(err.message);
      },
    },
  });

  function guardar(data: EditarPrototipoPeticion) {
    setError(null);
    editar.mutate({ prototipoId: prototipo.id, data });
  }

  const actual = prototipo.recamaras === null || prototipo.recamaras === undefined ? '' : String(prototipo.recamaras);

  function alTerminarRecamaras() {
    if (recamaras === null || recamaras === actual) {
      setRecamaras(null);
      return;
    }
    const numero = recamaras.trim() === '' ? null : Number(recamaras);
    if (numero !== null && (!Number.isInteger(numero) || numero < 0)) {
      setError('Las recámaras son un número entero, cero o más.');
      return;
    }
    guardar({ recamaras: numero });
  }

  return (
    <>
      <td className="is-num">
        <select
          className="select"
          aria-label={`Niveles de ${prototipo.clave}`}
          value={prototipo.niveles ?? ''}
          disabled={editar.isPending}
          onChange={(e) => guardar({ niveles: e.target.value === '' ? null : Number(e.target.value) })}
        >
          <option value="">—</option>
          <option value="1">1</option>
          <option value="2">2</option>
        </select>
      </td>
      <td className="is-num">
        <input
          className="input"
          type="number"
          min={0}
          step={1}
          style={{ width: '5rem' }}
          aria-label={`Recámaras de ${prototipo.clave}`}
          value={recamaras ?? actual}
          disabled={editar.isPending}
          onChange={(e) => setRecamaras(e.target.value)}
          onBlur={alTerminarRecamaras}
          onKeyDown={(e) => {
            if (e.key === 'Enter') e.currentTarget.blur();
          }}
        />
        {error && (
          <div className="text-xs" role="alert" style={{ color: 'var(--c-danger)' }}>
            {error}
          </div>
        )}
      </td>
    </>
  );
}
