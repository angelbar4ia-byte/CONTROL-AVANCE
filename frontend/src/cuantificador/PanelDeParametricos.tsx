/**
 * Los elementos paramétricos (D-602, D-604): castillo, trabe o cadena, zapata y losa. Cada uno es una pieza con sus
 * medidas, su armado y sus estribos; de **una muestra** salen concreto, acero, estribos, alambre de amarre y cimbra
 * (la receta, que calcula el servidor). Son del catálogo de la organización: Control de obra y Costos los definen.
 *
 * **Sin botones de guardar**: cada parámetro llega a la API al salir del campo o al dar Enter, y la receta se rehace.
 * Pendiente (D-603): el diseño de la cimbra como sub-elemento (forro, usos), y que un concepto «tome» una parte.
 */

import { Trash2 } from 'lucide-react';
import { useState, type KeyboardEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getListarElementosParametricosApiV1ElementosParametricosGetQueryKey,
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
import { CAMPOS_POR_TIPO, NOMBRE_DEL_TIPO, formatoDeReceta, lineasDeReceta, type TipoParametrico } from './parametricos';
import { numeroTecleado } from './volumen';

interface Props {
  /** El plano elegido: de él salen los totales de lo colocado. */
  readonly planoId: string;
  readonly puedeDefinir: boolean;
  readonly onCambio: (aviso?: string) => void;
  readonly onError: (mensaje: string) => void;
}

function enEnter(e: KeyboardEvent<HTMLInputElement>) {
  if (e.key === 'Enter') e.currentTarget.blur();
}

export function PanelDeParametricos({ planoId, puedeDefinir, onCambio, onError }: Props) {
  const consulta = useListarElementosParametricosApiV1ElementosParametricosGet();
  const delPlano = useElementosDelPlanoApiV1PlanosPlanoIdElementosParametricosGet(planoId, { query: { enabled: planoId !== '' } });
  const conceptosDelPlano = useConceptosDelPlanoApiV1PlanosPlanoIdElementosParametricosConceptosGet(planoId, { query: { enabled: planoId !== '' } });
  const crear = useCrearElementoParametricoApiV1ElementosParametricosPost<ErrorApi>();
  const actualizar = useActualizarElementoParametricoApiV1ElementosParametricosElementoIdPatch<ErrorApi>();
  const eliminar = useEliminarElementoParametricoApiV1ElementosParametricosElementoIdDelete<ErrorApi>();
  const [nuevo, setNuevo] = useState({ clave: '', nombre: '', tipo: 'castillo' as TipoParametrico });
  const [editando, setEditando] = useState<Readonly<Record<string, string>>>({});
  const [abierto, setAbierto] = useState<string | null>(null);

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
      const r = await crear.mutateAsync({ data: { clave: nuevo.clave.trim(), nombre: nuevo.nombre.trim(), tipo: nuevo.tipo } });
      setNuevo({ clave: '', nombre: '', tipo: nuevo.tipo });
      setAbierto(r.id);
      recargar();
      onCambio(`${nuevo.clave.trim().toUpperCase()} creado con las medidas por defecto: ajústalas.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear el elemento.');
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
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 6 }}>
        {elementos.map((e) => {
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
                </button>
                <span className="badge badge--outline">{NOMBRE_DEL_TIPO[tipo]}</span>
                {puedeDefinir && (
                  <button type="button" className="btn btn--ghost btn--sm" aria-label={`Borrar ${e.clave}`} onClick={() => void borrar(e)}>
                    <Trash2 size={12} aria-hidden />
                  </button>
                )}
              </div>
              {abiertoAhora && (
                <>
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
            onChange={(ev) => setNuevo((n) => ({ ...n, tipo: ev.target.value as TipoParametrico }))}
          >
            {(Object.keys(NOMBRE_DEL_TIPO) as TipoParametrico[]).map((t) => (
              <option key={t} value={t}>
                {NOMBRE_DEL_TIPO[t]}
              </option>
            ))}
          </select>
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
