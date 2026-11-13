/**
 * La tarjeta del muro de contención de piedra (MCT-01010). Simple a propósito: los parámetros arriba, lo que sale
 * abajo. **No calcula nada**: cada cambio de parámetro se manda al servidor (`/biblioteca-de-elementos/MCT-01010/calcular`)
 * y se muestra lo que responde.
 *
 * Lo que la especificación deja abierto se ve como pendiente: el espesor del filtro de grava queda «por definir» y los
 * insumos del dren sin precio se marcan como provisionales.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCalcularElementoApiV1BibliotecaDeElementosClaveCalcularPost,
  useDefinicionDelElementoApiV1BibliotecaDeElementosClaveGet,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { CalculoDelMuro, CalculoDelMuroPeticion } from '@/api/generado/modelo';

import { numeroTecleado } from '../volumen';
import { VistasDelMuro } from './VistasDelMuro';

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

interface Props {
  readonly clave: string;
}

export function TarjetaMuroContencion({ clave }: Props) {
  const definicion = useDefinicionDelElementoApiV1BibliotecaDeElementosClaveGet(clave);
  const calcular = useCalcularElementoApiV1BibliotecaDeElementosClaveCalcularPost<ErrorApi>();
  const [alto, setAlto] = useState('2.00');
  const [manual, setManual] = useState(false);
  const [corona, setCorona] = useState('');
  const [base, setBase] = useState('');
  const [dentellon, setDentellon] = useState(true);
  const [lluvia, setLluvia] = useState<'baja' | 'alta'>('baja');
  const [tubo, setTubo] = useState<'pvc' | 'concreto'>('pvc');
  const [relleno, setRelleno] = useState<'vertical' | 'inclinada'>('vertical');
  const [filtro, setFiltro] = useState('');
  const [calculo, setCalculo] = useState<CalculoDelMuro | null>(null);
  const [error, setError] = useState<string | null>(null);
  const turno = useRef(0);

  const peticion = useMemo<CalculoDelMuroPeticion | null>(() => {
    const h = numeroTecleado(alto);
    if (!(h > 0)) return null;
    const c = manual ? numeroTecleado(corona) / 100 : 0;
    const b = manual ? numeroTecleado(base) / 100 : 0;
    const f = numeroTecleado(filtro);
    return {
      alto_m: h,
      corona_m: c > 0 ? c : undefined,
      base_m: b > 0 ? b : undefined,
      dentellon,
      lluvia,
      tubo,
      relleno,
      filtro_cm: f > 0 ? f : undefined,
    };
  }, [alto, manual, corona, base, dentellon, lluvia, tubo, relleno, filtro]);

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
          setError(e instanceof Error ? e.message : 'No se pudo calcular el muro.');
        });
    }, 200);
    return () => clearTimeout(espera);
  }, [clave, peticion, mutateAsync]);

  // Al activar «a mano», corona y base arrancan con lo que dio el Cuadro 1.
  function alternarManual(valor: boolean) {
    setManual(valor);
    if (valor && calculo) {
      setCorona(String(Math.round(calculo.seccion.corona_m * 100)));
      setBase(String(Math.round(calculo.seccion.base_m * 100)));
    }
  }

  const d = definicion.data;
  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando el elemento…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;

  const v = calculo?.volumen;
  const dren = calculo?.dren;
  const sinPrecio = (calculo?.insumos_por_m3 ?? []).filter((i) => i.provisional && i.cantidad > 0);

  return (
    <article className="mct" aria-label={`${d.clave} ${d.nombre}`}>
      <header className="mct__cabecera">
        <div>
          <h2 className="mct__titulo">
            <span className="mono">{d.clave}</span> · {d.nombre}
          </h2>
          <div className="text-mute text-xs">
            {d.categoria.nombre} › {d.subcategoria.nombre} · se mide por {d.se_mide_por}
          </div>
        </div>
        <span className="badge badge--outline" title="Calculado por el servidor">
          {d.concepto.clave} · {d.concepto.unidad === 'm3' ? 'm³' : d.concepto.unidad}
        </span>
      </header>

      <section className="mct__parametros" aria-label="Parámetros del muro">
        <label className="mct__campo">
          <span>Altura (m)</span>
          <input
            className="input"
            inputMode="decimal"
            aria-label="Altura del muro en metros"
            value={alto}
            onChange={(e) => setAlto(e.target.value)}
          />
        </label>
        <label className="mct__campo">
          <span>Dentellón (desde 2.00 m)</span>
          <select className="select" aria-label="Dentellón" value={dentellon ? 'si' : 'no'} onChange={(e) => setDentellon(e.target.value === 'si')}>
            <option value="si">Sí (b2 0.40, b1 0.30, h 0.60)</option>
            <option value="no">No</option>
          </select>
        </label>
        <label className="mct__campo">
          <span>Relleno del lado de</span>
          <select className="select" aria-label="Relleno" value={relleno} onChange={(e) => setRelleno(e.target.value as 'vertical' | 'inclinada')}>
            <option value="vertical">Cara vertical (trasdós)</option>
            <option value="inclinada">Cara inclinada (escarpio)</option>
          </select>
        </label>
        <label className="mct__campo">
          <span>Lluvia</span>
          <select className="select" aria-label="Lluvia" value={lluvia} onChange={(e) => setLluvia(e.target.value as 'baja' | 'alta')}>
            <option value="baja">Baja: lloraderos cada 3.00 m</option>
            <option value="alta">Alta: cada 1.50 m</option>
          </select>
        </label>
        <label className="mct__campo">
          <span>Tubo de 3&quot;</span>
          <select className="select" aria-label="Tubo del lloradero" value={tubo} onChange={(e) => setTubo(e.target.value as 'pvc' | 'concreto')}>
            <option value="pvc">PVC (pieza de 6.00 m)</option>
            <option value="concreto">Concreto (pieza de 1.00 m)</option>
          </select>
        </label>
        <label className="mct__campo">
          <span>Filtro de grava (cm)</span>
          <input
            className="input"
            inputMode="decimal"
            aria-label="Espesor del filtro de grava en centímetros"
            placeholder="por definir"
            value={filtro}
            onChange={(e) => setFiltro(e.target.value)}
          />
        </label>
        <div className="mct__campo mct__campo--manual">
          <label className="mct__manual">
            <input type="checkbox" checked={manual} onChange={(e) => alternarManual(e.target.checked)} /> Ajustar corona y base a mano
          </label>
          {manual && (
            <div className="mct__par">
              <input className="input" inputMode="decimal" aria-label="Corona en centímetros" value={corona} onChange={(e) => setCorona(e.target.value)} />
              <input className="input" inputMode="decimal" aria-label="Base en centímetros" value={base} onChange={(e) => setBase(e.target.value)} />
              <span className="text-mute text-xs">cm · cm</span>
            </div>
          )}
        </div>
      </section>

      {peticion === null && <p className="text-sm mct__aviso">La altura se captura en metros y debe ser mayor que cero.</p>}
      {error && (
        <p className="text-sm mct__error" role="alert">
          {error}
        </p>
      )}

      {calculo && v && dren && (
        <>
          <section className="mct__resumen" aria-label="Resultado">
            <span className="chip" data-testid="mct-seccion">
              Corona {num(calculo.seccion.corona_m)} m · base {num(calculo.seccion.base_m)} m
              {calculo.seccion.manual ? ' (a mano)' : ` (Cuadro 1, fila de ${num(calculo.seccion.fila_cuadro_1.H)} m)`}
            </span>
            <span className="chip">Muro {num(v.muro_m3_ml, 3)} m³</span>
            <span className="chip">
              {calculo.dentellon.aplica ? `+ dentellón ${num(v.dentellon_m3_ml)} m³` : 'Sin dentellón'}
            </span>
            <span className="chip chip--fuerte" data-testid="mct-total">
              <b>{num(v.total_m3_ml, 3)} m³ por metro de trazo</b>
            </span>
            <span className="chip">Piedra a comprar {num(v.piedra_a_comprar_m3_ml)} m³</span>
          </section>

          {dren.aplica ? (
            <section className="mct__bloque" aria-label="Dren">
              <h3>Dren (va dentro del concepto {calculo.concepto.clave})</h3>
              <div className="mct__resumen">
                <span className="chip">
                  {dren.hileras} hilera{dren.hileras > 1 ? 's' : ''} de lloraderos: a 0.50 m y cada 1.00 m
                </span>
                <span className="chip">{num(dren.lloraderos_por_ml)} lloraderos por metro</span>
                <span className="chip">
                  Tubo de 3&quot;: {num(dren.tubo.ml_por_ml_de_trazo)} ml por metro de trazo
                </span>
                <span className="chip" data-testid="mct-tubo-piezas">
                  <b>
                    {num(dren.tubo.piezas_por_ml_de_trazo, 3)} pza de {num(dren.tubo.largo_pieza_m)} m por metro de trazo
                  </b>
                </span>
                <span className="chip">
                  {dren.tubo.lloraderos_por_pieza > 0
                    ? `${dren.tubo.lloraderos_por_pieza} lloradero${dren.tubo.lloraderos_por_pieza > 1 ? 's' : ''} por pieza`
                    : `${num(dren.tubo.piezas_por_lloradero, 0)} piezas por lloradero`}
                </span>
                <span className="chip">Corona: carpeta de 3 cm</span>
              </div>
            </section>
          ) : (
            <p className="text-mute text-xs">Con menos de 2.00 m de altura el manual no pide drenes.</p>
          )}

          <section className="mct__bloque" aria-label="Lo que el dren suma al concepto">
            <h3>
              Lo que se suma al APU de {calculo.concepto.clave} <span className="text-mute">(por m³ de muro)</span>
            </h3>
            <table className="mct__tabla">
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th className="n">Cantidad</th>
                  <th>Unidad</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {calculo.insumos_por_m3.map((i) => (
                  <tr key={i.clave}>
                    <td>
                      <span className="mono">{i.clave}</span> {i.descripcion}
                      <div className="text-mute text-xs">{i.detalle}</div>
                    </td>
                    <td className="n mono">{num(i.cantidad, 4)}</td>
                    <td>{i.unidad === 'm3' ? 'm³' : i.unidad}</td>
                    <td>{i.provisional ? <span className="badge badge--warn">Provisional, sin precio</span> : <span className="badge badge--ok">Catálogo</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {sinPrecio.length > 0 && (
              <p className="text-xs mct__aviso" data-testid="mct-sin-precio">
                El precio unitario no incluye {sinPrecio.map((i) => i.clave).join(', ')} porque aún no tienen precio: Costos los asigna.
              </p>
            )}
          </section>

          {calculo.advertencias.length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias">
              {calculo.advertencias.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}

          <section className="mct__bloque" aria-label="Vistas">
            <h3>Vistas, corte, dentellón y dren</h3>
            <VistasDelMuro calculo={calculo} definicion={d} />
          </section>
        </>
      )}

      <details className="mct__bloque">
        <summary>Cuadro 1 del manual (volumetría de 1 m lineal)</summary>
        <div className="mct__tabla-caja">
          <table className="mct__tabla">
            <thead>
              <tr>
                <th className="n">H (m)</th>
                <th className="n">Base</th>
                <th className="n">Corona</th>
                <th className="n">Muro (m³)</th>
                <th className="n">Piedra (m³)</th>
                <th className="n">Cemento (kg)</th>
                <th className="n">Arena (m³)</th>
                <th className="n">Agua (l)</th>
              </tr>
            </thead>
            <tbody>
              {d.cuadro_1.map((f) => (
                <tr key={f.H} className={calculo && f.H === calculo.seccion.fila_cuadro_1.H ? 'is-fila' : undefined}>
                  <td className="n">{num(f.H)}</td>
                  <td className="n">{num(f.B)}</td>
                  <td className="n">{num(f.B1)}</td>
                  <td className="n">{num(f.Vm)}</td>
                  <td className="n">{num(f.piedra)}</td>
                  <td className="n">{num(f.cemento_kg)}</td>
                  <td className="n">{num(f.arena_m3)}</td>
                  <td className="n">{num(f.agua_l)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-mute text-xs">{d.fuente}</p>
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
