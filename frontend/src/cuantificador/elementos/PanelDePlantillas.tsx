/** El panel izquierdo de la pestaña «Artefacto»: las plantillas de muro vigentes. La que se elige se edita en el área de trabajo. */

import { useListarPlantillasApiV1MuroPlantillasGet } from '@/api/generado/artefacto-de-muros/artefacto-de-muros';

export const PLANTILLA_NUEVA = 'nueva';

interface Props {
  readonly elegida: string | null;
  readonly onElegir: (id: string) => void;
  readonly puedeCrear: boolean;
}

export function PanelDePlantillas({ elegida, onElegir, puedeCrear }: Props) {
  const consulta = useListarPlantillasApiV1MuroPlantillasGet();
  if (consulta.isLoading)
    return (
      <p className="text-mute text-sm" style={{ padding: 10 }}>
        Cargando las plantillas…
      </p>
    );
  if (consulta.isError)
    return (
      <p className="text-sm" style={{ padding: 10 }} role="alert">
        No se pudieron cargar las plantillas de muro.
      </p>
    );
  const plantillas = consulta.data ?? [];
  return (
    <nav aria-label="Plantillas de muro" style={{ padding: 10, display: 'grid', gap: 8, alignContent: 'start' }}>
      {puedeCrear && (
        <button
          type="button"
          className={elegida === PLANTILLA_NUEVA ? 'btn is-active' : 'btn'}
          aria-pressed={elegida === PLANTILLA_NUEVA}
          onClick={() => onElegir(PLANTILLA_NUEVA)}
        >
          + Nueva plantilla
        </button>
      )}
      {plantillas.length === 0 && <p className="text-mute text-sm">Aún no hay plantillas de muro.</p>}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 4 }}>
        {plantillas.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              className={elegida === p.id ? 'chip is-active' : 'chip'}
              style={{ width: '100%', justifyContent: 'space-between', display: 'flex', gap: 8 }}
              aria-current={elegida === p.id ? 'true' : undefined}
              onClick={() => onElegir(p.id)}
            >
              <span>{p.nombre}</span>
              <span className={p.validacion === 'validada' ? 'badge badge--ok' : 'badge badge--warn'}>
                {p.validacion === 'validada' ? `v${p.version}` : 'por validar'}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
