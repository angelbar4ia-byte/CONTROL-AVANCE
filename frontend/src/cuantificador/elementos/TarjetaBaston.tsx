/**
 * La tarjeta del bastón (BA-1) — Ola 4, lane 4D. Como las demás, **no calcula nada**: cada cambio se manda al servidor
 * (`/biblioteca-de-elementos/baston/{clave}/calcular`) y se dibuja lo que responde.
 *
 * El bastón se mide por **longitud de trazo**: varilla, separación y largo del bastón. El largo capturado INCLUYE los ganchos y es el corte (el tramo recto es el largo menos los ganchos y nombra el escalón). Se corta con los módulos de 1, 1.5, 2, 3,
 * 4 y 6 m (corte ajustado, lo más conservador, Q28); el corte exacto se muestra solo como referencia. Muestra el escalón del catálogo que
 * lo paga (exacto, el primero más largo o ninguno), su conciliación (= ≈ ≠) y las versiones propuestas. Cuando falta el escalón avisa y
 * deja proponer un concepto nuevo con clave provisional, sin precio ni destajo; solo Control de obra autoriza.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost as useAutorizarPropuesta,
  useCalcularElBastonApiV1BibliotecaDeElementosBastonClaveCalcularPost as useCalcularBaston,
  useDefinicionDelBastonApiV1BibliotecaDeElementosBastonClaveGet as useDefinicion,
  useProponerActualizacionDeApuApiV1BibliotecaDeElementosBastonClavePropuestasActualizarApuPost as useProponerApu,
  useProponerConceptoNuevoApiV1BibliotecaDeElementosBastonClavePropuestasConceptoNuevoPost as useProponerConceptoNuevo,
  usePropuestasDelBastonApiV1BibliotecaDeElementosBastonClavePropuestasGet as usePropuestas,
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost as useRechazarPropuesta,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { CalculoDelBaston, CalculoDelBastonPeticion } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';
import { useSesion } from '@/app/sesion';

import { DriversUsadosDelCalculo } from './DriversUsadosDelCalculo';

import { numeroTecleado } from '../volumen';

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const MARCA: Record<string, { texto: string; clase: string }> = {
  '=': { texto: '=', clase: 'badge badge--ok' },
  '≈': { texto: '≈', clase: 'badge badge--info' },
  '≠': { texto: '≠', clase: 'badge badge--danger' },
  solo_catalogo: { texto: 'solo en el catálogo', clase: 'badge badge--warn' },
  solo_elemento: { texto: 'solo en el elemento', clase: 'badge badge--outline' },
};
const ESTADO: Record<string, string> = { pendiente: 'Pendiente', autorizada: 'Autorizada', rechazada: 'Rechazada' };
const ROL: Record<string, string> = { costos: 'Costos', control_obra: 'Control de obra' };
const ESCALON: Record<string, string> = {
  exacto: 'Escalón exacto del catálogo',
  mayor: 'Primer escalón más largo del catálogo',
  sin_escalon: 'Sin escalón en el catálogo',
};

interface Props {
  readonly clave: string;
  /** La obra actual: el cálculo lee sus drivers (traslape, tolerancia de corte, máximo de piezas). */
  readonly obraId?: string;
}

/** La varilla de 12 m con los bastones que salen de ella, a escala. Solo dibuja lo que el servidor calculó. */
function VarillaCortada({ c }: { readonly c: CalculoDelBaston }) {
  const corte = c.ajustado.corte;
  const ancho = 360;
  const k = ancho / c.varilla.largo_m;
  const n = corte.piezas_por_varilla;
  const modulo = corte.modulo_m;
  const piezas = Array.from({ length: n }, (_, i) => i);
  return (
    <svg viewBox={`0 0 ${ancho + 10} 44`} width="100%" role="img" aria-label="Varilla de 12 metros cortada en módulos" data-testid="baston-varilla">
      {piezas.map((i) => (
        <g key={i}>
          <rect x={5 + i * modulo * k} y={6} width={modulo * k} height={22} fill="var(--c-surface-2, #e6d5c3)" stroke="currentColor" strokeWidth={1} />
          <text x={5 + (i + 0.5) * modulo * k} y={21} textAnchor="middle" fontSize={9} fill="currentColor">
            {num(modulo, 1)}
          </text>
        </g>
      ))}
      <rect x={5} y={6} width={ancho} height={22} fill="none" stroke="currentColor" strokeWidth={1.5} />
      <text x={5} y={41} fontSize={9} fill="currentColor">
        varilla de {num(c.varilla.largo_m, 0)} m · {n} módulo{n === 1 ? '' : 's'} de {num(modulo, 1)} m
      </text>
    </svg>
  );
}

export function TarjetaBaston({ clave, obraId = '' }: Props) {
  const { sesion } = useSesion();
  const puedeProponer = sesion?.rol === 'control_obra' || sesion?.rol === 'costos';
  const puedeAutorizar = sesion?.rol === 'control_obra';
  const definicion = useDefinicion(clave);
  const calcular = useCalcularBaston<ErrorApi>();
  const propuestas = usePropuestas(clave);
  const proponerNuevo = useProponerConceptoNuevo<ErrorApi>();
  const proponerApu = useProponerApu<ErrorApi>();
  const autorizar = useAutorizarPropuesta<ErrorApi>();
  const rechazar = useRechazarPropuesta<ErrorApi>();
  const d = definicion.data;

  const [trazo, setTrazo] = useState('1');
  const [varilla, setVarilla] = useState('3');
  const [sep, setSep] = useState('25');
  const [largo, setLargo] = useState('120');
  const [puntas, setPuntas] = useState('0');
  // El largo capturado ya incluye los ganchos (decisión 2026-11-19): corte = largo; tramo recto = largo − ganchos. Número de ganchos y su largo en diámetros; `gancho` en cm vacío = se usan los diámetros.
  const [ganchos, setGanchos] = useState('2');
  const [ganchoDiam, setGanchoDiam] = useState('12');
  const [ganchoCm, setGanchoCm] = useState('');
  // `null` = sin tocar: el traslape lo da el driver de la obra (o el valor por defecto) y no se manda.
  const [traslape, setTraslape] = useState<string | null>(null);
  const [calculo, setCalculo] = useState<CalculoDelBaston | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const turno = useRef(0);

  // Al cambiar de elemento, la tarjeta vuelve a los valores del elemento.
  useEffect(() => {
    if (!d) return;
    const p = d.parametros_por_defecto;
    setTrazo(String(p.trazo_m));
    setVarilla(String(p.varilla_numero));
    setSep(String(p.sep_cm));
    setLargo(String(p.largo_cm));
    setPuntas(String(p.puntas_cm));
    setGanchos(String(p.ganchos));
    setGanchoDiam(String(p.gancho_diametros));
    setGanchoCm('');
    setTraslape(null);
    setCalculo(null);
    setError(null);
    setAviso(null);
  }, [d]);

  const peticion = useMemo<CalculoDelBastonPeticion | null>(() => {
    if (!d) return null;
    if ([trazo, sep, largo, puntas, ganchos, ganchoDiam, traslape ?? '0'].some((t) => t.trim() === '')) return null;
    const t = numeroTecleado(trazo);
    const s = numeroTecleado(sep);
    const l = numeroTecleado(largo);
    const p = numeroTecleado(puntas);
    const tr = traslape === null ? null : numeroTecleado(traslape);
    const g = Math.trunc(numeroTecleado(ganchos));
    const gd = numeroTecleado(ganchoDiam);
    const gc = ganchoCm.trim() === '' ? null : numeroTecleado(ganchoCm);
    const v = Math.trunc(numeroTecleado(varilla));
    if (!(t > 0 && s >= 5 && s <= 200 && l >= 10 && l <= 3000 && p >= 0 && p <= 100 && (tr === null || (tr >= 0 && tr <= 100)) && v >= 3 && v <= 6 && g >= 0 && g <= 2 && gd >= 0 && gd <= 40 && (gc === null || (gc >= 0 && gc <= 100)))) return null;
    return {
      trazo_m: t,
      varilla_numero: v,
      sep_cm: s,
      largo_cm: l,
      puntas_cm: p,
      ganchos: g,
      gancho_diametros: gd,
      ...(gc === null ? {} : { gancho_cm: gc }),
      ...(tr === null ? {} : { traslape_diametros: tr }),
      ...(obraId === '' ? {} : { obra_id: obraId }),
    };
  }, [d, trazo, varilla, sep, largo, puntas, ganchos, ganchoDiam, ganchoCm, traslape, obraId]);

  const { mutateAsync } = calcular;
  useEffect(() => {
    if (peticion === null) return;
    const mio = ++turno.current;
    const espera = setTimeout(() => {
      mutateAsync({ clave, data: peticion })
        .then((r) => {
          if (mio !== turno.current) return;
          setCalculo(r);
          setError(null);
        })
        .catch((e: unknown) => {
          if (mio !== turno.current) return;
          setError(e instanceof Error ? e.message : 'No se pudo calcular el bastón.');
        });
    }, 200);
    return () => clearTimeout(espera);
  }, [clave, peticion, mutateAsync]);

  function recargar() {
    void queryClient.invalidateQueries();
  }
  async function correr(accion: () => Promise<string>) {
    try {
      setAviso(await accion());
      setError(null);
      recargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo completar la acción.');
    }
  }

  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando el elemento…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;

  const lista = propuestas.data ?? [];
  const pendientes = lista.filter((p) => p.estado === 'pendiente');
  const sinEscalon = calculo?.escalon === 'sin_escalon';
  const hayDiferencias = (calculo?.conciliacion ?? []).some((c) => (c.resumen['≈'] ?? 0) + (c.resumen['≠'] ?? 0) > 0);
  const propuestaDe = (conceptoClave: string, insumo: string) => {
    const mias = lista
      .filter((p) => p.concepto_clave === conceptoClave && p.clase === 'version_de_concepto' && p.estado !== 'rechazada')
      .sort((a, b) => (a.estado === 'autorizada' ? 0 : 1) - (b.estado === 'autorizada' ? 0 : 1));
    for (const p of mias) {
      const c = p.cambios.find((x) => x.insumo.toUpperCase() === insumo.toUpperCase());
      if (c) return { valor: c.despues, estado: p.estado };
    }
    return null;
  };

  return (
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`} data-baston={d.clave}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span> · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se mide por {d.se_mide_por} · módulos de corte {d.modulos_de_corte_m.map((m) => num(m, m % 1 === 0 ? 0 : 1)).join(', ')} m
          </div>
        </div>
        {calculo && (
          <span className={calculo.concepto.estado === 'propuesto' ? 'badge badge--warn' : 'badge badge--outline'} data-testid="baston-concepto">
            {calculo.concepto.clave}
            {calculo.concepto.estado === 'propuesto' ? ' · provisional' : ''}
          </span>
        )}
      </header>

      <section className="mct__parametros" aria-label="Parámetros del bastón">
        <label className="mct__campo">
          <span>Longitud de trazo (m)</span>
          <input className="input" inputMode="decimal" aria-label="Longitud de trazo" value={trazo} onChange={(e) => setTrazo(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Varilla</span>
          <select className="select" aria-label="Varilla" value={varilla} onChange={(e) => setVarilla(e.target.value)}>
            {d.varillas.map((v) => (
              <option key={v.numero} value={String(v.numero)}>
                {v.nombre} · {v.clave}
              </option>
            ))}
          </select>
        </label>
        <label className="mct__campo">
          <span>Cada cuánto (cm)</span>
          <input className="input" inputMode="decimal" aria-label="Separación en centímetros" value={sep} onChange={(e) => setSep(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Largo del bastón (cm; incluye los ganchos)</span>
          <input className="input" inputMode="decimal" aria-label="Largo del bastón en centímetros" value={largo} onChange={(e) => setLargo(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Puntas (cm; anclaje que no es gancho)</span>
          <input className="input" inputMode="decimal" aria-label="Puntas en centímetros" value={puntas} onChange={(e) => setPuntas(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Ganchos por bastón (0 = sin gancho)</span>
          <select className="input" aria-label="Ganchos por bastón" value={ganchos} onChange={(e) => setGanchos(e.target.value)}>
            <option value="0">0 · sin gancho</option>
            <option value="1">1 · en una punta</option>
            <option value="2">2 · en las dos puntas</option>
          </select>
        </label>
        <label className="mct__campo">
          <span>Gancho (diámetros de la varilla)</span>
          <input className="input" inputMode="decimal" aria-label="Gancho en diámetros" value={ganchoDiam} onChange={(e) => setGanchoDiam(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Gancho (cm; vacío = por diámetros)</span>
          <input
            className="input"
            inputMode="decimal"
            aria-label="Gancho en centímetros"
            placeholder={calculo ? num(calculo.gancho.longitud_cm, 2) : ''}
            value={ganchoCm}
            onChange={(e) => setGanchoCm(e.target.value)}
          />
        </label>
        <label className="mct__campo">
          <span>Traslape (diámetros)</span>
          <input className="input" inputMode="decimal" aria-label="Traslape en diámetros" value={traslape ?? String(calculo?.parametros.traslape_diametros ?? d?.parametros_por_defecto.traslape_diametros ?? 40)} onChange={(e) => setTraslape(e.target.value)} />
        </label>
      </section>

      <DriversUsadosDelCalculo usados={calculo?.drivers_usados} hayObra={obraId !== ''} />

      {peticion === null && (
        <p className="text-sm mct__aviso">Captura la separación (5 a 200 cm), el largo (10 a 3000 cm), las puntas (0 a 100 cm), los ganchos (0 a 2; 0 a 40 diámetros o 0 a 100 cm) y un trazo mayor que cero.</p>
      )}
      {error && (
        <p className="text-sm mct__error" role="alert">
          {error}
        </p>
      )}
      {aviso && (
        <p className="text-sm" role="status" data-testid="baston-aviso">
          {aviso}
        </p>
      )}

      {calculo && (
        <>
          <section className="mct__resumen" aria-label="Resultado">
            <span className="chip" data-testid="baston-piezas">
              <b>{num(calculo.ajustado.bastones, 0)} bastones</b> (pago por pieza)
            </span>
            <span className="chip" data-testid="baston-gancho">
              Gancho {num(calculo.gancho.ganchos, 0)} × {num(calculo.gancho.longitud_cm, 2)} cm = {num(calculo.gancho.total_por_baston_cm, 2)} cm por bastón
            </span>
            <span className="chip" data-testid="baston-corte">
              Corte de {num(calculo.ajustado.corte.necesario_m, 2)} m, de los cuales {num(calculo.gancho.total_por_baston_cm, 2)} cm de ganchos: {num(calculo.ajustado.corte.piezas_por_baston, 0)} × {num(calculo.ajustado.corte.modulo_m, 1)} m · {num(calculo.ajustado.corte.piezas_por_varilla, 0)} por varilla
            </span>
            <span className="chip" data-testid="baston-recto">
              Tramo recto {num(calculo.ajustado.corte.recto_m, 2)} m (nombra el escalón)
            </span>
            <span className="chip" data-testid="baston-varillas">
              <b>{num(calculo.ajustado.varillas, 0)} varillas</b> de {num(calculo.varilla.largo_m, 0)} m
            </span>
            <span className="chip" data-testid="baston-kg">
              {num(calculo.ajustado.kg, 2)} kg · sobra {num(calculo.ajustado.sobra_m, 2)} m
            </span>
          </section>

          <VarillaCortada c={calculo} />

          <section className="mct__bloque" aria-label="Corte ajustado y corte exacto">
            <h3>Corte ajustado a módulos y corte exacto</h3>
            <p className="text-mute text-xs">
              Se paga el ajustado (Q28, lo más conservador: cada bastón gasta su módulo completo). El exacto es solo la referencia del mockup.
            </p>
            <div className="mct__tabla-caja">
              <table className="mct__tabla" data-testid="baston-comparacion">
                <thead>
                  <tr>
                    <th>Corte</th>
                    <th className="n">Bastones</th>
                    <th className="n">Varillas</th>
                    <th className="n">Material (m)</th>
                    <th className="n">kg</th>
                    <th className="n">Sobra (m)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr data-corte="ajustado">
                    <td>Ajustado a módulos</td>
                    <td className="n mono">{num(calculo.ajustado.bastones, 0)}</td>
                    <td className="n mono">{num(calculo.ajustado.varillas, 0)}</td>
                    <td className="n mono">{num(calculo.ajustado.material_m, 2)}</td>
                    <td className="n mono">{num(calculo.ajustado.kg, 2)}</td>
                    <td className="n mono">{num(calculo.ajustado.sobra_m, 2)}</td>
                  </tr>
                  <tr data-corte="exacto">
                    <td>Exacto (referencia)</td>
                    <td className="n mono">{num(calculo.exacto.bastones, 0)}</td>
                    <td className="n mono">{num(calculo.exacto.varillas, 0)}</td>
                    <td className="n mono">{num(calculo.exacto.material_m, 2)}</td>
                    <td className="n mono">{num(calculo.exacto.kg, 2)}</td>
                    <td className="n mono">{num(calculo.exacto.sobra_m, 2)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section className="mct__bloque" aria-label="Concepto que lo paga" data-concepto-elegido={calculo.concepto.clave} data-escalon={calculo.escalon}>
            <h3>Concepto que lo paga</h3>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <span className="mono">{calculo.concepto.clave}</span>
              <span className="text-sm">{calculo.concepto.descripcion}</span>
              <span className={sinEscalon ? 'badge badge--warn' : calculo.escalon === 'mayor' ? 'badge badge--info' : 'badge badge--ok'} data-testid="baston-escalon">
                {ESCALON[calculo.escalon]}
              </span>
            </div>
            {sinEscalon && (
              <p className="text-sm mct__aviso" data-testid="baston-sin-escalon">
                Falta el escalón en el catálogo: se propone un concepto nuevo con clave provisional, sin precio ni destajo, pendiente de que Control de obra lo autorice.
              </p>
            )}
          </section>

          <section className="mct__bloque" aria-label="Conciliación con el catálogo">
            <h3>Conciliación con el catálogo</h3>
            <p className="text-mute text-xs">
              = hasta 3 %, ≈ hasta 8 %, ≠ más de 8 %, por metro de trazo. El catálogo no se edita; si hace falta se propone como nueva versión del concepto.
            </p>
            {calculo.conciliacion.length === 0 && (
              <p className="text-sm" data-testid="baston-sin-catalogo">
                <span className="badge badge--warn">Sin concepto en el catálogo</span> No hay con qué compararlo.
              </p>
            )}
            {calculo.conciliacion.map((c) => (
              <div key={c.concepto.clave} className="mct__bloque" data-conciliacion={c.concepto.clave}>
                <div>
                  <b className="mono">{c.concepto.clave}</b> · {c.concepto.descripcion} <span className="text-mute text-xs">({c.sobre})</span>
                </div>
                <div className="mct__tabla-caja">
                  <table className="mct__tabla">
                    <thead>
                      <tr>
                        <th>Insumo</th>
                        <th className="n">Catálogo</th>
                        <th className="n">Versión propuesta</th>
                        <th className="n">Elemento</th>
                        <th className="n">Diferencia</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {c.filas.map((f) => {
                        const vp = propuestaDe(c.concepto.clave, f.clave);
                        return (
                          <tr key={f.clave} data-marca={f.marca} data-insumo={f.clave}>
                            <td>
                              <span className="mono">{f.clave}</span> {f.descripcion}
                            </td>
                            <td className="n mono">{num(f.catalogo, 4)}</td>
                            <td className="n mono">
                              {vp ? (
                                <>
                                  {num(vp.valor, 4)} <span className="text-mute text-xs">({ESTADO[vp.estado]?.toLowerCase()})</span>
                                </>
                              ) : (
                                '—'
                              )}
                            </td>
                            <td className="n mono">{num(f.elemento, 4)}</td>
                            <td className="n mono">
                              {f.diferencia_pct === null || f.diferencia_pct === undefined ? '—' : `${f.diferencia_pct >= 0 ? '+' : ''}${num(f.diferencia_pct, 1)} %`}
                            </td>
                            <td>
                              <span className={MARCA[f.marca]?.clase}>{MARCA[f.marca]?.texto ?? f.marca}</span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {c.avisos.map((a) => (
                  <p key={a} className="text-xs mct__aviso">
                    {a}
                  </p>
                ))}
              </div>
            ))}
          </section>

          {calculo.avisos.length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias">
              {calculo.avisos.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
        </>
      )}

      <section className="mct__bloque" aria-label="Versiones propuestas">
        <h3>Versiones propuestas del catálogo</h3>
        <p className="text-mute text-xs">
          Costos propone y solo Control de obra autoriza; cada autorización crea la versión siguiente del concepto. El catálogo no se edita y no se
          inventan precios ni destajos.
        </p>
        {lista.length === 0 && <p className="text-sm">Este elemento no tiene propuestas.</p>}
        {lista.map((p) => (
          <div key={p.id} data-propuesta={p.concepto_clave} style={{ display: 'grid', gap: 3, padding: '4px 0', borderBottom: '1px solid var(--c-line-soft)' }}>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <span className="mono">{p.concepto_clave}</span>
              <span className={p.estado === 'autorizada' ? 'badge badge--ok' : p.estado === 'rechazada' ? 'badge badge--danger' : 'badge badge--warn'}>
                {ESTADO[p.estado]}
                {p.version ? ` · versión ${p.version}` : ''}
              </span>
              <span className="text-mute text-xs">
                {p.clase === 'concepto_nuevo' ? 'Concepto nuevo' : 'Nueva versión'} · propuso {p.propuso_nombre ?? '—'} ({ROL[p.propuso_rol ?? ''] ?? '—'})
              </span>
            </div>
            <div className="text-sm">{p.resumen}</div>
            {p.cambios.map((c) => (
              <div className="text-xs" key={c.insumo}>
                <span className="mono">{c.insumo}</span>: {num(c.antes, 4)} → {num(c.despues, 4)} {c.unidad}
              </div>
            ))}
            {p.motivo && <div className="text-xs">Motivo del rechazo: {p.motivo}</div>}
            {p.estado === 'pendiente' && puedeAutorizar && (
              <div className="row" style={{ gap: 6 }}>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() =>
                    void correr(async () => {
                      const r = await autorizar.mutateAsync({ propuestaId: p.id });
                      return `${p.concepto_clave}: propuesta autorizada, versión ${r.version}.`;
                    })
                  }
                >
                  Autorizar
                </button>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() =>
                    void correr(async () => {
                      const motivo = window.prompt('¿Por qué se rechaza? (opcional)') ?? undefined;
                      await rechazar.mutateAsync({ propuestaId: p.id, data: { motivo: motivo === '' ? null : motivo } });
                      return `${p.concepto_clave}: propuesta rechazada.`;
                    })
                  }
                >
                  Rechazar
                </button>
              </div>
            )}
          </div>
        ))}
        {puedeProponer && peticion !== null && (
          <div className="row" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            {calculo && calculo.concepto.estado === 'propuesto' && (
              <button
                type="button"
                className="btn btn--sm"
                disabled={proponerNuevo.isPending}
                onClick={() =>
                  void correr(async () => {
                    const r = await proponerNuevo.mutateAsync({ clave, data: peticion });
                    return r.creadas.length === 0
                      ? `${calculo.concepto.clave} ya está propuesto.`
                      : `${calculo.concepto.clave} propuesto como concepto nuevo: espera la autorización de Control de obra.`;
                  })
                }
              >
                Proponer el concepto nuevo
              </button>
            )}
            {calculo && calculo.concepto.estado === 'catalogo' && (
              <button
                type="button"
                className="btn btn--sm"
                disabled={proponerApu.isPending || !hayDiferencias}
                title={hayDiferencias ? undefined : 'El cálculo coincide con el catálogo: no hay nada que proponer.'}
                onClick={() =>
                  void correr(async () => {
                    const r = await proponerApu.mutateAsync({ clave, data: peticion });
                    const n = r.creadas.length;
                    return n === 0 ? 'No hay una versión nueva que proponer.' : `${n} versión${n > 1 ? 'es' : ''} propuesta${n > 1 ? 's' : ''} del concepto.`;
                  })
                }
              >
                Confirmar cálculo → proponer actualizar el APU
              </button>
            )}
            {pendientes.length > 0 && <span className="text-mute text-xs">{pendientes.length} esperan a Control de obra.</span>}
          </div>
        )}
      </section>

      <details className="mct__bloque" aria-label="Preguntas pendientes" data-testid="baston-pendientes">
        <summary>Preguntas pendientes del bastón</summary>
        <ul className="text-xs">
          {d.pendientes.map((p) => (
            <li key={p.clave} data-pendiente={p.clave}>
              <b>{p.clave}</b>. {p.texto}
            </li>
          ))}
        </ul>
      </details>
    </article>
  );
}
