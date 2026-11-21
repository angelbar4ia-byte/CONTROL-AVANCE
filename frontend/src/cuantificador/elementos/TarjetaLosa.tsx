/**
 * La tarjeta de la losa de la biblioteca (fase 2 de las zonas de losa): la losa maciza y la nervada como elementos, con su matriz de conceptos.
 * Simple a propósito: los parámetros arriba, lo que sale abajo. **No calcula nada**: cada cambio se manda al servidor
 * (`/biblioteca-de-elementos/losa/{clave}/calcular`) y se muestra lo que responde.
 *
 * Se capturan el espesor, el uso (entrepiso, azotea o cimentación: elige el concreto del catálogo), las áreas de los polígonos de losa y los elementos de la
 * zona (trabes, contratrabes y nervaduras, por ml o por pieza, con su pago). Sale el concreto y la cimbra de la losa, el acero y el concreto de
 * los elementos y los **conceptos que paga cada parte** con su cantidad medida. Los conceptos nuevos (el de la losa por m², regla F7; el de colado
 * y cimbra por ml de cada trabe con pago propio, D8) son **propuestos**: clave provisional, sin precio, el destajo por ml sin importe y
 * pendientes de autorizar por Control de obra. El elemento no calcula mano de obra ni el casetón; los pendientes se muestran.
 *
 * La matriz de una zona del plano (con sus polígonos y elementos reales) está en el panel de zonas de la pestaña Trazos.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCalcularLaLosaApiV1BibliotecaDeElementosLosaClaveCalcularPost,
  useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet,
  useProponerConceptoDeLaLosaApiV1BibliotecaDeElementosLosaClavePropuestasConceptoPost,
  usePropuestasDeLaLosaApiV1BibliotecaDeElementosLosaClavePropuestasGet,
} from '@/api/generado/losas/losas';
import type { CalculoDeLaLosaPeticion, ElementoDeLaMatrizPeticion, MatrizDeLosa } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

import { numeroTecleado } from '../volumen';
import { DriversUsadosDelCalculo } from './DriversUsadosDelCalculo';
import { PropuestaDeConceptoNuevo } from './PropuestaDeConceptoNuevo';

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

export const NOMBRE_DE_PARTE: Record<string, string> = { losa: 'Losa', acero: 'Acero del elemento', colado: 'Colado y cimbra del elemento' };
export const NOMBRE_DE_PARTE_DE_INSUMO: Record<string, string> = { acero: 'Acero', concreto: 'Concreto', cimbra: 'Cimbra' };
const unidadVisible = (u: string) => (u === 'm3' ? 'm³' : u === 'm2' ? 'm²' : u);

interface Fila {
  readonly id: number;
  readonly clave: string;
  readonly modo: 'ml' | 'pieza';
  readonly cantidad: string;
  readonly largo: string;
  readonly pago: 'en_la_losa' | 'propio';
}

interface Props {
  readonly clave: string;
  readonly rol?: string | null;
  /** La obra actual: el cálculo lee sus drivers (desperdicio de concreto, traslapes, cortes…). */
  readonly obraId?: string;
}

/** «40, 12.5» → [40, 12.5]; cualquier valor que no sea un número positivo anula el cálculo. */
function areasDe(texto: string): number[] | null {
  const partes = texto.split(/[,;\s]+/).filter((x) => x !== '');
  const areas = partes.map((x) => numeroTecleado(x));
  return areas.every((a) => a > 0) ? areas : null;
}

export function TarjetaLosa({ clave, rol, obraId = '' }: Props) {
  const definicion = useDefinicionDeLaLosaApiV1BibliotecaDeElementosLosaClaveGet(clave);
  const calcular = useCalcularLaLosaApiV1BibliotecaDeElementosLosaClaveCalcularPost<ErrorApi>();
  const propuestas = usePropuestasDeLaLosaApiV1BibliotecaDeElementosLosaClavePropuestasGet(clave);
  const proponer = useProponerConceptoDeLaLosaApiV1BibliotecaDeElementosLosaClavePropuestasConceptoPost<ErrorApi>();
  const d = definicion.data;
  const [espesor, setEspesor] = useState('0.12');
  const [uso, setUso] = useState<'entrepiso' | 'azotea' | 'cimentacion'>('entrepiso');
  const [capa, setCapa] = useState('5');
  const [areas, setAreas] = useState('100');
  const [filas, setFilas] = useState<readonly Fila[]>([]);
  const siguiente = useRef(1);
  const [calculo, setCalculo] = useState<MatrizDeLosa | null>(null);
  const [error, setError] = useState<string | null>(null);
  const turno = useRef(0);

  // Al cambiar de elemento, la tarjeta vuelve a los valores del elemento.
  useEffect(() => {
    if (!d) return;
    setEspesor(String(d.espesor_por_defecto_m));
    setCapa(String(d.capa_de_compresion_cm ?? 5));
    setUso('entrepiso');
    setFilas([]);
    setCalculo(null);
    setError(null);
  }, [d]);

  const nervada = d?.tipo === 'nervada';
  const peticion = useMemo<CalculoDeLaLosaPeticion | null>(() => {
    if (!d) return null;
    const e = numeroTecleado(espesor);
    const lista = areasDe(areas);
    if (!(e > 0) || lista === null) return null;
    const elementos: ElementoDeLaMatrizPeticion[] = [];
    for (const f of filas) {
      const q = numeroTecleado(f.cantidad);
      if (!(q > 0)) return null;
      const el: ElementoDeLaMatrizPeticion = { clave: f.clave, modo: f.modo, cantidad: q, pago: f.pago };
      if (f.modo === 'pieza') {
        const l = numeroTecleado(f.largo);
        if (!(l > 0)) return null;
        el.largo_m = l;
      }
      elementos.push(el);
    }
    const base: CalculoDeLaLosaPeticion = {
      espesor_m: e, uso, losas: lista.map((a) => ({ area_m2: a })), elementos, ...(obraId === '' ? {} : { obra_id: obraId }),
    };
    if (nervada) {
      const c = numeroTecleado(capa);
      if (!(c > 0)) return null;
      base.capa_de_compresion_cm = c;
    }
    return base;
  }, [d, espesor, uso, capa, areas, filas, nervada, obraId]);

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
          setError(e instanceof Error ? e.message : 'No se pudo calcular la losa.');
        });
    }, 200);
    return () => clearTimeout(espera);
  }, [clave, peticion, mutateAsync]);

  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando la losa…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;

  const claveDeElemento = d.elementos_permitidos[0]?.clave ?? 'T-1-15x25';
  const agregar = () => {
    setFilas((prev) => [...prev, { id: siguiente.current++, clave: claveDeElemento, modo: 'ml', cantidad: '10', largo: '4.00', pago: 'en_la_losa' }]);
  };
  const cambiar = (id: number, cambio: Partial<Fila>) => setFilas((prev) => prev.map((f) => (f.id === id ? { ...f, ...cambio } : f)));

  return (
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`} data-losa={d.clave}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span> · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se mide por {d.se_mide_por}
          </div>
        </div>
        <span className="badge badge--warn" title="Concepto nuevo propuesto, con clave provisional">
          {d.concepto.clave} · {d.concepto.unidad} · propuesto
        </span>
      </header>

      <section className="mct__parametros" aria-label="Parámetros de la losa">
        <label className="mct__campo">
          <span>Espesor de la losa (m)</span>
          <input className="input" inputMode="decimal" aria-label="Espesor de la losa en metros" value={espesor} onChange={(e) => setEspesor(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Uso</span>
          <select className="select" aria-label="Uso de la losa" value={uso} onChange={(e) => setUso(e.target.value as 'entrepiso' | 'azotea')}>
            <option value="entrepiso">Entrepiso</option>
            <option value="azotea">Azotea</option>
            <option value="cimentacion">Cimentación</option>
          </select>
        </label>
        {nervada && (
          <label className="mct__campo">
            <span>Capa de compresión (cm)</span>
            <input className="input" inputMode="decimal" aria-label="Capa de compresión en centímetros" value={capa} onChange={(e) => setCapa(e.target.value)} />
          </label>
        )}
        <label className="mct__campo" title="Un área por polígono de losa, separadas por coma. Una subzona con espesor propio se captura en la zona del plano.">
          <span>Áreas de los polígonos de losa (m²)</span>
          <input className="input" aria-label="Áreas de los polígonos de losa en metros cuadrados" value={areas} onChange={(e) => setAreas(e.target.value)} />
        </label>
      </section>

      <section className="mct__bloque" aria-label="Elementos de la zona" data-elementos-de-la-losa>
        <h3>Elementos de la zona</h3>
        <p className="text-mute text-xs">
          Trabes, contratrabes y nervaduras de la biblioteca. Con pago «en la losa» (lo que hace el catálogo) la losa paga su concreto y su cimbra por m²; con
          pago «propio» los paga su concepto de colado y cimbra por ml. Su acero lo paga siempre su auxiliar del catálogo.
        </p>
        {filas.map((f, i) => (
          <div key={f.id} className="mct__par" data-elemento-de-la-losa={f.clave}>
            <select className="select" aria-label={`Elemento ${i + 1}`} value={f.clave} onChange={(e) => cambiar(f.id, { clave: e.target.value })}>
              {d.elementos_permitidos.map((x) => (
                <option key={x.clave} value={x.clave}>
                  {x.clave}
                </option>
              ))}
            </select>
            <select className="select" aria-label={`Se mide por del elemento ${i + 1}`} value={f.modo} onChange={(e) => cambiar(f.id, { modo: e.target.value as 'ml' | 'pieza' })}>
              <option value="ml">ml de trazo</option>
              <option value="pieza">piezas</option>
            </select>
            <input className="input" inputMode="decimal" aria-label={`Cantidad del elemento ${i + 1}`} value={f.cantidad} onChange={(e) => cambiar(f.id, { cantidad: e.target.value })} />
            {f.modo === 'pieza' && (
              <input className="input" inputMode="decimal" aria-label={`Largo de la pieza del elemento ${i + 1}`} value={f.largo} onChange={(e) => cambiar(f.id, { largo: e.target.value })} />
            )}
            <select className="select" aria-label={`Pago del elemento ${i + 1}`} value={f.pago} onChange={(e) => cambiar(f.id, { pago: e.target.value as 'en_la_losa' | 'propio' })}>
              <option value="en_la_losa">paga la losa</option>
              <option value="propio">paga su concepto por ml</option>
            </select>
            <button type="button" className="btn btn--sm" aria-label={`Quitar el elemento ${i + 1}`} onClick={() => setFilas((prev) => prev.filter((x) => x.id !== f.id))}>
              Quitar
            </button>
          </div>
        ))}
        <button type="button" className="btn btn--sm" onClick={agregar}>
          Agregar un elemento
        </button>
      </section>

      {error && (
        <p className="text-sm" role="alert">
          {error}
        </p>
      )}

      {calculo && (
        <>
          <section className="mct__bloque" aria-label="Resumen de la losa" data-resumen-de-la-losa>
            <h3>Resumen de la zona</h3>
            <p className="text-sm" data-testid="losa-area">
              Área {num(calculo.area_m2)} m² en {calculo.losas.length} {calculo.losas.length === 1 ? 'polígono' : 'polígonos'}
            </p>
            <p className="text-sm" data-testid="losa-concreto">
              Concreto de la losa <span className="mono">{calculo.concreto.clave}</span>: {num(calculo.concreto.geometrico_m3, 3)} m³ + {num(calculo.concreto.desperdicio_pct, 0)} %
              de desperdicio = {num(calculo.concreto.con_desperdicio_m3, 3)} m³
            </p>
            <p className="text-sm" data-testid="losa-cimbra">
              Cimbra de la losa <span className="mono">{calculo.cimbra.clave}</span>: {num(calculo.cimbra.m2)} m²
            </p>
            {calculo.parrilla && (
              <p className="text-sm" data-testid="losa-parrilla">
                Parrilla del catálogo <span className="mono">{calculo.parrilla.clave}</span>: {calculo.parrilla.insumos.map((i) => `${num(i.total ?? 0, 2)} ${unidadVisible(i.unidad)} de ${i.clave}`).join(' · ')}
              </p>
            )}
            <table className="mct__tabla" aria-label="Totales de la zona">
              <tbody>
                <tr>
                  <td>Metros de elementos</td>
                  <td className="n">{num(calculo.totales.longitud_de_elementos_ml)} ml</td>
                </tr>
                <tr>
                  <td>Concreto total</td>
                  <td className="n" data-testid="losa-concreto-total">
                    {num(calculo.totales.concreto_m3, 3)} m³
                  </td>
                </tr>
                <tr>
                  <td>· lo paga la losa</td>
                  <td className="n">{num(calculo.totales.concreto_pagado_por_la_losa_m3, 3)} m³</td>
                </tr>
                <tr>
                  <td>· lo pagan los elementos</td>
                  <td className="n">{num(calculo.totales.concreto_pagado_por_elementos_m3, 3)} m³</td>
                </tr>
                <tr>
                  <td>Cimbra total</td>
                  <td className="n">{num(calculo.totales.cimbra_m2)} m²</td>
                </tr>
                <tr>
                  <td>Acero de los elementos</td>
                  <td className="n">{num(calculo.totales.acero_de_elementos_kg)} kg</td>
                </tr>
                <tr>
                  <td>Solape trabe-losa (no se descuenta)</td>
                  <td className="n">{num(calculo.totales.solape_con_la_losa_m3, 3)} m³</td>
                </tr>
              </tbody>
            </table>
          </section>

          <section className="mct__bloque" aria-label="Conceptos de la matriz" data-conceptos-de-la-matriz>
            <h3>Conceptos que paga cada parte</h3>
            <div className="mct__tabla-caja">
              <table className="mct__tabla">
                <thead>
                  <tr>
                    <th>Parte</th>
                    <th>Concepto</th>
                    <th className="n">Cantidad</th>
                    <th>Toma</th>
                  </tr>
                </thead>
                <tbody>
                  {calculo.conceptos.map((c, i) => (
                    <tr key={`${c.concepto.clave}-${i}`} data-concepto={c.concepto.clave} data-estado={c.concepto.estado} data-parte={c.parte}>
                      <td>
                        {NOMBRE_DE_PARTE[c.parte] ?? c.parte}
                        {c.parte !== 'losa' && <span className="text-mute text-xs mono"> {c.elemento_clave}</span>}
                      </td>
                      <td>
                        <span className="mono">{c.concepto.clave}</span>{' '}
                        <span className={c.concepto.estado === 'propuesto' ? 'badge badge--warn' : 'badge badge--ok'}>
                          {c.concepto.estado === 'propuesto' ? 'propuesto · clave provisional' : 'del catálogo'}
                        </span>
                        <div className="text-mute text-xs">{c.concepto.descripcion}</div>
                      </td>
                      <td className="n">
                        {num(c.cantidad)} {unidadVisible(c.unidad)}
                      </td>
                      <td>{c.toma.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="mct__bloque" aria-label="Insumos de la matriz">
            <h3>Insumos</h3>
            <div className="mct__tabla-caja">
              <table className="mct__tabla">
                <thead>
                  <tr>
                    <th>Parte</th>
                    <th>Insumo</th>
                    <th className="n">Cantidad</th>
                    <th>Lo paga</th>
                  </tr>
                </thead>
                <tbody>
                  {calculo.insumos.map((i, n) => (
                    <tr key={`${i.clave}-${i.paga}-${n}`} data-insumo={i.clave} data-paga={i.paga}>
                      <td>{NOMBRE_DE_PARTE_DE_INSUMO[i.parte] ?? i.parte}</td>
                      <td>
                        <span className="mono">{i.clave}</span> {i.descripcion}
                      </td>
                      <td className="n">
                        {num(i.cantidad, 3)} {unidadVisible(i.unidad)}
                      </td>
                      <td>{i.paga === 'losa' ? 'la losa' : 'el elemento'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <p className="text-mute text-xs" data-testid="losa-sin-mano-de-obra">
            {calculo.mano_de_obra.nota}
          </p>
          {calculo.advertencias.length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias">
              {calculo.advertencias.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
          <DriversUsadosDelCalculo usados={calculo.drivers_usados} hayObra={obraId !== ''} />
        </>
      )}

      <section className="mct__bloque" aria-label="Concepto nuevo de la losa" data-concepto-de-la-losa={d.concepto.clave}>
        <h3>Concepto nuevo de la losa (regla F7)</h3>
        <p className="text-xs">
          {d.concepto.descripcion}. El catálogo solo trae losas por prototipo, con un lote fijo de m²; este concepto por m² se propone con clave provisional,
          sin precio ni destajo, y solo Control de obra lo autoriza.
        </p>
        <PropuestaDeConceptoNuevo
          conceptoClave={d.concepto.clave}
          lista={propuestas.data ?? []}
          rol={rol}
          textoDelBoton="Proponer el concepto de la losa"
          proponiendo={proponer.isPending}
          onProponer={() =>
            void proponer.mutateAsync({ clave }).then(
              () => queryClient.invalidateQueries(),
              (e: unknown) => window.alert(e instanceof Error ? e.message : 'No se pudo proponer el concepto de la losa.'),
            )
          }
        />
      </section>

      <section className="mct__bloque" aria-label="Qué toma del catálogo">
        <h3>Lo que toma del catálogo</h3>
        <ul className="text-xs">
          {d.concreto_por_uso.map((c) => (
            <li key={c.uso}>
              Concreto de {c.uso}: <span className="mono">{c.clave}</span> {c.descripcion}
            </li>
          ))}
          <li>
            Cimbra: <span className="mono">{d.cimbra.clave}</span> {d.cimbra.descripcion}, {num(d.cimbra.por_m2_de_losa, 1)} m² por m² de losa.
          </li>
          {d.parrilla && (
            <li>
              Parrilla de la maciza: <span className="mono">{d.parrilla.clave}</span> {d.parrilla.descripcion} (por m²).
            </li>
          )}
          <li>
            Destajos de losa del catálogo, por m² (no se elige ninguno):{' '}
            {d.destajos_candidatos.map((x) => `${x.clave} ${x.descripcion}`).join(' · ')}.
          </li>
        </ul>
      </section>

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
