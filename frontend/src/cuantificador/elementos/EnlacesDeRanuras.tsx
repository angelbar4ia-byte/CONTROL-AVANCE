/**
 * El enlace de ranuras con el árbol de la obra (Ola 4B). Una ranura es un concepto que un elemento o una plantilla necesita; aquí se
 * enlaza, en esta obra y por capa (nivel, etapa, ubicación), con un concepto que ya existe en el catálogo. Gana la capa más
 * específica. Si el árbol de la obra no trae la partida, la ranura avisa y NO cuenta. No se inventa ningún concepto, precio ni destajo.
 * Costos y Control de obra enlazan; los demás roles ven la tabla en solo lectura. El servidor resuelve y valida.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useBibliotecaDeElementosApiV1BibliotecaDeElementosGet } from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { EnlaceDeRanuraRespuesta } from '@/api/generado/modelo';
import {
  getEnlacesDeRanuraApiV1ObrasObraIdEnlacesDeRanuraGetQueryKey,
  useEnlacesDeRanuraApiV1ObrasObraIdEnlacesDeRanuraGet,
  useEnlazarRanuraApiV1ObrasObraIdEnlacesDeRanuraPut,
  useQuitarEnlaceApiV1ObrasObraIdEnlacesDeRanuraEnlaceIdDelete,
} from '@/api/generado/parametrico/parametrico';
import { queryClient } from '@/app/queryClient';

interface Props {
  readonly obraId: string;
  readonly puedeEditar: boolean;
}

const UBICACIONES: ReadonlyArray<readonly [string, string]> = [
  ['interior', 'Interior'],
  ['fachada_a', 'Fachada A'],
  ['fachada_b', 'Fachada B'],
  ['pretil', 'Pretil'],
  ['barda', 'Barda'],
];
const PARTES: ReadonlyArray<readonly [string, string]> = [
  ['acero', 'Acero'],
  ['colado', 'Colado y cimbra'],
  ['completo', 'Completo (acero, colado y cimbra)'],
];
const nombreDeUbicacion = (u: string | null | undefined) => UBICACIONES.find(([k]) => k === u)?.[1] ?? u ?? null;

function nombreDeRanura(ranura: string): string {
  const [tipo, a, b] = ranura.split(':');
  if (tipo === 'elemento') return `Elemento ${a} · ${PARTES.find(([k]) => k === b)?.[1] ?? b}`;
  if (tipo === 'mamposteria') return `Mampostería · ${(a ?? '').replace(/_/g, ' ')}`;
  return `Acabado ${a} · cara ${b}`;
}

export function EnlacesDeRanuras({ obraId, puedeEditar }: Props) {
  const consulta = useEnlacesDeRanuraApiV1ObrasObraIdEnlacesDeRanuraGet(obraId, { query: { enabled: obraId !== '' } });
  const biblioteca = useBibliotecaDeElementosApiV1BibliotecaDeElementosGet();
  const enlazar = useEnlazarRanuraApiV1ObrasObraIdEnlacesDeRanuraPut<ErrorApi>();
  const quitar = useQuitarEnlaceApiV1ObrasObraIdEnlacesDeRanuraEnlaceIdDelete<ErrorApi>();
  const [grupo, setGrupo] = useState<'plantilla' | 'elemento'>('plantilla');
  const [plantilla, setPlantilla] = useState('');
  const [elemento, setElemento] = useState('');
  const [parte, setParte] = useState('acero');
  const [concepto, setConcepto] = useState('');
  const [nivel, setNivel] = useState('');
  const [etapa, setEtapa] = useState('');
  const [ubicacion, setUbicacion] = useState('');
  const [error, setError] = useState<string | null>(null);

  const datos = consulta.data;
  const enlaces: readonly EnlaceDeRanuraRespuesta[] = datos?.enlaces ?? [];
  const ranurasDePlantilla = datos?.ranuras_de_plantilla ?? [];
  const elementos = (biblioteca.data ?? []).flatMap((c) => c.subcategorias.flatMap((s) => s.elementos));
  const nombreDeCapa = (id: string | null | undefined, lista: ReadonlyArray<{ id: string; clave: string; descripcion: string }>) =>
    id ? (lista.find((x) => x.id === id)?.descripcion ?? lista.find((x) => x.id === id)?.clave ?? id) : null;

  const ranura = grupo === 'plantilla' ? plantilla : elemento ? `elemento:${elemento}:${parte}` : '';
  const sugerido = ranurasDePlantilla.find((r) => r.ranura === plantilla)?.sugerido_clave ?? null;

  const recargar = () => queryClient.invalidateQueries({ queryKey: getEnlacesDeRanuraApiV1ObrasObraIdEnlacesDeRanuraGetQueryKey(obraId) });
  async function intentar(accion: () => Promise<unknown>) {
    setError(null);
    try {
      await accion();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar el enlace.');
    }
    await recargar();
  }

  const falta = enlaces.filter((e) => !e.cuenta).length;
  return (
    <section className="mct__bloque" aria-label="Enlace de ranuras con el Presupuesto" data-enlaces-de-ranura>
      <h3>Enlace de ranuras con el Presupuesto</h3>
      <p className="text-mute text-xs">
        Cada ranura (el concepto que un elemento o una plantilla necesita) se enlaza con un concepto del catálogo en esta obra, por nivel,
        etapa o ubicación; si varios enlaces aplican, gana el más específico. Si el árbol de la obra no trae la partida, la ranura avisa y no
        cuenta. Aquí no se crean conceptos: lo que falta se crea en el árbol o en el catálogo y luego se enlaza.
      </p>
      {error && (
        <p className="mct__error" role="alert">
          {error}
        </p>
      )}
      {falta > 0 && (
        <p className="mct__aviso" role="status">
          {falta === 1 ? '1 enlace no cuenta' : `${falta} enlaces no cuentan`}: falta la partida en el árbol de la obra.
        </p>
      )}
      {consulta.isLoading ? (
        <p className="text-mute text-sm">Cargando los enlaces…</p>
      ) : enlaces.length === 0 ? (
        <p className="text-mute text-sm">Esta obra no tiene enlaces de ranura: los elementos usan sus conceptos por defecto.</p>
      ) : (
        <div className="mct__tabla-caja">
          <table className="mct__tabla" aria-label="Enlaces de ranura de la obra">
            <thead>
              <tr>
                <th>Ranura</th>
                <th>Capa</th>
                <th>Concepto del Presupuesto</th>
                <th>Estado</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {enlaces.map((e) => {
                const capa = [
                  nombreDeCapa(e.capa.nivel_id, datos?.niveles ?? []),
                  nombreDeCapa(e.capa.etapa_id, datos?.etapas ?? []),
                  nombreDeUbicacion(e.capa.ubicacion),
                ].filter(Boolean);
                return (
                  <tr key={e.id} data-enlace={e.ranura} data-estado={e.estado}>
                    <td>
                      {nombreDeRanura(e.ranura)}
                      <div className="text-mute text-xs mono">{e.ranura}</div>
                    </td>
                    <td>{capa.length > 0 ? capa.join(' · ') : 'Cualquiera'}</td>
                    <td>
                      <b className="mono">{e.concepto_clave}</b> · {e.concepto_descripcion}
                      {e.unidad ? ` (${e.unidad})` : ''}
                    </td>
                    <td>
                      {e.cuenta ? (
                        <span className="badge badge--ok">enlazado{e.partida_nombre ? ` · ${e.partida_nombre}` : ''}</span>
                      ) : (
                        <>
                          <span className="badge badge--warn">falta la partida · no cuenta</span>
                          {e.aviso && <div className="text-xs mct__aviso">{e.aviso}</div>}
                        </>
                      )}
                    </td>
                    <td>
                      {puedeEditar && (
                        <button
                          type="button"
                          className="btn btn--sm"
                          aria-label={`Quitar el enlace de ${e.ranura}`}
                          onClick={() => void intentar(() => quitar.mutateAsync({ obraId, enlaceId: e.id }))}
                        >
                          ×
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {puedeEditar && (
        <div className="mct__parametros" role="group" aria-label="Enlazar una ranura">
          <label className="mct__campo">
            Qué se enlaza
            <select className="input" value={grupo} onChange={(e) => setGrupo(e.target.value as 'plantilla' | 'elemento')}>
              <option value="plantilla">Mampostería o acabado de una plantilla</option>
              <option value="elemento">Un elemento de la biblioteca</option>
            </select>
          </label>
          {grupo === 'plantilla' ? (
            <label className="mct__campo">
              Ranura
              <select className="input" value={plantilla} onChange={(e) => setPlantilla(e.target.value)}>
                <option value="">— elige —</option>
                {ranurasDePlantilla.map((r) => (
                  <option key={r.ranura} value={r.ranura}>
                    {r.nombre}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <>
              <label className="mct__campo">
                Elemento
                <select className="input" value={elemento} onChange={(e) => setElemento(e.target.value)}>
                  <option value="">— elige —</option>
                  {elementos.map((x) => (
                    <option key={x.clave} value={x.clave}>
                      {x.clave} · {x.nombre}
                    </option>
                  ))}
                </select>
              </label>
              <label className="mct__campo">
                Parte
                <select className="input" value={parte} onChange={(e) => setParte(e.target.value)}>
                  {PARTES.map(([k, n]) => (
                    <option key={k} value={k}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          <label className="mct__campo">
            Concepto (clave del catálogo)
            <input
              className="input"
              list="conceptos-del-arbol"
              value={concepto}
              onChange={(e) => setConcepto(e.target.value.toUpperCase())}
              placeholder="EST-02010"
            />
          </label>
          <datalist id="conceptos-del-arbol">
            {(datos?.conceptos_del_arbol ?? []).map((c) => (
              <option key={c.clave} value={c.clave}>
                {c.descripcion}
              </option>
            ))}
          </datalist>
          {sugerido && concepto !== sugerido && (
            <button type="button" className="btn btn--sm" onClick={() => setConcepto(sugerido)}>
              Usar {sugerido} (propuesto por la especificación)
            </button>
          )}
          <label className="mct__campo">
            Nivel
            <select className="input" value={nivel} onChange={(e) => setNivel(e.target.value)}>
              <option value="">Cualquiera</option>
              {(datos?.niveles ?? []).map((n) => (
                <option key={n.id} value={n.id}>
                  {n.descripcion}
                </option>
              ))}
            </select>
          </label>
          <label className="mct__campo">
            Etapa
            <select className="input" value={etapa} onChange={(e) => setEtapa(e.target.value)}>
              <option value="">Cualquiera</option>
              {(datos?.etapas ?? []).map((n) => (
                <option key={n.id} value={n.id}>
                  {n.descripcion}
                </option>
              ))}
            </select>
          </label>
          <label className="mct__campo">
            Ubicación
            <select className="input" value={ubicacion} onChange={(e) => setUbicacion(e.target.value)}>
              <option value="">Cualquiera</option>
              {UBICACIONES.map(([k, n]) => (
                <option key={k} value={k}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <div className="mct__par">
            <button
              type="button"
              className="btn btn--primary btn--sm"
              disabled={ranura === '' || concepto.trim() === '' || enlazar.isPending}
              onClick={() =>
                void intentar(async () => {
                  await enlazar.mutateAsync({
                    obraId,
                    data: {
                      ranura,
                      concepto_clave: concepto.trim(),
                      nivel_id: nivel || null,
                      etapa_id: etapa || null,
                      ubicacion: ubicacion || null,
                    },
                  });
                  setConcepto('');
                })
              }
            >
              Enlazar
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
