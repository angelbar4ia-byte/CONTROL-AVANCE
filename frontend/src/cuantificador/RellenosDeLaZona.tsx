/**
 * Los rellenos de una zona de losa (Fase 3), dentro del panel de zonas de la pestaña Trazos: el relleno es un elemento SEPARADO de la losa.
 *
 * - Cada relleno (de azotea con el concepto ALB-03014 del catálogo, o compactado con el concepto nuevo propuesto EJ-810) cubre **toda la zona** o **un
 *   polígono** de su losa (medición derivada: el área sale del polígono y de la escala del plano). Un elemento no cubre dos veces lo mismo.
 * - Sus parámetros son editables (espesor mínimo, pendiente y recorrido, adaptarse a los espesores de losa distintos, abundamiento o mortero); solo Control
 *   de obra los cambia.
 * - Cada relleno dice en qué **espacio** está (0143); si no, cada polígono cae en el suyo. Cada concepto dice en qué **partida** del árbol se mide o por qué no
 *   cuenta, y la suma de los espacios es el total del relleno (sin doble conteo).
 * - El relleno de azotea se **concilia** contra la composición vigente de ALB-03014 por m² (el catálogo no se edita).
 *
 * No calcula nada: pinta lo que responde el servidor.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import type { Espacio, RellenoDeLaZonaCalculado, RellenoDeLaZonaPeticion, ZonaDeLosa } from '@/api/generado/modelo';
import {
  getCalculoDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosCalculoGetQueryKey,
  useAgregarRellenoApiV1ZonasDeLosaZonaIdRellenosPost,
  useCalculoDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosCalculoGet,
  useCambiarRellenoApiV1RellenosDeZonaRellenoIdPut,
  useProponerConceptosDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosPropuestasPost,
  useQuitarRellenoApiV1RellenosDeZonaRellenoIdDelete,
} from '@/api/generado/rellenos/rellenos';
import { queryClient } from '@/app/queryClient';

import { NOMBRE_DEL_ESTADO_DE_PARTIDA } from './espacios';

function mensaje(err: unknown, defecto: string): string {
  return err instanceof Error ? err.message : defecto;
}

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const unidadVisible = (u: string) => (u === 'm3' ? 'm³' : u === 'm2' ? 'm²' : u);
const MARCA: Record<string, { texto: string; clase: string }> = {
  '=': { texto: '=', clase: 'badge badge--ok' },
  '≈': { texto: '≈', clase: 'badge badge--info' },
  '≠': { texto: '≠', clase: 'badge badge--danger' },
  solo_catalogo: { texto: 'solo en el catálogo', clase: 'badge badge--danger' },
  solo_elemento: { texto: 'solo en el relleno', clase: 'badge badge--warn' },
};
const CLAVES = ['REL-AZOTEA', 'REL-COMPACTADO'] as const;
const NOMBRE_DEL_RELLENO: Record<string, string> = { 'REL-AZOTEA': 'Relleno de azotea', 'REL-COMPACTADO': 'Relleno compactado' };

function refrescar() {
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('zonas-de-losa') });
  // Los espacios cuentan lo que tienen asignado y las partidas reciben lo medido: cambian al agregar, mover o quitar un relleno.
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/espacios') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/cuantificacion') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/biblioteca-de-elementos') });
}

/** Un campo numérico: vacío = el de omisión del elemento (`undefined`); lo que no es un número válido, `null`. */
function opcional(texto: string): number | undefined | null {
  if (texto.trim() === '') return undefined;
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) && n >= 0 ? n : null;
}

interface Props {
  readonly zona: ZonaDeLosa;
  readonly puedeEditar: boolean;
  /** El rol de quien mira: Costos y Control de obra proponen el concepto nuevo del compactado. */
  readonly rol: string | null;
  /** Los espacios de la obra (0143): cada relleno elige el suyo. */
  readonly espacios?: readonly Espacio[];
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function RellenosDeLaZona({ zona, puedeEditar, rol, espacios = [], onCambio, onError }: Props) {
  const [abierta, setAbierta] = useState(false);
  return (
    <div className="zonas-losa__rellenos" data-testid="rellenos-de-la-zona" data-zona={zona.id}>
      <div className="row">
        <button type="button" className="btn btn--sm" aria-expanded={abierta} aria-label={`Rellenos de ${zona.nombre}`} onClick={() => setAbierta((v) => !v)}>
          {abierta ? 'Ocultar los rellenos' : 'Rellenos'}
        </button>
        <span className="text-mute text-xs">Elemento separado de la losa</span>
      </div>
      {abierta && <CuerpoDeLosRellenos zona={zona} puedeEditar={puedeEditar} rol={rol} espacios={espacios} onCambio={onCambio} onError={onError} />}
    </div>
  );
}

function CuerpoDeLosRellenos({ zona, puedeEditar, rol, espacios = [], onCambio, onError }: Props) {
  const consulta = useCalculoDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosCalculoGet(zona.id, { conciliar: true }, { query: { retry: false } });
  const agregar = useAgregarRellenoApiV1ZonasDeLosaZonaIdRellenosPost<ErrorApi>();
  const proponer = useProponerConceptosDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosPropuestasPost<ErrorApi>();
  const [clave, setClave] = useState<(typeof CLAVES)[number]>('REL-AZOTEA');
  const [cubre, setCubre] = useState('');
  const [espacio, setEspacio] = useState('');
  const c = consulta.data;
  const puedeProponer = rol === 'control_obra' || rol === 'costos';
  const sinProponer = (c?.rellenos ?? []).flatMap((r) => r.conceptos).filter((k) => k.concepto.provisional && !k.propuesta);

  async function agregarRelleno() {
    try {
      const datos: RellenoDeLaZonaPeticion = { elemento_clave: clave, ...(cubre ? { trazo_id: cubre } : {}), ...(espacio ? { espacio_id: espacio } : {}) };
      await agregar.mutateAsync({ zonaId: zona.id, data: datos });
      refrescar();
      onCambio(`${NOMBRE_DEL_RELLENO[clave]} agregado a la zona.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo agregar el relleno.'));
    }
  }

  async function proponerFaltantes() {
    try {
      const r = await proponer.mutateAsync({ zonaId: zona.id });
      refrescar();
      void queryClient.invalidateQueries({ queryKey: getCalculoDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosCalculoGetQueryKey(zona.id, { conciliar: true }) });
      onCambio(r.creadas.length > 0 ? 'Se propuso el concepto nuevo del relleno compactado (clave provisional, sin precio).' : 'El concepto del relleno ya estaba propuesto.');
    } catch (err) {
      onError(mensaje(err, 'No se pudo proponer el concepto.'));
    }
  }

  return (
    <div className="zonas-losa__cuerpo" data-testid="cuerpo-de-los-rellenos">
      {consulta.isLoading && <p className="text-mute text-xs">Calculando los rellenos…</p>}
      {consulta.isError && (
        <p className="text-xs" role="alert">
          {mensaje(consulta.error, 'No se pudo calcular los rellenos de la zona.')}
        </p>
      )}
      {c && c.rellenos.length === 0 && <p className="text-mute text-xs">La zona no tiene rellenos. Agrega uno: la losa no lo incluye.</p>}
      {c?.advertencias.map((a) => (
        <p key={a} className="text-xs" role="alert">
          {a}
        </p>
      ))}
      {c?.rellenos.map((r, i) => (
        <FilaDelRelleno key={r.id} r={r} numero={i + 1} zona={zona} puedeEditar={puedeEditar} espacios={espacios} onCambio={onCambio} onError={onError} />
      ))}
      {c && c.rellenos.length > 0 && (
        <p className="text-sm" data-testid="rellenos-resumen">
          Total: área {num(c.totales.area_m2)} m² · volumen {num(c.totales.volumen_m3, 3)} m³ ·{' '}
          {c.totales.conceptos.map((k) => `${k.concepto.clave} ${num(k.cantidad)} ${unidadVisible(k.unidad)}`).join(' · ')}
        </p>
      )}
      {c && c.por_espacio.length > 0 && (
        <div className="mct__tabla-caja">
          <table className="table" aria-label="Lo que paga el relleno de cada espacio">
            <thead>
              <tr>
                <th>Espacio</th>
                <th>Concepto</th>
                <th>Cantidad</th>
                <th>Partida</th>
              </tr>
            </thead>
            <tbody>
              {c.por_espacio.flatMap((g) =>
                g.conceptos.map((k) => (
                  <tr key={`${g.espacio_id ?? 'sin'}-${k.concepto.clave}`} data-espacio={g.espacio_nombre ?? 'sin espacio'} data-concepto={k.concepto.clave} data-estado-de-partida={k.resolucion?.estado ?? ''}>
                    <td>{g.espacio_nombre ?? 'sin espacio'}</td>
                    <td className="mono">{k.concepto.clave}</td>
                    <td className="mono">
                      {num(k.cantidad)} {unidadVisible(k.unidad)}
                    </td>
                    <td>
                      {k.resolucion?.cuenta ? (
                        <span className="badge badge--ok">{k.resolucion.partida_nombre ?? 'partida del árbol'}</span>
                      ) : (
                        <span className="badge badge--warn" title={k.resolucion?.aviso ?? undefined}>
                          {NOMBRE_DEL_ESTADO_DE_PARTIDA[k.resolucion?.estado ?? ''] ?? 'sin resolver'}
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
          Proponer el concepto del relleno compactado
        </button>
      )}
      {puedeEditar && (
        <div className="zonas-losa__form" role="group" aria-label="Agregar un relleno a la zona">
          <label className="mct__campo">
            Relleno
            <select className="input" aria-label="Elemento del relleno" value={clave} onChange={(e) => setClave(e.target.value as (typeof CLAVES)[number])}>
              {CLAVES.map((k) => (
                <option key={k} value={k}>
                  {k} · {NOMBRE_DEL_RELLENO[k]}
                </option>
              ))}
            </select>
          </label>
          <label className="mct__campo">
            Cubre
            <select className="input" aria-label="Lo que cubre el relleno" value={cubre} onChange={(e) => setCubre(e.target.value)}>
              <option value="">Toda la zona</option>
              {zona.losas.map((lo, n) => (
                <option key={lo.trazo_id} value={lo.trazo_id}>
                  Polígono {n + 1}
                  {lo.espesor_propio_m != null ? ` (subzona ${lo.espesor_m} m)` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="mct__campo">
            Espacio
            <select className="input" aria-label="Espacio del relleno" value={espacio} onChange={(e) => setEspacio(e.target.value)}>
              <option value="">El de cada polígono</option>
              {espacios.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nombre}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn--sm" disabled={agregar.isPending} onClick={() => void agregarRelleno()}>
            Agregar el relleno
          </button>
        </div>
      )}
    </div>
  );
}

function FilaDelRelleno({
  r, numero, zona, puedeEditar, espacios = [], onCambio, onError,
}: {
  readonly r: RellenoDeLaZonaCalculado;
  readonly numero: number;
  readonly zona: ZonaDeLosa;
  readonly puedeEditar: boolean;
  readonly espacios?: readonly Espacio[];
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}) {
  const cambiar = useCambiarRellenoApiV1RellenosDeZonaRellenoIdPut<ErrorApi>();
  const quitar = useQuitarRellenoApiV1RellenosDeZonaRellenoIdDelete<ErrorApi>();
  const compactado = r.tipo === 'compactado';
  const p = r.parametros;
  const [espesor, setEspesor] = useState(String(p.espesor_m));
  const [pendiente, setPendiente] = useState(String(p.pendiente_pct));
  const [recorrido, setRecorrido] = useState(String(p.recorrido_m));
  const [abundamiento, setAbundamiento] = useState(String(p.abundamiento_pct));
  const [mortero, setMortero] = useState(String(p.mortero_m3_por_m2));
  const [compensar, setCompensar] = useState(p.compensar_espesores);
  const poligono = r.trazo_id ? zona.losas.findIndex((lo) => lo.trazo_id === r.trazo_id) + 1 : 0;

  function datos(extra: { espacio_id?: string | null } = {}): RellenoDeLaZonaPeticion | null {
    const valores = [opcional(espesor), opcional(pendiente), opcional(recorrido), opcional(abundamiento), opcional(mortero)];
    if (valores.includes(null)) return null;
    const [e, pe, re, ab, mo] = valores as (number | undefined)[];
    return {
      elemento_clave: r.clave as RellenoDeLaZonaPeticion['elemento_clave'],
      ...(r.trazo_id ? { trazo_id: r.trazo_id } : {}),
      ...(e === undefined ? {} : { espesor_m: e }),
      ...(pe === undefined ? {} : { pendiente_pct: pe }),
      ...(re === undefined ? {} : { recorrido_m: re }),
      ...(compactado ? (ab === undefined ? {} : { abundamiento_pct: ab }) : mo === undefined ? {} : { mortero_m3_por_m2: mo }),
      compensar_espesores: compensar,
      ...extra,
    };
  }

  async function guardar(extra: { espacio_id?: string | null } = {}, aviso = `${r.nombre} actualizado.`) {
    const d = datos(extra);
    if (d === null) {
      onError('Un parámetro del relleno no es un número válido (usa 0 o más).');
      return;
    }
    try {
      await cambiar.mutateAsync({ rellenoId: r.id, data: d });
      refrescar();
      onCambio(aviso);
    } catch (err) {
      onError(mensaje(err, 'No se pudo cambiar el relleno.'));
    }
  }

  async function quitarRelleno() {
    try {
      await quitar.mutateAsync({ rellenoId: r.id });
      refrescar();
      onCambio(`${r.nombre} quitado de la zona.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo quitar el relleno.'));
    }
  }

  const cada = r.espacio_id ?? '';
  return (
    <div className="mct__bloque" data-relleno-de-la-zona={r.clave} data-origen={r.origen} aria-label={`Relleno ${numero}: ${r.nombre}`}>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <strong>
          <span className="mono">{r.clave}</span> · {r.nombre}
        </strong>
        <span className="badge badge--outline">{r.origen === 'poligono' ? (poligono > 0 ? `polígono ${poligono}` : 'un polígono') : 'toda la zona'}</span>
        {r.conceptos.map((k) => (
          <span key={k.concepto.clave} className={k.concepto.estado === 'propuesto' ? 'badge badge--warn' : 'badge badge--ok'} title={k.concepto.descripcion}>
            {k.concepto.clave} · {k.concepto.estado === 'propuesto' ? `propuesto${k.propuesta ? ` (${k.propuesta.estado})` : ''}` : 'del catálogo'}
          </span>
        ))}
      </div>
      <p className="text-sm" data-testid="relleno-de-la-zona-resumen">
        Área {num(r.area_m2)} m² · volumen {num(r.volumen_m3, 3)} m³ · espesor medio {num(r.espesor_medio_m * 100, 1)} cm
        {r.volumen_suelto_m3 !== null && r.volumen_suelto_m3 !== undefined && ` · suelto ${num(r.volumen_suelto_m3, 3)} m³`}
        {' · '}
        {r.conceptos.map((k) => `${num(k.cantidad)} ${unidadVisible(k.unidad)} de ${k.concepto.clave}`).join(' · ')}
      </p>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <label className="mct__campo">
          Espesor mínimo (m)
          <input className="input" inputMode="decimal" aria-label={`Espesor mínimo del relleno ${numero}`} disabled={!puedeEditar} value={espesor} onChange={(e) => setEspesor(e.target.value)} />
        </label>
        <label className="mct__campo">
          Pendiente (%)
          <input className="input" inputMode="decimal" aria-label={`Pendiente del relleno ${numero}`} disabled={!puedeEditar} value={pendiente} onChange={(e) => setPendiente(e.target.value)} />
        </label>
        <label className="mct__campo">
          Recorrido (m)
          <input className="input" inputMode="decimal" aria-label={`Recorrido de la pendiente del relleno ${numero}`} disabled={!puedeEditar} value={recorrido} onChange={(e) => setRecorrido(e.target.value)} />
        </label>
        {compactado ? (
          <label className="mct__campo">
            Abundamiento (%)
            <input className="input" inputMode="decimal" aria-label={`Abundamiento del relleno ${numero}`} disabled={!puedeEditar} value={abundamiento} onChange={(e) => setAbundamiento(e.target.value)} />
          </label>
        ) : (
          <label className="mct__campo">
            Mortero (m³ por m²)
            <input className="input" inputMode="decimal" aria-label={`Mortero del relleno ${numero}`} disabled={!puedeEditar} value={mortero} onChange={(e) => setMortero(e.target.value)} />
          </label>
        )}
        <label className="mct__campo mct__campo--casilla">
          <input type="checkbox" aria-label={`Adaptarse a los espesores de losa en el relleno ${numero}`} disabled={!puedeEditar} checked={compensar} onChange={(e) => setCompensar(e.target.checked)} />
          <span>Adaptarse a los espesores de losa</span>
        </label>
        <label className="mct__campo">
          Espacio
          <select
            className="input"
            aria-label={`Espacio del relleno ${numero}`}
            disabled={!puedeEditar || cambiar.isPending}
            value={cada}
            onChange={(e) => void guardar({ espacio_id: e.target.value || null }, e.target.value ? `${r.nombre} asignado a su espacio.` : `${r.nombre} sigue el espacio de cada polígono.`)}
          >
            <option value="">El de cada polígono</option>
            {espacios.map((x) => (
              <option key={x.id} value={x.id}>
                {x.nombre}
              </option>
            ))}
          </select>
        </label>
      </div>
      {puedeEditar && (
        <div className="row" style={{ gap: 6 }}>
          <button type="button" className="btn btn--sm" aria-label={`Guardar los parámetros del relleno ${numero}`} disabled={cambiar.isPending} onClick={() => void guardar()}>
            Guardar los parámetros
          </button>
          <button type="button" className="btn btn--sm" aria-label={`Quitar el relleno ${numero}`} disabled={quitar.isPending} onClick={() => void quitarRelleno()}>
            Quitar
          </button>
        </div>
      )}
      <table className="table" aria-label={`Espesor por polígono del relleno ${numero}`}>
        <thead>
          <tr>
            <th>Polígono</th>
            <th>Área</th>
            <th>Losa</th>
            <th>Compensa</th>
            <th>Relleno</th>
            <th>Volumen</th>
          </tr>
        </thead>
        <tbody>
          {r.poligonos.map((po, i) => (
            <tr key={`${po.id}-${i}`}>
              <td>{po.id}{po.subzona ? ' · subzona' : ''}</td>
              <td className="mono">{num(po.area_m2)} m²</td>
              <td className="mono">{num(po.espesor_de_losa_m * 100, 1)} cm</td>
              <td className="mono">{num(po.compensacion_m * 100, 1)} cm</td>
              <td className="mono">{num(po.espesor_m * 100, 1)} cm</td>
              <td className="mono">{num(po.volumen_m3, 3)} m³</td>
            </tr>
          ))}
        </tbody>
      </table>
      {r.conciliacion && (
        <div data-testid="conciliacion-del-relleno" data-concepto-conciliado={r.conciliacion.concepto.clave}>
          <p className="text-xs">
            Contra <span className="mono">{r.conciliacion.concepto.clave}</span> {r.conciliacion.concepto.descripcion}. {r.conciliacion.nota}
          </p>
          {r.conciliacion.filas.length > 0 && (
            <table className="table" aria-label={`Conciliación del relleno ${numero} con el catálogo`}>
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th>Catálogo (por m²)</th>
                  <th>Relleno (por m²)</th>
                  <th>Marca</th>
                </tr>
              </thead>
              <tbody>
                {r.conciliacion.filas.map((f) => {
                  const marca = MARCA[f.marca] ?? { texto: f.marca, clase: 'badge' };
                  return (
                    <tr key={f.clave} data-marca={f.marca}>
                      <td>
                        <span className="mono">{f.clave}</span> {f.descripcion}
                      </td>
                      <td className="mono">{f.catalogo === null || f.catalogo === undefined ? '—' : num(f.catalogo, 4)}</td>
                      <td className="mono">{f.elemento === null || f.elemento === undefined ? '—' : num(f.elemento, 4)}</td>
                      <td>
                        <span className={marca.clase}>{marca.texto}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      )}
      {r.advertencias.map((a) => (
        <p key={a} className="text-mute text-xs">
          {a}
        </p>
      ))}
    </div>
  );
}
