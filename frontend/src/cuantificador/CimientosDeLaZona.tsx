/**
 * Los cimientos de una zona de losa (Fase 4b), dentro del panel de zonas de la pestaña Trazos: el muro de cimentación de piedra (CIM-01010) medido sobre una línea del plano
 * con **cotas de desplante** (relativas al piso terminado de PB = 0).
 *
 * - La altura sale de la corona menos el desplante; la longitud, de la línea del plano y de la escala del plano (medición derivada). El desplante se teclea o sale de un punto de
 *   nivel exterior del plano (si el punto cambia, el cimiento cambia). La corona vale el arranque de la cadena de desplante (piso de la zona − 20 cm) si no se teclea.
 * - Se paga con el concepto que ya existe en el catálogo (MCT-01011, por m³). Cada cimiento dice en qué **espacio** está (0143) y su concepto en qué **partida** del árbol se mide o
 *   por qué no cuenta; la suma de los espacios es el total (sin doble conteo). Solo Control de obra edita. Los cimientos se agregan desde el detalle de una línea del plano.
 *
 * No calcula nada: pinta lo que responde el servidor.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCalculoDeLosCimientosApiV1ZonasDeLosaZonaIdCimientosCalculoGet,
  useCambiarCimientoApiV1CimientosDeZonaCimientoIdPut,
  useQuitarCimientoApiV1CimientosDeZonaCimientoIdDelete,
} from '@/api/generado/cimientos/cimientos';
import type { CimientoDeLaZonaCalculado, CimientoDeLaZonaPeticion, Espacio, ZonaDeLosa } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

import { NOMBRE_DEL_ESTADO_DE_PARTIDA } from './espacios';

export interface PuntoDeNivelDelPlano {
  readonly trazo_id: string;
  readonly cota_m: string;
  readonly rotulo?: string | null;
}

function mensaje(err: unknown, defecto: string): string {
  return err instanceof Error ? err.message : defecto;
}

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const NOMBRE_DEL_ORIGEN_DE_COTA: Record<string, string> = {
  explicita: 'tecleada',
  cadena_de_desplante: 'del arranque de la cadena de desplante',
  zona: 'del piso de la zona',
  punto_de_nivel: 'de un punto de nivel exterior',
  sin_cota: 'sin cota',
};

export function refrescarCimientos() {
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('zonas-de-losa') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/espacios') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/cuantificacion') });
}

/** Una cota (puede ser negativa): vacío = la de la zona o el punto (`undefined`); lo que no es un número, `null`. */
export function cotaOpcional(texto: string): number | undefined | null {
  if (texto.trim() === '') return undefined;
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) ? n : null;
}

interface Props {
  readonly zona: ZonaDeLosa;
  readonly puntos?: readonly PuntoDeNivelDelPlano[];
  readonly puedeEditar: boolean;
  readonly espacios?: readonly Espacio[];
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function CimientosDeLaZona({ zona, puntos = [], puedeEditar, espacios = [], onCambio, onError }: Props) {
  const [abierta, setAbierta] = useState(false);
  return (
    <div className="zonas-losa__cimientos" data-testid="cimientos-de-la-zona" data-zona={zona.id}>
      <div className="row">
        <button type="button" className="btn btn--sm" aria-expanded={abierta} aria-label={`Cimientos de ${zona.nombre}`} onClick={() => setAbierta((v) => !v)}>
          {abierta ? 'Ocultar los cimientos' : 'Cimientos'}
        </button>
        <span className="text-mute text-xs">Con cotas de desplante</span>
      </div>
      {abierta && <CuerpoDeLosCimientos zona={zona} puntos={puntos} puedeEditar={puedeEditar} espacios={espacios} onCambio={onCambio} onError={onError} />}
    </div>
  );
}

function CuerpoDeLosCimientos({ zona, puntos = [], puedeEditar, espacios = [], onCambio, onError }: Props) {
  const consulta = useCalculoDeLosCimientosApiV1ZonasDeLosaZonaIdCimientosCalculoGet(zona.id, { query: { retry: false } });
  const c = consulta.data;
  return (
    <div className="zonas-losa__cuerpo" data-testid="cuerpo-de-los-cimientos">
      {consulta.isLoading && <p className="text-mute text-xs">Calculando los cimientos…</p>}
      {consulta.isError && (
        <p className="text-xs" role="alert">
          {mensaje(consulta.error, 'No se pudo calcular los cimientos de la zona.')}
        </p>
      )}
      {c && c.cimientos.length === 0 && (
        <p className="text-mute text-xs">La zona no tiene cimientos. Elige una línea del plano y úsala como cimiento con su cota de desplante.</p>
      )}
      {c?.advertencias.map((a) => (
        <p key={a} className="text-xs" role="alert">
          {a}
        </p>
      ))}
      {c?.cimientos.map((e, i) => (
        <FilaDelCimiento key={e.id} e={e} numero={i + 1} puntos={puntos} puedeEditar={puedeEditar} espacios={espacios} onCambio={onCambio} onError={onError} />
      ))}
      {c && c.cimientos.length > 0 && (
        <p className="text-sm" data-testid="cimientos-resumen">
          Total: {num(c.totales.longitud_m)} m · {num(c.totales.volumen_m3, 3)} m³
          {c.totales.conceptos.length > 0 && ' · '}
          {c.totales.conceptos.map((k) => `${k.concepto.clave} ${num(k.cantidad, 3)} m³`).join(' · ')}
        </p>
      )}
      {c && c.por_espacio.length > 0 && (
        <div className="mct__tabla-caja">
          <table className="table" aria-label="Lo que paga el cimiento de cada espacio">
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
                    <td className="mono">{num(k.cantidad, 3)} m³</td>
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
    </div>
  );
}

function FilaDelCimiento({
  e, numero, puntos, puedeEditar, espacios = [], onCambio, onError,
}: {
  readonly e: CimientoDeLaZonaCalculado;
  readonly numero: number;
  readonly puntos: readonly PuntoDeNivelDelPlano[];
  readonly puedeEditar: boolean;
  readonly espacios?: readonly Espacio[];
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}) {
  const cambiar = useCambiarCimientoApiV1CimientosDeZonaCimientoIdPut<ErrorApi>();
  const quitar = useQuitarCimientoApiV1CimientosDeZonaCimientoIdDelete<ErrorApi>();
  const r = e.calculo;
  // Lo que está vacío sale del punto de nivel o de la zona: solo se manda lo que se tecleó.
  const [desplante, setDesplante] = useState(e.origen_de_cotas.desplante === 'explicita' && r ? String(r.cotas.desplante_m) : '');
  const [corona, setCorona] = useState(e.origen_de_cotas.corona === 'explicita' && r ? String(r.cotas.corona_m) : '');
  const [punto, setPunto] = useState(e.punto_nivel_id ?? '');
  const [caras, setCaras] = useState(String(r?.seccion.caras ?? 1));
  const [dentellon, setDentellon] = useState(r?.dentellon.opcion ?? false);

  function datos(extra: { espacio_id?: string | null } = {}): CimientoDeLaZonaPeticion | null {
    const d = cotaOpcional(desplante);
    const co = cotaOpcional(corona);
    if (d === null || co === null) return null;
    return {
      trazo_id: e.trazo_id,
      ...(d === undefined ? {} : { cota_desplante_m: d }),
      ...(punto ? { punto_nivel_id: punto } : {}),
      ...(co === undefined ? {} : { cota_corona_m: co }),
      caras: caras === '2' ? 2 : 1,
      dentellon,
      ...extra,
    };
  }

  async function guardar(extra: { espacio_id?: string | null } = {}, aviso = `Cimiento ${numero} actualizado.`) {
    const d = datos(extra);
    if (d === null) {
      onError('Una cota del cimiento no es un número válido.');
      return;
    }
    try {
      await cambiar.mutateAsync({ cimientoId: e.id, data: d });
      refrescarCimientos();
      onCambio(aviso);
    } catch (err) {
      onError(mensaje(err, 'No se pudo cambiar el cimiento.'));
    }
  }

  async function quitarCimiento() {
    try {
      await quitar.mutateAsync({ cimientoId: e.id });
      refrescarCimientos();
      onCambio(`Cimiento ${numero} quitado de la zona.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudo quitar el cimiento.'));
    }
  }

  return (
    <div className="mct__bloque" data-cimiento-de-la-zona={e.id} data-con-error={e.error ? 'si' : 'no'} aria-label={`Cimiento ${numero}`}>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        <strong>Cimiento {numero}</strong>
        <span className="badge badge--outline">longitud de una línea del plano: {num(e.longitud_m)} m</span>
        {r?.conceptos.map((k) => (
          <span key={k.concepto.clave} className="badge badge--ok" title={k.concepto.descripcion}>
            {k.concepto.clave} · del catálogo
          </span>
        ))}
      </div>
      {e.error && (
        <p className="text-sm" role="alert" data-testid="cimiento-error">
          {e.error}
        </p>
      )}
      {r && (
        <p className="text-sm" data-testid="cimiento-de-la-zona-resumen">
          Desplante {num(r.cotas.desplante_m)} m ({NOMBRE_DEL_ORIGEN_DE_COTA[e.origen_de_cotas.desplante]}) · corona {num(r.cotas.corona_m)} m (
          {NOMBRE_DEL_ORIGEN_DE_COTA[e.origen_de_cotas.corona]}) · altura {num(r.cotas.altura_m)} m · base {num(r.seccion.base_m)} m · {num(r.volumen_m3_ml, 3)} m³ por metro ·{' '}
          {num(r.volumen_m3, 3)} m³ de {r.conceptos[0]?.concepto.clave}
        </p>
      )}
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <label className="mct__campo">
          Cota de desplante (m)
          <input className="input" inputMode="decimal" aria-label={`Cota de desplante del cimiento ${numero}`} disabled={!puedeEditar} placeholder="la del punto de nivel" value={desplante} onChange={(x) => setDesplante(x.target.value)} />
        </label>
        <label className="mct__campo">
          Punto de nivel del desplante
          <select className="input" aria-label={`Punto de nivel del cimiento ${numero}`} disabled={!puedeEditar} value={punto} onChange={(x) => setPunto(x.target.value)}>
            <option value="">Ninguno</option>
            {puntos.map((p) => (
              <option key={p.trazo_id} value={p.trazo_id}>
                {p.rotulo ?? 'Sin rótulo'} ({num(Number(p.cota_m))} m)
              </option>
            ))}
          </select>
        </label>
        <label className="mct__campo">
          Cota de la corona (m)
          <input className="input" inputMode="decimal" aria-label={`Cota de la corona del cimiento ${numero}`} disabled={!puedeEditar} placeholder="arranque de la cadena de desplante" value={corona} onChange={(x) => setCorona(x.target.value)} />
        </label>
        <label className="mct__campo">
          Caras inclinadas
          <select className="input" aria-label={`Caras del cimiento ${numero}`} disabled={!puedeEditar} value={caras} onChange={(x) => setCaras(x.target.value)}>
            <option value="1">1 (de lindero)</option>
            <option value="2">2 (simétrico)</option>
          </select>
        </label>
        <label className="mct__campo mct__campo--casilla">
          <input type="checkbox" aria-label={`Dentellón del cimiento ${numero}`} disabled={!puedeEditar} checked={dentellon} onChange={(x) => setDentellon(x.target.checked)} />
          <span>Dentellón (desde 2.00 m)</span>
        </label>
        <label className="mct__campo">
          Espacio
          <select
            className="input"
            aria-label={`Espacio del cimiento ${numero}`}
            disabled={!puedeEditar || cambiar.isPending}
            value={e.espacio_id ?? ''}
            onChange={(x) => void guardar({ espacio_id: x.target.value || null }, x.target.value ? `Cimiento ${numero} asignado a su espacio.` : `Cimiento ${numero} sin espacio.`)}
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
          <button type="button" className="btn btn--sm" aria-label={`Guardar el cimiento ${numero}`} disabled={cambiar.isPending} onClick={() => void guardar()}>
            Guardar el cimiento
          </button>
          <button type="button" className="btn btn--sm" aria-label={`Quitar el cimiento ${numero}`} disabled={quitar.isPending} onClick={() => void quitarCimiento()}>
            Quitar
          </button>
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
