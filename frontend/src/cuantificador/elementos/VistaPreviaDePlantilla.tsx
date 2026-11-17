/**
 * La vista previa de la plantilla de muro: la fachada de un tramo de 6 m a escala, con las partes de altura (y sus caras A y B), los
 * castillos y las cadenas de la plantilla. Solo dibuja lo que el borrador dice; las cantidades no se calculan aquí.
 */

import type { Geometria } from './plantillaDeMuro';

const ESCALA = 70; // px por metro
const MARGEN_IZQ = 64;
const MARGEN_SUP = 18;
const MARGEN_INF = 30;

const NOMBRE_DE_REGLA: Record<Geometria['castillos'][number]['regla'], string> = {
  separacion: 'cada separación y extremos',
  extremos: 'solo extremos',
  por_ml: 'por ml de muro',
  total: 'total del prototipo',
};
const NOMBRE_DE_CARA: Record<string, string> = { exterior: 'ext', interior: 'int', '': '—' };

export function VistaPreviaDePlantilla({ g, aparente }: { readonly g: Geometria; readonly aparente?: boolean }) {
  const ancho = MARGEN_IZQ + g.largo_m * ESCALA + 12;
  const alto = MARGEN_SUP + g.altura_m * ESCALA + MARGEN_INF;
  const y = (m: number) => MARGEN_SUP + (g.altura_m - m) * ESCALA; // el nivel 0 queda abajo
  const x = (m: number) => MARGEN_IZQ + m * ESCALA;
  return (
    <svg
      role="img"
      aria-label="Vista previa de la plantilla de muro"
      viewBox={`0 0 ${ancho} ${alto}`}
      width="100%"
      style={{ maxWidth: ancho * 1.4 }}
    >
      <rect x={x(0)} y={y(g.altura_m)} width={g.largo_m * ESCALA} height={g.altura_m * ESCALA} fill="var(--c-surface-2, #f1ece4)" stroke="var(--c-line)" />
      {g.partes.map((p, i) => (
        <g key={`${p.nombre}-${i}`}>
          <rect
            x={x(0)}
            y={y(p.hasta_m)}
            width={g.largo_m * ESCALA}
            height={(p.hasta_m - p.desde_m) * ESCALA}
            fill={i % 2 === 0 ? 'var(--c-accent-soft, #e8dcc8)' : 'transparent'}
            fillOpacity={0.55}
            stroke="var(--c-line-soft, #ccc)"
            strokeDasharray="3 3"
          />
          <text x={x(0) - 6} y={y((p.desde_m + p.hasta_m) / 2) + 3} textAnchor="end" fontSize="9" fill="var(--c-text-mute, #666)">
            {`A ${NOMBRE_DE_CARA[p.caraA] ?? p.caraA} · B ${NOMBRE_DE_CARA[p.caraB] ?? p.caraB}`}
          </text>
          <text x={x(g.largo_m) + 4} y={y(p.hasta_m) + 3} fontSize="9" fill="var(--c-text-mute, #666)">
            {`${p.hasta_m.toFixed(2)}`}
          </text>
        </g>
      ))}
      {g.cadenas.map((c) => (
        <rect
          key={c.uid}
          data-cadena={c.uid}
          x={x(0)}
          y={y(c.desde_m + c.alto_m)}
          width={g.largo_m * ESCALA}
          height={Math.max(c.alto_m * ESCALA, 3)}
          fill="var(--c-text, #444)"
          fillOpacity={0.7}
        >
          <title>{`${c.ref}: cadena`}</title>
        </rect>
      ))}
      {g.castillos.map((c, i) => (
        <rect
          key={`${c.uid}-${i}`}
          data-castillo={c.uid}
          data-regla={c.regla}
          x={x(c.x_m)}
          y={y(g.altura_m)}
          width={Math.max(c.ancho_m * ESCALA, 3)}
          height={g.altura_m * ESCALA}
          fill={c.estimado ? 'none' : 'var(--c-text, #444)'}
          fillOpacity={0.85}
          stroke="var(--c-text, #444)"
          strokeDasharray={c.estimado ? '3 2' : undefined}
        >
          <title>
            {c.estimado
              ? `Castillo estimado · ${NOMBRE_DE_REGLA[c.regla]}${c.regla === 'por_ml' || c.regla === 'total' ? ` · ${c.piezas} pza en el tramo` : ''}`
              : 'Castillo ubicado'}
          </title>
        </rect>
      ))}
      <line x1={x(0)} y1={y(0)} x2={x(g.largo_m)} y2={y(0)} stroke="var(--c-text, #444)" strokeWidth={1.5} />
      <text x={x(0)} y={y(0) + 14} fontSize="9" fill="var(--c-text-mute, #666)">
        0
      </text>
      <text x={x(g.largo_m)} y={y(0) + 14} fontSize="9" textAnchor="end" fill="var(--c-text-mute, #666)">
        {`${g.largo_m.toFixed(0)} m`}
      </text>
      {aparente && <text x={x(0)} y={y(g.altura_m) - 5} fontSize="9" fill="var(--c-text-mute, #666)">Tramo de muestra</text>}
    </svg>
  );
}
