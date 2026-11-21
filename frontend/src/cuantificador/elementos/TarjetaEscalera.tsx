/**
 * La tarjeta de la escalera de la biblioteca (Fase 4a: escaleras con cotas): la escalera forjada como elemento que sale de la diferencia de cotas de las zonas.
 * Simple a propósito: los parámetros arriba, lo que sale abajo. **No calcula nada**: cada cambio se manda al servidor
 * (`/biblioteca-de-elementos/escalera/{clave}/calcular`) y se muestra lo que responde.
 *
 * Se capturan la cota de arranque y la de llegada (relativas al piso terminado de PB = 0), los peldaños (si no, salen del desnivel y de la contrahuella
 * máxima), la huella o el recorrido que mediría una línea del plano, el ancho, el espesor, las rampas y el largo del descanso. Sale el desnivel, la contrahuella,
 * la huella, las rampas y el descanso, y los **conceptos que paga**: el escalón usa el concepto que YA existe en el catálogo (EST-01510, por escalón de 1.20 m) y
 * el descanso entre rampas un concepto nuevo propuesto (EJ-820, clave provisional, sin precio, regla F7) que solo Control de obra autoriza. No calcula mano de
 * obra con importe ni lee drivers; los pendientes se muestran.
 *
 * Las escaleras de una zona real del plano (con sus cotas, su línea, su espacio y su partida) están en el panel de zonas de la pestaña Trazos.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import type { CalculoDeLaEscaleraPeticion, EscaleraCalculada } from '@/api/generado/modelo';
import {
  useCalcularLaEscaleraApiV1BibliotecaDeElementosEscaleraClaveCalcularPost,
  useDefinicionDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClaveGet,
  useProponerConceptoDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClavePropuestasConceptoPost,
  usePropuestasDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClavePropuestasGet,
} from '@/api/generado/escaleras/escaleras';
import { queryClient } from '@/app/queryClient';

import { PropuestaDeConceptoNuevo } from './PropuestaDeConceptoNuevo';

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const unidadVisible = (u: string) => (u === 'm3' ? 'm³' : u === 'm2' ? 'm²' : u);
export const NOMBRE_DE_PARTE_DE_LA_ESCALERA: Record<string, string> = { rampa: 'Rampa', descanso: 'Descanso' };

interface Props {
  readonly clave: string;
  readonly rol?: string | null;
}

/** Un campo numérico opcional: vacío = el de omisión del elemento (`undefined`); lo que no es un número válido anula el cálculo (`null`). */
function opcional(texto: string, minimo = 0): number | undefined | null {
  if (texto.trim() === '') return undefined;
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) && n >= minimo ? n : null;
}

/** Una cota (puede ser negativa): vacío = el valor de omisión de la tarjeta. */
function cota(texto: string): number | null {
  const n = Number(texto.trim().replace(',', '.'));
  return texto.trim() !== '' && Number.isFinite(n) ? n : null;
}

export function TarjetaEscalera({ clave, rol }: Props) {
  const definicion = useDefinicionDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClaveGet(clave);
  const calcular = useCalcularLaEscaleraApiV1BibliotecaDeElementosEscaleraClaveCalcularPost<ErrorApi>();
  const propuestas = usePropuestasDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClavePropuestasGet(clave);
  const proponer = useProponerConceptoDeLaEscaleraApiV1BibliotecaDeElementosEscaleraClavePropuestasConceptoPost<ErrorApi>();
  const d = definicion.data;
  const [arranque, setArranque] = useState('0');
  const [llegada, setLlegada] = useState('3.12');
  const [peldanos, setPeldanos] = useState('');
  const [contrahuella, setContrahuella] = useState('');
  const [huella, setHuella] = useState('');
  const [recorrido, setRecorrido] = useState('');
  const [ancho, setAncho] = useState('');
  const [espesor, setEspesor] = useState('');
  const [rampas, setRampas] = useState('');
  const [descanso, setDescanso] = useState('');
  const [calculo, setCalculo] = useState<EscaleraCalculada | null>(null);
  const [error, setError] = useState<string | null>(null);
  const turno = useRef(0);

  // Al cambiar de elemento, la tarjeta vuelve a los valores del elemento.
  useEffect(() => {
    if (!d) return;
    setArranque('0');
    setLlegada('3.12');
    for (const poner of [setPeldanos, setContrahuella, setHuella, setRecorrido, setAncho, setEspesor, setRampas, setDescanso]) poner('');
    setCalculo(null);
    setError(null);
  }, [d]);

  const peticion = useMemo<CalculoDeLaEscaleraPeticion | null>(() => {
    if (!d) return null;
    const a = cota(arranque);
    const l = cota(llegada);
    if (a === null || l === null) return null;
    const pe = opcional(peldanos, 2);
    const cm = opcional(contrahuella, 0.0001);
    const hu = opcional(huella, 0.0001);
    const re = opcional(recorrido, 0.0001);
    const an = opcional(ancho, 0.0001);
    const es = opcional(espesor, 0.0001);
    const ra = opcional(rampas, 1);
    const de = opcional(descanso, 0.0001);
    if ([pe, cm, hu, re, an, es, ra, de].includes(null)) return null;
    return {
      cota_arranque_m: a,
      cota_llegada_m: l,
      ...(pe === undefined ? {} : { peldanos: Math.round(pe as number) }),
      ...(cm === undefined ? {} : { contrahuella_max_m: cm as number }),
      ...(hu === undefined ? {} : { huella_m: hu as number }),
      ...(re === undefined ? {} : { recorrido_m: re as number }),
      ...(an === undefined ? {} : { ancho_m: an as number }),
      ...(es === undefined ? {} : { espesor_m: es as number }),
      ...(ra === undefined ? {} : { rampas: Math.round(ra as number) }),
      ...(de === undefined ? {} : { largo_descanso_m: de as number }),
    };
  }, [d, arranque, llegada, peldanos, contrahuella, huella, recorrido, ancho, espesor, rampas, descanso]);

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
          setCalculo(null);
          setError(e instanceof Error ? e.message : 'No se pudo calcular la escalera.');
        });
    }, 200);
    return () => clearTimeout(espera);
  }, [clave, peticion, mutateAsync]);

  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando la escalera…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;

  const defecto = d.parametros_por_defecto;
  const g = calculo?.geometria;

  return (
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`} data-escalera={d.clave}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span> · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se mide por {d.se_mide_por}
          </div>
        </div>
        <span className="badge badge--ok" title="Concepto que ya existe en el catálogo">
          {d.concepto.clave} · {d.concepto.unidad} · del catálogo
        </span>
      </header>

      <section className="mct__parametros" aria-label="Cotas y parámetros de la escalera">
        <label className="mct__campo" title="Cota del piso de arranque, relativa al piso terminado de PB = 0.">
          <span>Cota de arranque (m)</span>
          <input className="input" inputMode="decimal" aria-label="Cota de arranque en metros" value={arranque} onChange={(e) => setArranque(e.target.value)} />
        </label>
        <label className="mct__campo" title="Cota de llegada: por omisión 3.12 m (3.00 m de altura libre más 12 cm de losa).">
          <span>Cota de llegada (m)</span>
          <input className="input" inputMode="decimal" aria-label="Cota de llegada en metros" value={llegada} onChange={(e) => setLlegada(e.target.value)} />
        </label>
        <label className="mct__campo" title="Sin él, los peldaños salen del desnivel y de la contrahuella máxima.">
          <span>Peldaños</span>
          <input className="input" inputMode="numeric" aria-label="Número de peldaños" placeholder="del desnivel" value={peldanos} onChange={(e) => setPeldanos(e.target.value)} />
        </label>
        <label className="mct__campo" title="Con ella los peldaños salen del desnivel. Valor de referencia (pendiente E2).">
          <span>Contrahuella máxima (m)</span>
          <input className="input" inputMode="decimal" aria-label="Contrahuella máxima en metros" placeholder={String(defecto.contrahuella_max_m)} value={contrahuella} onChange={(e) => setContrahuella(e.target.value)} />
        </label>
        <label className="mct__campo" title="El fondo de cada peldaño. Valor de referencia (pendiente E2).">
          <span>Huella (m)</span>
          <input className="input" inputMode="decimal" aria-label="Huella en metros" placeholder={String(defecto.huella_m)} value={huella} onChange={(e) => setHuella(e.target.value)} />
        </label>
        <label className="mct__campo" title="Lo que mediría una línea del plano: el recorrido horizontal de las rampas. Manda sobre la huella.">
          <span>Recorrido de las rampas (m)</span>
          <input className="input" inputMode="decimal" aria-label="Recorrido de las rampas en metros" placeholder="la huella" value={recorrido} onChange={(e) => setRecorrido(e.target.value)} />
        </label>
        <label className="mct__campo" title="El escalón del catálogo es de 1.20 m: la cantidad escala con ancho ÷ 1.20.">
          <span>Ancho (m)</span>
          <input className="input" inputMode="decimal" aria-label="Ancho de la escalera en metros" placeholder={String(defecto.ancho_m)} value={ancho} onChange={(e) => setAncho(e.target.value)} />
        </label>
        <label className="mct__campo" title="Espesor del concreto de la rampa y del descanso.">
          <span>Espesor (m)</span>
          <input className="input" inputMode="decimal" aria-label="Espesor de la rampa en metros" placeholder={String(defecto.espesor_m)} value={espesor} onChange={(e) => setEspesor(e.target.value)} />
        </label>
        <label className="mct__campo" title="Entre rampas hay un descanso.">
          <span>Rampas</span>
          <input className="input" inputMode="numeric" aria-label="Número de rampas" placeholder={String(defecto.rampas)} value={rampas} onChange={(e) => setRampas(e.target.value)} />
        </label>
        <label className="mct__campo" title="Sin él, el descanso es cuadrado (largo = ancho).">
          <span>Largo del descanso (m)</span>
          <input className="input" inputMode="decimal" aria-label="Largo del descanso en metros" placeholder="el ancho" value={descanso} onChange={(e) => setDescanso(e.target.value)} />
        </label>
      </section>

      {error && (
        <p className="text-sm" role="alert">
          {error}
        </p>
      )}

      {calculo && g && (
        <>
          <section className="mct__bloque" aria-label="Resumen de la escalera" data-resumen-de-la-escalera>
            <h3>Resumen</h3>
            <p className="text-sm" data-testid="escalera-desnivel">
              Desnivel {num(calculo.cotas.desnivel_m, 3)} m (de {num(calculo.cotas.arranque_m, 2)} a {num(calculo.cotas.llegada_m, 2)} m)
            </p>
            <p className="text-sm" data-testid="escalera-peldanos">
              {g.peldanos} peldaños {g.origen_de_peldanos === 'desnivel' ? '(del desnivel)' : '(tecleados)'} · contrahuella {num(g.contrahuella_m * 100, 1)} cm · huella{' '}
              {num(g.huella_m * 100, 1)} cm {g.origen_de_huella === 'linea' ? '(de la línea del plano)' : ''}
            </p>
            <p className="text-sm" data-testid="escalera-rampas">
              {g.rampas.length} {g.rampas.length === 1 ? 'rampa' : 'rampas'}: {g.rampas.map((r) => `${r.peldanos} peldaños`).join(' + ')} · recorrido horizontal{' '}
              {num(g.recorrido_horizontal_m)} m · {g.descansos} {g.descansos === 1 ? 'descanso' : 'descansos'}
              {g.descansos > 0 && ` de ${num(g.area_de_descanso_m2)} m²`}
            </p>
            <p className="text-sm" data-testid="escalera-concreto">
              Concreto de la rampa {num(g.volumen_de_rampa_m3, 3)} m³ sobre {num(g.superficie_de_rampa_m2)} m² inclinados
              {g.descansos > 0 && ` · del descanso ${num(g.volumen_de_descanso_m3, 3)} m³`}
            </p>
          </section>

          <section className="mct__bloque" aria-label="Conceptos de la escalera" data-conceptos-de-la-escalera>
            <h3>Conceptos que paga la escalera</h3>
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

          <section className="mct__bloque" aria-label="Insumos de la escalera">
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
                    <tr key={`${i.parte}-${i.clave}`} data-insumo={i.clave} data-parte={i.parte}>
                      <td>{NOMBRE_DE_PARTE_DE_LA_ESCALERA[i.parte] ?? i.parte}</td>
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

          <p className="text-mute text-xs" data-testid="escalera-sin-mano-de-obra">
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

      <section className="mct__bloque" aria-label="Qué toma del catálogo" data-concepto-de-la-escalera={d.concepto.clave}>
        <h3>Lo que toma del catálogo</h3>
        <ul className="text-xs">
          <li>
            Concepto: <span className="mono">{d.concepto.clave}</span> {d.concepto.descripcion} (por {d.concepto.unidad}, un escalón de {num(d.largo_base_del_escalon_m)} m). Regla F7: ya existe en
            el catálogo, no se propone ninguno nuevo.
          </li>
          <li>
            Composición del escalón:{' '}
            {d.composicion_del_escalon.map((i) => `${i.clave} ${num(i.por_escalon, 4)} ${unidadVisible(i.unidad)}`).join(' · ')}. El concreto y el acero se calculan por geometría y se
            concilian; el resto se informa.
          </li>
          <li>
            Parrilla de acero por m² (<span className="mono">AUX-06010</span>): {d.parrilla_por_m2.map((i) => `${i.clave} ${num(i.por_m2, 5)} ${unidadVisible(i.unidad)}`).join(' · ')}.
          </li>
          <li>Destajos del catálogo (no se les pone importe): {d.destajos_candidatos.map((x) => `${x.clave} ${x.descripcion}`).join(' · ')}.</li>
        </ul>
      </section>

      <section className="mct__bloque" aria-label="Concepto nuevo del descanso" data-concepto-del-descanso={d.concepto_del_descanso.clave}>
        <h3>Concepto nuevo del descanso (regla F7)</h3>
        <p className="text-xs">
          {d.concepto_del_descanso.descripcion}. El catálogo no trae un descanso de concreto; este concepto por m² se propone con clave provisional, sin destajo ni precio, y solo Control de
          obra lo autoriza. Mientras no esté autorizado y en el catálogo, su cantidad se informa pero no se escribe en ninguna partida.
        </p>
        <PropuestaDeConceptoNuevo
          conceptoClave={d.concepto_del_descanso.clave}
          lista={propuestas.data ?? []}
          rol={rol}
          textoDelBoton="Proponer el concepto del descanso"
          proponiendo={proponer.isPending}
          onProponer={() =>
            void proponer.mutateAsync({ clave }).then(
              () => queryClient.invalidateQueries(),
              (e: unknown) => window.alert(e instanceof Error ? e.message : 'No se pudo proponer el concepto del descanso.'),
            )
          }
        />
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
