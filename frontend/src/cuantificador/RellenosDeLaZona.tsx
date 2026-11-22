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
 * - **Relleno dinámico de azotea (0147):** con bajadas pluviales (un punto del plano cada una; la línea de pendiente es opcional y, si no se traza, el sistema la
 *   genera) el relleno lleva dos capas: arenilla de espesor variable (5 cm en la bajada + pendiente × distancia, concepto nuevo propuesto EJ-830 por m³) y plantilla de
 *   mortero de 5 cm (ALB-03014 por m²). Precio y cantidades cambian al hacer el trazo; las guías (líneas de pendiente e hilos de nivel punteados) salen en el visor.
 * - REL-COMPACTADO: la cantidad es el volumen compactado × el factor de abundamiento (1.00 por omisión).
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
  useCambiarBajadaApiV1BajadasDeRellenoBajadaIdPut,
  useCambiarRellenoApiV1RellenosDeZonaRellenoIdPut,
  useProponerConceptosDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosPropuestasPost,
  useQuitarBajadaApiV1BajadasDeRellenoBajadaIdDelete,
  useQuitarRellenoApiV1RellenosDeZonaRellenoIdDelete,
} from '@/api/generado/rellenos/rellenos';
import { queryClient } from '@/app/queryClient';

import { NOMBRE_DEL_ESTADO_DE_PARTIDA } from './espacios';
import type { PorColocar } from './ZonasDeLosa';

function mensaje(err: unknown, defecto: string): string {
  return err instanceof Error ? err.message : defecto;
}

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const unidadVisible = (u: string) => (u === 'm3' ? 'm³' : u === 'm2' ? 'm²' : u);
/** Los m³ se muestran con tres decimales (la arenilla y el compactado); lo demás, con dos. */
const decimalesDe = (u: string) => (u === 'm³' || u === 'm3' ? 3 : 2);
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
  // Las guías del relleno dinámico (líneas de pendiente, hilos de nivel y bajadas) las pinta el visor y cambian con cualquier parámetro.
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('guias-de-relleno') });
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
  /** Lo que el plano está pidiendo colocar (una bajada o una línea de pendiente), para marcar el botón activo. */
  readonly colocando?: PorColocar | null;
  readonly onColocar?: (c: PorColocar | null) => void;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function RellenosDeLaZona({ zona, puedeEditar, rol, espacios = [], colocando = null, onColocar, onCambio, onError }: Props) {
  const [abierta, setAbierta] = useState(false);
  return (
    <div className="zonas-losa__rellenos" data-testid="rellenos-de-la-zona" data-zona={zona.id}>
      <div className="row">
        <button type="button" className="btn btn--sm" aria-expanded={abierta} aria-label={`Rellenos de ${zona.nombre}`} onClick={() => setAbierta((v) => !v)}>
          {abierta ? 'Ocultar los rellenos' : 'Rellenos'}
        </button>
        <span className="text-mute text-xs">Elemento separado de la losa</span>
      </div>
      {abierta && (
        <CuerpoDeLosRellenos zona={zona} puedeEditar={puedeEditar} rol={rol} espacios={espacios} colocando={colocando} onColocar={onColocar} onCambio={onCambio} onError={onError} />
      )}
    </div>
  );
}

function CuerpoDeLosRellenos({ zona, puedeEditar, rol, espacios = [], colocando = null, onColocar, onCambio, onError }: Props) {
  const consulta = useCalculoDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosCalculoGet(zona.id, { conciliar: true }, { query: { retry: false } });
  const agregar = useAgregarRellenoApiV1ZonasDeLosaZonaIdRellenosPost<ErrorApi>();
  const proponer = useProponerConceptosDeLosRellenosApiV1ZonasDeLosaZonaIdRellenosPropuestasPost<ErrorApi>();
  const [clave, setClave] = useState<(typeof CLAVES)[number]>('REL-AZOTEA');
  const [cubre, setCubre] = useState('');
  const [espacio, setEspacio] = useState('');
  const c = consulta.data;
  const puedeProponer = rol === 'control_obra' || rol === 'costos';
  const sinProponer = (c?.rellenos ?? []).flatMap((r) => r.conceptos).filter((k) => k.concepto.provisional && !k.propuesta);
  const faltaArenilla = sinProponer.some((k) => k.concepto.clave === 'EJ-830');
  const faltaCompactado = sinProponer.some((k) => k.concepto.clave !== 'EJ-830');

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
      onCambio(r.creadas.length > 0 ? 'Se propuso el concepto nuevo del relleno (clave provisional, sin precio).' : 'El concepto del relleno ya estaba propuesto.');
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
        <FilaDelRelleno
          key={r.id} r={r} numero={i + 1} zona={zona} puedeEditar={puedeEditar} espacios={espacios} colocando={colocando} onColocar={onColocar} onCambio={onCambio} onError={onError}
        />
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
          {faltaArenilla && faltaCompactado
            ? 'Proponer los conceptos nuevos de los rellenos'
            : faltaArenilla
              ? 'Proponer el concepto de la arenilla'
              : 'Proponer el concepto del relleno compactado'}
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
  r, numero, zona, puedeEditar, espacios = [], colocando = null, onColocar, onCambio, onError,
}: {
  readonly r: RellenoDeLaZonaCalculado;
  readonly numero: number;
  readonly zona: ZonaDeLosa;
  readonly puedeEditar: boolean;
  readonly espacios?: readonly Espacio[];
  readonly colocando?: PorColocar | null;
  readonly onColocar?: (c: PorColocar | null) => void;
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
  const [factor, setFactor] = useState(String(p.factor_abundamiento));
  const [mortero, setMortero] = useState(String(p.mortero_m3_por_m2));
  const [pendienteZona, setPendienteZona] = useState(String(p.pendiente_zona_pct));
  const [espesorBajada, setEspesorBajada] = useState(String(p.espesor_bajada_m));
  const [morteroEspesor, setMorteroEspesor] = useState(String(p.mortero_espesor_m));
  const [compensar, setCompensar] = useState(p.compensar_espesores);
  const poligono = r.trazo_id ? zona.losas.findIndex((lo) => lo.trazo_id === r.trazo_id) + 1 : 0;

  function datos(extra: { espacio_id?: string | null } = {}): RellenoDeLaZonaPeticion | null {
    const valores = [
      opcional(espesor), opcional(pendiente), opcional(recorrido), opcional(factor), opcional(mortero), opcional(pendienteZona), opcional(espesorBajada), opcional(morteroEspesor),
    ];
    if (valores.includes(null)) return null;
    const [e, pe, re, fa, mo, pz, eb, me] = valores as (number | undefined)[];
    return {
      elemento_clave: r.clave as RellenoDeLaZonaPeticion['elemento_clave'],
      ...(r.trazo_id ? { trazo_id: r.trazo_id } : {}),
      ...(e === undefined ? {} : { espesor_m: e }),
      ...(pe === undefined ? {} : { pendiente_pct: pe }),
      ...(re === undefined ? {} : { recorrido_m: re }),
      ...(compactado
        ? fa === undefined ? {} : { factor_abundamiento: fa }
        : {
            ...(mo === undefined ? {} : { mortero_m3_por_m2: mo }),
            ...(pz === undefined ? {} : { pendiente_zona_pct: pz }),
            ...(eb === undefined ? {} : { espesor_bajada_m: eb }),
            ...(me === undefined ? {} : { mortero_espesor_m: me }),
          }),
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
  const dinamico = r.modo === 'bajadas' ? r.dinamico : null;
  return (
    <div className="mct__bloque" data-relleno-de-la-zona={r.clave} data-origen={r.origen} data-modo={r.modo} aria-label={`Relleno ${numero}: ${r.nombre}`}>
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
        {r.conceptos.map((k) => `${num(k.cantidad, decimalesDe(k.unidad))} ${unidadVisible(k.unidad)} de ${k.concepto.clave}`).join(' · ')}
      </p>
      {dinamico && <ResumenDinamico d={dinamico} numero={numero} />}
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
            Factor de abundamiento
            <input className="input" inputMode="decimal" aria-label={`Factor de abundamiento del relleno ${numero}`} disabled={!puedeEditar} value={factor} onChange={(e) => setFactor(e.target.value)} />
          </label>
        ) : (
          <label className="mct__campo">
            Mortero (m³ por m²)
            <input className="input" inputMode="decimal" aria-label={`Mortero del relleno ${numero}`} disabled={!puedeEditar} value={mortero} onChange={(e) => setMortero(e.target.value)} />
          </label>
        )}
        {!compactado && (
          <fieldset className="mct__campo" aria-label={`Parámetros con bajadas pluviales del relleno ${numero}`} style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="text-mute text-xs">Con bajadas pluviales (arenilla + mortero)</legend>
            <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <label className="mct__campo">
                Pendiente de la zona (%)
                <input className="input" inputMode="decimal" aria-label={`Pendiente de la zona del relleno ${numero}`} disabled={!puedeEditar} value={pendienteZona} onChange={(e) => setPendienteZona(e.target.value)} />
              </label>
              <label className="mct__campo">
                Espesor en la bajada (m)
                <input className="input" inputMode="decimal" aria-label={`Espesor en la bajada del relleno ${numero}`} disabled={!puedeEditar} value={espesorBajada} onChange={(e) => setEspesorBajada(e.target.value)} />
              </label>
              <label className="mct__campo">
                Mortero de la plantilla (m)
                <input className="input" inputMode="decimal" aria-label={`Mortero de la plantilla del relleno ${numero}`} disabled={!puedeEditar} value={morteroEspesor} onChange={(e) => setMorteroEspesor(e.target.value)} />
              </label>
            </div>
          </fieldset>
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
      {!compactado && <BajadasDelRelleno r={r} numero={numero} puedeEditar={puedeEditar} colocando={colocando} onColocar={onColocar} onCambio={onCambio} onError={onError} />}
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

type Dinamico = NonNullable<RellenoDeLaZonaCalculado['dinamico']>;

/** Lo que el relleno con bajadas calcula: las dos capas, el espesor de la arenilla, el método numérico y su error. No calcula nada: pinta lo que responde el servidor. */
function ResumenDinamico({ d, numero }: { readonly d: Dinamico; readonly numero: number }) {
  if (d.estado === 'sin_escala') {
    return (
      <p className="text-xs" role="alert" data-testid="relleno-dinamico" data-estado="sin_escala">
        El plano no tiene escala calibrada: el relleno con bajadas no da cantidades hasta calibrar la escala.
      </p>
    );
  }
  const cm = (m: number | null | undefined) => `${num((m ?? 0) * 100, 1)} cm`;
  return (
    <div className="text-xs" data-testid="relleno-dinamico" data-estado="calculado" aria-label={`Relleno dinámico ${numero}`}>
      <p>
        Dos capas: <strong>arenilla</strong> de espesor variable ({cm(d.espesor_en_bajada_m)} en cada bajada + {num(d.pendiente_pct, 2)} % por metro de distancia; medio{' '}
        {cm(d.espesor_arenilla_medio_m)}, máximo {cm(d.espesor_arenilla_maximo_m)}) = {num(d.volumen_arenilla_m3, 3)} m³, y plantilla de <strong>mortero</strong> de{' '}
        {cm(d.mortero_espesor_m)} = {num(d.volumen_mortero_m3, 3)} m³.
      </p>
      <p className="text-mute" data-testid="relleno-dinamico-metodo">
        Método: {d.metodo} Retícula de {num((d.celda_m ?? 0) * 100, 1)} cm, {d.muestras} muestras; error estimado {num(d.error_estimado_m3, 4)} m³ (
        {num((d.error_relativo ?? 0) * 100, 3)} %).
      </p>
    </div>
  );
}

/** Las bajadas pluviales del relleno de azotea: cada una es un punto del plano; la línea de pendiente es opcional (sin ella el sistema genera la dirección). */
function BajadasDelRelleno({
  r, numero, puedeEditar, colocando, onColocar, onCambio, onError,
}: {
  readonly r: RellenoDeLaZonaCalculado;
  readonly numero: number;
  readonly puedeEditar: boolean;
  readonly colocando: PorColocar | null;
  readonly onColocar?: (c: PorColocar | null) => void;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}) {
  const cambiar = useCambiarBajadaApiV1BajadasDeRellenoBajadaIdPut<ErrorApi>();
  const quitar = useQuitarBajadaApiV1BajadasDeRellenoBajadaIdDelete<ErrorApi>();
  const bajadas = r.bajadas ?? [];
  const metricas = new Map((r.dinamico?.bajadas ?? []).map((b) => [b.id, b]));
  const colocandoBajada = colocando?.tipo === 'bajada' && colocando.rellenoId === r.id;

  async function guardar(id: string, lineaTrazoId: string | null, rotulo: string | null, aviso: string) {
    try {
      await cambiar.mutateAsync({ bajadaId: id, data: { linea_trazo_id: lineaTrazoId, rotulo } });
      refrescar();
      onCambio(aviso);
    } catch (err) {
      onError(mensaje(err, 'No se pudo cambiar la bajada.'));
    }
  }

  async function quitarBajada(id: string) {
    try {
      await quitar.mutateAsync({ bajadaId: id });
      refrescar();
      onCambio('Bajada quitada del relleno.');
    } catch (err) {
      onError(mensaje(err, 'No se pudo quitar la bajada.'));
    }
  }

  return (
    <div className="mct__bloque" role="group" aria-label={`Bajadas pluviales del relleno ${numero}`} data-testid="bajadas-del-relleno">
      <div className="row" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <strong className="text-sm">Bajadas pluviales</strong>
        <span className="text-mute text-xs">
          {bajadas.length === 0
            ? 'Sin bajadas: el relleno es parejo (espesor mínimo). Coloca un punto por cada bajada y el sistema calcula la arenilla.'
            : 'El área marca la zona, cada punto es una bajada y la línea marca hacia dónde van las pendientes (si no la trazas, el sistema la genera).'}
        </span>
      </div>
      {bajadas.map((b, i) => {
        const m = metricas.get(b.id);
        const enColocacion = colocando?.tipo === 'pendiente' && colocando.bajadaId === b.id;
        return (
          <div key={b.id} className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }} data-testid="bajada-del-relleno" data-bajada-id={b.id} data-linea={b.linea ? 'trazada' : 'generada'}>
            <span className="badge badge--outline">{b.rotulo ?? `Bajada ${i + 1}`}</span>
            <input
              className="input" style={{ width: 110 }} aria-label={`Rótulo de la bajada ${i + 1} del relleno ${numero}`} placeholder="Rótulo" defaultValue={b.rotulo ?? ''}
              disabled={!puedeEditar}
              onBlur={(e) => {
                const nuevo = e.target.value.trim();
                if (nuevo !== (b.rotulo ?? '')) void guardar(b.id, b.linea_trazo_id ?? null, nuevo || null, 'Rótulo de la bajada guardado.');
              }}
            />
            {m && m.area_m2 != null && (
              <span className="text-xs mono" data-testid="bajada-del-relleno-drena">
                drena {num(m.area_m2)} m² · arenilla hasta {num((m.espesor_maximo_m ?? 0) * 100, 1)} cm
                {m.fuera_de_la_zona ? ' · fuera de la zona' : ''}
              </span>
            )}
            <span className="badge badge--info">{b.linea ? 'línea trazada' : 'línea generada'}</span>
            {puedeEditar && onColocar && (
              <button
                type="button" className={enColocacion ? 'btn btn--sm is-active' : 'btn btn--sm'} aria-pressed={enColocacion}
                aria-label={`Trazar la línea de pendiente de la bajada ${i + 1} del relleno ${numero}`}
                onClick={() => onColocar(enColocacion ? null : { tipo: 'pendiente', bajadaId: b.id, rotulo: b.rotulo ?? null })}
              >
                Trazar línea de pendiente
              </button>
            )}
            {puedeEditar && b.linea && (
              <button type="button" className="btn btn--sm" aria-label={`Quitar la línea de la bajada ${i + 1} del relleno ${numero}`} disabled={cambiar.isPending} onClick={() => void guardar(b.id, null, b.rotulo ?? null, 'Línea de pendiente quitada: el sistema genera la dirección.')}>
                Quitar la línea
              </button>
            )}
            {puedeEditar && (
              <button type="button" className="btn btn--sm" aria-label={`Quitar la bajada ${i + 1} del relleno ${numero}`} disabled={quitar.isPending} onClick={() => void quitarBajada(b.id)}>
                Quitar la bajada
              </button>
            )}
          </div>
        );
      })}
      {puedeEditar && onColocar && (
        <div className="row" style={{ gap: 6 }}>
          <button
            type="button" className={colocandoBajada ? 'btn btn--sm is-active' : 'btn btn--sm'} aria-pressed={colocandoBajada} aria-label={`Colocar bajada pluvial del relleno ${numero}`}
            onClick={() => onColocar(colocandoBajada ? null : { tipo: 'bajada', rellenoId: r.id })}
          >
            Colocar bajada pluvial
          </button>
        </div>
      )}
    </div>
  );
}
