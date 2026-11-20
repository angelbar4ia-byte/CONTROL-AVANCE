/**
 * La matriz de conceptos de la losa de una zona (fase 2 de las zonas de losa), dentro del panel de zonas de la pestaña Trazos.
 *
 * - El **tipo** (maciza o nervada) y el **uso** (entrepiso o azotea) de la losa de la zona; solo Control de obra los cambia.
 * - Los **elementos** de la zona (trabes, contratrabes, nervaduras): a mano (metros o piezas) o medidos de una **línea del plano** (la medida
 *   se deriva de la geometría y de la escala; se agregan desde el detalle de la línea elegida). Cada uno con su pago: «paga la losa» (como el
 *   catálogo) o «paga su concepto por ml» (colado y cimbra por ml, D8).
 * - La **matriz calculada** por el servidor: área, concreto, cimbra, acero, y los **conceptos que paga cada parte** con su cantidad. Los
 *   conceptos nuevos son **propuestos** con clave provisional (sin precio ni destajo con importe); Costos o Control de obra los proponen y solo
 *   Control de obra los autoriza (en la tarjeta del elemento, o con «Proponer los conceptos que faltan»).
 * - La **conciliación** del total de la zona contra un concepto del catálogo vigente (el catálogo no se edita).
 * - Por **espacio** (0143): cada elemento (y cada polígono de losa, desde su detalle) dice en qué espacio está; la matriz se reparte por espacio (la suma es
 *   el total de la zona) y cada concepto dice en qué partida del árbol se mide, o por qué no cuenta.
 *
 * No calcula nada: pinta lo que responde el servidor.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getMatrizDeLaZonaApiV1ZonasDeLosaZonaIdMatrizGetQueryKey,
  useAgregarElementoApiV1ZonasDeLosaZonaIdElementosPost,
  useCambiarElementoApiV1ElementosDeLosaElementoIdPut,
  useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet,
  useMatrizDeLaZonaApiV1ZonasDeLosaZonaIdMatrizGet,
  useProponerConceptosDeLaZonaApiV1ZonasDeLosaZonaIdMatrizProponerConceptosPost,
  useQuitarElementoApiV1ElementosDeLosaElementoIdDelete,
} from '@/api/generado/losas/losas';
import type { ElementoCalculado, Espacio, ZonaDeLosa } from '@/api/generado/modelo';
import { useCambiarZonaApiV1ZonasDeLosaZonaIdPut } from '@/api/generado/zonas-de-losa/zonas-de-losa';
import { queryClient } from '@/app/queryClient';

import { NOMBRE_DEL_ESTADO_DE_PARTIDA } from './espacios';
import { numeroTecleado } from './volumen';

function mensaje(err: unknown, defecto: string): string {
  return err instanceof Error ? err.message : defecto;
}

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const unidadVisible = (u: string) => (u === 'm3' ? 'm³' : u === 'm2' ? 'm²' : u);
const NOMBRE_DE_PARTE: Record<string, string> = { losa: 'Losa', acero: 'Acero', colado: 'Colado y cimbra' };
const MARCA: Record<string, { texto: string; clase: string }> = {
  '=': { texto: '=', clase: 'badge badge--ok' },
  '≈': { texto: '≈', clase: 'badge badge--info' },
  '≠': { texto: '≠', clase: 'badge badge--danger' },
  solo_catalogo: { texto: 'solo en el catálogo', clase: 'badge badge--danger' },
  solo_elemento: { texto: 'solo en la matriz', clase: 'badge badge--warn' },
};

function refrescar() {
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('zonas-de-losa') });
  // Los espacios cuentan lo que tienen asignado (elementos, losas, muros): cambia al agregar, mover o quitar un elemento.
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/espacios') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/biblioteca-de-elementos') });
}

interface Props {
  readonly zona: ZonaDeLosa;
  readonly puedeEditar: boolean;
  /** El rol de quien mira: Costos y Control de obra proponen los conceptos nuevos. */
  readonly rol: string | null;
  /** Los espacios de la obra (0143): con ellos cada elemento elige el suyo y la matriz se reparte por espacio. */
  readonly espacios?: readonly Espacio[];
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function MatrizDeLaZona({ zona, puedeEditar, rol, espacios = [], onCambio, onError }: Props) {
  const [abierta, setAbierta] = useState(false);
  return (
    <div className="zonas-losa__matriz" data-testid="matriz-de-la-zona" data-zona={zona.id}>
      <div className="row">
        <button
          type="button"
          className="btn btn--sm"
          aria-expanded={abierta}
          aria-label={`Matriz de conceptos de ${zona.nombre}`}
          onClick={() => setAbierta((v) => !v)}
        >
          {abierta ? 'Ocultar la matriz' : 'Matriz de conceptos'}
        </button>
        <span className="text-mute text-xs">
          Losa {zona.tipo_de_losa === 'nervada' ? 'nervada' : 'maciza'} · {zona.uso_de_losa === 'azotea' ? 'azotea' : 'entrepiso'}
        </span>
      </div>
      {abierta && <CuerpoDeLaMatriz zona={zona} puedeEditar={puedeEditar} rol={rol} espacios={espacios} onCambio={onCambio} onError={onError} />}
    </div>
  );
}

function CuerpoDeLaMatriz({ zona, puedeEditar, rol, espacios = [], onCambio, onError }: Props) {
  const [conciliar, setConciliar] = useState('');
  const [aConciliar, setAConciliar] = useState('');
  const consulta = useMatrizDeLaZonaApiV1ZonasDeLosaZonaIdMatrizGet(zona.id, aConciliar === '' ? undefined : { concepto_clave: aConciliar }, {
    query: { retry: false },
  });
  const ficha = useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet(zona.tipo_de_losa === 'nervada' ? 'LOSA-NERVADA' : 'LOSA-MACIZA');
  const cambiarZona = useCambiarZonaApiV1ZonasDeLosaZonaIdPut<ErrorApi>();
  const agregar = useAgregarElementoApiV1ZonasDeLosaZonaIdElementosPost<ErrorApi>();
  const cambiarElemento = useCambiarElementoApiV1ElementosDeLosaElementoIdPut<ErrorApi>();
  const quitar = useQuitarElementoApiV1ElementosDeLosaElementoIdDelete<ErrorApi>();
  const proponer = useProponerConceptosDeLaZonaApiV1ZonasDeLosaZonaIdMatrizProponerConceptosPost<ErrorApi>();
  const [clave, setClave] = useState('');
  const [modo, setModo] = useState<'ml' | 'pieza'>('ml');
  const [cantidad, setCantidad] = useState('10');
  const [largo, setLargo] = useState('4.00');
  const [pago, setPago] = useState<'en_la_losa' | 'propio'>('en_la_losa');
  const [espacioPorAgregar, setEspacioPorAgregar] = useState('');
  const m = consulta.data;
  const permitidos = ficha.data?.elementos_permitidos ?? [];
  const elegida = clave || permitidos[0]?.clave || '';

  async function guardarZona(cambio: { tipo_de_losa?: 'maciza' | 'nervada'; uso_de_losa?: 'entrepiso' | 'azotea' }) {
    try {
      await cambiarZona.mutateAsync({
        zonaId: zona.id,
        data: {
          nombre: zona.nombre, nivel: zona.nivel, cota_piso_m: zona.cota_piso_m, altura_libre_m: zona.altura_libre_m, espesor_m: zona.espesor_m,
          tipo_de_losa: cambio.tipo_de_losa ?? zona.tipo_de_losa, uso_de_losa: cambio.uso_de_losa ?? zona.uso_de_losa,
        },
      });
      refrescar();
      onCambio('Losa de la zona actualizada.');
    } catch (err) {
      onError(mensaje(err, 'No se pudo guardar el tipo de losa.'));
    }
  }

  async function agregarElemento() {
    const q = numeroTecleado(cantidad);
    const l = numeroTecleado(largo);
    if (elegida === '' || !(q > 0) || (modo === 'pieza' && !(l > 0))) {
      onError('Elige el elemento y captura una cantidad mayor que cero (y el largo de la pieza).');
      return;
    }
    try {
      await agregar.mutateAsync({
        zonaId: zona.id,
        data: { elemento_clave: elegida, modo, cantidad: q, largo_m: modo === 'pieza' ? l : null, pago, ...(espacioPorAgregar ? { espacio_id: espacioPorAgregar } : {}) },
      });
      refrescar();
      onCambio(`${elegida} agregado a la matriz de «${zona.nombre}».`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo agregar el elemento.'));
    }
  }

  async function cambiarElPago(e: ElementoCalculado, nuevo: 'en_la_losa' | 'propio') {
    if (!e.id) return;
    try {
      await cambiarElemento.mutateAsync({
        elementoId: e.id,
        data: {
          elemento_clave: e.clave, modo: e.modo, pago: nuevo, ...(e.espacio_id ? { espacio_id: e.espacio_id } : {}),
          ...(e.origen === 'trazo' && e.trazo_id ? { trazo_id: e.trazo_id } : { cantidad: e.cantidad, largo_m: e.largo_m }),
        },
      });
      refrescar();
    } catch (err) {
      onError(mensaje(err, 'No se pudo cambiar el pago del elemento.'));
    }
  }

  async function cambiarElEspacio(e: ElementoCalculado, nuevo: string) {
    if (!e.id) return;
    try {
      await cambiarElemento.mutateAsync({
        elementoId: e.id,
        data: {
          elemento_clave: e.clave, modo: e.modo, pago: e.pago, espacio_id: nuevo || null,
          ...(e.origen === 'trazo' && e.trazo_id ? { trazo_id: e.trazo_id } : { cantidad: e.cantidad, largo_m: e.largo_m }),
        },
      });
      refrescar();
      void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/cuantificacion') });
      onCambio(nuevo ? `${e.clave} asignado a su espacio.` : `${e.clave} quedó sin espacio.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo asignar el espacio del elemento.'));
    }
  }

  async function quitarElemento(e: ElementoCalculado) {
    if (!e.id) return;
    try {
      await quitar.mutateAsync({ elementoId: e.id });
      refrescar();
      onCambio(`${e.clave} quitado de la matriz.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo quitar el elemento.'));
    }
  }

  async function proponerFaltantes() {
    try {
      const r = await proponer.mutateAsync({ zonaId: zona.id });
      refrescar();
      void queryClient.invalidateQueries({ queryKey: getMatrizDeLaZonaApiV1ZonasDeLosaZonaIdMatrizGetQueryKey(zona.id) });
      onCambio(
        r.creadas.length > 0
          ? `Se propusieron ${r.creadas.length} concepto${r.creadas.length === 1 ? '' : 's'} nuevo${r.creadas.length === 1 ? '' : 's'} (clave provisional, sin precio).`
          : 'Todos los conceptos nuevos de la zona ya estaban propuestos.',
      );
    } catch (err) {
      onError(mensaje(err, 'No se pudieron proponer los conceptos.'));
    }
  }

  const sinProponer = (m?.conceptos ?? []).filter((c) => c.concepto.provisional && !c.propuesta);
  const puedeProponer = rol === 'control_obra' || rol === 'costos';

  return (
    <div className="zonas-losa__cuerpo" data-testid="cuerpo-de-la-matriz">
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <label className="mct__campo">
          Tipo de losa
          <select
            className="input"
            aria-label="Tipo de losa de la zona"
            value={zona.tipo_de_losa}
            disabled={!puedeEditar || cambiarZona.isPending}
            onChange={(e) => void guardarZona({ tipo_de_losa: e.target.value as 'maciza' | 'nervada' })}
          >
            <option value="maciza">Maciza</option>
            <option value="nervada">Nervada</option>
          </select>
        </label>
        <label className="mct__campo">
          Uso
          <select
            className="input"
            aria-label="Uso de la losa de la zona"
            value={zona.uso_de_losa}
            disabled={!puedeEditar || cambiarZona.isPending}
            onChange={(e) => void guardarZona({ uso_de_losa: e.target.value as 'entrepiso' | 'azotea' })}
          >
            <option value="entrepiso">Entrepiso</option>
            <option value="azotea">Azotea</option>
          </select>
        </label>
      </div>
      {consulta.isLoading && <p className="text-mute text-xs">Calculando la matriz…</p>}
      {consulta.isError && (
        <p className="text-xs" role="alert">
          {mensaje(consulta.error, 'No se pudo calcular la matriz de la zona.')}
        </p>
      )}
      {m && (
        <>
          {m.escala_definida === false && (
            <p className="text-mute text-xs">El plano no tiene escala calibrada: se toma 1 unidad de plano = 1 m para las áreas y las longitudes.</p>
          )}
          <p className="text-sm" data-testid="matriz-resumen">
            Área {num(m.area_m2)} m² · concreto de la losa {num(m.concreto.con_desperdicio_m3, 3)} m³ <span className="mono">{m.concreto.clave}</span> · cimbra{' '}
            {num(m.cimbra.m2)} m²
          </p>
          <div className="zonas-losa__elementos" aria-label="Elementos de la zona" data-testid="elementos-de-la-zona">
            {m.elementos.length === 0 && <p className="text-mute text-xs">La zona no tiene trabes, contratrabes ni nervaduras.</p>}
            {m.elementos.map((e) => (
              <div key={e.id ?? e.clave} className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }} data-testid="elemento-de-la-zona" data-elemento={e.clave}>
                <span className="mono">{e.clave}</span>
                <span className="text-xs">
                  {e.modo === 'ml' ? `${num(e.cantidad)} ml` : `${num(e.cantidad, 0)} pza de ${num(e.largo_m)} m`}
                  {e.origen === 'trazo' && ` · de la línea del plano (${num(e.longitud_del_trazo_m)} m)`}
                </span>
                <select
                  className="input"
                  aria-label={`Pago de ${e.clave}`}
                  value={e.pago}
                  disabled={!puedeEditar || cambiarElemento.isPending}
                  onChange={(ev) => void cambiarElPago(e, ev.target.value as 'en_la_losa' | 'propio')}
                >
                  <option value="en_la_losa">paga la losa</option>
                  <option value="propio">paga su concepto por ml</option>
                </select>
                {(espacios.length > 0 || e.espacio_id) && (
                  <select
                    className="input"
                    aria-label={`Espacio de ${e.clave}`}
                    value={e.espacio_id ?? ''}
                    disabled={!puedeEditar || cambiarElemento.isPending}
                    onChange={(ev) => void cambiarElEspacio(e, ev.target.value)}
                  >
                    <option value="">sin espacio</option>
                    {espacios.map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.nombre}
                      </option>
                    ))}
                  </select>
                )}
                {puedeEditar && (
                  <button type="button" className="btn btn--sm" aria-label={`Quitar ${e.clave} de la matriz`} onClick={() => void quitarElemento(e)}>
                    Quitar
                  </button>
                )}
              </div>
            ))}
          </div>
          {puedeEditar && (
            <div className="zonas-losa__form" role="group" aria-label="Agregar un elemento a la zona">
              <select className="input" aria-label="Elemento por agregar" value={elegida} onChange={(e) => setClave(e.target.value)}>
                {permitidos.map((x) => (
                  <option key={x.clave} value={x.clave}>
                    {x.clave}
                  </option>
                ))}
              </select>
              <select className="input" aria-label="Se mide por" value={modo} onChange={(e) => setModo(e.target.value as 'ml' | 'pieza')}>
                <option value="ml">ml de trazo</option>
                <option value="pieza">piezas</option>
              </select>
              <input className="input" inputMode="decimal" aria-label="Cantidad del elemento" value={cantidad} onChange={(e) => setCantidad(e.target.value)} />
              {modo === 'pieza' && (
                <input className="input" inputMode="decimal" aria-label="Largo de la pieza" value={largo} onChange={(e) => setLargo(e.target.value)} />
              )}
              <select className="input" aria-label="Pago del elemento por agregar" value={pago} onChange={(e) => setPago(e.target.value as 'en_la_losa' | 'propio')}>
                <option value="en_la_losa">paga la losa</option>
                <option value="propio">paga su concepto por ml</option>
              </select>
              {espacios.length > 0 && (
                <select className="input" aria-label="Espacio del elemento por agregar" value={espacioPorAgregar} onChange={(e) => setEspacioPorAgregar(e.target.value)}>
                  <option value="">sin espacio</option>
                  {espacios.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.nombre}
                    </option>
                  ))}
                </select>
              )}
              <button type="button" className="btn btn--sm btn--primary" disabled={agregar.isPending} onClick={() => void agregarElemento()}>
                Agregar elemento
              </button>
              <p className="text-mute text-xs">También se puede medir con una línea del plano: elige la línea y usa «Medir un elemento de losa» en su detalle.</p>
            </div>
          )}
          <table className="table" aria-label="Conceptos de la matriz de la zona" data-testid="conceptos-de-la-zona">
            <thead>
              <tr>
                <th>Parte</th>
                <th>Concepto</th>
                <th>Cantidad</th>
              </tr>
            </thead>
            <tbody>
              {m.conceptos.map((c, i) => (
                <tr key={`${c.concepto.clave}-${i}`} data-concepto={c.concepto.clave} data-parte={c.parte} data-estado={c.propuesta?.estado ?? (c.concepto.provisional ? 'sin_proponer' : 'catalogo')}>
                  <td>
                    {NOMBRE_DE_PARTE[c.parte] ?? c.parte}
                    {c.parte !== 'losa' && <div className="text-mute text-xs mono">{c.elemento_clave}</div>}
                  </td>
                  <td>
                    <span className="mono">{c.concepto.clave}</span>{' '}
                    {c.concepto.provisional ? (
                      <span className={c.propuesta?.estado === 'autorizada' ? 'badge badge--ok' : 'badge badge--warn'}>
                        {c.propuesta ? (c.propuesta.estado === 'autorizada' ? `autorizado · versión ${c.propuesta.version ?? 1}` : 'propuesto · pendiente') : 'sin proponer · clave provisional'}
                      </span>
                    ) : (
                      <span className="badge badge--ok">del catálogo</span>
                    )}
                    <div className="text-mute text-xs">{c.concepto.descripcion}</div>
                  </td>
                  <td className="mono">
                    {num(c.cantidad)} {unidadVisible(c.unidad)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {(m.por_espacio ?? []).some((g) => g.espacio_id) && (
            <div data-testid="matriz-por-espacio">
              <p className="text-xs">
                Por espacio: cada polígono y cada elemento está en un solo espacio, así que la suma de los espacios es el total de la zona. Solo cuenta en el
                presupuesto lo asignado a un espacio, con concepto del catálogo y partida en el árbol.
              </p>
              <table className="table" aria-label="Matriz de la zona por espacio">
                <thead>
                  <tr>
                    <th>Espacio</th>
                    <th>Concepto</th>
                    <th>Cantidad</th>
                    <th>Partida</th>
                  </tr>
                </thead>
                <tbody>
                  {(m.por_espacio ?? []).flatMap((g) =>
                    g.conceptos
                      .filter((c) => c.cantidad > 0)
                      .map((c, i) => (
                        <tr
                          key={`${g.espacio_id ?? 'sin'}-${c.concepto.clave}-${c.elemento_clave}-${i}`}
                          data-espacio={g.espacio_nombre ?? 'sin espacio'}
                          data-concepto={c.concepto.clave}
                          data-estado-de-partida={c.resolucion?.estado ?? ''}
                        >
                          <td>{g.espacio_nombre ?? 'sin espacio'}</td>
                          <td className="mono">{c.concepto.clave}</td>
                          <td className="mono">
                            {num(c.cantidad)} {unidadVisible(c.unidad)}
                          </td>
                          <td>
                            {c.resolucion?.cuenta ? (
                              <span className="badge badge--ok">{c.resolucion.partida_nombre ?? 'partida del árbol'}</span>
                            ) : (
                              <span className="badge badge--warn" title={c.resolucion?.aviso ?? undefined}>
                                {NOMBRE_DEL_ESTADO_DE_PARTIDA[c.resolucion?.estado ?? ''] ?? 'sin resolver'}
                              </span>
                            )}
                          </td>
                        </tr>
                      )),
                  )}
                </tbody>
              </table>
            </div>
          )}
          {puedeProponer && sinProponer.length > 0 && (
            <button type="button" className="btn btn--sm" disabled={proponer.isPending} onClick={() => void proponerFaltantes()}>
              Proponer los conceptos que faltan ({sinProponer.length})
            </button>
          )}
          <p className="text-mute text-xs" data-testid="matriz-sin-mano-de-obra">
            {m.mano_de_obra.nota}
          </p>
          {m.advertencias.map((a) => (
            <p key={a} className="text-mute text-xs">
              {a}
            </p>
          ))}
          <div className="zonas-losa__form" role="group" aria-label="Conciliar con el catálogo">
            <label className="mct__campo" title="Una clave del catálogo vigente, p. ej. EST-21011: se compara el total de la zona con el lote del catálogo.">
              Conciliar con un concepto del catálogo
              <input className="input" aria-label="Clave del concepto del catálogo" value={conciliar} onChange={(e) => setConciliar(e.target.value)} />
            </label>
            <button type="button" className="btn btn--sm" onClick={() => setAConciliar(conciliar.trim().toUpperCase())}>
              Conciliar
            </button>
            {aConciliar !== '' && (
              <button
                type="button"
                className="btn btn--sm"
                onClick={() => {
                  setAConciliar('');
                  setConciliar('');
                }}
              >
                Quitar la conciliación
              </button>
            )}
          </div>
          {m.conciliacion && (
            <div data-testid="conciliacion-de-la-zona" data-concepto-conciliado={m.conciliacion.concepto.clave}>
              <p className="text-xs">
                Contra <span className="mono">{m.conciliacion.concepto.clave}</span> {m.conciliacion.concepto.descripcion}. {m.conciliacion.nota}
              </p>
              <table className="table" aria-label="Conciliación de la zona con el catálogo">
                <thead>
                  <tr>
                    <th>Insumo</th>
                    <th>Catálogo</th>
                    <th>Zona</th>
                    <th>Marca</th>
                  </tr>
                </thead>
                <tbody>
                  {m.conciliacion.filas.map((f) => {
                    const marca = MARCA[f.marca] ?? { texto: f.marca, clase: 'badge' };
                    return (
                      <tr key={f.clave} data-marca={f.marca}>
                        <td>
                          <span className="mono">{f.clave}</span> {f.descripcion}
                        </td>
                        <td className="mono">{f.catalogo === null || f.catalogo === undefined ? '—' : num(f.catalogo, 3)}</td>
                        <td className="mono">{f.elemento === null || f.elemento === undefined ? '—' : num(f.elemento, 3)}</td>
                        <td>
                          <span className={marca.clase}>{marca.texto}</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
