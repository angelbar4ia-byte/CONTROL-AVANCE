/**
 * Las vistas del muro de contención de piedra: planta, fachada con drenes y cotas, corte transversal y detalle del
 * dentellón. Solo dibujan lo que calculó el servidor (`CalculoDelMuro`): no recalculan nada.
 */

import type { ReactNode } from 'react';

import type { CalculoDelMuro, DefinicionDelElemento } from '@/api/generado/modelo';

const FG = 'var(--c-text)';
const MUT = 'var(--c-text-mute)';
const ACC = 'var(--c-accent)';
const CONC = 'var(--c-elev)';
const SOFT = 'var(--c-panel)';

const m2 = (n: number) => n.toFixed(2);

/** Una cota: línea con puntos en los extremos y su texto. */
function Cota({
  x1,
  y1,
  x2,
  y2,
  texto,
  tx,
  ty,
  ancla = 'middle',
  girar = false,
  tam = 9,
}: {
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
  readonly texto: string;
  readonly tx: number;
  readonly ty: number;
  readonly ancla?: 'start' | 'middle' | 'end';
  readonly girar?: boolean;
  readonly tam?: number;
}) {
  return (
    <g>
      <line x1={x1} y1={y1} x2={x2} y2={y2} stroke={MUT} strokeWidth={0.8} />
      <circle cx={x1} cy={y1} r={1.5} fill={MUT} />
      <circle cx={x2} cy={y2} r={1.5} fill={MUT} />
      <text
        x={tx}
        y={ty}
        textAnchor={ancla}
        fontSize={tam}
        fill={FG}
        transform={girar ? `rotate(-90 ${tx} ${ty})` : undefined}
      >
        {texto}
      </text>
    </g>
  );
}

interface Props {
  readonly calculo: CalculoDelMuro;
  readonly definicion: DefinicionDelElemento;
}

/** Corte transversal: corona, base, altura, nivel del suelo, relleno y filtro, y el dentellón bajo el suelo. */
export function CorteDelMuro({ calculo, definicion }: Props) {
  const { alto_m: H, corona_m: B1, base_m: B } = calculo.seccion;
  const den = calculo.dentellon.aplica;
  const D = definicion.dentellon;
  const inclinada = calculo.dren.filtro.relleno === 'inclinada';
  const filtro = calculo.dren.aplica ? (calculo.dren.filtro.espesor_cm ?? null) : null;
  const k = Math.min(260 / (B + 1.4), 190 / (H + (den ? D.h : 0) + 0.6));
  const Mx = 70;
  const My = 34;
  const x0 = Mx + 0.5 * k;
  const gy = My + H * k;
  const W = Mx + (B + 2.7) * k;
  const xTop0 = x0;
  const xTop1 = xTop0 + B1 * k;
  const xB1 = x0 + B * k;
  const grosor = (filtro ? filtro / 100 : 0.25) * k;
  const yb = gy + (den ? D.h * k : 0) + 14;
  return (
    <svg
      viewBox={`0 0 ${W.toFixed(0)} ${(gy + (den ? D.h * k : 0) + 58).toFixed(0)}`}
      width="100%"
      role="img"
      aria-label="Corte transversal del muro de piedra"
    >
      <rect x={Mx - 8} y={gy} width={W - Mx} height={(den ? D.h * k : 0) + 22} fill={SOFT} opacity={0.7} />
      {inclinada && (
        <>
          <polygon
            points={`${xTop1},${My} ${xB1},${gy} ${W - 14},${gy} ${W - 14},${My}`}
            fill={SOFT}
            stroke={MUT}
            strokeDasharray="3 2"
          />
          <polygon
            points={`${xTop1},${My} ${xB1},${gy} ${xB1 + grosor},${gy} ${xTop1 + grosor},${My}`}
            fill="none"
            stroke={MUT}
            strokeDasharray={filtro ? '0' : '3 2'}
          />
          <text x={(xB1 + W - 14) / 2} y={My + (H * k) / 2} textAnchor="middle" fontSize={9} fill={MUT}>
            relleno
          </text>
        </>
      )}
      <line x1={Mx - 14} y1={gy} x2={W - 6} y2={gy} stroke={FG} strokeDasharray="6 3" />
      <text x={W - 8} y={gy + 11} textAnchor="end" fontSize={8} fill={FG}>
        nivel del suelo
      </text>
      <polygon
        points={`${xTop0},${My} ${xTop1},${My} ${xB1},${gy} ${x0},${gy}`}
        fill={CONC}
        stroke={FG}
        strokeWidth={1.2}
      />
      <rect x={xTop0} y={My - 3} width={B1 * k} height={3} fill={FG} />
      {den && (
        <>
          <polygon
            points={`${x0},${gy} ${x0 + D.b2 * k},${gy} ${x0 + D.b1 * k},${gy + D.h * k} ${x0},${gy + D.h * k}`}
            fill={CONC}
            stroke={FG}
            strokeWidth={1.2}
            strokeDasharray="4 2"
          />
          <text x={x0 + D.b2 * k + 6} y={gy + (D.h * k) / 2 + 3} fontSize={8} fill={FG}>
            dentellón
          </text>
        </>
      )}
      <text x={x0 - 6} y={My + (H * k) / 2} textAnchor="end" fontSize={8} fill={MUT}>
        {inclinada ? 'cara vertical (vista)' : 'relleno'}
      </text>
      <Cota x1={xTop0} y1={My - 12} x2={xTop1} y2={My - 12} texto={`corona ${m2(B1)} m`} tx={(xTop0 + xTop1) / 2} ty={My - 16} />
      {inclinada ? (
        <Cota x1={x0 - 16} y1={My} x2={x0 - 16} y2={gy} texto={`H ${m2(H)} m`} tx={x0 - 20} ty={(My + gy) / 2} girar />
      ) : (
        <Cota x1={xB1 + 16} y1={My} x2={xB1 + 16} y2={gy} texto={`H ${m2(H)} m`} tx={xB1 + 28} ty={(My + gy) / 2} girar />
      )}
      <Cota x1={x0} y1={yb} x2={xB1} y2={yb} texto={`base ${m2(B)} m`} tx={(x0 + xB1) / 2} ty={yb + 11} />
      {den && (
        <Cota
          x1={x0 - 14}
          y1={gy}
          x2={x0 - 14}
          y2={gy + D.h * k}
          texto={`h ${m2(D.h)} m`}
          tx={x0 - 18}
          ty={gy + (D.h * k) / 2 + 3}
          ancla="end"
        />
      )}
    </svg>
  );
}

/** Detalle del dentellón: b2 en la unión con la base, b1 abajo y h de profundidad. */
export function DetalleDelDentellon({ definicion }: { readonly definicion: DefinicionDelElemento }) {
  const D = definicion.dentellon;
  const k = 170;
  const Mx = 60;
  const My = 44;
  const W = Mx + (D.b2 + 0.5) * k + Mx;
  const Hh = My + (D.h + 0.28) * k + 36;
  const x0 = Mx + 0.2 * k;
  const gy = My + 0.2 * k;
  return (
    <svg viewBox={`0 0 ${W.toFixed(0)} ${Hh.toFixed(0)}`} width="100%" role="img" aria-label="Detalle del dentellón">
      <rect x={Mx - 14} y={My} width={W - Mx * 2 + 28} height={0.2 * k} fill={CONC} opacity={0.5} stroke={FG} strokeDasharray="4 2" />
      <text x={Mx + (W - Mx * 2) / 2} y={My + (0.2 * k) / 2 + 3} textAnchor="middle" fontSize={8} fill={FG}>
        base del muro
      </text>
      <line x1={Mx - 14} y1={gy} x2={W - Mx + 14} y2={gy} stroke={FG} strokeDasharray="6 3" />
      <text x={W - Mx + 14} y={gy - 3} textAnchor="end" fontSize={8} fill={FG}>
        nivel del suelo
      </text>
      <polygon
        points={`${x0},${gy} ${x0 + D.b2 * k},${gy} ${x0 + D.b1 * k},${gy + D.h * k} ${x0},${gy + D.h * k}`}
        fill={CONC}
        stroke={FG}
        strokeWidth={1.4}
      />
      <Cota x1={x0} y1={My - 12} x2={x0 + D.b2 * k} y2={My - 12} texto={`b2 ${m2(D.b2)} m`} tx={x0 + (D.b2 * k) / 2} ty={My - 17} tam={10} />
      <Cota x1={x0} y1={gy + D.h * k + 14} x2={x0 + D.b1 * k} y2={gy + D.h * k + 14} texto={`b1 ${m2(D.b1)} m`} tx={x0 + (D.b1 * k) / 2} ty={gy + D.h * k + 27} tam={10} />
      <Cota x1={x0 - 14} y1={gy} x2={x0 - 14} y2={gy + D.h * k} texto={`h ${m2(D.h)} m`} tx={x0 - 19} ty={gy + (D.h * k) / 2} girar tam={10} />
    </svg>
  );
}

/** Fachada del tramo: lloraderos al tresbolillo con las cotas de alturas, separación, desfase y margen. */
export function FachadaDelMuro({ calculo }: { readonly calculo: CalculoDelMuro }) {
  const { alto_m: H } = calculo.seccion;
  const L = calculo.vistas.tramo_m;
  const hileras = calculo.vistas.hileras;
  const lin = hileras.length;
  const sep = calculo.dren.separacion_m;
  const kh = Math.min(60, 100 / Math.max(H, 0.5), 360 / L);
  const Mx = 62;
  const MxR = 64;
  const W = L * kh;
  const Hf = H * kh;
  const My = 18;
  const SH = Hf + My + 62;
  const baseY = My + Hf;
  const r = Math.max(2.4, 0.038 * kh);
  const cx = Mx - 12;
  const marcas: ReactNode[] = [];
  for (let hh = 0.5; hh < H - 1e-9; hh += 0.5) {
    marcas.push(
      <line key={hh} x1={Mx} y1={baseY - hh * kh} x2={Mx + W} y2={baseY - hh * kh} stroke="var(--c-surface)" strokeWidth={0.5} opacity={0.55} />,
    );
  }
  const alturas = [0, ...hileras.map((h) => h.altura_m), H];
  const d0 = hileras[0]?.x_m ?? [];
  const d1 = hileras[1]?.x_m ?? [];
  const yc = baseY + 12;
  const a0 = d0[0];
  const a1 = d0[1];
  const b0 = d1[0];
  return (
    <svg
      viewBox={`0 0 ${W + Mx + MxR} ${SH}`}
      width="100%"
      role="img"
      aria-label="Fachada del muro de piedra con los lloraderos y sus cotas"
    >
      <rect x={Mx} y={My} width={W} height={Hf} fill={CONC} stroke={FG} />
      <rect x={Mx} y={My - 3} width={W} height={3} fill={FG} />
      {marcas}
      {hileras.map((h) =>
        h.x_m.map((x) => (
          <circle
            key={`${h.altura_m}-${x}`}
            cx={Mx + x * kh}
            cy={baseY - h.altura_m * kh}
            r={r}
            fill="var(--c-surface)"
            stroke={ACC}
            strokeWidth={1.6}
          />
        )),
      )}
      <text x={Mx - 50} y={My + Hf / 2} textAnchor="middle" fontSize={9} fill={FG} transform={`rotate(-90 ${Mx - 50} ${My + Hf / 2})`}>
        H {m2(H)} m
      </text>
      {lin > 0 ? (
        <>
          {alturas.slice(0, -1).map((a, q) => {
            const sig = alturas[q + 1] ?? a;
            const ya = baseY - a * kh;
            const yb = baseY - sig * kh;
            return <Cota key={q} x1={cx} y1={ya} x2={cx} y2={yb} texto={m2(sig - a)} tx={cx - 3} ty={(ya + yb) / 2 + 3} ancla="end" tam={8} />;
          })}
          {a0 !== undefined && a1 !== undefined && (
            <Cota
              x1={Mx + a0 * kh}
              y1={yc}
              x2={Mx + a1 * kh}
              y2={yc}
              texto={`${m2(sep)} m entre lloraderos de la misma hilera`}
              tx={Mx + ((a0 + a1) / 2) * kh}
              ty={yc + 10}
              tam={8}
            />
          )}
          {a0 !== undefined && (
            <Cota x1={Mx} y1={yc + 22} x2={Mx + a0 * kh} y2={yc + 22} texto={m2(sep / 4)} tx={Mx + (a0 * kh) / 2} ty={yc + 31} tam={8} />
          )}
          {lin > 1 && a0 !== undefined && b0 !== undefined && (
            <Cota
              x1={Mx + a0 * kh}
              y1={baseY - kh + r + 7}
              x2={Mx + b0 * kh}
              y2={baseY - kh + r + 7}
              texto={m2(sep / 2)}
              tx={Mx + ((a0 + b0) / 2) * kh}
              ty={baseY - kh + r + 16}
              tam={8}
            />
          )}
          <text x={Mx + W + 6} y={baseY - 0.5 * kh + 3} fontSize={8} fill={ACC}>
            1.ª a 0.50
          </text>
          <text x={Mx + W / 2} y={SH - 3} textAnchor="middle" fontSize={9} fill={ACC}>
            {`lloraderos de 3" al tresbolillo · ${lin} hilera${lin > 1 ? 's' : ''}`}
          </text>
        </>
      ) : (
        <text x={Mx + W / 2} y={SH - 6} textAnchor="middle" fontSize={9} fill={FG}>
          sin dren (menos de 2.00 m de altura)
        </text>
      )}
    </svg>
  );
}

/** Planta del tramo: corona con su carpeta, la banda inclinada, el filtro de grava y los tubos que cruzan el muro. */
export function PlantaDelMuro({ calculo }: { readonly calculo: CalculoDelMuro }) {
  const { alto_m: H, corona_m: B1, base_m: B } = calculo.seccion;
  const L = calculo.vistas.tramo_m;
  const hileras = calculo.vistas.hileras;
  const inclinada = calculo.dren.filtro.relleno === 'inclinada';
  const filtroCm = calculo.dren.filtro.espesor_cm ?? null;
  const fil = filtroCm ? filtroCm / 100 : 0.3;
  const kh = Math.min(60, 100 / Math.max(H, 0.5), 360 / L);
  const kt = Math.min(kh, 100 / (B + fil + 0.3));
  const Mx = 62;
  const MxR = 64;
  const W = L * kh;
  const Mt = 18;
  const Pw = Mx + MxR + W;
  const y0 = Mt + (inclinada ? 0 : fil * kt) + 14;
  const Ph = y0 + B * kt + (inclinada ? fil * kt + 16 : 0) + 12;
  const yF = inclinada ? y0 + B * kt : y0 - fil * kt;
  return (
    <svg viewBox={`0 0 ${Pw} ${Ph}`} width="100%" role="img" aria-label="Planta del muro de piedra con los lloraderos">
      <rect x={Mx} y={yF} width={W} height={fil * kt} fill="none" stroke={MUT} strokeDasharray={filtroCm ? '0' : '3 2'} />
      <text x={Mx + W / 2} y={yF + (fil * kt) / 2 + 3} textAnchor="middle" fontSize={8} fill={MUT}>
        {`filtro de grava${filtroCm ? ` ${filtroCm} cm` : ' (espesor por definir)'}`}
      </text>
      <text x={Mx + W / 2} y={inclinada ? yF + fil * kt + 11 : y0 - fil * kt - 4} textAnchor="middle" fontSize={8} fill={MUT}>
        {inclinada ? 'relleno (sobre la cara inclinada)' : 'relleno (trasdós, cara vertical)'}
      </text>
      {inclinada && (
        <text x={Mx} y={y0 - 6} fontSize={8} fill={MUT}>
          cara vertical (vista)
        </text>
      )}
      <rect x={Mx} y={y0} width={W} height={B * kt} fill={CONC} opacity={0.55} stroke={FG} strokeDasharray="4 2" />
      <rect x={Mx} y={y0} width={W} height={B1 * kt} fill={CONC} stroke={FG} />
      <text x={Mx + W / 2} y={y0 + (B1 * kt) / 2 + 3} textAnchor="middle" fontSize={8} fill={FG}>
        {`corona ${Math.round(B1 * 100)} cm · carpeta 3 cm`}
      </text>
      {hileras.map((h, k3) => {
        const ye = y0 + (B1 + ((B - B1) * (H - h.altura_m)) / H) * kt;
        return h.x_m.map((x) => (
          <g key={`${h.altura_m}-${x}`}>
            <line x1={Mx + x * kh} y1={y0} x2={Mx + x * kh} y2={ye} stroke={ACC} strokeWidth={2.2} opacity={k3 % 2 ? 0.45 : 0.95} />
            <circle cx={Mx + x * kh} cy={ye} r={2.6} fill="var(--c-surface)" stroke={ACC} strokeWidth={1.3} />
          </g>
        ));
      })}
    </svg>
  );
}

/** Las cuatro vistas con su pie de explicación. */
export function VistasDelMuro({ calculo, definicion }: Props) {
  const lin = calculo.vistas.hileras.length;
  const L = calculo.vistas.tramo_m;
  const { alto_m: H, corona_m: B1, base_m: B } = calculo.seccion;
  const inclinada = calculo.dren.filtro.relleno === 'inclinada';
  return (
    <div className="mct-vistas">
      <figure>
        <PlantaDelMuro calculo={calculo} />
        <figcaption>
          Planta, tramo de {L} m: corona de {Math.round(B1 * 100)} cm con carpeta de 3 cm, cara inclinada hasta la base de{' '}
          {Math.round(B * 100)} cm
          {lin > 0
            ? `, tubos de 3" que cruzan el muro y ${inclinada ? 'filtro de grava sobre la cara inclinada (el relleno va de ese lado)' : 'filtro de grava detrás del paramento vertical'}. Las hileras alternas se desplazan 50 % (tresbolillo).`
            : '; sin dren.'}
        </figcaption>
      </figure>
      <figure>
        <FachadaDelMuro calculo={calculo} />
        <figcaption>
          {lin > 0
            ? `Fachada, tramo de ${L} m: ${lin} hilera${lin > 1 ? 's' : ''} de lloraderos de 3", la primera a 0.50 m del suelo y las demás cada 1.00 m, cada ${m2(calculo.dren.separacion_m)} m y desplazadas ${m2(calculo.dren.separacion_m / 2)} m una hilera de otra. Cotas en metros.`
            : `Fachada, tramo de ${L} m: sin dren (menos de 2.00 m de altura).`}
        </figcaption>
      </figure>
      <figure>
        <CorteDelMuro calculo={calculo} definicion={definicion} />
        <figcaption>
          Corte transversal: corona de {m2(B1)} m, base de {m2(B)} m y altura de {m2(H)} m.
          {inclinada ? ' El relleno va sobre la cara inclinada.' : ''}
          {calculo.dentellon.aplica ? ' El dentellón va por debajo del nivel del suelo.' : ' Sin dentellón.'}
        </figcaption>
      </figure>
      {calculo.dentellon.aplica && (
        <figure>
          <DetalleDelDentellon definicion={definicion} />
          <figcaption>
            Detalle del dentellón: b2 {m2(definicion.dentellon.b2)} m en la unión con la base, b1 {m2(definicion.dentellon.b1)} m abajo y{' '}
            {m2(definicion.dentellon.h)} m de profundidad; {m2(calculo.volumen.dentellon_m3_ml)} m³ por metro de muro, igual a su excavación. Va del
            nivel del suelo hacia abajo.
          </figcaption>
        </figure>
      )}
    </div>
  );
}
