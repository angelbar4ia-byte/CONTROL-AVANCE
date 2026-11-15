/**
 * El trazo con pendiente de un muro de piedra (Q38): largo en planta, altura en el primer punto y pendiente del terreno.
 * La corona va a nivel constante, así que la altura sigue el terreno. **No calcula nada**: manda los datos a
 * `/biblioteca-de-elementos/{clave}/calcular-trazo` y dibuja el perfil que responde.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useCalcularElTrazoApiV1BibliotecaDeElementosClaveCalcularTrazoPost } from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';
import type { CalculoDelTrazo } from '@/api/generado/modelo';

import { numeroTecleado } from '../volumen';

function num(n: number, dec = 2): string {
  return n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

interface Props {
  readonly clave: string;
  /** Los parámetros del muro (sin la altura): los mismos de su cálculo por metro. */
  readonly parametros: Record<string, unknown>;
}

function Perfil({ t }: { readonly t: CalculoDelTrazo }) {
  const W = 360;
  const H = 110;
  const hmax = Math.max(t.altura_maxima_m, 0.5);
  const x = (s: number) => 10 + (s / t.longitud_m) * (W - 20);
  const y = (h: number) => H - 8 - (h / hmax) * (H - 28);
  const puntos = t.perfil.map((p) => `${x(p.s_m).toFixed(1)},${y(p.altura_m).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Alzado del muro sobre el trazo con pendiente">
      <polygon
        points={`10,${H - 8} ${puntos} ${W - 10},${H - 8}`}
        fill="var(--c-elev)"
        stroke="var(--c-text)"
        strokeWidth={1}
      />
      <text x={12} y={12} fontSize={10} fill="var(--c-text)">
        {num(t.altura_inicial_m)} m
      </text>
      <text x={W - 12} y={12} textAnchor="end" fontSize={10} fill="var(--c-text)">
        {num(t.altura_final_m)} m
      </text>
    </svg>
  );
}

export function TrazoDelMuro({ clave, parametros }: Props) {
  const calcular = useCalcularElTrazoApiV1BibliotecaDeElementosClaveCalcularTrazoPost<ErrorApi>();
  const [longitud, setLongitud] = useState('10.00');
  const [altura, setAltura] = useState('2.00');
  const [pendiente, setPendiente] = useState('0');
  const [trazo, setTrazo] = useState<CalculoDelTrazo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const turno = useRef(0);

  const clavesDeParametros = JSON.stringify(parametros);
  const peticion = useMemo(() => {
    const l = numeroTecleado(longitud);
    const h = numeroTecleado(altura);
    const p = pendiente.trim() === '' || pendiente.trim() === '-' ? 0 : numeroTecleado(pendiente);
    if (!(l > 0) || !(h > 0) || !Number.isFinite(p)) return null;
    return {
      longitud_m: l,
      altura_inicial_m: h,
      pendiente_pct: p,
      parametros: JSON.parse(clavesDeParametros) as Record<string, unknown>,
    };
  }, [longitud, altura, pendiente, clavesDeParametros]);

  const { mutateAsync } = calcular;
  useEffect(() => {
    if (peticion === null) return;
    const mio = ++turno.current;
    const espera = setTimeout(() => {
      mutateAsync({ clave, data: peticion })
        .then((r) => {
          if (mio !== turno.current) return;
          setTrazo(r);
          setError(null);
        })
        .catch((e: unknown) => {
          if (mio !== turno.current) return;
          setError(e instanceof Error ? e.message : 'No se pudo calcular el trazo.');
        });
    }, 250);
    return () => clearTimeout(espera);
  }, [clave, peticion, mutateAsync]);

  return (
    <section className="mct__bloque" aria-label="Trazo con pendiente">
      <h3>Trazo con pendiente</h3>
      <p className="text-mute text-xs">
        La altura inicial es la del primer punto del trazo; la corona va a nivel constante, así que la altura sigue el
        terreno (pendiente positiva: el muro crece hacia el final).
      </p>
      <div className="mct__parametros">
        <label className="mct__campo">
          <span>Largo del trazo (m)</span>
          <input className="input" inputMode="decimal" aria-label="Largo del trazo en metros" value={longitud} onChange={(e) => setLongitud(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Altura inicial (m)</span>
          <input className="input" inputMode="decimal" aria-label="Altura inicial del trazo en metros" value={altura} onChange={(e) => setAltura(e.target.value)} />
        </label>
        <label className="mct__campo">
          <span>Pendiente del terreno (%)</span>
          <input className="input" inputMode="decimal" aria-label="Pendiente del terreno en por ciento" value={pendiente} onChange={(e) => setPendiente(e.target.value)} />
        </label>
      </div>
      {peticion === null && <p className="text-sm mct__aviso">El largo y la altura inicial deben ser mayores que cero.</p>}
      {error && (
        <p className="text-sm mct__error" role="alert">
          {error}
        </p>
      )}
      {trazo && (
        <>
          <div className="mct__resumen">
            <span className="chip" data-testid="trazo-alturas">
              Altura de {num(trazo.altura_inicial_m)} m a {num(trazo.altura_final_m)} m
            </span>
            <span className="chip">Largo real {num(trazo.longitud_real_m)} m</span>
            <span className="chip" data-testid="trazo-total">
              <b>{num(trazo.volumen.total_m3, 3)} m³ en el trazo</b>
            </span>
            {trazo.volumen.dentellon_m3 > 0 && <span className="chip">con dentellón {num(trazo.volumen.dentellon_m3, 3)} m³</span>}
          </div>
          <Perfil t={trazo} />
          {trazo.advertencias.length > 0 && (
            <ul className="mct__advertencias" aria-label="Advertencias del trazo">
              {trazo.advertencias.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
