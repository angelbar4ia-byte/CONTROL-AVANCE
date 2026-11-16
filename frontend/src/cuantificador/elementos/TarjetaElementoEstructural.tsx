/**
 * La tarjeta de un elemento estructural de la biblioteca (Ola 3B): trabes, contratrabes, nervaduras, la zapata Z-1 y la columna C-1.
 * Simple a propósito: los parámetros arriba, lo que sale abajo. **No calcula nada**: cada cambio se manda al servidor
 * (`/biblioteca-de-elementos/estructura/{clave}/calcular`) y se muestra lo que responde.
 *
 * Se mide por metro lineal de trazo o por pieza de largo conocido (la zapata y la columna, siempre por pieza). Abajo del cálculo va la
 * conciliación con la composición real del catálogo (= ≈ ≠ solo en el catálogo / solo en el elemento): lo que el catálogo trae
 * distinto se muestra, no se corrige. El elemento NO tiene mano de obra y el concepto de colado y cimbra por ml queda por registrar
 * (Q51, Q52): la tarjeta lo dice y no crea nada.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCalcularElementoEstructuralApiV1BibliotecaDeElementosEstructuraLinealClaveCalcularPost,
  useDefinicionDelElementoEstructuralApiV1BibliotecaDeElementosEstructuraLinealClaveGet,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type {
  CalculoDelElementoEstructural,
  CalculoDelElementoEstructuralPeticion,
  DefinicionDelElementoEstructural,
  ZonaDeAnilloDelElemento,
} from '@/api/generado/modelo';

import { numeroTecleado } from '../volumen';
import { CorreccionesDelCatalogo } from './CorreccionesDelCatalogo';
import { DriversUsadosDelCalculo } from './DriversUsadosDelCalculo';

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const MARCA: Record<string, { texto: string; clase: string }> = {
  '=': { texto: '=', clase: 'badge badge--ok' },
  '≈': { texto: '≈', clase: 'badge badge--info' },
  '≠': { texto: '≠', clase: 'badge badge--danger' },
  solo_catalogo: { texto: 'solo en el catálogo', clase: 'badge badge--danger' },
  solo_elemento: { texto: 'solo en el elemento', clase: 'badge badge--warn' },
};
const PARTE: Record<string, string> = {
  acero: 'Acero',
  estribos: 'Anillos',
  alambre: 'Alambre',
  concreto: 'Concreto',
  cimbra: 'Cimbra',
};
const unidadVisible = (u: string) => (u === 'm3' ? 'm³' : u === 'm2' ? 'm²' : u);

interface Props {
  readonly clave: string;
  /** El rol de quien mira: Costos y Control de obra ven las correcciones propuestas al catálogo. */
  readonly rol?: string | null;
  /** La obra actual: el cálculo lee sus drivers (traslapes, puntas, desperdicios…). */
  readonly obraId?: string;
}

function separacionDelCatalogo(d: DefinicionDelElementoEstructural): string {
  const fila = d.armado.find((p) => p.parte === 'anillos');
  const m = fila ? /@([\d.]+)/.exec(fila.detalle) : null;
  return m?.[1] ?? '20';
}

export function TarjetaElementoEstructural({ clave, rol, obraId = '' }: Props) {
  const definicion = useDefinicionDelElementoEstructuralApiV1BibliotecaDeElementosEstructuraLinealClaveGet(clave);
  const calcular = useCalcularElementoEstructuralApiV1BibliotecaDeElementosEstructuraLinealClaveCalcularPost<ErrorApi>();
  const d = definicion.data;
  const [modo, setModo] = useState<'ml' | 'pieza'>('ml');
  const [largo, setLargo] = useState('4.00');
  const [alto, setAlto] = useState('6.00');
  const [cantidad, setCantidad] = useState('1');
  const [zonas, setZonas] = useState(false);
  const [zonaLargo, setZonaLargo] = useState('50');
  const [zonaSep, setZonaSep] = useState('10');
  const [centroSep, setCentroSep] = useState('');
  const [calculo, setCalculo] = useState<CalculoDelElementoEstructural | null>(null);
  const [error, setError] = useState<string | null>(null);
  const turno = useRef(0);

  // Al cambiar de elemento, la tarjeta vuelve a los valores del elemento (su modo, su largo y su altura).
  useEffect(() => {
    if (!d) return;
    setModo(d.modo_por_defecto);
    setLargo(String(d.largo_por_defecto_m ?? 4));
    setAlto(String(d.alto_por_defecto_m ?? 6));
    setCentroSep(separacionDelCatalogo(d));
    setZonas(false);
    setCalculo(null);
    setError(null);
  }, [d]);

  const esLineal = d?.tipo === 'lineal_estructural';
  const esColumna = d?.tipo === 'columna_de_concreto';

  const peticion = useMemo<CalculoDelElementoEstructuralPeticion | null>(() => {
    if (!d) return null;
    const q = numeroTecleado(cantidad);
    if (!(q > 0)) return null;
    const base: CalculoDelElementoEstructuralPeticion = { modo: esLineal ? modo : 'pieza', cantidad: q, ...(obraId === '' ? {} : { obra_id: obraId }) };
    if (esLineal && modo === 'pieza') {
      const l = numeroTecleado(largo);
      if (!(l > 0)) return null;
      base.largo_m = l;
      if (zonas) {
        const zl = numeroTecleado(zonaLargo);
        const zs = numeroTecleado(zonaSep);
        const cs = numeroTecleado(centroSep);
        if (!(zl > 0 && zs > 0 && cs > 0)) return null;
        const lista: ZonaDeAnilloDelElemento[] = [{ len_cm: zl, sep_cm: zs }, { sep_cm: cs }];
        base.zonas_de_anillo = lista;
      }
    }
    if (esColumna) {
      const a = numeroTecleado(alto);
      if (!(a > 0)) return null;
      base.alto_m = a;
    }
    return base;
  }, [d, esLineal, esColumna, modo, largo, alto, cantidad, zonas, zonaLargo, zonaSep, centroSep, obraId]);

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

  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando el elemento…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;

  const unidadDeCalculo = calculo?.unidad === 'ml' ? 'por metro' : 'por pieza';
  const camino = calculo?.camino_de_colado_y_cimbra ?? d.camino_de_colado_y_cimbra;
  const mostrarCorrecciones = d.categoria.clave === 'trabes';

  return (
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`} data-elemento-estructural={d.clave}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span> · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se mide por {d.se_mide_por}
          </div>
          <div className="text-mute text-xs" data-testid="ee-seccion">
            Sección {num(d.seccion.ancho_cm, 0)} × {num(d.seccion.peralte_cm, 0)} cm (ancho × peralte)
            {d.seccion.largo_cm ? ` · planta ${num(d.seccion.largo_cm, 0)} × ${num(d.seccion.ancho_cm, 0)} cm` : ''}
          </div>
        </div>
        <span className="badge badge--outline" title="Concepto del catálogo que paga este elemento">
          {d.concepto.clave} · {d.concepto.unidad}
        </span>
      </header>

      <section className="mct__parametros" aria-label="Parámetros del elemento">
        {d.modos.length > 1 && (
          <label className="mct__campo">
            <span>Se mide por</span>
            <select className="select" aria-label="Se mide por" value={modo} onChange={(e) => setModo(e.target.value as 'ml' | 'pieza')}>
              <option value="ml">Metro lineal de trazo</option>
              <option value="pieza">Pieza de largo conocido</option>
            </select>
          </label>
        )}
        {esLineal && modo === 'pieza' && (
          <label className="mct__campo">
            <span>Largo de la pieza (m)</span>
            <input className="input" inputMode="decimal" aria-label="Largo de la pieza en metros" value={largo} onChange={(e) => setLargo(e.target.value)} />
          </label>
        )}
        {esColumna && (
          <label className="mct__campo">
            <span>Altura de la columna (m)</span>
            <input className="input" inputMode="decimal" aria-label="Altura de la columna en metros" value={alto} onChange={(e) => setAlto(e.target.value)} />
          </label>
        )}
        <label className="mct__campo">
          <span>{esLineal && modo === 'ml' ? 'Metros que se piden' : 'Piezas que se piden'}</span>
          <input className="input" inputMode="decimal" aria-label="Cantidad que se pide" value={cantidad} onChange={(e) => setCantidad(e.target.value)} />
        </label>
        {esLineal && modo === 'pieza' && (
          <div className="mct__campo mct__campo--manual">
            <label className="mct__manual">
              <input type="checkbox" checked={zonas} onChange={(e) => setZonas(e.target.checked)} /> Anillos con zona más cerrada en cada extremo
            </label>
            {zonas && (
              <div className="mct__par">
                <input className="input" inputMode="decimal" aria-label="Largo de la zona de extremo en centímetros" value={zonaLargo} onChange={(e) => setZonaLargo(e.target.value)} />
                <input className="input" inputMode="decimal" aria-label="Separación en el extremo en centímetros" value={zonaSep} onChange={(e) => setZonaSep(e.target.value)} />
                <input className="input" inputMode="decimal" aria-label="Separación en el centro en centímetros" value={centroSep} onChange={(e) => setCentroSep(e.target.value)} />
                <span className="text-mute text-xs">cm de zona · @cm extremo · @cm centro</span>
              </div>
            )}
          </div>
        )}
      </section>

      <section className="mct__bloque" aria-label="Armado del catálogo">
        <h3>Armado</h3>
        <ul className="mct__pendientes" style={{ margin: 0, paddingLeft: 18 }}>
          {d.armado.map((p) => (
            <li key={`${p.parte}:${p.clave}`}>
              {p.cantidad > 1 || p.parte === 'varillas' || p.parte === 'arriba' || p.parte === 'abajo' ? `${num(p.cantidad, 0)} × ` : ''}
              <span className="mono">{p.clave}</span> {p.descripcion}
              {p.detalle ? <span className="text-mute"> · {p.detalle}</span> : null}
            </li>
          ))}
        </ul>
        <p className="text-mute text-xs">
          Lados de cimbra: {d.lados_de_cimbra}
          {d.usos_total > 0 ? ` · el catálogo lo usa dentro de ${d.usos_total} losa${d.usos_total > 1 ? 's' : ''}` : ''}
        </p>
      </section>

      {peticion === null && <p className="text-sm mct__aviso">Las medidas se capturan en metros y centímetros y deben ser mayores que cero.</p>}
      {error && (
        <p className="text-sm mct__error" role="alert">
          {error}
        </p>
      )}

      <DriversUsadosDelCalculo usados={calculo?.drivers_usados} hayObra={obraId !== ''} />

      {calculo && (
        <>
          <section className="mct__resumen" aria-label="Resultado">
            <span className="chip" data-testid="ee-concreto">
              Concreto {num(calculo.concreto.m3, 4)} m³ {unidadDeCalculo}
            </span>
            <span className="chip" data-testid="ee-cimbra">
              Cimbra {num(calculo.cimbra.m2, 2)} m² ({calculo.cimbra.lados} lado{calculo.cimbra.lados === 1 ? '' : 's'})
            </span>
            <span className="chip" data-testid="ee-acero">
              Acero {num(calculo.acero_kg, 2)} kg {unidadDeCalculo}
            </span>
            <span className="badge badge--outline" data-testid="ee-sin-mano-de-obra" title={calculo.mano_de_obra.nota}>
              Sin mano de obra
            </span>
          </section>

          <section className="mct__bloque" aria-label="Insumos del elemento">
            <h3>
              Insumos <span className="text-mute">({unidadDeCalculo}; total para {num(calculo.cantidad, 2)} {calculo.unidad})</span>
            </h3>
            <div className="mct__tabla-caja">
              <table className="mct__tabla">
                <thead>
                  <tr>
                    <th>Parte</th>
                    <th>Insumo</th>
                    <th className="n">{unidadDeCalculo === 'por metro' ? 'Por metro' : 'Por pieza'}</th>
                    <th className="n">Total</th>
                    <th>Unidad</th>
                    <th className="n">A comprar</th>
                  </tr>
                </thead>
                <tbody>
                  {calculo.insumos.map((i) => (
                    <tr key={`${i.parte}:${i.clave}`}>
                      <td>{PARTE[i.parte] ?? i.parte}</td>
                      <td>
                        <span className="mono">{i.clave}</span> {i.descripcion}
                        {i.detalle ? <div className="text-mute text-xs">{i.detalle}</div> : null}
                      </td>
                      <td className="n mono">{num(i.por_unidad, 4)}</td>
                      <td className="n mono">{num(i.total, 3)}</td>
                      <td>{unidadVisible(i.unidad)}</td>
                      <td className="n mono">{i.a_comprar === null || i.a_comprar === undefined ? '—' : num(i.a_comprar, 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {calculo.receta_acero && (
            <details className="mct__bloque">
              <summary>Cortes, traslapes y anillos del acero</summary>
              <ul className="mct__pendientes" style={{ margin: 0, paddingLeft: 18 }}>
                {calculo.receta_acero.varillas.map((v) => (
                  <li key={`${v.clave}:${v.etiqueta}:${v.varillas}`}>
                    {v.varillas} × <span className="mono">{v.clave}</span> {v.etiqueta}: traslape {num(v.traslape_m, 3)} m
                    {v.puntas_m > 0 ? `, puntas ${num(v.puntas_m, 3)} m` : ''}
                    {v.corte ? `, corte de ${v.corte.piezas} pza de ${num(v.corte.modulo_m, 2)} m` : ''}
                  </li>
                ))}
                {calculo.receta_acero.anillos && (
                  <li>
                    Anillos: {num(calculo.receta_acero.anillos.pza, 1)} pza de {num(calculo.receta_acero.anillos.largo_anillo_m, 3)} m,{' '}
                    {num(calculo.receta_acero.anillos.kg, 2)} kg
                  </li>
                )}
                <li>
                  Desperdicio: sobrante de corte {num(calculo.receta_acero.desperdicio.sobrante_de_corte_m, 2)} m, traslape{' '}
                  {num(calculo.receta_acero.desperdicio.traslape_m, 2)} m
                </li>
              </ul>
            </details>
          )}
          {calculo.parrilla && (
            <p className="text-mute text-xs">
              Parrilla de {calculo.parrilla.varillas_por_sentido[0]} × {calculo.parrilla.varillas_por_sentido[1]} varillas a cada {num(calculo.parrilla.separacion_cm, 0)} cm,{' '}
              {calculo.parrilla.capas} capa(s): {num(calculo.parrilla.ml, 2)} m de varilla.
            </p>
          )}

          <section className="mct__bloque" aria-label="Conciliación con el catálogo">
            <h3>Conciliación con el catálogo</h3>
            <p className="text-mute text-xs">
              = hasta 3 %, ≈ hasta 8 % (por ejemplo el traslape de 40 diámetros contra el 8 % del catálogo), ≠ más de 8 %. Lo que el catálogo trae
              distinto se muestra: no se corrige.
            </p>
            {calculo.conciliacion.map((c) => (
              <div key={c.concepto.clave} className="mct__bloque" data-conciliacion={c.concepto.clave}>
                <div>
                  <b className="mono">{c.concepto.clave}</b> · {c.concepto.descripcion}{' '}
                  <span className="text-mute text-xs">
                    ({c.concepto.unidad}; compara {c.concepto.toma.join(', ')} {c.sobre}; {c.concepto.fuente})
                  </span>
                </div>
                <div className="mct__tabla-caja">
                  <table className="mct__tabla">
                    <thead>
                      <tr>
                        <th>Insumo</th>
                        <th className="n">Catálogo</th>
                        <th className="n">Elemento</th>
                        <th className="n">Diferencia</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {c.filas.map((f) => (
                        <tr key={f.clave} data-marca={f.marca}>
                          <td>
                            <span className="mono">{f.clave}</span> {f.descripcion}
                          </td>
                          <td className="n mono">{f.catalogo === null || f.catalogo === undefined ? '—' : num(f.catalogo, 4)}</td>
                          <td className="n mono">{f.elemento === null || f.elemento === undefined ? '—' : num(f.elemento, 4)}</td>
                          <td className="n mono">
                            {f.diferencia_pct === null || f.diferencia_pct === undefined ? '—' : `${f.diferencia_pct >= 0 ? '+' : ''}${num(f.diferencia_pct, 1)} %`}
                          </td>
                          <td>
                            <span className={MARCA[f.marca]?.clase}>{MARCA[f.marca]?.texto ?? f.marca}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {c.mano_de_obra.length > 0 && (
                  <p className="text-mute text-xs">
                    El destajo del concepto va en el concepto y el elemento no lo calcula:{' '}
                    {c.mano_de_obra.map((m) => `${m.clave} ${m.descripcion}${m.costo !== null && m.costo !== undefined ? ` ($${num(m.costo)})` : ''}`).join(', ')}.
                  </p>
                )}
                {c.avisos.map((a) => (
                  <p key={a} className="text-xs mct__aviso">
                    {a}
                  </p>
                ))}
              </div>
            ))}
          </section>

          {calculo.advertencias.length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias">
              {calculo.advertencias.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
        </>
      )}

      {camino && (
        <section className="mct__bloque" aria-label="Colado, cimbra y destajo" data-camino={camino.estado}>
          <h3>Colado, cimbra y destajo</h3>
          <p className="text-xs">{camino.motivo}</p>
          {camino.estado === 'por_registrar' && camino.borrador && (
            <>
              <p className="text-xs" data-testid="ee-camino-colado">
                <span className="badge badge--warn">Concepto nuevo por registrar</span> {camino.borrador.descripcion_sugerida}. Concreto{' '}
                <span className="mono">{camino.borrador.concreto.clave}</span>
                {camino.borrador.cimbra.length > 0 ? `; cimbra ${camino.borrador.cimbra.map((c) => c.clave).join(', ')}` : '; sin cimbra'}.
              </p>
              <p className="text-mute text-xs">
                Cómo se registra: <span className="mono">{camino.borrador.ruta}</span>. Queda propuesto, sin precio, pendiente de Control de obra. Todavía no se crea.
              </p>
            </>
          )}
          <p className="text-mute text-xs" data-testid="ee-sin-destajo">
            {camino.mano_de_obra.nota ?? 'La mano de obra va en el concepto del catálogo.'}
          </p>
        </section>
      )}

      {mostrarCorrecciones && <CorreccionesDelCatalogo rol={rol} />}

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
