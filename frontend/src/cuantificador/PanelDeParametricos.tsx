/**
 * Los elementos paramétricos (D-602, D-604): castillo, trabe o cadena, zapata y losa. Cada uno es una pieza con sus
 * medidas, su armado y sus estribos; de **una muestra** salen concreto, acero, estribos, alambre de amarre y cimbra
 * (la receta, que calcula el servidor). Son del catálogo de la organización: Control de obra y Costos los definen.
 *
 * **Sin botones de guardar**: cada parámetro llega a la API al salir del campo o al dar Enter, y la receta se rehace.
 * Pendiente (D-603): el diseño de la cimbra como sub-elemento (forro, usos), y que un concepto «tome» una parte.
 */

import { Trash2 } from 'lucide-react';
import { useEffect, useState, type KeyboardEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getListarElementosParametricosApiV1ElementosParametricosGetQueryKey,
  useClasificacionDeElementosApiV1ElementosParametricosClasificacionGet,
  useConceptosDelPlanoApiV1PlanosPlanoIdElementosParametricosConceptosGet,
  useElementosDelPlanoApiV1PlanosPlanoIdElementosParametricosGet,
  useActualizarElementoParametricoApiV1ElementosParametricosElementoIdPatch,
  useCrearElementoParametricoApiV1ElementosParametricosPost,
  useEliminarElementoParametricoApiV1ElementosParametricosElementoIdDelete,
  useListarElementosParametricosApiV1ElementosParametricosGet,
} from '@/api/generado/elementos-parametricos/elementos-parametricos';
import type { ElementoParametricoRespuesta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

import { ConceptosDelElemento } from './ConceptosDelElemento';
import { ConceptosPorContexto } from './ConceptosPorContexto';
import { InsumosDelElemento } from './InsumosDelElemento';
import {
  CAMPOS_POR_TIPO,
  NOMBRE_DEL_TIPO,
  categoriasDelTipo,
  formatoDeReceta,
  lineasDeReceta,
  rotuloDeUso,
  type TipoParametrico,
} from './parametricos';
import { numeroTecleado } from './volumen';

interface Props {
  /** El plano elegido: de él salen los totales de lo colocado. */
  readonly planoId: string;
  readonly puedeDefinir: boolean;
  readonly onCambio: (aviso?: string) => void;
  readonly onError: (mensaje: string) => void;
  /** «Colocar este elemento»: elige la herramienta y marca lo que se trace como este elemento (D-604). */
  readonly onColocar?: (elemento: { id: string; clave: string; tipo: TipoParametrico }) => void;
  /** El elemento que se está colocando, si hay uno. */
  readonly colocandoId?: string | null;
  /** Un elemento que debe aparecer abierto (desde «Ver el elemento» del detalle del trazo). */
  readonly abrirId?: string | null;
}

function enEnter(e: KeyboardEvent<HTMLInputElement>) {
  if (e.key === 'Enter') e.currentTarget.blur();
}

export function PanelDeParametricos({ planoId, puedeDefinir, onCambio, onError, onColocar, colocandoId = null, abrirId = null }: Props) {
  const consulta = useListarElementosParametricosApiV1ElementosParametricosGet();
  const delPlano = useElementosDelPlanoApiV1PlanosPlanoIdElementosParametricosGet(planoId, { query: { enabled: planoId !== '' } });
  const conceptosDelPlano = useConceptosDelPlanoApiV1PlanosPlanoIdElementosParametricosConceptosGet(planoId, { query: { enabled: planoId !== '' } });
  const crear = useCrearElementoParametricoApiV1ElementosParametricosPost<ErrorApi>();
  const actualizar = useActualizarElementoParametricoApiV1ElementosParametricosElementoIdPatch<ErrorApi>();
  const eliminar = useEliminarElementoParametricoApiV1ElementosParametricosElementoIdDelete<ErrorApi>();
  const clasificacion = useClasificacionDeElementosApiV1ElementosParametricosClasificacionGet();
  const categorias = clasificacion.data ?? [];
  // Categoría y subcategoría vacías: el servidor usa las de defecto del tipo (castillos/muro, cadenas/cerramiento…).
  const [nuevo, setNuevo] = useState({ clave: '', nombre: '', tipo: 'castillo' as TipoParametrico, categoria: '', subcategoria: '' });
  const [editando, setEditando] = useState<Readonly<Record<string, string>>>({});
  const [abierto, setAbierto] = useState<string | null>(null);
  const [buscar, setBuscar] = useState('');
  useEffect(() => {
    if (abrirId) setAbierto(abrirId);
  }, [abrirId]);

  const elementos = consulta.data ?? [];
  const recargar = () =>
    void queryClient.invalidateQueries({ queryKey: getListarElementosParametricosApiV1ElementosParametricosGetQueryKey() });

  async function ponerParametro(e: ElementoParametricoRespuesta, clave: string) {
    const llave = `${e.id}:${clave}`;
    const texto = editando[llave];
    if (texto === undefined) return;
    setEditando(({ [llave]: _quitado, ...resto }) => resto);
    const valor = numeroTecleado(texto);
    if (!Number.isFinite(valor) || valor === Number(e.parametros[clave])) return;
    try {
      await actualizar.mutateAsync({ elementoId: e.id, data: { parametros: { [clave]: valor } } });
      recargar();
      onCambio();
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar el parámetro.');
    }
  }

  async function crearElemento() {
    if (nuevo.clave.trim() === '' || nuevo.nombre.trim() === '') return;
    try {
      const r = await crear.mutateAsync({
        data: {
          clave: nuevo.clave.trim(),
          nombre: nuevo.nombre.trim(),
          tipo: nuevo.tipo,
          ...(nuevo.categoria !== '' ? { categoria: nuevo.categoria } : {}),
          ...(nuevo.categoria !== '' && nuevo.subcategoria !== '' ? { subcategoria: nuevo.subcategoria } : {}),
        },
      });
      setNuevo({ clave: '', nombre: '', tipo: nuevo.tipo, categoria: nuevo.categoria, subcategoria: nuevo.subcategoria });
      setAbierto(r.id);
      recargar();
      onCambio(`${nuevo.clave.trim().toUpperCase()} creado con las medidas por defecto: ajústalas.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear el elemento.');
    }
  }

  async function reclasificar(e: ElementoParametricoRespuesta, categoria: string, subcategoria: string) {
    if (categoria === e.categoria && subcategoria === e.subcategoria) return;
    try {
      await actualizar.mutateAsync({ elementoId: e.id, data: { categoria, subcategoria } });
      recargar();
      onCambio(`${e.clave} pasó a ${rotuloDeUso(categorias, categoria, subcategoria)}.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar la clasificación.');
    }
  }

  async function borrar(e: ElementoParametricoRespuesta) {
    if (!window.confirm(`¿Borrar ${e.clave}?`)) return;
    try {
      await eliminar.mutateAsync({ elementoId: e.id });
      recargar();
      onCambio(`${e.clave} borrado.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo borrar el elemento.');
    }
  }

  return (
    <section aria-label="Elementos paramétricos" style={{ display: 'grid', gap: 6, padding: '8px' }}>
      <h3 className="text-sm" style={{ margin: 0 }}>
        Elementos paramétricos
      </h3>
      <p className="text-mute text-xs" style={{ margin: 0 }}>
        Una pieza con sus medidas y su armado: de una muestra salen concreto, acero, estribos, alambre y cimbra. La cimbra se
        da por número de lados (un castillo aislado lleva 4, junto a un vano 3, en un muro continuo 2).
      </p>
      {(delPlano.data?.totales.length ?? 0) > 0 && (
        <div role="group" aria-label="Lo colocado en este plano" style={{ display: 'grid', gap: 2 }}>
          <div className="text-xs text-mute">En este plano</div>
          {delPlano.data?.totales.map((t) => (
            <div key={t.elemento_id} className="text-xs" data-colocado={t.clave}>
              <span className="mono">{t.clave}</span> · {t.colocados} {t.colocados === 1 ? 'trazo' : 'trazos'} · {formatoDeReceta(t.cantidad, 2)} {t.unidad}
              {' — '}concreto {formatoDeReceta(t.concreto_m3, 3)} m³ · acero {formatoDeReceta(t.acero_kg, 1)} kg · estribos {formatoDeReceta(t.estribos_kg, 1)} kg · alambre{' '}
              {formatoDeReceta(t.alambre_kg, 2)} kg · cimbra {formatoDeReceta(t.cimbra_m2, 2)} m²
            </div>
          ))}
          {(conceptosDelPlano.data ?? []).map((c) => (
            <div key={`${c.elemento_id}:${c.concepto_id}`} className="text-xs text-mute" data-concepto-del-plano={c.clave}>
              <span className="mono">{c.clave}</span> · {formatoDeReceta(c.cantidad, 2)} {c.unidad}
              {' — '}
              {Object.entries(c.materiales)
                .map(([m, v]) => `${m} ${formatoDeReceta(v.cantidad, 2)} ${v.unidad}`)
                .join(' · ')}
            </div>
          ))}
        </div>
      )}
      {elementos.length === 0 && !consulta.isLoading && <div className="text-mute text-xs">Aún no hay elementos paramétricos.</div>}
      {elementos.length > 3 && (
        <input
          className="input"
          type="search"
          aria-label="Buscar elemento"
          placeholder="Buscar elemento"
          value={buscar}
          onChange={(e) => setBuscar(e.target.value)}
        />
      )}
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
        {elementos.filter((e) => `${e.clave} ${e.nombre}`.toLowerCase().includes(buscar.trim().toLowerCase())).map((e) => {
          const tipo = e.tipo as TipoParametrico;
          const abiertoAhora = abierto === e.id;
          return (
            <li key={e.id} data-parametrico={e.clave} style={{ display: 'grid', gap: 4 }}>
              <div className="row">
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  aria-expanded={abiertoAhora}
                  aria-label={`${abiertoAhora ? 'Ocultar' : 'Ver'} ${e.clave}`}
                  onClick={() => setAbierto(abiertoAhora ? null : e.id)}
                >
                  <span className="mono">{e.clave}</span> · {e.nombre}
                  {(e as { version?: number }).version !== undefined && (e as { version?: number }).version! > 1 && (
                    <span className="badge badge--outline" title="Versión del elemento: las obras asignadas conservan la anterior (D-639)">v{(e as { version?: number }).version}</span>
                  )}
                </button>
                <span className="badge badge--outline">{NOMBRE_DEL_TIPO[tipo]}</span>
                <span className="badge badge--outline" data-uso-del-elemento={e.clave} title="Categoría › subcategoría de la biblioteca: el uso forma parte de la identidad del elemento">
                  {rotuloDeUso(categorias, e.categoria, e.subcategoria)}
                </span>
                {onColocar && (
                  <button
                    type="button"
                    className={colocandoId === e.id ? 'chip is-active' : 'chip'}
                    aria-pressed={colocandoId === e.id}
                    aria-label={`Colocar ${e.clave} en el plano`}
                    title="Traza con la herramienta que le toca: cada trazo nace marcado como este elemento. Esc termina."
                    onClick={() => onColocar({ id: e.id, clave: e.clave, tipo })}
                  >
                    {colocandoId === e.id ? 'Colocando…' : 'Colocar'}
                  </button>
                )}
                {puedeDefinir && (
                  <button type="button" className="btn btn--ghost btn--sm" aria-label={`Borrar ${e.clave}`} onClick={() => void borrar(e)}>
                    <Trash2 size={12} aria-hidden />
                  </button>
                )}
              </div>
              {abiertoAhora && (
                <>
                  {puedeDefinir && (
                    <div className="arbol-edicion__alta" role="group" aria-label={`Clasificación de ${e.clave}`}>
                      <select
                        aria-label={`Categoría de ${e.clave}`}
                        value={e.categoria}
                        onChange={(ev) => void reclasificar(e, ev.target.value, '')}
                      >
                        {categoriasDelTipo(categorias, e.tipo).map((c) => (
                          <option key={c.clave} value={c.clave}>
                            {c.nombre}
                          </option>
                        ))}
                      </select>
                      <select
                        aria-label={`Subcategoría de ${e.clave}`}
                        value={e.subcategoria}
                        onChange={(ev) => void reclasificar(e, e.categoria, ev.target.value)}
                      >
                        {(categorias.find((c) => c.clave === e.categoria)?.subcategorias ?? []).map((sc) => (
                          <option key={sc.clave} value={sc.clave}>
                            {sc.nombre}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div className="arbol-edicion__alta" role="group" aria-label={`Parámetros de ${e.clave}`}>
                    {CAMPOS_POR_TIPO[tipo].map((c) => {
                      const llave = `${e.id}:${c.clave}`;
                      return (
                        <label key={c.clave} className="text-xs text-mute" style={{ display: 'grid', gap: 2 }}>
                          {c.etiqueta}
                          {c.unidad ? ` (${c.unidad})` : ''}
                          <input
                            aria-label={`${c.etiqueta} de ${e.clave}`}
                            inputMode="decimal"
                            style={{ width: 64 }}
                            disabled={!puedeDefinir}
                            value={editando[llave] ?? String(e.parametros[c.clave] ?? '')}
                            onChange={(ev) => setEditando((a) => ({ ...a, [llave]: ev.target.value }))}
                            onBlur={() => void ponerParametro(e, c.clave)}
                            onKeyDown={enEnter}
                          />
                        </label>
                      );
                    })}
                  </div>
                  <dl style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 8px' }} aria-label={`Receta de ${e.clave}`}>
                    {lineasDeReceta(e.receta).map(([rotulo, texto]) => (
                      <div key={rotulo} style={{ display: 'contents' }}>
                        <dt className="text-mute text-xs">{rotulo}</dt>
                        <dd className="text-xs" style={{ margin: 0 }}>
                          {texto}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <ConceptosDelElemento
                    elementoId={e.id}
                    clave={e.clave}
                    unidades={tipo === 'castillo' ? ['pza', 'ml'] : tipo === 'lineal' ? ['ml'] : tipo === 'losa' ? ['m²'] : ['pza']}
                    puedeDefinir={puedeDefinir}
                    onCambio={(aviso) => onCambio(aviso)}
                    onError={onError}
                  />
                  <ConceptosPorContexto elementoId={e.id} clave={e.clave} />
                  <InsumosDelElemento
                    elementoId={e.id}
                    clave={e.clave}
                    tipo={tipo}
                    materiales={e.materiales as Record<string, unknown>}
                    puedeDefinir={puedeDefinir}
                    onCambio={(aviso) => onCambio(aviso)}
                    onError={onError}
                  />
                </>
              )}
            </li>
          );
        })}
      </ul>
      {puedeDefinir && (
        <div className="arbol-edicion__alta" role="group" aria-label="Nuevo elemento paramétrico">
          <select
            aria-label="Tipo de elemento paramétrico"
            value={nuevo.tipo}
            onChange={(ev) => setNuevo((n) => ({ ...n, tipo: ev.target.value as TipoParametrico, categoria: '', subcategoria: '' }))}
          >
            {(Object.keys(NOMBRE_DEL_TIPO) as TipoParametrico[]).map((t) => (
              <option key={t} value={t}>
                {NOMBRE_DEL_TIPO[t]}
              </option>
            ))}
          </select>
          <select
            aria-label="Categoría del elemento nuevo"
            value={nuevo.categoria}
            onChange={(ev) => setNuevo((n) => ({ ...n, categoria: ev.target.value, subcategoria: '' }))}
          >
            <option value="">Categoría por defecto</option>
            {categoriasDelTipo(categorias, nuevo.tipo).map((c) => (
              <option key={c.clave} value={c.clave}>
                {c.nombre}
              </option>
            ))}
          </select>
          {nuevo.categoria !== '' && (
            <select
              aria-label="Subcategoría del elemento nuevo"
              value={nuevo.subcategoria}
              onChange={(ev) => setNuevo((n) => ({ ...n, subcategoria: ev.target.value }))}
            >
              <option value="">Primera subcategoría</option>
              {(categorias.find((c) => c.clave === nuevo.categoria)?.subcategorias ?? []).map((sc) => (
                <option key={sc.clave} value={sc.clave}>
                  {sc.nombre}
                </option>
              ))}
            </select>
          )}
          <input aria-label="Clave del elemento" placeholder="Clave (K-1)" style={{ width: 70 }} value={nuevo.clave} onChange={(ev) => setNuevo((n) => ({ ...n, clave: ev.target.value }))} />
          <input
            aria-label="Nombre del elemento"
            placeholder="Nombre · Intro crea"
            value={nuevo.nombre}
            onChange={(ev) => setNuevo((n) => ({ ...n, nombre: ev.target.value }))}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter') void crearElemento();
            }}
          />
          <button type="button" className="btn btn--sm" disabled={crear.isPending || nuevo.clave.trim() === '' || nuevo.nombre.trim() === ''} onClick={() => void crearElemento()}>
            Crear
          </button>
        </div>
      )}
    </section>
  );
}
