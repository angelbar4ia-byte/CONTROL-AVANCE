/**
 * Las escaleras de una zona de losa (Fase 4a), dentro del panel de zonas de la pestaña Trazos: la escalera sale de la **diferencia de cotas** de las zonas.
 *
 * - Cada escalera arranca en el piso de esta zona y llega al piso de otra zona (o a la cara alta de la losa de esta); se pueden teclear las dos cotas. Los
 *   peldaños salen del desnivel y de la contrahuella máxima. Si una zona cambia de cota, la escalera se recalcula sola.
 * - El escalón se paga con el concepto que ya existe en el catálogo (EST-01510, un escalón de 1.20 m); el descanso entre rampas, con el concepto nuevo propuesto
 *   EJ-820 (clave provisional, sin precio). Solo Control de obra edita; los demás roles leen.
 * - Una línea del plano puede dar el recorrido (medición derivada: se asigna desde el detalle de la línea) y de ella sale la huella.
 * - **Descansos** propios (largo × ancho, espesor y giro de 0°, 90° o 180°, entre dos rampas) y **escalones de abanico** (peldaño trapezoidal con el fondo en el borde
 *   interior y exterior; son parte de los peldaños del desnivel) viven en `DescansosYAbanicos` (Fase 4d).
 * - Cada escalera dice en qué **espacio** está (0143); su concepto dice en qué **partida** del árbol se mide o por qué no cuenta, y la suma de los espacios es el
 *   total (sin doble conteo). Se **concilia** contra la composición vigente de EST-01510 por escalón (el catálogo no se edita).
 *
 * No calcula nada: pinta lo que responde el servidor.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  getCalculoDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasCalculoGetQueryKey,
  useAgregarEscaleraApiV1ZonasDeLosaZonaIdEscalerasPost,
  useCalculoDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasCalculoGet,
  useCambiarEscaleraApiV1EscalerasDeZonaEscaleraIdPut,
  useProponerConceptosDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasPropuestasPost,
  useQuitarEscaleraApiV1EscalerasDeZonaEscaleraIdDelete,
} from '@/api/generado/escaleras/escaleras';
import type { Espacio, EscaleraDeLaZonaCalculada, EscaleraDeLaZonaPeticion, ZonaDeLosa } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

import { AbanicosDeLaEscalera, DescansosDeLaEscalera } from './DescansosYAbanicos';
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
  solo_elemento: { texto: 'solo en la escalera', clase: 'badge badge--warn' },
};
const NOMBRE_DEL_ORIGEN_DE_COTA: Record<string, string> = {
  explicita: 'tecleada',
  zona: 'del piso de la zona',
  zona_de_llegada: 'del piso de la zona de llegada',
  losa_de_la_zona: 'de la cara alta de la losa',
};

function refrescar() {
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('zonas-de-losa') });
  // Los espacios cuentan lo que tienen asignado y las partidas reciben lo medido: cambian al agregar, mover o quitar una escalera.
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/espacios') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/cuantificacion') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/biblioteca-de-elementos') });
}

/** Un campo numérico: vacío = el de omisión del elemento (`undefined`); lo que no es un número válido, `null`. */
function opcional(texto: string, minimo = 0): number | undefined | null {
  if (texto.trim() === '') return undefined;
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) && n >= minimo ? n : null;
}

/** Una cota (puede ser negativa): vacío = la de la zona. */
function cotaOpcional(texto: string): number | undefined | null {
  if (texto.trim() === '') return undefined;
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) ? n : null;
}

interface Props {
  readonly zona: ZonaDeLosa;
  /** Todas las zonas del plano: la escalera puede llegar al piso de otra. */
  readonly zonas?: readonly ZonaDeLosa[];
  readonly puedeEditar: boolean;
  /** El rol de quien mira: Costos y Control de obra proponen el concepto nuevo del descanso. */
  readonly rol: string | null;
  /** Los espacios de la obra (0143): cada escalera elige el suyo. */
  readonly espacios?: readonly Espacio[];
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function EscalerasDeLaZona({ zona, zonas = [], puedeEditar, rol, espacios = [], onCambio, onError }: Props) {
  const [abierta, setAbierta] = useState(false);
  return (
    <div className="zonas-losa__escaleras" data-testid="escaleras-de-la-zona" data-zona={zona.id}>
      <div className="row">
        <button type="button" className="btn btn--sm" aria-expanded={abierta} aria-label={`Escaleras de ${zona.nombre}`} onClick={() => setAbierta((v) => !v)}>
          {abierta ? 'Ocultar las escaleras' : 'Escaleras'}
        </button>
        <span className="text-mute text-xs">Salen de la diferencia de cotas</span>
      </div>
      {abierta && <CuerpoDeLasEscaleras zona={zona} zonas={zonas} puedeEditar={puedeEditar} rol={rol} espacios={espacios} onCambio={onCambio} onError={onError} />}
    </div>
  );
}

function CuerpoDeLasEscaleras({ zona, zonas = [], puedeEditar, rol, espacios = [], onCambio, onError }: Props) {
  const consulta = useCalculoDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasCalculoGet(zona.id, { conciliar: true }, { query: { retry: false } });
  const agregar = useAgregarEscaleraApiV1ZonasDeLosaZonaIdEscalerasPost<ErrorApi>();
  const proponer = useProponerConceptosDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasPropuestasPost<ErrorApi>();
  const [llegada, setLlegada] = useState('');
  const [espacio, setEspacio] = useState('');
  const c = consulta.data;
  const otras = zonas.filter((z) => z.id !== zona.id);
  const puedeProponer = rol === 'control_obra' || rol === 'costos';
  const sinProponer = (c?.escaleras ?? []).flatMap((e) => e.calculo?.conceptos ?? []).filter((k) => k.concepto.provisional && !k.propuesta);

  async function agregarEscalera() {
    try {
      const datos: EscaleraDeLaZonaPeticion = { ...(llegada ? { zona_llegada_id: llegada } : {}), ...(espacio ? { espacio_id: espacio } : {}) };
      await agregar.mutateAsync({ zonaId: zona.id, data: datos });
      refrescar();
      onCambio('Escalera agregada a la zona.');
    } catch (err) {
      onError(mensaje(err, 'No se pudo agregar la escalera.'));
    }
  }

  async function proponerFaltantes() {
    try {
      const r = await proponer.mutateAsync({ zonaId: zona.id });
      refrescar();
      void queryClient.invalidateQueries({ queryKey: getCalculoDeLasEscalerasApiV1ZonasDeLosaZonaIdEscalerasCalculoGetQueryKey(zona.id, { conciliar: true }) });
      onCambio(r.creadas.length > 0 ? 'Se propuso el concepto nuevo del descanso (clave provisional, sin precio).' : 'El concepto del descanso ya estaba propuesto.');
    } catch (err) {
      onError(mensaje(err, 'No se pudo proponer el concepto.'));
    }
  }

  return (
    <div className="zonas-losa__cuerpo" data-testid="cuerpo-de-las-escaleras">
      {consulta.isLoading && <p className="text-mute text-xs">Calculando las escaleras…</p>}
      {consulta.isError && (
        <p className="text-xs" role="alert">
          {mensaje(consulta.error, 'No se pudo calcular las escaleras de la zona.')}
        </p>
      )}
      {c && c.escaleras.length === 0 && <p className="text-mute text-xs">La zona no tiene escaleras. Agrega una: sube de la cota del piso de la zona a la de llegada.</p>}
      {c?.advertencias.map((a) => (
        <p key={a} className="text-xs" role="alert">
          {a}
        </p>
      ))}
      {c?.escaleras.map((e, i) => (
        <FilaDeLaEscalera key={e.id} e={e} numero={i + 1} zona={zona} otras={otras} puedeEditar={puedeEditar} espacios={espacios} onCambio={onCambio} onError={onError} />
      ))}
      {c && c.escaleras.length > 0 && (
        <p className="text-sm" data-testid="escaleras-resumen">
          Total: {c.totales.peldanos} peldaños · {num(c.totales.escalones_de_catalogo)} escalones de 1.20 m
          {c.totales.peldanos_de_abanico > 0 && ` · ${c.totales.peldanos_de_abanico} de abanico`}
          {c.totales.area_de_descanso_m2 > 0 && ` · descanso ${num(c.totales.area_de_descanso_m2)} m²`}
          {c.totales.conceptos.length > 0 && ' · '}
          {c.totales.conceptos.map((k) => `${k.concepto.clave} ${num(k.cantidad)} ${unidadVisible(k.unidad)}`).join(' · ')}
        </p>
      )}
      {c && c.por_espacio.length > 0 && (
        <div className="mct__tabla-caja">
          <table className="table" aria-label="Lo que paga la escalera de cada espacio">
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
          Proponer el concepto del descanso
        </button>
      )}
      {puedeEditar && (
        <div className="zonas-losa__form" role="group" aria-label="Agregar una escalera a la zona">
          <label className="mct__campo">
            Llega a
            <select className="input" aria-label="Zona de llegada de la escalera" value={llegada} onChange={(e) => setLlegada(e.target.value)}>
              <option value="">La cara alta de la losa de esta zona</option>
              {otras.map((z) => (
                <option key={z.id} value={z.id}>
                  Piso de {z.nombre} ({num(Number(z.cota_piso_m), 2)} m)
                </option>
              ))}
            </select>
          </label>
          <label className="mct__campo">
            Espacio
            <select className="input" aria-label="Espacio de la escalera nueva" value={espacio} onChange={(e) => setEspacio(e.target.value)}>
              <option value="">Sin espacio</option>
              {espacios.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.nombre}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn btn--sm" disabled={agregar.isPending} onClick={() => void agregarEscalera()}>
            Agregar la escalera
          </button>
        </div>
      )}
    </div>
  );
}

function FilaDeLaEscalera({
  e, numero, zona, otras, puedeEditar, espacios = [], onCambio, onError,
}: {
  readonly e: EscaleraDeLaZonaCalculada;
  readonly numero: number;
  readonly zona: ZonaDeLosa;
  readonly otras: readonly ZonaDeLosa[];
  readonly puedeEditar: boolean;
  readonly espacios?: readonly Espacio[];
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}) {
  const cambiar = useCambiarEscaleraApiV1EscalerasDeZonaEscaleraIdPut<ErrorApi>();
  const quitar = useQuitarEscaleraApiV1EscalerasDeZonaEscaleraIdDelete<ErrorApi>();
  const r = e.calculo;
  const p = r?.parametros;
  // Lo que está vacío es lo que sale de las zonas o del elemento: solo se manda lo que se tecleó.
  const [arranque, setArranque] = useState(e.origen_de_cotas.arranque === 'explicita' && r ? String(r.cotas.arranque_m) : '');
  const [cotaLlegada, setCotaLlegada] = useState(e.origen_de_cotas.llegada === 'explicita' && r ? String(r.cotas.llegada_m) : '');
  const [zonaLlegada, setZonaLlegada] = useState(e.zona_llegada_id ?? '');
  const [peldanos, setPeldanos] = useState(p && r?.geometria.origen_de_peldanos === 'tecleados' ? String(p.peldanos) : '');
  const [huella, setHuella] = useState(p && r?.geometria.origen_de_huella === 'tecleada' ? String(p.huella_m) : '');
  const [ancho, setAncho] = useState(p ? String(p.ancho_m) : '');
  const [rampas, setRampas] = useState(p ? String(p.rampas) : '');
  const [descanso, setDescanso] = useState(p?.largo_descanso_m != null ? String(p.largo_descanso_m) : '');
  const enLinea = e.trazo_id !== null && e.trazo_id !== undefined;

  function datos(extra: { espacio_id?: string | null } = {}): EscaleraDeLaZonaPeticion | null {
    const cotas = [cotaOpcional(arranque), cotaOpcional(cotaLlegada)];
    const valores = [opcional(peldanos, 2), opcional(huella), opcional(ancho), opcional(rampas, 1), opcional(descanso)];
    if (cotas.includes(null) || valores.includes(null)) return null;
    const [ca, cl] = cotas as (number | undefined)[];
    const [pe, hu, an, ra, de] = valores as (number | undefined)[];
    return {
      ...(zonaLlegada ? { zona_llegada_id: zonaLlegada } : {}),
      ...(ca === undefined ? {} : { cota_arranque_m: ca }),
      ...(cl === undefined ? {} : { cota_llegada_m: cl }),
      ...(e.trazo_id ? { trazo_id: e.trazo_id } : {}),
      ...(pe === undefined ? {} : { peldanos: Math.round(pe) }),
      ...(hu === undefined ? {} : { huella_m: hu }),
      ...(an === undefined ? {} : { ancho_m: an }),
      ...(ra === undefined ? {} : { rampas: Math.round(ra) }),
      ...(de === undefined ? {} : { largo_descanso_m: de }),
      ...(r?.parametros.espesor_m !== undefined ? { espesor_m: r.parametros.espesor_m } : {}),
      ...(r?.parametros.contrahuella_max_m !== undefined ? { contrahuella_max_m: r.parametros.contrahuella_max_m } : {}),
      ...extra,
    };
  }

  async function guardar(extra: { espacio_id?: string | null } = {}, aviso = `Escalera ${numero} actualizada.`) {
    const d = datos(extra);
    if (d === null) {
      onError('Un valor de la escalera no es un número válido.');
      return;
    }
    try {
      await cambiar.mutateAsync({ escaleraId: e.id, data: d });
      refrescar();
      onCambio(aviso);
    } catch (err) {
      onError(mensaje(err, 'No se pudo cambiar la escalera.'));
    }
  }

  async function quitarEscalera() {
    try {
      await quitar.mutateAsync({ escaleraId: e.id });
      refrescar();
      onCambio(`Escalera ${numero} quitada de la zona.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo quitar la escalera.'));
    }
  }

  return (
    <div className="mct__bloque" data-escalera-de-la-zona={e.id} data-con-error={e.error ? 'si' : 'no'} aria-label={`Escalera ${numero}`}>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <strong>Escalera {numero}</strong>
        {enLinea && <span className="badge badge--outline">recorrido de una línea del plano</span>}
        {r?.conceptos.map((k) => (
          <span key={k.concepto.clave} className={k.concepto.estado === 'propuesto' ? 'badge badge--warn' : 'badge badge--ok'} title={k.concepto.descripcion}>
            {k.concepto.clave} · {k.concepto.estado === 'propuesto' ? `propuesto${k.propuesta ? ` (${k.propuesta.estado})` : ''}` : 'del catálogo'}
          </span>
        ))}
      </div>
      {e.error && (
        <p className="text-sm" role="alert" data-testid="escalera-error">
          {e.error}
        </p>
      )}
      {r && (
        <p className="text-sm" data-testid="escalera-de-la-zona-resumen">
          Desnivel {num(r.cotas.desnivel_m, 3)} m (de {num(r.cotas.arranque_m)} a {num(r.cotas.llegada_m)} m; arranque {NOMBRE_DEL_ORIGEN_DE_COTA[e.origen_de_cotas.arranque]}, llegada{' '}
          {NOMBRE_DEL_ORIGEN_DE_COTA[e.origen_de_cotas.llegada]}) · {r.geometria.peldanos} peldaños · contrahuella {num(r.geometria.contrahuella_m * 100, 1)} cm · huella{' '}
          {num(r.geometria.huella_m * 100, 1)} cm · {r.geometria.rampas.length} {r.geometria.rampas.length === 1 ? 'rampa' : 'rampas'}
          {r.geometria.descansos > 0 && ` · descanso ${num(r.geometria.area_de_descanso_m2)} m²`}
          {r.geometria.peldanos_de_abanico > 0 && ` · ${r.geometria.peldanos_de_abanico} de abanico y ${r.geometria.peldanos_rectos} rectos`}
          {' · '}
          {r.conceptos.map((k) => `${num(k.cantidad)} ${unidadVisible(k.unidad)} de ${k.concepto.clave}`).join(' · ')}
        </p>
      )}
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <label className="mct__campo">
          Llega a
          <select className="input" aria-label={`Zona de llegada de la escalera ${numero}`} disabled={!puedeEditar || cotaLlegada.trim() !== ''} value={zonaLlegada} onChange={(x) => setZonaLlegada(x.target.value)}>
            <option value="">La cara alta de la losa de {zona.nombre}</option>
            {otras.map((z) => (
              <option key={z.id} value={z.id}>
                Piso de {z.nombre}
              </option>
            ))}
          </select>
        </label>
        <label className="mct__campo">
          Cota de arranque (m)
          <input className="input" inputMode="decimal" aria-label={`Cota de arranque de la escalera ${numero}`} disabled={!puedeEditar} placeholder="la de la zona" value={arranque} onChange={(x) => setArranque(x.target.value)} />
        </label>
        <label className="mct__campo">
          Cota de llegada (m)
          <input className="input" inputMode="decimal" aria-label={`Cota de llegada de la escalera ${numero}`} disabled={!puedeEditar || zonaLlegada !== ''} placeholder="la de la zona" value={cotaLlegada} onChange={(x) => setCotaLlegada(x.target.value)} />
        </label>
        <label className="mct__campo">
          Peldaños
          <input className="input" inputMode="numeric" aria-label={`Peldaños de la escalera ${numero}`} disabled={!puedeEditar} placeholder="del desnivel" value={peldanos} onChange={(x) => setPeldanos(x.target.value)} />
        </label>
        <label className="mct__campo">
          Huella (m)
          <input className="input" inputMode="decimal" aria-label={`Huella de la escalera ${numero}`} disabled={!puedeEditar || enLinea} placeholder={enLinea ? 'de la línea' : '0.25'} value={enLinea ? '' : huella} onChange={(x) => setHuella(x.target.value)} />
        </label>
        <label className="mct__campo">
          Ancho (m)
          <input className="input" inputMode="decimal" aria-label={`Ancho de la escalera ${numero}`} disabled={!puedeEditar} value={ancho} onChange={(x) => setAncho(x.target.value)} />
        </label>
        <label className="mct__campo">
          Rampas
          <input className="input" inputMode="numeric" aria-label={`Rampas de la escalera ${numero}`} disabled={!puedeEditar} value={rampas} onChange={(x) => setRampas(x.target.value)} />
        </label>
        <label className="mct__campo">
          Largo del descanso (m)
          <input className="input" inputMode="decimal" aria-label={`Largo del descanso de la escalera ${numero}`} disabled={!puedeEditar} placeholder="el ancho" value={descanso} onChange={(x) => setDescanso(x.target.value)} />
        </label>
        <label className="mct__campo">
          Espacio
          <select
            className="input"
            aria-label={`Espacio de la escalera ${numero}`}
            disabled={!puedeEditar || cambiar.isPending}
            value={e.espacio_id ?? ''}
            onChange={(x) => void guardar({ espacio_id: x.target.value || null }, x.target.value ? `Escalera ${numero} asignada a su espacio.` : `Escalera ${numero} sin espacio.`)}
          >
            <option value="">Sin espacio</option>
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
          <button type="button" className="btn btn--sm" aria-label={`Guardar la escalera ${numero}`} disabled={cambiar.isPending} onClick={() => void guardar()}>
            Guardar la escalera
          </button>
          <button type="button" className="btn btn--sm" aria-label={`Quitar la escalera ${numero}`} disabled={quitar.isPending} onClick={() => void quitarEscalera()}>
            Quitar
          </button>
        </div>
      )}
      {r && (
        <table className="table" aria-label={`Detalle por rampa (escalera ${numero})`}>
          <thead>
            <tr>
              <th>Rampa</th>
              <th>Peldaños</th>
              <th>Recorrido</th>
              <th>Altura</th>
            </tr>
          </thead>
          <tbody>
            {r.geometria.rampas.map((x) => (
              <tr key={x.numero}>
                <td>{x.numero}</td>
                <td className="mono">{x.peldanos}</td>
                <td className="mono">{num(x.recorrido_m)} m</td>
                <td className="mono">{num(x.altura_m)} m</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <DescansosDeLaEscalera e={e} numero={numero} puedeEditar={puedeEditar} onCambio={onCambio} onError={onError} />
      <AbanicosDeLaEscalera e={e} numero={numero} puedeEditar={puedeEditar} onCambio={onCambio} onError={onError} />
      {e.conciliacion && (
        <div data-testid="conciliacion-de-la-escalera" data-concepto-conciliado={e.conciliacion.concepto.clave}>
          <p className="text-xs">
            Contra <span className="mono">{e.conciliacion.concepto.clave}</span> {e.conciliacion.concepto.descripcion}. {e.conciliacion.nota}
          </p>
          {e.conciliacion.filas.length > 0 && (
            <table className="table" aria-label={`Conciliación de la escalera ${numero} con el catálogo`}>
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th>Catálogo (por escalón)</th>
                  <th>Escalera (por escalón)</th>
                  <th>Marca</th>
                </tr>
              </thead>
              <tbody>
                {e.conciliacion.filas.map((f) => {
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
      {r?.advertencias.map((a) => (
        <p key={a} className="text-mute text-xs">
          {a}
        </p>
      ))}
    </div>
  );
}
