/**
 * La tarjeta de un muro de tabique (EST-02010, EST-02011 por nivel, EST-02020, AUX-04010), de un aparejo nuevo (capuchino EST-02005,
 * tizón EST-02030, muro de 42 EST-02040, sardinel EST-02050) o del piso de petatillo (ACA-02090) — Ola 3, lane 3C. Como las demás,
 * **no calcula nada**: cada cambio se manda al servidor (`/biblioteca-de-elementos/tabique/{clave}/calcular`) y se dibuja lo que
 * responde.
 *
 * Muestra el aparejo con su planta, las piezas y la mezcla por m² (o por ml de hilada), el concepto que paga según el nivel, la
 * conciliación con la composición real del catálogo (= ≈ ≠), la sección opcional de herramienta y equipo (vacía, sin precios), las
 * versiones propuestas y la tabla de revisión de claves. Lo que el catálogo trae distinto no se edita: se propone como nueva versión
 * del concepto y solo Control de obra la autoriza. Los conceptos nuevos son «propuestos», con clave provisional, sin destajo ni precio.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useAutorizarPropuestaApiV1PropuestasDeEstructuraPropuestaIdAutorizarPost as useAutorizarPropuesta,
  useCalcularTabiqueApiV1BibliotecaDeElementosTabiqueClaveCalcularPost as useCalcularTabique,
  useDefinicionDelTabiqueApiV1BibliotecaDeElementosTabiqueClaveGet as useDefinicion,
  useProponerActualizacionDeApuApiV1BibliotecaDeElementosTabiqueClavePropuestasActualizarApuPost as useProponerApu,
  useProponerCorreccionesDeTabiqueApiV1BibliotecaDeElementosTabiqueClavePropuestasCorreccionesPost as useProponerCorrecciones,
  useProponerConceptoNuevoApiV1BibliotecaDeElementosTabiqueClavePropuestasConceptoNuevoPost as useProponerConceptoNuevo,
  usePropuestasDeTabiqueApiV1BibliotecaDeElementosTabiqueClavePropuestasGet as usePropuestas,
  useRechazarPropuestaApiV1PropuestasDeEstructuraPropuestaIdRechazarPost as useRechazarPropuesta,
  useTablaDeRevisionDeTabiqueApiV1BibliotecaDeElementosTabiqueTablaDeRevisionGet as useTablaDeRevision,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { CalculoDelTabique, CalculoDelTabiquePeticion, GeometriaDelTabique, RenglonDeHerramienta } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';
import { useSesion } from '@/app/sesion';

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
const ANDAMIO: RenglonDeHerramienta = { descripcion: 'ANDAMIO (renta por jornada)', unidad: 'jornal', por_unidad: 0 };

interface Props {
  readonly clave: string;
}

/** La planta de la hilada: cada hilera con su espesor, a escala, y la junta entre hileras. Solo dibuja lo que el servidor calculó. */
export function PlantaDeLaHilada({ g, junta }: { readonly g: GeometriaDelTabique; readonly junta: number }) {
  const ancho = 300;
  const hiladas = g.hiladas;
  const maximo = Math.max(...hiladas.map((h) => h.espesor_cm), 1);
  const k = ancho / maximo;
  let y = 6;
  const cuerpo = hiladas.map((h, i) => {
    let x = 0;
    const filas = h.filas.map((f, j) => {
      const w = f.espesor_cm * k;
      const r = (
        <g key={`${i}-${j}`}>
          <rect x={x} y={y} width={w} height={26} fill="var(--c-surface-2, #e6d5c3)" stroke="currentColor" strokeWidth={1} />
          <text x={x + w / 2} y={y + 17} textAnchor="middle" fontSize={10} fill="currentColor">
            {f.etiqueta} {num(f.espesor_cm, 0)}
          </text>
        </g>
      );
      x += w + (j < h.filas.length - 1 ? junta * k : 0);
      return r;
    });
    const fila = (
      <g key={i}>
        {filas}
        <text x={ancho + 8} y={y + 17} fontSize={10} fill="currentColor">
          {num(h.espesor_cm, 1)} cm
        </text>
      </g>
    );
    y += 34;
    return fila;
  });
  return (
    <svg viewBox={`0 0 ${ancho + 60} ${y}`} width="100%" role="img" aria-label="Planta de la hilada con el espesor del muro" data-testid="tabique-planta">
      {cuerpo}
    </svg>
  );
}

export function TarjetaMuroTabique({ clave }: Props) {
  const { sesion } = useSesion();
  const puedeProponer = sesion?.rol === 'control_obra' || sesion?.rol === 'costos';
  const puedeAutorizar = sesion?.rol === 'control_obra';
  const definicion = useDefinicion(clave);
  const calcular = useCalcularTabique<ErrorApi>();
  const propuestas = usePropuestas(clave);
  const tabla = useTablaDeRevision();
  const proponerNuevo = useProponerConceptoNuevo<ErrorApi>();
  const proponerApu = useProponerApu<ErrorApi>();
  const proponerCorrecciones = useProponerCorrecciones<ErrorApi>();
  const autorizar = useAutorizarPropuesta<ErrorApi>();
  const rechazar = useRechazarPropuesta<ErrorApi>();
  const d = definicion.data;

  const [cantidad, setCantidad] = useState('1');
  const [nivel, setNivel] = useState('1');
  const [junta, setJunta] = useState('2');
  const [juntaHileras, setJuntaHileras] = useState('');
  const [despPieza, setDespPieza] = useState('12');
  const [despMezcla, setDespMezcla] = useState('5');
  const [cama, setCama] = useState('0');
  const [tipo, setTipo] = useState('');
  const [herramienta, setHerramienta] = useState<RenglonDeHerramienta[]>([]);
  const [calculo, setCalculo] = useState<CalculoDelTabique | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const turno = useRef(0);

  // Al cambiar de elemento, la tarjeta vuelve a los valores del elemento.
  useEffect(() => {
    if (!d) return;
    const p = d.parametros_por_defecto;
    setCantidad('1');
    setNivel('1');
    setJunta(String(p.junta_cm));
    setJuntaHileras(p.junta_entre_hileras_cm === null || p.junta_entre_hileras_cm === undefined ? '' : String(p.junta_entre_hileras_cm));
    setDespPieza(String(p.desperdicio_de_pieza_pct));
    setDespMezcla(String(p.desperdicio_de_mezcla_pct));
    setCama(p.cama_cm === null || p.cama_cm === undefined ? '0' : String(p.cama_cm));
    setTipo(p.tipo_de_sardinel ?? '');
    setHerramienta([]);
    setCalculo(null);
    setError(null);
    setAviso(null);
  }, [d]);

  const conNivel = d?.parametros_por_defecto.nivel_desde_3er_nivel !== null && d?.parametros_por_defecto.nivel_desde_3er_nivel !== undefined;
  const conCama = d?.parametros_por_defecto.cama_cm !== null && d?.parametros_por_defecto.cama_cm !== undefined;
  const conJuntaHileras = d?.parametros_por_defecto.junta_entre_hileras_cm !== null && d?.parametros_por_defecto.junta_entre_hileras_cm !== undefined;

  const peticion = useMemo<CalculoDelTabiquePeticion | null>(() => {
    if (!d) return null;
    const q = numeroTecleado(cantidad);
    const j = numeroTecleado(junta);
    const dp = numeroTecleado(despPieza);
    const dm = numeroTecleado(despMezcla);
    if (!(q > 0) || junta.trim() === '' || despPieza.trim() === '' || despMezcla.trim() === '') return null;
    if (!(j >= 0 && dp >= 0 && dm >= 0)) return null;
    const base: CalculoDelTabiquePeticion = { cantidad: q, junta_cm: j, desperdicio_de_pieza_pct: dp, desperdicio_de_mezcla_pct: dm };
    if (conNivel) {
      const n = Math.trunc(numeroTecleado(nivel));
      if (!(n >= 1)) return null;
      base.nivel = n;
    }
    if (conJuntaHileras && juntaHileras.trim() !== '') {
      const jh = numeroTecleado(juntaHileras);
      if (!(jh >= 0)) return null;
      base.junta_entre_hileras_cm = jh;
    }
    if (conCama) {
      const c = numeroTecleado(cama);
      if (!(c >= 0)) return null;
      base.cama_cm = c;
    }
    if (tipo !== '') base.tipo_de_sardinel = tipo;
    if (herramienta.length > 0) base.herramienta = herramienta;
    return base;
  }, [d, cantidad, nivel, junta, juntaHileras, despPieza, despMezcla, cama, tipo, herramienta, conNivel, conCama, conJuntaHileras]);

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
  const porUnidad = d.medida === 'ml' ? 'metro lineal de hilada' : 'm²';
  const claveDelConcepto = calculo?.concepto.clave ?? d.conceptos[0]?.clave ?? clave;
  const esNuevo = d.conceptos.every((c) => c.estado === 'propuesto');
  // El aviso del mortero (1:5 contra 1:4) sigue visible mientras la corrección de texto no esté autorizada.
  const textoCorregido = lista.some((p) => p.concepto_clave === 'AUX-04010' && p.estado === 'autorizada' && p.clase === 'version_de_concepto');
  const textoPendiente = lista.some((p) => p.concepto_clave === 'AUX-04010' && p.estado === 'pendiente');
  const sinAvisoDeMortero = (a: string) => !(textoCorregido && a.includes('1:5'));
  const conCorrecciones = d.clave === 'EST-02020' || d.clave === 'AUX-04010';
  const hayDiferencias = (calculo?.conciliacion ?? []).some((c) => (c.resumen['≈'] ?? 0) + (c.resumen['≠'] ?? 0) > 0);
  // La versión propuesta de cada insumo, por concepto: la autorizada gana a la pendiente.
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
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`} data-tabique={d.clave}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span> · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se mide por {porUnidad} · espesor real {num(d.espesor_real_cm, 1)} cm
            {d.espesor_nominal_cm ? ` (nominal ${d.espesor_nominal_cm})` : ''}
          </div>
        </div>
        <span className={esNuevo ? 'badge badge--warn' : 'badge badge--outline'} data-testid="tabique-concepto">
          {claveDelConcepto}
          {esNuevo ? ' · provisional' : ''}
        </span>
      </header>

      <section className="mct__parametros" aria-label="Parámetros del elemento">
        <label className="mct__campo">
          <span>{d.medida === 'ml' ? 'Metros de hilada' : 'm² de muro (sin huecos)'}</span>
          <input className="input" inputMode="decimal" aria-label="Cantidad" value={cantidad} onChange={(e) => setCantidad(e.target.value)} />
        </label>
        {conNivel && (
          <label className="mct__campo">
            <span>Nivel del plano (1 = planta baja)</span>
            <input className="input" inputMode="numeric" aria-label="Nivel del plano" value={nivel} onChange={(e) => setNivel(e.target.value)} />
          </label>
        )}
        <label className="mct__campo">
          <span>Junta (cm)</span>
          <input className="input" inputMode="decimal" aria-label="Junta en centímetros" value={junta} onChange={(e) => setJunta(e.target.value)} />
        </label>
        {conJuntaHileras && (
          <label className="mct__campo">
            <span>Junta entre las dos hileras (cm)</span>
            <input
              className="input"
              inputMode="decimal"
              aria-label="Junta entre hileras en centímetros"
              value={juntaHileras}
              onChange={(e) => setJuntaHileras(e.target.value)}
            />
          </label>
        )}
        <label className="mct__campo">
          <span>Desperdicio de pieza (%)</span>
          <input className="input" inputMode="decimal" aria-label="Desperdicio de pieza" value={despPieza} onChange={(e) => setDespPieza(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Desperdicio de mezcla (%)</span>
          <input className="input" inputMode="decimal" aria-label="Desperdicio de mezcla" value={despMezcla} onChange={(e) => setDespMezcla(e.target.value)} />
        </label>
        {conCama && (
          <label className="mct__campo">
            <span>Cama de mortero (cm; el catálogo no la trae)</span>
            <input className="input" inputMode="decimal" aria-label="Cama de mortero en centímetros" value={cama} onChange={(e) => setCama(e.target.value)} />
          </label>
        )}
        {d.tipos_de_sardinel.length > 0 && (
          <label className="mct__campo">
            <span>Tipo de sardinel</span>
            <select className="select" aria-label="Tipo de sardinel" value={tipo} onChange={(e) => setTipo(e.target.value)}>
              {d.tipos_de_sardinel.map((t) => (
                <option key={t.clave} value={t.clave}>
                  {t.clave} · {t.descripcion}
                </option>
              ))}
            </select>
          </label>
        )}
      </section>

      {peticion === null && <p className="text-sm mct__aviso">Las medidas se capturan en centímetros y por ciento, y la cantidad debe ser mayor que cero.</p>}
      {error && (
        <p className="text-sm mct__error" role="alert">
          {error}
        </p>
      )}
      {aviso && (
        <p className="text-sm" role="status" data-testid="tabique-aviso">
          {aviso}
        </p>
      )}

      {calculo && (
        <>
          <section className="mct__resumen" aria-label="Resultado">
            <span className="chip" data-testid="tabique-piezas">
              Tabique <b>{num(calculo.piezas.por_unidad, 1)} pza</b> por {calculo.unidad}
            </span>
            <span className="chip" data-testid="tabique-mezcla">
              Mezcla 1:4 <b>{num(calculo.mezcla.por_unidad, 4)} m³</b> por {calculo.unidad}
            </span>
            <span className="chip" data-testid="tabique-espesor">
              Espesor real {num(calculo.geometria.espesor_real_cm, 1)} cm
            </span>
            <span className="chip" data-testid="tabique-total">
              {num(calculo.piezas.total, 1)} pza ({num(calculo.piezas.a_comprar, 0)} a comprar) · {num(calculo.mezcla.total_m3, 3)} m³
            </span>
            <span className="badge badge--outline" data-testid="tabique-mano-de-obra" title={calculo.mano_de_obra.nota}>
              {calculo.mano_de_obra.destajo ? `Destajo ${calculo.mano_de_obra.destajo.clave}` : 'Sin mano de obra (sin destajo)'}
            </span>
          </section>

          <section className="mct__bloque" aria-label="Concepto que lo paga" data-concepto-elegido={calculo.concepto.clave}>
            <h3>Concepto que lo paga</h3>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              <span className="mono">{calculo.concepto.clave}</span>
              <span className="text-sm">{calculo.concepto.descripcion}</span>
              <span className="text-mute text-xs">{calculo.concepto.etiqueta}</span>
              {calculo.concepto.estado === 'propuesto' && (
                <span className="badge badge--warn">Concepto nuevo propuesto · clave provisional · pendiente de autorizar por Control de obra</span>
              )}
            </div>
            {d.conceptos.length > 1 && (
              <p className="text-mute text-xs">
                Por nivel: {d.conceptos.map((c) => `${c.clave} (${c.nivel_desde ? `nivel ${c.nivel_desde} en adelante` : 'niveles 1 y 2'})`).join(' · ')}. La azotea de una casa de
                dos plantas es el tercer nivel.
              </p>
            )}
            <p className="text-mute text-xs">{calculo.mano_de_obra.nota}</p>
          </section>

          <section className="mct__bloque" aria-label="Aparejo">
            <h3>Aparejo: {d.aparejo}</h3>
            <p className="text-sm">
              Pieza {num(calculo.pieza.ancho_cm, 0)} × {num(calculo.pieza.alto_cm, 0)} × {num(calculo.pieza.largo_cm, 0)} cm, {d.aparejo_texto}
            </p>
            <PlantaDeLaHilada g={calculo.geometria} junta={calculo.parametros.junta_entre_hileras_cm ?? calculo.parametros.junta_cm} />
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
              La mezcla se abre en {calculo.mezcla_compuesta.map((m) => `${num(m.total, 3)} ${m.unidad} de ${m.descripcion.toLowerCase()}`).join(', ')}.
            </p>
          </section>

          <section className="mct__bloque" aria-label="Herramienta y equipo" data-testid="tabique-herramienta">
            <h3>Herramienta y equipo (opcional, vacío por defecto)</h3>
            {herramienta.length === 0 ? (
              <p className="text-mute text-xs">
                Sin herramienta ni equipo. El catálogo no trae insumos de esta clase (ni andamios): la sección queda vacía y sin precios.
              </p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {herramienta.map((h, i) => (
                  <li key={h.descripcion} className="row" style={{ gap: 6, alignItems: 'center' }}>
                    <span>{h.descripcion}</span>
                    <input
                      className="input"
                      inputMode="decimal"
                      style={{ width: 80 }}
                      aria-label={`Cantidad de ${h.descripcion} por ${calculo.unidad}`}
                      value={String(h.por_unidad)}
                      onChange={(e) => {
                        const v = numeroTecleado(e.target.value);
                        setHerramienta((hs) => hs.map((x, k) => (k === i ? { ...x, por_unidad: v >= 0 ? v : 0 } : x)));
                      }}
                    />
                    <span className="text-mute text-xs">
                      {h.unidad} por {calculo.unidad} · sin precio
                    </span>
                    <button type="button" className="btn btn--sm" onClick={() => setHerramienta((hs) => hs.filter((_, k) => k !== i))}>
                      Quitar
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="row" style={{ gap: 6 }}>
              <button
                type="button"
                className="btn btn--sm"
                disabled={herramienta.some((h) => h.descripcion === ANDAMIO.descripcion)}
                onClick={() => setHerramienta((hs) => [...hs, { ...ANDAMIO }])}
              >
                Sugerencia: andamio
              </button>
            </div>
            {calculo.herramienta.length > 0 && (
              <p className="text-mute text-xs">
                Total: {calculo.herramienta.map((h) => `${num(h.total, 2)} ${h.unidad} de ${h.descripcion.toLowerCase()}`).join(', ')}.
              </p>
            )}
          </section>

          <section className="mct__bloque" aria-label="Conciliación con el catálogo">
            <h3>Conciliación con el catálogo</h3>
            <p className="text-mute text-xs">
              = hasta 3 %, ≈ hasta 8 %, ≠ más de 8 %. Lo que el catálogo trae distinto se muestra: no se edita; si hace falta se propone como nueva
              versión del concepto. La mano de obra y el destajo no se calculan.
            </p>
            {calculo.conciliacion.length === 0 && (
              <p className="text-sm" data-testid="tabique-sin-catalogo">
                <span className="badge badge--warn">Sin concepto en el catálogo</span> Este aparejo es un concepto nuevo propuesto: no hay con qué compararlo.
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
                {c.mano_de_obra.length > 0 && (
                  <p className="text-mute text-xs">
                    Destajo del catálogo (el elemento no lo calcula): {c.mano_de_obra.map((m) => `${m.clave} ${m.descripcion}`).join(', ')}.
                  </p>
                )}
                {c.avisos.filter(sinAvisoDeMortero).map((a) => (
                  <p key={a} className="text-xs mct__aviso" data-testid="tabique-aviso-catalogo">
                    {a}
                  </p>
                ))}
              </div>
            ))}
          </section>

          {calculo.avisos.filter(sinAvisoDeMortero).length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias">
              {calculo.avisos.filter(sinAvisoDeMortero).map((a) => (
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
        {puedeProponer && (
          <div className="row" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            {esNuevo && (
              <button
                type="button"
                className="btn btn--sm"
                disabled={proponerNuevo.isPending}
                onClick={() =>
                  void correr(async () => {
                    const r = await proponerNuevo.mutateAsync({ clave });
                    return r.creadas.length === 0
                      ? `${clave} ya está propuesto.`
                      : `${clave} propuesto como concepto nuevo: espera la autorización de Control de obra.`;
                  })
                }
              >
                Proponer el concepto nuevo
              </button>
            )}
            {!esNuevo && peticion !== null && (
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
            {conCorrecciones && (
              <button
                type="button"
                className="btn btn--sm"
                disabled={proponerCorrecciones.isPending}
                onClick={() =>
                  void correr(async () => {
                    const r = await proponerCorrecciones.mutateAsync({ clave });
                    return r.creadas.length === 0 ? 'No hay correcciones nuevas que proponer.' : 'Corrección propuesta: espera la autorización de Control de obra.';
                  })
                }
              >
                Proponer la corrección del catálogo
              </button>
            )}
            {textoPendiente && !textoCorregido && (
              <span className="text-mute text-xs" data-testid="tabique-texto-pendiente">
                La corrección del texto del mortero está pendiente: la diferencia sigue visible.
              </span>
            )}
            {pendientes.length > 0 && <span className="text-mute text-xs">{pendientes.length} esperan a Control de obra.</span>}
          </div>
        )}
      </section>

      <details className="mct__bloque" aria-label="Tabla de revisión de claves y aparejos" data-testid="tabique-revision">
        <summary>Tabla de revisión de claves y aparejos</summary>
        <p className="text-mute text-xs">
          Las claves marcadas «provisional» son propuestas: Control de obra las confirma. El espesor real es el de la pieza 14×6×26 con junta de 2 cm; el nombre
          conserva el espesor nominal de la imagen. Piezas con 12 % de desperdicio y mezcla con 5 %.
        </p>
        <div className="mct__tabla-caja">
          <table className="mct__tabla">
            <thead>
              <tr>
                <th>Clave</th>
                <th>Nombre nominal</th>
                <th className="n">Espesor real (cm)</th>
                <th>Aparejo</th>
                <th className="n">Piezas</th>
                <th className="n">Mezcla (m³)</th>
                <th>Contra el catálogo</th>
              </tr>
            </thead>
            <tbody>
              {(tabla.data ?? []).map((f) => (
                <tr key={f.clave} data-revision={f.clave}>
                  <td>
                    <span className="mono">{f.clave}</span> {f.provisional && <span className="badge badge--warn">provisional</span>}
                  </td>
                  <td>{f.nombre_nominal}</td>
                  <td className="n mono">{num(f.espesor_real_cm, 1)}</td>
                  <td>{f.aparejo}</td>
                  <td className="n mono">
                    {num(f.piezas_por_unidad, 1)} /{f.unidad}
                  </td>
                  <td className="n mono">
                    {num(f.mezcla_m3_por_unidad, 4)} /{f.unidad}
                  </td>
                  <td className="text-xs">{f.contraste}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

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
