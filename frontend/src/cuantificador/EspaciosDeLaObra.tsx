/**
 * La capa «espacio» (0143, D-565/D-566): el cuarto o área (recámara 1, baño, cochera…) donde se asignan zonas de losa, muros y elementos.
 *
 * - `PanelDeEspacios`: los espacios de la obra con lo que tiene asignado cada uno (muros, losas, elementos y ramas del árbol); Control de obra los
 *   crea y los borra, los demás roles leen.
 * - `EspacioDelTrazo`: en el detalle del trazo elegido: un polígono de losa se asigna a un espacio; un muro se asigna a un espacio o se COMPARTE entre dos
 *   (mitad y mitad por omisión, o un % para el principal). El muro se traza una vez y el servidor reparte su cantidad sin contarla dos veces.
 *
 * No calcula nada: pinta lo que responde el servidor.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { queryClient } from '@/app/queryClient';
import {
  useAsignarEspacioAlTrazoApiV1TrazosTrazoIdEspacioPut,
  useBorrarEspacioApiV1EspaciosEspacioIdDelete,
  useCrearEspacioApiV1ObrasObraIdEspaciosPost,
  useEspacioDelTrazoApiV1TrazosTrazoIdEspacioGet,
  useEspaciosDeLaObraApiV1ObrasObraIdEspaciosGet,
} from '@/api/generado/espacios/espacios';
import type { Espacio } from '@/api/generado/modelo';

import {
  NOMBRE_DE_TIPO_DE_ESPACIO,
  TIPOS_DE_ESPACIO,
  type TipoDeEspacio,
  repartoTecleado,
  textoDelReparto,
} from './espacios';

function mensaje(err: unknown, defecto: string): string {
  return err instanceof Error ? err.message : defecto;
}

/** Lo que cambia al tocar un espacio o una asignación: los espacios, los trazos del plano, las zonas y sus matrices, y lo medido. */
function refrescarTodo() {
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/espacios') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/trazos') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('zonas-de-losa') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/cuantificacion') });
}

/** Los espacios de la obra (la misma consulta para el panel, el detalle del trazo y la matriz de la zona). */
export function useEspaciosDeLaObra(obraId: string): readonly Espacio[] {
  const consulta = useEspaciosDeLaObraApiV1ObrasObraIdEspaciosGet(obraId, { query: { enabled: obraId !== '' } });
  return consulta.data ?? [];
}

interface PanelProps {
  readonly obraId: string;
  readonly puedeEditar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function PanelDeEspacios({ obraId, puedeEditar, onCambio, onError }: PanelProps) {
  const espacios = useEspaciosDeLaObra(obraId);
  const crear = useCrearEspacioApiV1ObrasObraIdEspaciosPost<ErrorApi>();
  const borrar = useBorrarEspacioApiV1EspaciosEspacioIdDelete<ErrorApi>();
  const [nombre, setNombre] = useState('');
  const [tipo, setTipo] = useState<TipoDeEspacio>('recamara');

  async function agregar() {
    const limpio = nombre.trim();
    if (limpio === '') {
      onError('Captura el nombre del espacio.');
      return;
    }
    try {
      await crear.mutateAsync({ obraId, data: { nombre: limpio, tipo } });
      setNombre('');
      refrescarTodo();
      onCambio(`Espacio «${limpio}» creado.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo crear el espacio.'));
    }
  }

  async function quitar(e: Espacio) {
    try {
      await borrar.mutateAsync({ espacioId: e.id });
      refrescarTodo();
      onCambio(`Espacio «${e.nombre}» borrado: lo que tenía asignado queda sin espacio.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo borrar el espacio.'));
    }
  }

  return (
    <section className="zonas-losa" aria-label="Espacios de la obra" data-testid="espacios-de-la-obra">
      <div className="estacion__subencabezado">
        <span className="estacion__subtitulo">Espacios</span>
      </div>
      <p className="text-mute text-xs">
        Un espacio (recámara, baño, cochera…) es donde se asignan las losas, los muros y los elementos: cada uno se mide en la partida de su espacio, sin contarse dos
        veces.{!puedeEditar && ' Solo Control de obra los edita.'}
      </p>
      {espacios.length === 0 && <div className="text-mute text-sm">Esta obra no tiene espacios.</div>}
      {espacios.map((e) => (
        <div key={e.id} className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }} data-testid="espacio" data-espacio={e.nombre}>
          <strong>{e.nombre}</strong>
          <span className="badge badge--outline">{NOMBRE_DE_TIPO_DE_ESPACIO[e.tipo as TipoDeEspacio] ?? e.tipo}</span>
          <span className="text-mute text-xs">
            {e.muros} {e.muros === 1 ? 'muro' : 'muros'} · {e.losas} {e.losas === 1 ? 'losa' : 'losas'} · {e.elementos}{' '}
            {e.elementos === 1 ? 'elemento' : 'elementos'}
          </span>
          {puedeEditar && (
            <button type="button" className="btn btn--sm" aria-label={`Borrar el espacio ${e.nombre}`} onClick={() => void quitar(e)}>
              Borrar
            </button>
          )}
        </div>
      ))}
      {puedeEditar && (
        <div className="zonas-losa__form" role="group" aria-label="Nuevo espacio">
          <label className="mct__campo">
            Nombre del espacio
            <input className="input" aria-label="Nombre del espacio" value={nombre} onChange={(ev) => setNombre(ev.target.value)} />
          </label>
          <label className="mct__campo">
            Tipo
            <select className="input" aria-label="Tipo de espacio" value={tipo} onChange={(ev) => setTipo(ev.target.value as TipoDeEspacio)}>
              {TIPOS_DE_ESPACIO.map((t) => (
                <option key={t} value={t}>
                  {NOMBRE_DE_TIPO_DE_ESPACIO[t]}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn--sm btn--primary" disabled={crear.isPending} onClick={() => void agregar()}>
            Agregar espacio
          </button>
        </div>
      )}
    </section>
  );
}

interface TrazoProps {
  readonly obraId: string;
  readonly trazoId: string;
  /** Un muro puede compartirse entre dos espacios; un polígono de losa solo se asigna a uno. */
  readonly esMuro: boolean;
  readonly puedeEditar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

/** En el detalle del trazo elegido: a qué espacio pertenece (un muro, también con quién se comparte y cómo se reparte). */
export function EspacioDelTrazo({ obraId, trazoId, esMuro, puedeEditar, onCambio, onError }: TrazoProps) {
  const espacios = useEspaciosDeLaObra(obraId);
  const consulta = useEspacioDelTrazoApiV1TrazosTrazoIdEspacioGet(trazoId);
  const asignar = useAsignarEspacioAlTrazoApiV1TrazosTrazoIdEspacioPut<ErrorApi>();
  const [reparto, setReparto] = useState('');
  const a = consulta.data;
  if (!a || (espacios.length === 0 && !a.espacio_id)) return null;
  const principal = a.espacio_id ?? '';
  const comparte = a.espacio_comparte_id ?? '';

  async function poner(cambio: { espacio_id?: string | null; espacio_comparte_id?: string | null; reparto_pct?: string | null }, aviso: string) {
    try {
      await asignar.mutateAsync({
        trazoId,
        data: { espacio_id: cambio.espacio_id ?? null, espacio_comparte_id: cambio.espacio_comparte_id ?? null, reparto_pct: cambio.reparto_pct ?? null },
      });
      refrescarTodo();
      onCambio(aviso);
    } catch (err) {
      onError(mensaje(err, 'No se pudo asignar el espacio.'));
    }
  }

  function guardarReparto() {
    const pct = repartoTecleado(reparto);
    if (reparto.trim() !== '' && pct === null) {
      onError('El reparto del espacio principal va de más de 0 a menos de 100 %.');
      return;
    }
    void poner(
      { espacio_id: principal, espacio_comparte_id: comparte, reparto_pct: pct === null ? null : String(pct) },
      pct === null ? 'El muro se reparte mitad y mitad.' : `El muro se reparte: ${pct} % del espacio principal.`,
    );
  }

  return (
    <div className="zonas-losa__trazo" data-testid="espacio-del-trazo">
      <div className="opciones__titulo">{esMuro ? 'Espacio del muro' : 'Espacio de la losa'}</div>
      <label className="mct__campo">
        {esMuro ? 'Espacio' : 'Espacio de esta losa'}
        <select
          className="input"
          aria-label="Espacio del trazo"
          value={principal}
          disabled={!puedeEditar || asignar.isPending}
          onChange={(e) =>
            void poner(
              { espacio_id: e.target.value || null, espacio_comparte_id: e.target.value && e.target.value !== comparte ? comparte || null : null },
              e.target.value ? 'Espacio asignado.' : 'El trazo quedó sin espacio.',
            )
          }
        >
          <option value="">Sin espacio</option>
          {espacios.map((e) => (
            <option key={e.id} value={e.id}>
              {e.nombre}
            </option>
          ))}
        </select>
      </label>
      {esMuro && principal !== '' && (
        <>
          <label className="mct__campo" title="El muro se traza una vez y su cantidad se reparte entre los dos espacios sin contarse dos veces.">
            Compartido con
            <select
              className="input"
              aria-label="Muro compartido con"
              value={comparte}
              disabled={!puedeEditar || asignar.isPending}
              onChange={(e) =>
                void poner(
                  { espacio_id: principal, espacio_comparte_id: e.target.value || null },
                  e.target.value ? 'El muro se comparte: mitad y mitad.' : 'El muro ya no se comparte.',
                )
              }
            >
              <option value="">No se comparte</option>
              {espacios
                .filter((e) => e.id !== principal)
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.nombre}
                  </option>
                ))}
            </select>
          </label>
          {comparte !== '' && puedeEditar && (
            <div className="row" style={{ gap: 6, alignItems: 'end' }}>
              <label className="mct__campo">
                % del espacio principal
                <input
                  className="input"
                  inputMode="decimal"
                  aria-label="Reparto del espacio principal en por ciento"
                  placeholder={a.reparto_pct ? String(Number(a.reparto_pct)) : '50'}
                  value={reparto}
                  onChange={(e) => setReparto(e.target.value)}
                />
              </label>
              <button type="button" className="btn btn--sm" disabled={asignar.isPending} onClick={guardarReparto}>
                Guardar reparto
              </button>
            </div>
          )}
        </>
      )}
      <p className="text-xs" data-testid="reparto-del-trazo">
        {a.reparto.length === 0 ? 'Sin espacio: cuenta como siempre.' : `Cuenta en: ${textoDelReparto(espacios, a.reparto)}.`}
      </p>
    </div>
  );
}
