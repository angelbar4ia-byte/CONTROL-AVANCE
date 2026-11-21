/**
 * La tarjeta del relleno de la biblioteca (Fase 3 de las zonas de losa): el relleno de azotea y el relleno compactado como elementos SEPARADOS de la losa.
 * Simple a propósito: los parámetros arriba, lo que sale abajo. **No calcula nada**: cada cambio se manda al servidor
 * (`/biblioteca-de-elementos/relleno/{clave}/calcular`) y se muestra lo que responde.
 *
 * Se capturan el espesor mínimo, la pendiente y su recorrido, si el relleno se adapta a los espesores de losa distintos de la zona (compensar), el
 * abundamiento (solo el compactado), el mortero por m² (solo la azotea) y los polígonos de losa que cubre (su área y, si es una subzona, su espesor propio).
 * Sale el volumen, el espesor de cada polígono y el **concepto que paga**: el relleno de azotea usa el concepto que YA existe en el catálogo (ALB-03014);
 * el compactado, un concepto nuevo propuesto (clave provisional, sin precio, regla F7) que solo Control de obra autoriza. El relleno no calcula mano de
 * obra con importe ni lee drivers; los pendientes se muestran.
 *
 * Los rellenos de una zona real del plano (con sus polígonos, su espacio y su partida) están en el panel de zonas de la pestaña Trazos.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import type { CalculoDelRellenoPeticion, RellenoCalculado } from '@/api/generado/modelo';
import {
  useCalcularElRellenoApiV1BibliotecaDeElementosRellenoClaveCalcularPost,
  useDefinicionDelRellenoApiV1BibliotecaDeElementosRellenoClaveGet,
  useProponerConceptoDelRellenoApiV1BibliotecaDeElementosRellenoClavePropuestasConceptoPost,
  usePropuestasDelRellenoApiV1BibliotecaDeElementosRellenoClavePropuestasGet,
} from '@/api/generado/rellenos/rellenos';
import { queryClient } from '@/app/queryClient';

import { numeroTecleado } from '../volumen';
import { PropuestaDeConceptoNuevo } from './PropuestaDeConceptoNuevo';

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const unidadVisible = (u: string) => (u === 'm3' ? 'm³' : u === 'm2' ? 'm²' : u);
export const NOMBRE_DE_INSUMO_DEL_RELLENO: Record<string, string> = { tezontle: 'Tezontle', mortero: 'Mortero' };

interface Props {
  readonly clave: string;
  readonly rol?: string | null;
}

interface Poligono {
  readonly id: number;
  readonly area: string;
  readonly espesorDeLosa: string;
}

/** Un campo numérico opcional: vacío = el de omisión del elemento (`undefined`); lo que no es un número válido anula el cálculo (`null`). */
function opcional(texto: string, minimo = 0): number | undefined | null {
  if (texto.trim() === '') return undefined;
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) && n >= minimo ? n : null;
}

export function TarjetaRelleno({ clave, rol }: Props) {
  const definicion = useDefinicionDelRellenoApiV1BibliotecaDeElementosRellenoClaveGet(clave);
  const calcular = useCalcularElRellenoApiV1BibliotecaDeElementosRellenoClaveCalcularPost<ErrorApi>();
  const propuestas = usePropuestasDelRellenoApiV1BibliotecaDeElementosRellenoClavePropuestasGet(clave);
  const proponer = useProponerConceptoDelRellenoApiV1BibliotecaDeElementosRellenoClavePropuestasConceptoPost<ErrorApi>();
  const d = definicion.data;
  const [espesorZona, setEspesorZona] = useState('0.12');
  const [espesor, setEspesor] = useState('');
  const [pendiente, setPendiente] = useState('');
  const [recorrido, setRecorrido] = useState('');
  const [compensar, setCompensar] = useState(true);
  const [abundamiento, setAbundamiento] = useState('');
  const [mortero, setMortero] = useState('');
  const [poligonos, setPoligonos] = useState<readonly Poligono[]>([{ id: 1, area: '100', espesorDeLosa: '' }]);
  const siguiente = useRef(2);
  const [calculo, setCalculo] = useState<RellenoCalculado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const turno = useRef(0);

  // Al cambiar de elemento, la tarjeta vuelve a los valores del elemento.
  useEffect(() => {
    if (!d) return;
    setEspesor('');
    setPendiente('');
    setRecorrido('');
    setAbundamiento('');
    setMortero('');
    setCompensar(true);
    setPoligonos([{ id: 1, area: '100', espesorDeLosa: '' }]);
    setCalculo(null);
    setError(null);
  }, [d]);

  const compactado = d?.tipo === 'compactado';
  const peticion = useMemo<CalculoDelRellenoPeticion | null>(() => {
    if (!d) return null;
    const z = numeroTecleado(espesorZona);
    if (!(z > 0)) return null;
    const lista: { area_m2: number; espesor_de_losa_m?: number }[] = [];
    for (const p of poligonos) {
      const a = numeroTecleado(p.area);
      if (!(a > 0)) return null;
      const e = opcional(p.espesorDeLosa, 0);
      if (e === null || e === 0) return null;
      lista.push(e === undefined ? { area_m2: a } : { area_m2: a, espesor_de_losa_m: e });
    }
    const e = opcional(espesor);
    const p = opcional(pendiente);
    const r = opcional(recorrido);
    const a = compactado ? opcional(abundamiento) : undefined;
    const m = compactado ? undefined : opcional(mortero);
    if ([e, p, r, a, m].includes(null)) return null;
    return {
      espesor_de_la_zona_m: z,
      poligonos: lista,
      compensar_espesores: compensar,
      ...(e === undefined ? {} : { espesor_m: e as number }),
      ...(p === undefined ? {} : { pendiente_pct: p as number }),
      ...(r === undefined ? {} : { recorrido_m: r as number }),
      ...(a === undefined ? {} : { abundamiento_pct: a as number }),
      ...(m === undefined ? {} : { mortero_m3_por_m2: m as number }),
    };
  }, [d, espesorZona, espesor, pendiente, recorrido, compensar, abundamiento, mortero, poligonos, compactado]);

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
          setError(e instanceof Error ? e.message : 'No se pudo calcular el relleno.');
        });
    }, 200);
    return () => clearTimeout(espera);
  }, [clave, peticion, mutateAsync]);

  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando el relleno…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;

  const defecto = d.parametros_por_defecto;
  const cambiarPoligono = (id: number, cambio: Partial<Poligono>) => setPoligonos((prev) => prev.map((p) => (p.id === id ? { ...p, ...cambio } : p)));
  const propuesto = d.concepto.estado === 'propuesto';

  return (
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`} data-relleno={d.clave}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span> · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se mide por {d.se_mide_por}
          </div>
        </div>
        <span
          className={propuesto ? 'badge badge--warn' : 'badge badge--ok'}
          title={propuesto ? 'Concepto nuevo propuesto, con clave provisional' : 'Concepto que ya existe en el catálogo'}
        >
          {d.concepto.clave} · {d.concepto.unidad} · {propuesto ? 'propuesto' : 'del catálogo'}
        </span>
      </header>

      <section className="mct__parametros" aria-label="Parámetros del relleno">
        <label className="mct__campo" title="El espesor de la losa de la zona: vale para el polígono que no trae espesor propio.">
          <span>Espesor de la losa de la zona (m)</span>
          <input className="input" inputMode="decimal" aria-label="Espesor de la losa de la zona en metros" value={espesorZona} onChange={(e) => setEspesorZona(e.target.value)} />
        </label>
        <label className="mct__campo" title="El espesor mínimo del relleno; a él se suman la compensación de espesores de losa y la pendiente.">
          <span>Espesor mínimo del relleno (m)</span>
          <input
            className="input"
            inputMode="decimal"
            aria-label="Espesor mínimo del relleno en metros"
            placeholder={String(defecto.espesor_m)}
            value={espesor}
            onChange={(e) => setEspesor(e.target.value)}
          />
        </label>
        <label className="mct__campo" title="Pendiente del relleno en %: con el recorrido da el volumen en cuña (pendiente × recorrido / 2). Por omisión 0.">
          <span>Pendiente (%)</span>
          <input className="input" inputMode="decimal" aria-label="Pendiente del relleno en por ciento" placeholder={String(defecto.pendiente_pct)} value={pendiente} onChange={(e) => setPendiente(e.target.value)} />
        </label>
        <label className="mct__campo" title="Recorrido en metros sobre el que corre la pendiente. Por omisión 0.">
          <span>Recorrido de la pendiente (m)</span>
          <input className="input" inputMode="decimal" aria-label="Recorrido de la pendiente en metros" placeholder={String(defecto.recorrido_m)} value={recorrido} onChange={(e) => setRecorrido(e.target.value)} />
        </label>
        {compactado ? (
          <label className="mct__campo" title="El catálogo no trae factor de abundamiento: por omisión 0.">
            <span>Abundamiento (%)</span>
            <input className="input" inputMode="decimal" aria-label="Abundamiento en por ciento" placeholder={String(defecto.abundamiento_pct)} value={abundamiento} onChange={(e) => setAbundamiento(e.target.value)} />
          </label>
        ) : (
          <label className="mct__campo" title="El mortero de la composición del catálogo ALB-03014, por m².">
            <span>Mortero (m³ por m²)</span>
            <input className="input" inputMode="decimal" aria-label="Mortero en metros cúbicos por metro cuadrado" placeholder={String(defecto.mortero_m3_por_m2)} value={mortero} onChange={(e) => setMortero(e.target.value)} />
          </label>
        )}
        <label className="mct__campo mct__campo--casilla">
          <input type="checkbox" aria-label="Compensar espesores de losa" checked={compensar} onChange={(e) => setCompensar(e.target.checked)} />
          <span>Adaptarse a los espesores de losa distintos de la zona</span>
        </label>
      </section>

      <section className="mct__bloque" aria-label="Polígonos de losa que cubre" data-poligonos-del-relleno>
        <h3>Polígonos de losa que cubre</h3>
        <p className="text-mute text-xs">
          El área de cada polígono y, si es una subzona, su espesor estructural propio (el relleno se adapta a la losa más gruesa). En una zona real del plano el
          área sale de los polígonos dibujados.
        </p>
        {poligonos.map((p, i) => (
          <div key={p.id} className="mct__par" data-poligono-del-relleno={i + 1}>
            <input className="input" inputMode="decimal" aria-label={`Área del polígono ${i + 1} en metros cuadrados`} value={p.area} onChange={(e) => cambiarPoligono(p.id, { area: e.target.value })} />
            <input
              className="input"
              inputMode="decimal"
              aria-label={`Espesor propio de la losa del polígono ${i + 1} en metros`}
              placeholder="el de la zona"
              value={p.espesorDeLosa}
              onChange={(e) => cambiarPoligono(p.id, { espesorDeLosa: e.target.value })}
            />
            <button type="button" className="btn btn--sm" aria-label={`Quitar el polígono ${i + 1}`} disabled={poligonos.length === 1} onClick={() => setPoligonos((prev) => prev.filter((x) => x.id !== p.id))}>
              Quitar
            </button>
          </div>
        ))}
        <button type="button" className="btn btn--sm" onClick={() => setPoligonos((prev) => [...prev, { id: siguiente.current++, area: '10', espesorDeLosa: '' }])}>
          Agregar un polígono
        </button>
      </section>

      {error && (
        <p className="text-sm" role="alert">
          {error}
        </p>
      )}

      {calculo && (
        <>
          <section className="mct__bloque" aria-label="Resumen del relleno" data-resumen-del-relleno>
            <h3>Resumen</h3>
            <p className="text-sm" data-testid="relleno-area">
              Área {num(calculo.area_m2)} m² en {calculo.poligonos.length} {calculo.poligonos.length === 1 ? 'polígono' : 'polígonos'}
            </p>
            <p className="text-sm" data-testid="relleno-volumen">
              Volumen del relleno {num(calculo.volumen_m3, 3)} m³ · espesor medio {num(calculo.espesor_medio_m * 100, 1)} cm
            </p>
            {calculo.volumen_suelto_m3 !== null && calculo.volumen_suelto_m3 !== undefined && (
              <p className="text-sm" data-testid="relleno-suelto">
                Volumen suelto por comprar (con el abundamiento) {num(calculo.volumen_suelto_m3, 3)} m³
              </p>
            )}
            <table className="mct__tabla" aria-label="Espesor por polígono">
              <thead>
                <tr>
                  <th>Polígono</th>
                  <th className="n">Área</th>
                  <th className="n">Losa</th>
                  <th className="n">Compensa</th>
                  <th className="n">Relleno</th>
                  <th className="n">Volumen</th>
                </tr>
              </thead>
              <tbody>
                {calculo.poligonos.map((p, i) => (
                  <tr key={`${p.id}-${i}`} data-poligono-calculado={i + 1}>
                    <td>{i + 1}{p.subzona && <span className="text-mute text-xs"> subzona</span>}</td>
                    <td className="n">{num(p.area_m2)} m²</td>
                    <td className="n">{num(p.espesor_de_losa_m * 100, 1)} cm</td>
                    <td className="n">{num(p.compensacion_m * 100, 1)} cm</td>
                    <td className="n">{num(p.espesor_m * 100, 1)} cm</td>
                    <td className="n">{num(p.volumen_m3, 3)} m³</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="mct__bloque" aria-label="Concepto del relleno" data-conceptos-del-relleno>
            <h3>Concepto que paga el relleno</h3>
            <div className="mct__tabla-caja">
              <table className="mct__tabla">
                <thead>
                  <tr>
                    <th>Concepto</th>
                    <th className="n">Cantidad</th>
                    <th>Toma</th>
                  </tr>
                </thead>
                <tbody>
                  {calculo.conceptos.map((c) => (
                    <tr key={c.concepto.clave} data-concepto={c.concepto.clave} data-estado={c.concepto.estado}>
                      <td>
                        <span className="mono">{c.concepto.clave}</span>{' '}
                        <span className={c.concepto.estado === 'propuesto' ? 'badge badge--warn' : 'badge badge--ok'}>
                          {c.concepto.estado === 'propuesto' ? 'propuesto · clave provisional' : 'del catálogo'}
                        </span>
                        <div className="text-mute text-xs">{c.concepto.descripcion}</div>
                        <div className="text-mute text-xs">{c.nota}</div>
                      </td>
                      <td className="n">
                        {num(c.cantidad, 3)} {unidadVisible(c.unidad)}
                      </td>
                      <td>{c.toma.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {calculo.insumos.length > 0 && (
            <section className="mct__bloque" aria-label="Insumos del relleno">
              <h3>Insumos</h3>
              <div className="mct__tabla-caja">
                <table className="mct__tabla">
                  <thead>
                    <tr>
                      <th>Parte</th>
                      <th>Insumo</th>
                      <th className="n">Cantidad</th>
                    </tr>
                  </thead>
                  <tbody>
                    {calculo.insumos.map((i) => (
                      <tr key={i.clave} data-insumo={i.clave}>
                        <td>{NOMBRE_DE_INSUMO_DEL_RELLENO[i.parte] ?? i.parte}</td>
                        <td>
                          <span className="mono">{i.clave}</span> {i.descripcion}
                          <div className="text-mute text-xs">{i.nota}</div>
                        </td>
                        <td className="n">
                          {num(i.cantidad, 4)} {unidadVisible(i.unidad)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <p className="text-mute text-xs" data-testid="relleno-sin-mano-de-obra">
            {calculo.mano_de_obra.nota}
          </p>
          {calculo.advertencias.length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias">
              {calculo.advertencias.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
        </>
      )}

      {propuesto ? (
        <section className="mct__bloque" aria-label="Concepto nuevo del relleno" data-concepto-del-relleno={d.concepto.clave}>
          <h3>Concepto nuevo del relleno (regla F7)</h3>
          <p className="text-xs">
            {d.concepto.descripcion}. El catálogo no trae un relleno compactado; este concepto por m³ se propone con clave provisional, sin insumos, destajo ni
            precio, y solo Control de obra lo autoriza. Mientras no esté autorizado y en el catálogo, su cantidad se informa pero no se escribe en ninguna partida.
          </p>
          <PropuestaDeConceptoNuevo
            conceptoClave={d.concepto.clave}
            lista={propuestas.data ?? []}
            rol={rol}
            textoDelBoton="Proponer el concepto del relleno"
            proponiendo={proponer.isPending}
            onProponer={() =>
              void proponer.mutateAsync({ clave }).then(
                () => queryClient.invalidateQueries(),
                (e: unknown) => window.alert(e instanceof Error ? e.message : 'No se pudo proponer el concepto del relleno.'),
              )
            }
          />
        </section>
      ) : (
        <section className="mct__bloque" aria-label="Qué toma del catálogo" data-concepto-del-relleno={d.concepto.clave}>
          <h3>Lo que toma del catálogo</h3>
          <ul className="text-xs">
            <li>
              Concepto: <span className="mono">{d.concepto.clave}</span> {d.concepto.descripcion} (por {d.concepto.unidad}). Regla F7: ya existe en el catálogo, no se propone ninguno nuevo.
            </li>
            {d.tezontle && (
              <li>
                Tezontle <span className="mono">{d.tezontle.clave}</span> {d.tezontle.descripcion}: {num(d.tezontle.por_m2, 6)} {d.tezontle.unidad} por m² de {num(d.tezontle.m3_por_viaje ?? 0, 0)} m³ cada uno
                (9 cm de espesor medio). Se calcula por geometría y se concilia contra la composición vigente.
              </li>
            )}
            {d.mortero && (
              <li>
                Mortero <span className="mono">{d.mortero.clave}</span> {d.mortero.descripcion}: {num(d.mortero.por_m2, 4)} m³ por m².
              </li>
            )}
            <li>
              Destajo del catálogo, por m² (no se le pone importe): {d.destajos_candidatos.map((x) => `${x.clave} ${x.descripcion}`).join(' · ')}.
            </li>
          </ul>
        </section>
      )}

      <section className="mct__bloque mct__pendientes" aria-label="Pendientes por confirmar">
        <h3>Pendientes por confirmar</h3>
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
