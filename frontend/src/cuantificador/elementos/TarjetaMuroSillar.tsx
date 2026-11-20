/**
 * La tarjeta del muro de sillar amarillo de 19 cm (BAP-01010; biblioteca › Muros › Muros de sillar). Como las demás, **no calcula nada**: cada
 * cambio se manda al servidor (`/biblioteca-de-elementos/sillar/{clave}/calcular`) y se dibuja lo que responde.
 *
 * Muestra la pieza real del catálogo (PET-00008, 19 × 25 × 45 cm, a hilo), las piezas y la mezcla por m², el concepto que lo paga (BAP-01010, el
 * mismo del catálogo: no se inventa un concepto ni un precio), el desglose de la mezcla, el destajo del catálogo, la conciliación con la
 * composición real del concepto (= ≈ ≠), los drivers que leyó el cálculo (el desperdicio sale de `desperdicio_mamposteria`, F6) y las versiones
 * propuestas. Lo que el catálogo trae distinto no se edita: se propone como nueva versión de BAP-01010 y solo Control de obra la autoriza.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost as useAutorizarPropuesta,
  useCalcularSillarApiV1BibliotecaDeElementosSillarClaveCalcularPost as useCalcularSillar,
  useDefinicionDelSillarApiV1BibliotecaDeElementosSillarClaveGet as useDefinicion,
  useProponerActualizacionDeApuDelSillarApiV1BibliotecaDeElementosSillarClavePropuestasActualizarApuPost as useProponerApu,
  usePropuestasDeSillarApiV1BibliotecaDeElementosSillarClavePropuestasGet as usePropuestas,
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost as useRechazarPropuesta,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { CalculoDelSillar, CalculoDelSillarPeticion } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';
import { useSesion } from '@/app/sesion';

import { numeroTecleado } from '../volumen';
import { DriversUsadosDelCalculo } from './DriversUsadosDelCalculo';
import { PlantaDeLaHilada } from './TarjetaMuroTabique';

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

interface Props {
  readonly clave: string;
  /** La obra actual: el cálculo lee sus drivers (el desperdicio de mampostería). */
  readonly obraId?: string;
}

export function TarjetaMuroSillar({ clave, obraId = '' }: Props) {
  const { sesion } = useSesion();
  const puedeProponer = sesion?.rol === 'control_obra' || sesion?.rol === 'costos';
  const puedeAutorizar = sesion?.rol === 'control_obra';
  const definicion = useDefinicion(clave);
  const calcular = useCalcularSillar<ErrorApi>();
  const propuestas = usePropuestas(clave);
  const proponerApu = useProponerApu<ErrorApi>();
  const autorizar = useAutorizarPropuesta<ErrorApi>();
  const rechazar = useRechazarPropuesta<ErrorApi>();
  const d = definicion.data;

  const [cantidad, setCantidad] = useState('1');
  const [junta, setJunta] = useState('2');
  // Vacío = el desperdicio sale del driver `desperdicio_mamposteria` (petición > obra > valor de partida); con un número, manda la petición.
  const [desperdicio, setDesperdicio] = useState('');
  const [calculo, setCalculo] = useState<CalculoDelSillar | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const turno = useRef(0);

  useEffect(() => {
    if (!d) return;
    setCantidad('1');
    setJunta(String(d.parametros_por_defecto.junta_cm));
    setDesperdicio('');
    setCalculo(null);
    setError(null);
    setAviso(null);
  }, [d]);

  const peticion = useMemo<CalculoDelSillarPeticion | null>(() => {
    if (!d) return null;
    const q = numeroTecleado(cantidad);
    const j = numeroTecleado(junta);
    if (!(q > 0) || junta.trim() === '' || !(j >= 0)) return null;
    const base: CalculoDelSillarPeticion = { cantidad: q, junta_cm: j };
    if (desperdicio.trim() !== '') {
      const dp = numeroTecleado(desperdicio);
      if (!(dp >= 0)) return null;
      base.desperdicio_pct = dp;
    }
    if (obraId !== '') base.obra_id = obraId;
    return base;
  }, [d, cantidad, junta, desperdicio, obraId]);

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
          setError(e instanceof Error ? e.message : 'No se pudo calcular el elemento.');
        });
    }, 200);
    return () => clearTimeout(espera);
  }, [clave, peticion, mutateAsync]);

  async function correr(accion: () => Promise<string>) {
    try {
      setAviso(await accion());
      setError(null);
      void queryClient.invalidateQueries();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo completar la acción.');
    }
  }

  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando el elemento…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;

  const lista = propuestas.data ?? [];
  const pendientes = lista.filter((p) => p.estado === 'pendiente');
  const concepto = d.conceptos[0];
  const hayDiferencias = (calculo?.conciliacion ?? []).some((c) => (c.resumen['≈'] ?? 0) + (c.resumen['≠'] ?? 0) > 0);
  // La versión propuesta de cada insumo: la autorizada gana a la pendiente.
  const propuestaDe = (insumo: string) => {
    const mias = lista
      .filter((p) => p.concepto_clave === concepto?.clave && p.clase === 'version_de_concepto' && p.estado !== 'rechazada')
      .sort((a, b) => (a.estado === 'autorizada' ? 0 : 1) - (b.estado === 'autorizada' ? 0 : 1));
    for (const p of mias) {
      const c = p.cambios.find((x) => x.insumo.toUpperCase() === insumo.toUpperCase());
      if (c) return { valor: c.despues, estado: p.estado };
    }
    return null;
  };

  return (
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`} data-sillar={d.clave}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span> · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se mide por {d.se_mide_por} · espesor real {num(d.espesor_real_cm, 1)} cm
          </div>
        </div>
        <span className="badge badge--outline" data-testid="sillar-concepto">
          {concepto?.clave ?? clave} · del catálogo
        </span>
      </header>

      <section className="mct__parametros" aria-label="Parámetros del elemento">
        <label className="mct__campo">
          <span>m² de muro (sin huecos)</span>
          <input className="input" inputMode="decimal" aria-label="Cantidad" value={cantidad} onChange={(e) => setCantidad(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Junta (cm; supuesto, el catálogo no la trae)</span>
          <input className="input" inputMode="decimal" aria-label="Junta en centímetros" value={junta} onChange={(e) => setJunta(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Desperdicio de pieza y mezcla (%; vacío = driver de la obra)</span>
          <input
            className="input"
            inputMode="decimal"
            aria-label="Desperdicio de mampostería"
            placeholder={calculo ? String(calculo.parametros.desperdicio_de_pieza_pct) : ''}
            value={desperdicio}
            onChange={(e) => setDesperdicio(e.target.value)}
          />
        </label>
      </section>

      {peticion === null && <p className="text-sm mct__aviso">Las medidas se capturan en centímetros y por ciento, y la cantidad debe ser mayor que cero.</p>}
      {error && (
        <p className="text-sm mct__error" role="alert">
          {error}
        </p>
      )}
      {aviso && (
        <p className="text-sm" role="status" data-testid="sillar-aviso">
          {aviso}
        </p>
      )}

      {calculo && (
        <>
          <section className="mct__resumen" aria-label="Resultado">
            <span className="chip" data-testid="sillar-piezas">
              Sillar <b>{num(calculo.piezas.por_unidad, 2)} pza</b> por {calculo.unidad}
            </span>
            <span className="chip" data-testid="sillar-mezcla">
              Mezcla 1:4 <b>{num(calculo.mezcla.por_unidad, 4)} m³</b> por {calculo.unidad}
            </span>
            <span className="chip" data-testid="sillar-espesor">
              Espesor real {num(calculo.geometria.espesor_real_cm, 1)} cm
            </span>
            <span className="chip" data-testid="sillar-total">
              {num(calculo.piezas.total, 1)} pza ({num(calculo.piezas.a_comprar, 0)} a comprar) · {num(calculo.mezcla.total_m3, 3)} m³
            </span>
            <span className="badge badge--outline" data-testid="sillar-mano-de-obra" title={calculo.mano_de_obra.nota}>
              {calculo.mano_de_obra.destajo ? `Destajo ${calculo.mano_de_obra.destajo.clave}` : 'Sin destajo'}
            </span>
          </section>

          <section className="mct__bloque" aria-label="Concepto que lo paga" data-concepto-elegido={calculo.concepto.clave}>
            <h3>Concepto que lo paga</h3>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <span className="mono">{calculo.concepto.clave}</span>
              <span className="text-sm">{calculo.concepto.descripcion}</span>
              <span className="badge badge--ok">Matriz del catálogo</span>
            </div>
            <p className="text-mute text-xs">
              El elemento se liga al concepto que el catálogo ya tiene (regla F7): no se propone un concepto nuevo ni se inventan precios. {calculo.mano_de_obra.nota}
            </p>
          </section>

          <section className="mct__bloque" aria-label="Aparejo">
            <h3>Aparejo: {d.aparejo}</h3>
            <p className="text-sm">
              Pieza {num(calculo.pieza.ancho_cm, 0)} × {num(calculo.pieza.alto_cm, 0)} × {num(calculo.pieza.largo_cm, 0)} cm (espesor × alto × largo), {d.aparejo_texto}
            </p>
            <PlantaDeLaHilada g={calculo.geometria} junta={calculo.parametros.junta_cm} />
            <p className="text-mute text-xs">{d.planta_nota}</p>
          </section>

          <section className="mct__bloque" aria-label="Insumos del elemento">
            <h3>
              Insumos <span className="text-mute">(por {calculo.unidad}; total para {num(calculo.cantidad, 2)} {calculo.unidad})</span>
            </h3>
            <div className="mct__tabla-caja">
              <table className="mct__tabla">
                <thead>
                  <tr>
                    <th>Insumo</th>
                    <th className="n">Por {calculo.unidad}</th>
                    <th className="n">Total</th>
                    <th>Unidad</th>
                    <th className="n">A comprar</th>
                  </tr>
                </thead>
                <tbody>
                  {calculo.insumos.map((i) => (
                    <tr key={i.clave}>
                      <td>
                        <span className="mono">{i.clave}</span> {i.descripcion}
                      </td>
                      <td className="n mono">{num(i.por_unidad, 4)}</td>
                      <td className="n mono">{num(i.total, 3)}</td>
                      <td>{i.unidad === 'm3' ? 'm³' : i.unidad}</td>
                      <td className="n mono">{i.a_comprar === null || i.a_comprar === undefined ? '—' : num(i.a_comprar, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-mute text-xs">
              La mezcla se abre en {calculo.mezcla_compuesta.map((m) => `${num(m.total, 3)} ${m.unidad} de ${m.descripcion.toLowerCase()}`).join(', ')}. Sin herramienta
              ni equipo: el catálogo no trae insumos de esa clase.
            </p>
          </section>

          <DriversUsadosDelCalculo usados={calculo.drivers_usados} hayObra={obraId !== ''} />

          <section className="mct__bloque" aria-label="Conciliación con el catálogo">
            <h3>Conciliación con el catálogo</h3>
            <p className="text-mute text-xs">
              = hasta 3 %, ≈ hasta 8 %, ≠ más de 8 %. Lo que el catálogo trae distinto se muestra: no se edita; si hace falta se propone como nueva versión de
              BAP-01010. La mano de obra y el destajo no se calculan.
            </p>
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
                        const vp = propuestaDe(f.clave);
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
                {c.mano_de_obra.length > 0 && (
                  <p className="text-mute text-xs">
                    Destajo del catálogo (el elemento no lo calcula): {c.mano_de_obra.map((m) => `${m.clave} ${m.descripcion}`).join(', ')}.
                  </p>
                )}
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
          Costos propone y solo Control de obra autoriza; cada autorización crea la versión siguiente del concepto. El catálogo no se edita y no se inventan
          precios ni destajos.
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
                Nueva versión · propuso {p.propuso_nombre ?? '—'} ({ROL[p.propuso_rol ?? ''] ?? '—'})
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
        {puedeProponer && (
          <div className="row" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            {peticion !== null && (
              <button
                type="button"
                className="btn btn--sm"
                disabled={proponerApu.isPending || !hayDiferencias}
                title={hayDiferencias ? undefined : 'El cálculo coincide con el catálogo: no hay nada que proponer.'}
                onClick={() =>
                  void correr(async () => {
                    const r = await proponerApu.mutateAsync({ clave, data: peticion });
                    return r.creadas.length === 0
                      ? 'No hay una versión nueva que proponer (ya hay una vigente).'
                      : 'Versión de BAP-01010 propuesta: espera la autorización de Control de obra.';
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

      <section className="mct__bloque mct__pendientes" aria-label="Pendientes por confirmar">
        <h3>Supuestos y pendientes por confirmar</h3>
        <ul>
          {d.pendientes.map((p) => (
            <li key={p.clave}>
              <span className="badge badge--outline">{p.clave}</span> {p.texto}
            </li>
          ))}
        </ul>
      </section>
    </article>
  );
}
