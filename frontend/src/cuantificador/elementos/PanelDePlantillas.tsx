/**
 * El panel izquierdo de la pestaña «Artefacto»: las plantillas de muro vigentes y, aparte, los prototipos del muro confinado (una
 * plantilla por prototipo y planta, y las globales de 1 y 2 plantas). La que se elige se edita en el área de trabajo; un prototipo
 * sin plantilla es estructura vacía que se captura con «Capturar».
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getListarPlantillasApiV1MuroPlantillasGetQueryKey,
  getPrototiposDeMuroApiV1MuroArtefactoPrototiposGetQueryKey,
  useCargarEjemplosDePrototipoApiV1MuroPlantillasEjemplosDePrototipoPost,
  useListarPlantillasApiV1MuroPlantillasGet,
  usePrototiposDeMuroApiV1MuroArtefactoPrototiposGet,
} from '@/api/generado/artefacto-de-muros/artefacto-de-muros';
import { queryClient } from '@/app/queryClient';

import { esPlantillaNueva, PLANTILLA_NUEVA, plantillaNuevaDe, type Planta } from './plantillaDeMuro';

export { PLANTILLA_NUEVA };

interface Props {
  readonly elegida: string | null;
  readonly onElegir: (id: string) => void;
  readonly puedeCrear: boolean;
}

export function PanelDePlantillas({ elegida, onElegir, puedeCrear }: Props) {
  const consulta = useListarPlantillasApiV1MuroPlantillasGet();
  const prototipos = usePrototiposDeMuroApiV1MuroArtefactoPrototiposGet();
  const cargar = useCargarEjemplosDePrototipoApiV1MuroPlantillasEjemplosDePrototipoPost<ErrorApi>();
  const [aviso, setAviso] = useState<string | null>(null);

  async function cargarEjemplos() {
    setAviso(null);
    try {
      const r = await cargar.mutateAsync();
      void queryClient.invalidateQueries({ queryKey: getListarPlantillasApiV1MuroPlantillasGetQueryKey() });
      void queryClient.invalidateQueries({ queryKey: getPrototiposDeMuroApiV1MuroArtefactoPrototiposGetQueryKey() });
      const partes = [
        r.creadas.length > 0 ? `Se crearon ${r.creadas.length} plantillas de ejemplo, por confirmar.` : null,
        r.omitidas.length > 0 ? `${r.omitidas.length} ya existían.` : null,
        ...r.faltan.map((f) => `«${f.plantilla}» no se creó: faltan en tu catálogo ${f.elementos.join(', ')}.`),
      ].filter(Boolean);
      setAviso(partes.join(' ') || 'No hay nada que cargar.');
    } catch (e) {
      setAviso(e instanceof Error ? e.message : 'No se pudieron cargar los ejemplos.');
    }
  }

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
              <span style={{ display: 'flex', gap: 4 }}>
                {p.por_confirmar && <span className="badge badge--outline">por confirmar</span>}
                <span className={p.validacion === 'validada' ? 'badge badge--ok' : 'badge badge--warn'}>
                  {p.validacion === 'validada' ? `v${p.version}` : 'por validar'}
                </span>
              </span>
            </button>
          </li>
        ))}
      </ul>

      <div role="group" aria-label="Prototipos del muro confinado" style={{ display: 'grid', gap: 6, marginTop: 6 }}>
        <div className="opciones__titulo">Prototipos (muro confinado)</div>
        <p className="text-mute text-xs" style={{ margin: 0 }}>
          Sin plano estructural, la plantilla del prototipo propone los castillos. Las plantas se infieren del subcapítulo «planta alta» del Excel.
        </p>
        {puedeCrear && (
          <button type="button" className="btn btn--sm" disabled={cargar.isPending} onClick={() => void cargarEjemplos()}>
            Cargar los ejemplos (Oro y global)
          </button>
        )}
        {aviso && (
          <p className="text-xs" role="status" data-testid="aviso-de-ejemplos" style={{ margin: 0 }}>
            {aviso}
          </p>
        )}
        {(prototipos.data ?? []).map((pr) => (
          <div key={pr.clave} data-prototipo={pr.clave} style={{ display: 'grid', gap: 3 }}>
            <strong className="text-sm">
              {pr.nombre} <span className="text-mute text-xs">{pr.plantas === 1 ? '1 planta' : '2 plantas'}</span>
            </strong>
            {pr.plantillas.map((x) => {
              const rotulo = x.planta ?? (pr.es_global ? 'Global' : '');
              return x.plantilla_id ? (
                <button
                  key={x.planta ?? 'global'}
                  type="button"
                  className={elegida === x.plantilla_id ? 'chip is-active' : 'chip'}
                  style={{ width: '100%', justifyContent: 'space-between', display: 'flex', gap: 8 }}
                  aria-current={elegida === x.plantilla_id ? 'true' : undefined}
                  aria-label={`${pr.nombre} ${rotulo}: abrir la plantilla`}
                  onClick={() => onElegir(x.plantilla_id as string)}
                >
                  <span>{rotulo}</span>
                  {x.por_confirmar && <span className="badge badge--outline">por confirmar</span>}
                </button>
              ) : (
                <div key={x.planta ?? 'global'} style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                  <span className="text-mute text-xs">{rotulo || 'Global'} · sin capturar</span>
                  {puedeCrear && (
                    <button
                      type="button"
                      className={esPlantillaNueva(elegida) && elegida === plantillaNuevaDe(pr.clave, (x.planta ?? null) as Planta | null) ? 'btn btn--sm is-active' : 'btn btn--sm'}
                      aria-label={`Capturar ${pr.nombre} ${rotulo}`}
                      onClick={() => onElegir(plantillaNuevaDe(pr.clave, (x.planta ?? null) as Planta | null))}
                    >
                      Capturar
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </nav>
  );
}
