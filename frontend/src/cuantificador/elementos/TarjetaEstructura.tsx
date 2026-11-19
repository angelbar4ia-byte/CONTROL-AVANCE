/**
 * La tarjeta de un castillo (K-1 a K-8), un aparente (BAP-03010, BAP-03020, BAP-03030) o una columna forjada (EST-07010,
 * EST-07011). Igual que la del muro de piedra, **no calcula nada**: cada cambio del alto se manda al servidor
 * (`/biblioteca-de-elementos/estructura/{clave}/calcular`) y se dibuja lo que responde.
 *
 * Muestra el armado con sus cortes, los conceptos del catálogo que lo pagan (con el escalón que corresponde al alto), la
 * conciliación contra la composición real del catálogo y las versiones propuestas. Lo que el catálogo trae mal no se edita: se
 * propone como **nueva versión de concepto** y solo Control de obra la autoriza. Sin precios ni destajos.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost as useAutorizarPropuesta,
  useCalcularEstructuraApiV1BibliotecaDeElementosEstructuraClaveCalcularPost as useCalcularEstructura,
  useConciliacionDeEstructuraApiV1BibliotecaDeElementosEstructuraClaveConciliacionGet as useConciliacion,
  useDefinicionDeEstructuraApiV1BibliotecaDeElementosEstructuraClaveGet as useDefinicion,
  useProponerConceptoPorAlturaApiV1BibliotecaDeElementosEstructuraClavePropuestasConceptoPorAlturaPost as useProponerPorAltura,
  useProponerCorreccionesApiV1BibliotecaDeElementosEstructuraClavePropuestasCorreccionesPost as useProponerCorrecciones,
  usePropuestasDeEstructuraApiV1BibliotecaDeElementosEstructuraClavePropuestasGet as usePropuestas,
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost as useRechazarPropuesta,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { CalculoDeEstructura, ConceptoConciliado } from '@/api/generado/modelo';
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
const RANURA: Record<string, string> = { acero: 'Acero · por pieza', colado: 'Colado y cimbra', completo: 'Completo · por metro' };
const ESTADO: Record<string, string> = { pendiente: 'Pendiente', autorizada: 'Autorizada', rechazada: 'Rechazada' };
const ROL: Record<string, string> = { costos: 'Costos', control_obra: 'Control de obra' };

interface Props {
  readonly clave: string;
  /** La obra actual: el cálculo lee sus drivers (altura estándar, traslapes, puntas, desperdicios…). */
  readonly obraId?: string;
}

export function TarjetaEstructura({ clave, obraId = '' }: Props) {
  const { sesion } = useSesion();
  const puedeProponer = sesion?.rol === 'control_obra' || sesion?.rol === 'costos';
  const puedeAutorizar = sesion?.rol === 'control_obra';
  const definicion = useDefinicion(clave);
  const calcular = useCalcularEstructura<ErrorApi>();
  const conciliacion = useConciliacion(clave);
  const propuestas = usePropuestas(clave);
  const proponer = useProponerCorrecciones<ErrorApi>();
  const proponerPorAltura = useProponerPorAltura<ErrorApi>();
  const autorizar = useAutorizarPropuesta<ErrorApi>();
  const rechazar = useRechazarPropuesta<ErrorApi>();
  const [alto, setAlto] = useState<string | null>(null);
  const [calculo, setCalculo] = useState<CalculoDeEstructura | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const turno = useRef(0);

  // Al cambiar de elemento, el alto vuelve al suyo y el cálculo anterior no se queda a medias.
  useEffect(() => {
    setAlto(null);
    setCalculo(null);
    setError(null);
    setAviso(null);
  }, [clave]);

  const altoPorDefecto = definicion.data?.alto_por_defecto_m;
  const campoAlto = alto ?? (calculo ? calculo.alto_m.toFixed(2) : altoPorDefecto !== undefined ? altoPorDefecto.toFixed(2) : '');
  const altoNumerico = useMemo(() => numeroTecleado(campoAlto), [campoAlto]);

  const { mutateAsync } = calcular;
  useEffect(() => {
    if (altoPorDefecto === undefined) return;
    const tecleado = alto === null ? null : numeroTecleado(alto);
    if (tecleado !== null && !(tecleado > 0)) return;
    const mio = ++turno.current;
    const espera = setTimeout(() => {
      // Con el alto sin tocar no se manda: lo da la altura estándar de la obra (driver) o el alto fijo del elemento.
      mutateAsync({ clave, data: { ...(tecleado === null ? {} : { alto_m: tecleado }), ...(obraId === '' ? {} : { obra_id: obraId }) } })
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
  }, [clave, alto, altoPorDefecto, obraId, mutateAsync]);

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

  const d = definicion.data;
  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando el elemento…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;

  const unidadDeCalculo = d.tipo === 'castillo' ? 'pieza' : 'metro lineal';
  const concreto = calculo
    ? calculo.forro
      ? `${num(calculo.conceptos.find((c) => c.insumos['MEZ-01020'] !== undefined)?.insumos['MEZ-01020'], 4)} m³ por pieza`
      : `${num(calculo.colado.concreto_m3_ml, 4)} m³ por metro`
    : '';
  const lista = propuestas.data ?? [];
  const pendientes = lista.filter((p) => p.estado === 'pendiente');

  return (
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`} data-estructura={d.clave}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span>
            {d.alias ? <span className="text-mute"> ({d.alias})</span> : null} · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se calcula por {unidadDeCalculo}
            {d.posicion ? ` · va en ${d.posicion}` : ''}
          </div>
        </div>
        <span className="badge badge--outline" title="Calculado por el servidor">
          {d.fuente}
        </span>
      </header>

      <section className="mct__parametros" aria-label="Parámetros del elemento">
        <label className="mct__campo">
          <span>{d.alto_fijo_m ? 'Alto (m): fijo en el catálogo' : 'Alto de la pieza (m)'}</span>
          <input
            className="input"
            inputMode="decimal"
            aria-label="Alto en metros"
            value={campoAlto}
            onChange={(e) => setAlto(e.target.value)}
          />
        </label>
        <div className="mct__campo">
          <span>Sección (cm)</span>
          <span className="mono" data-testid="estructura-seccion">
            {d.tipo === 'castillo'
              ? `${num(d.seccion.ancho_cm, 0)} × ${num(d.seccion.largo_cm, 0)} (ancho del muro × largo)`
              : `${num(d.seccion.ancho_cm, 0)} × ${num(d.seccion.peralte_cm, 0)} (ancho × peralte)`}
          </span>
        </div>
        <div className="mct__campo">
          <span>Armado</span>
          <span data-testid="estructura-armado">
            {d.armado.tipo === 'armex'
              ? `Armex ${d.armado.armex}`
              : `${d.armado.varillas.map((v) => `${v.cantidad} var. no.${v.numero}`).join(' + ')}${
                  d.armado.anillo ? `, ${d.armado.anillo.insumo} @${d.armado.anillo.sep_cm} cm` : ''
                }`}
          </span>
        </div>
      </section>

      {!(altoNumerico > 0) && <p className="text-sm mct__aviso">El alto se captura en metros y debe ser mayor que cero.</p>}
      {error && (
        <p className="text-sm mct__error" role="alert">
          {error}
        </p>
      )}
      {aviso && (
        <p className="text-sm" role="status" data-testid="estructura-aviso">
          {aviso}
        </p>
      )}

      <DriversUsadosDelCalculo usados={calculo?.drivers_usados} hayObra={obraId !== ''} />

      {calculo && (
        <>
          <section className="mct__resumen" aria-label="Resultado">
            <span className="chip" data-testid="estructura-concreto">
              Concreto <b>{concreto}</b>
            </span>
            <span className="chip" data-testid="estructura-cimbra">
              Cimbra: {calculo.lados_cimbra} {calculo.lados_cimbra === 1 ? 'lado' : 'lados'}
              {calculo.forro ? ` · ${num(calculo.forro.cimbra_m2, 3)} m²` : ` · ${num(calculo.acero.cimbra.m2, 3)} m² a ${num(calculo.alto_m)} m`}
            </span>
            <span className="chip">Acero {calculo.acero.acero_kg_completo ? `${num(calculo.acero.acero_kg)} kg` : 'sin kg de armex (el catálogo no trae peso)'}</span>
            <span className="chip">Alambre {num(calculo.acero.alambre.kg, 3)} kg</span>
          </section>

          <section className="mct__bloque" aria-label="Cortes del acero">
            <h3>Acero: cortes con módulos de 1 a 6 m</h3>
            <table className="mct__tabla">
              <thead>
                <tr>
                  <th>Pieza</th>
                  <th>Corte</th>
                  <th className="n">Traslape + puntas (m)</th>
                  <th className="n">Piezas comerciales</th>
                </tr>
              </thead>
              <tbody>
                {calculo.acero.armex && (
                  <tr>
                    <td>
                      Armex <span className="mono">{calculo.acero.armex.clave}</span>
                    </td>
                    <td>
                      {calculo.acero.armex.corte
                        ? `${calculo.acero.armex.corte.piezas} × ${num(calculo.acero.armex.corte.modulo_m)} m`
                        : 'tramo continuo'}
                    </td>
                    <td className="n">
                      {num(calculo.acero.armex.traslape_m)} + {num(calculo.acero.armex.puntas_m)}
                    </td>
                    <td className="n">{num(calculo.acero.armex.piezas_comerciales, 3)}</td>
                  </tr>
                )}
                {calculo.acero.varillas.map((v) => (
                  <tr key={v.clave}>
                    <td>
                      {v.varillas} var. no.{v.numero} <span className="mono">{v.clave}</span>
                    </td>
                    <td>{v.corte ? `${v.corte.piezas} × ${num(v.corte.modulo_m)} m` : 'tramo continuo'}</td>
                    <td className="n">
                      {num(v.traslape_m, 3)} + {num(v.puntas_m, 3)}
                    </td>
                    <td className="n">{num(v.piezas_comerciales, 3)}</td>
                  </tr>
                ))}
                {calculo.acero.anillos && (
                  <tr>
                    <td>Anillos</td>
                    <td>
                      {num(calculo.acero.anillos.pza, 1)} pza de {num(calculo.acero.anillos.largo_anillo_m, 3)} m
                    </td>
                    <td className="n">—</td>
                    <td className="n">{num(calculo.acero.anillos.kg, 3)} kg</td>
                  </tr>
                )}
              </tbody>
            </table>
          </section>

          {calculo.forro && (
            <section className="mct__bloque" aria-label="Forro de tabique">
              <h3>Forro de tabique por geometría (cimbra de 1 lado)</h3>
              <table className="mct__tabla">
                <thead>
                  <tr>
                    <th>Cara</th>
                    <th className="n">Área (m²)</th>
                    <th className="n">Pza por m²</th>
                    <th className="n">Pza netas</th>
                  </tr>
                </thead>
                <tbody>
                  {calculo.forro.caras.map((c) => (
                    <tr key={c.clave}>
                      <td>{c.etiqueta}</td>
                      <td className="n">{num(c.area_m2, 3)}</td>
                      <td className="n">{num(c.pza_por_m2, 2)}</td>
                      <td className="n">{num(c.pza_netas, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="mct__resumen">
                <span className="chip" data-testid="estructura-tabique">
                  <b>{num(calculo.forro.tabique_pza, 1)} pza de tabique</b> (12 % de desperdicio)
                </span>
                <span className="chip">Mezcla {num(calculo.forro.mezcla_m3, 4)} m³</span>
              </div>
            </section>
          )}

          <section className="mct__bloque" aria-label="Conceptos del catálogo">
            <h3>Conceptos que lo pagan, con lo que calcula el elemento por unidad</h3>
            {calculo.conceptos.map((c) => (
              <div key={`${c.ranura}-${c.clave}`} data-concepto={c.clave} style={{ display: 'grid', gap: 4 }}>
                <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span className="badge badge--info">{RANURA[c.ranura] ?? c.ranura}</span>
                  <span className="mono">{c.clave}</span>
                  <span className="text-mute text-xs">por {c.unidad === 'm' ? 'metro' : 'pieza'}</span>
                  {c.hasta_m !== null && c.hasta_m !== undefined && <span className="badge">hasta {num(c.hasta_m)} m</span>}
                  {c.nuevo && <span className="badge badge--warn">Concepto nuevo, pendiente de autorizar</span>}
                  {c.rebasa && <span className="badge badge--warn">El alto rebasa el último escalón</span>}
                </div>
                {c.escalones.length > 1 && (
                  <div className="text-mute text-xs">
                    Escalones: {c.escalones.map((x) => `${x.clave} hasta ${num(x.hasta_m)} m`).join(' · ')}
                  </div>
                )}
                <div className="mct__resumen">
                  {Object.entries(c.insumos).map(([k, v]) => (
                    <span className="chip" key={k}>
                      <span className="mono">{k}</span> {num(v, 4)}
                    </span>
                  ))}
                </div>
              </div>
            ))}
            {calculo.solo_en_catalogo.length > 0 && (
              <ul className="text-xs" aria-label="Solo en el catálogo">
                {calculo.solo_en_catalogo.map((s) => (
                  <li key={s.clave}>
                    <span className="badge badge--warn">solo en el catálogo</span> <span className="mono">{s.clave}</span> {s.motivo}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {calculo.concepto_nuevo_por_altura && (
            <section className="mct__bloque" aria-label="Concepto nuevo por altura" data-testid="estructura-concepto-nuevo">
              <h3>Otra altura es un concepto nuevo</h3>
              <p className="text-sm">
                El catálogo trae {d.clave} solo para {num(d.alto_fijo_m)} m. Con {num(calculo.alto_m)} m haría falta{' '}
                <span className="mono">{calculo.concepto_nuevo_por_altura.clave_propuesta}</span>, pendiente de autorizar por Control de obra
                y sin precio ni destajo.
              </p>
              {puedeProponer && (
                <button
                  type="button"
                  className="btn btn--sm"
                  disabled={proponerPorAltura.isPending}
                  onClick={() =>
                    void correr(async () => {
                      await proponerPorAltura.mutateAsync({ clave, data: { alto_m: calculo.alto_m } });
                      return `${calculo.concepto_nuevo_por_altura?.clave_propuesta ?? ''} propuesto: espera la autorización de Control de obra.`;
                    })
                  }
                >
                  Proponer el concepto nuevo
                </button>
              )}
            </section>
          )}

          {calculo.advertencias.length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias">
              {calculo.advertencias.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
        </>
      )}

      <section className="mct__bloque" aria-label="Conciliación con el catálogo">
        <h3>Conciliación con el catálogo</h3>
        <p className="text-mute text-xs">
          Cada concepto se compara con su composición real, con los auxiliares expandidos hasta los insumos y al alto de su escalón. = hasta 3 %,
          ≈ hasta 8 %, ≠ más. La mano de obra y el destajo no se calculan. Lo que el catálogo trae mal no se edita: se propone como nueva versión.
        </p>
        {conciliacion.isLoading && <p className="text-mute text-sm">Cargando la conciliación…</p>}
        {conciliacion.isError && <p className="text-sm">No se pudo cargar la conciliación.</p>}
        {(conciliacion.data?.conceptos ?? []).map((b) => (
          <BloqueConciliado key={b.concepto_clave} b={b} />
        ))}
      </section>

      <section className="mct__bloque" aria-label="Versiones propuestas">
        <h3>Versiones propuestas del catálogo</h3>
        <p className="text-mute text-xs">
          Costos propone y solo Control de obra autoriza; cada autorización crea la versión siguiente del concepto. La versión propuesta iguala los kg de
          anillo al cálculo del elemento (perímetro del núcleo más 10 cm de gancho); el catálogo vigente sigue activo y Control de obra autoriza
          cuál de los dos queda.
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
            {p.destajo_por_definir && <div className="text-xs">Destajo por definir por Costos: {p.destajo_por_definir}.</div>}
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
          <div className="row" style={{ gap: 6, alignItems: 'center' }}>
            <button
              type="button"
              className="btn btn--sm"
              disabled={proponer.isPending}
              onClick={() =>
                void correr(async () => {
                  const r = await proponer.mutateAsync({ clave });
                  const n = r.creadas.length;
                  if (n === 0) return 'No hay correcciones nuevas que proponer.';
                  return n === 1 ? '1 corrección propuesta.' : `${n} correcciones propuestas.`;
                })
              }
            >
              Proponer las correcciones del catálogo
            </button>
            {pendientes.length > 0 && <span className="text-mute text-xs">{pendientes.length} esperan a Control de obra.</span>}
          </div>
        )}
      </section>

      <section className="mct__bloque mct__pendientes" aria-label="Pendientes por confirmar">
        <h3>Pendientes por confirmar</h3>
        <ul>
          {d.pendientes.length === 0 && <li>Ninguno.</li>}
          {d.pendientes.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      </section>
    </article>
  );
}

function BloqueConciliado({ b }: { readonly b: ConceptoConciliado }) {
  return (
    <details className="mct__bloque" open={b.filas.length > 0 && !b.nuevo} data-conciliacion={b.concepto_clave}>
      <summary>
        <span className="mono">{b.concepto_clave}</span> · {RANURA[b.ranura] ?? b.ranura} · a {num(b.alto_m)} m
        {b.nuevo ? ' · concepto nuevo' : b.sin_catalogo ? ' · no está en el catálogo de esta organización' : ''}
        {b.propuestas.length > 0 && <span className="badge badge--warn"> {b.propuestas.length} propuesta{b.propuestas.length > 1 ? 's' : ''}</span>}
      </summary>
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
            {b.filas.map((f) => {
              const m = MARCA[f.marca];
              return (
                <tr key={f.clave} data-insumo={f.clave}>
                  <td>
                    <span className="mono">{f.clave}</span> {f.descripcion}
                    {f.motivo && <div className="text-mute text-xs">{f.motivo}</div>}
                  </td>
                  <td className="n">{num(f.catalogo, 4)}</td>
                  <td className="n">
                    {f.propuesta ? (
                      <>
                        {num(f.propuesta.valor, 4)} <span className="text-mute text-xs">({ESTADO[f.propuesta.estado]?.toLowerCase()})</span>
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="n">{num(f.elemento, 4)}</td>
                  <td className="n">{f.diferencia_pct === null || f.diferencia_pct === undefined ? '—' : `${f.diferencia_pct >= 0 ? '+' : ''}${num(f.diferencia_pct, 1)} %`}</td>
                  <td>{m && <span className={m.clase}>{m.texto}</span>}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {b.mano_de_obra.length > 0 && (
        <p className="text-mute text-xs">
          Destajo y mano de obra del catálogo (el elemento no los calcula): {b.mano_de_obra.map((m) => `${m.clave} ${num(m.cantidad, 2)} ${m.unidad}`).join(', ')}.
        </p>
      )}
    </details>
  );
}
