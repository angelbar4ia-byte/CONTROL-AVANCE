/**
 * La tarjeta del muro de cimentación de piedra (CIM-01010). Igual que la del muro de contención: los parámetros arriba y
 * lo que sale abajo. **No calcula nada**: cada cambio se manda a `/biblioteca-de-elementos/CIM-01010/calcular` y se muestra
 * lo que responde (sección por el escarpio 1.5 : 1, volumen y contraste con el concepto MCT-01011 del catálogo).
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCalcularCimientoApiV1BibliotecaDeElementosCIM01010CalcularPost,
  useDefinicionDelElementoApiV1BibliotecaDeElementosClaveGet,
} from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { CalculoDelCimiento, CalculoDelCimientoPeticion } from '@/api/generado/modelo';

import { numeroTecleado } from '../volumen';
import { TrazoDelMuro } from './TrazoDelMuro';

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

const MARCAS: Record<string, string> = { '=': '=', '≈': '≈', '≠': '≠', solo_catalogo: 'solo catálogo', solo_elemento: 'solo elemento' };

/** Corte transversal: trasdós vertical (cuando es de una cara), cara vista inclinada y el dentellón bajo el suelo. */
function CorteDelCimiento({ c }: { readonly c: CalculoDelCimiento }) {
  const { alto_m: H, corona_m: B1, base_m: B, caras } = c.seccion;
  const den = c.dentellon.aplica;
  const k = Math.min(240 / (B + 0.4), 150 / (H + (den ? c.dentellon.h_m : 0) + 0.3));
  const Mx = 40;
  const My = 24;
  const gy = My + H * k;
  const off = caras === 2 ? ((B - B1) / 2) * k : 0;
  const x0 = Mx;
  const pts = `${x0 + off},${My} ${x0 + off + B1 * k},${My} ${x0 + B * k},${gy} ${x0},${gy}`;
  const dh = den ? c.dentellon.h_m * k : 0;
  return (
    <svg viewBox={`0 0 ${(Mx + B * k + Mx).toFixed(0)} ${(gy + dh + 34).toFixed(0)}`} width="100%" role="img" aria-label="Corte transversal del muro de cimentación">
      <polygon points={pts} fill="var(--c-elev)" stroke="var(--c-text)" strokeWidth={1} />
      {den && (
        <polygon
          points={`${x0},${gy} ${x0 + c.dentellon.b2_m * k},${gy} ${x0 + c.dentellon.b1_m * k},${gy + dh} ${x0},${gy + dh}`}
          fill="var(--c-elev)"
          stroke="var(--c-text)"
          strokeDasharray="3 2"
        />
      )}
      <text x={x0 + off + (B1 * k) / 2} y={My - 6} textAnchor="middle" fontSize={10} fill="var(--c-text)">
        corona {num(B1 * 100, 0)} cm
      </text>
      <text x={x0 + (B * k) / 2} y={gy + dh + 18} textAnchor="middle" fontSize={10} fill="var(--c-text)">
        base {num(B * 100, 0)} cm
      </text>
      <text x={x0 + (B * k) / 2 + 6} y={My + (H * k) / 2} fontSize={9} fill="var(--c-accent)">
        escarpio {num(c.escarpio.minimo, 1)} : 1
      </text>
    </svg>
  );
}

export function TarjetaMuroCimentacion({ clave }: { readonly clave: string }) {
  const definicion = useDefinicionDelElementoApiV1BibliotecaDeElementosClaveGet(clave);
  const calcular = useCalcularCimientoApiV1BibliotecaDeElementosCIM01010CalcularPost<ErrorApi>();
  const [alto, setAlto] = useState('1.00');
  const [caras, setCaras] = useState<1 | 2>(1);
  const [dentellon, setDentellon] = useState(false);
  const [manual, setManual] = useState(false);
  const [corona, setCorona] = useState('');
  const [base, setBase] = useState('');
  const [calculo, setCalculo] = useState<CalculoDelCimiento | null>(null);
  const [error, setError] = useState<string | null>(null);
  const turno = useRef(0);

  const peticion = useMemo<CalculoDelCimientoPeticion | null>(() => {
    const h = numeroTecleado(alto);
    if (!(h > 0)) return null;
    const c = manual ? numeroTecleado(corona) / 100 : 0;
    const b = manual ? numeroTecleado(base) / 100 : 0;
    return { alto_m: h, caras, dentellon, corona_m: c > 0 ? c : undefined, base_m: b > 0 ? b : undefined };
  }, [alto, caras, dentellon, manual, corona, base]);

  const { mutateAsync } = calcular;
  useEffect(() => {
    if (peticion === null) return;
    const mio = ++turno.current;
    const espera = setTimeout(() => {
      mutateAsync({ data: peticion })
        .then((r) => {
          if (mio !== turno.current) return;
          setCalculo(r);
          setError(null);
        })
        .catch((e: unknown) => {
          if (mio !== turno.current) return;
          setError(e instanceof Error ? e.message : 'No se pudo calcular el muro de cimentación.');
        });
    }, 200);
    return () => clearTimeout(espera);
  }, [peticion, mutateAsync]);

  function alternarManual(valor: boolean) {
    setManual(valor);
    if (valor && calculo) {
      setCorona(String(Math.round(calculo.seccion.corona_m * 100)));
      setBase(String(Math.round(calculo.seccion.base_m * 100)));
    }
  }

  const parametrosDelTrazo = useMemo(() => ({ caras, dentellon }), [caras, dentellon]);

  const d = definicion.data;
  if (definicion.isLoading) return <p className="text-mute text-sm">Cargando el elemento…</p>;
  if (!d) return <p className="text-sm">No se pudo cargar el elemento {clave}.</p>;
  const v = calculo?.volumen;

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
          {d.concepto.clave} · m³
        </span>
      </header>

      <section className="mct__parametros" aria-label="Parámetros del muro de cimentación">
        <label className="mct__campo">
          <span>Altura (m)</span>
          <input className="input" inputMode="decimal" aria-label="Altura del muro en metros" value={alto} onChange={(e) => setAlto(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Caras inclinadas</span>
          <select className="select" aria-label="Caras inclinadas" value={String(caras)} onChange={(e) => setCaras(e.target.value === '2' ? 2 : 1)}>
            <option value="1">1 (lindero: trasdós vertical)</option>
            <option value="2">2 (simétrico)</option>
          </select>
        </label>
        <label className="mct__campo">
          <span>Dentellón (desde 2.00 m)</span>
          <select className="select" aria-label="Dentellón" value={dentellon ? 'si' : 'no'} onChange={(e) => setDentellon(e.target.value === 'si')}>
            <option value="no">No</option>
            <option value="si">Sí (b2 0.40, b1 0.30, h 0.60)</option>
          </select>
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

      {calculo && v && (
        <>
          <section className="mct__resumen" aria-label="Resultado">
            <span className="chip" data-testid="cim-seccion">
              Corona {num(calculo.seccion.corona_m)} m · base {num(calculo.seccion.base_m)} m
              {calculo.seccion.manual ? ' (a mano)' : ` (escarpio ${num(calculo.escarpio.minimo, 1)} : 1)`}
            </span>
            <span className="chip">Muro {num(v.muro_m3_ml, 3)} m³</span>
            <span className="chip">{calculo.dentellon.aplica ? `+ dentellón ${num(v.dentellon_m3_ml)} m³` : 'Sin dentellón'}</span>
            <span className="chip" data-testid="cim-total">
              <b>{num(v.total_m3_ml, 3)} m³ por metro de trazo</b>
            </span>
            <span className="chip">Piedra a comprar {num(v.piedra_a_comprar_m3_ml)} m³</span>
            <span className={calculo.escarpio.cumple ? 'badge badge--ok' : 'badge badge--warn'}>
              {calculo.escarpio.cumple ? 'Escarpio cumple la norma 8.4' : 'Escarpio más tendido que 1.5 : 1'}
            </span>
          </section>

          {calculo.advertencias.length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias">
              {calculo.advertencias.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}

          <section className="mct__bloque" aria-label="Corte">
            <h3>Corte transversal</h3>
            <CorteDelCimiento c={calculo} />
            <p className="text-mute text-xs">
              {calculo.seccion.caras === 1
                ? 'El trasdós (lado del relleno) es vertical y la cara vista es la inclinada.'
                : 'Las dos caras son inclinadas.'}{' '}
              {calculo.escarpio.angulo_real_grados !== null && calculo.escarpio.angulo_real_grados !== undefined
                ? `Ángulo de la cara: ${num(calculo.escarpio.angulo_real_grados, 1)}° (mínimo ${num(calculo.escarpio.angulo_minimo_grados, 1)}°).`
                : ''}
            </p>
          </section>

          <section className="mct__bloque" aria-label="No incluye" data-testid="cim-no-incluye">
            <h3>No incluye (se miden aparte)</h3>
            <ul>
              {calculo.no_incluye.map((x) => (
                <li key={x.clave}>{x.texto}</li>
              ))}
            </ul>
          </section>

          <section className="mct__bloque" aria-label="Contraste con el catálogo">
            <h3>
              Contraste con el concepto {calculo.contraste.concepto} <span className="text-mute">(por m³ de muro)</span>
            </h3>
            <table className="mct__tabla">
              <thead>
                <tr>
                  <th>Insumo</th>
                  <th className="n">Catálogo</th>
                  <th className="n">Elemento</th>
                  <th>Marca</th>
                </tr>
              </thead>
              <tbody>
                {calculo.contraste.filas.map((f) => (
                  <tr key={f.clave} data-testid={`contraste-${f.clave}`}>
                    <td>
                      <span className="mono">{f.clave}</span> {f.descripcion}
                      <span className="text-mute text-xs"> ({f.unidad})</span>
                    </td>
                    <td className="n mono">{num(f.catalogo, 4)}</td>
                    <td className="n mono">{num(f.elemento, 4)}</td>
                    <td>
                      {MARCAS[f.marca] ?? f.marca}
                      {f.diferencia_pct !== null && f.diferencia_pct !== undefined ? ` (${num(f.diferencia_pct, 1)} %)` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="text-mute text-xs">
              La mano de obra no se compara:{' '}
              {calculo.contraste.mano_de_obra.map((m) => `${m.clave} ${m.descripcion} (${m.cantidad} ${m.unidad})`).join(', ')}. El catálogo no se
              edita: {calculo.contraste.version_propuesta.cambio} Es la versión {calculo.contraste.version_propuesta.version} del concepto,{' '}
              {calculo.contraste.version_propuesta.estado}.
            </p>
          </section>
        </>
      )}

      <TrazoDelMuro clave={clave} parametros={parametrosDelTrazo} />

      <section className="mct__bloque mct__pendientes" aria-label="Pendientes por confirmar">
        <h3>Pendientes por confirmar</h3>
        <ul>
          {d.pendientes.map((p) => (
            <li key={p.clave}>
              <span className="badge badge--outline">{p.clave}</span> {p.texto}
            </li>
          ))}
        </ul>
        <p className="text-mute text-xs">{d.fuente}</p>
      </section>
    </article>
  );
}
