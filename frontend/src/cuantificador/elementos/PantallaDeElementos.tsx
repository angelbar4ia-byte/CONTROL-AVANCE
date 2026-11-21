/**
 * El área de trabajo de la pestaña «Elementos»: solo la tarjeta del elemento elegido en la biblioteca (que vive en el
 * panel izquierdo): los muros de piedra MCT-01010 (contención) y CIM-01010 (cimentación) y los castillos, aparentes y columnas
 * forjadas, los muros de tabique con sus aparejos, el muro de sillar amarillo BAP-01010 y el piso de petatillo, y los elementos estructurales lineales (trabes,
 * contratrabes, nervaduras, zapata Z-1 y columna C-1), el bastón BA-1 (por longitud de trazo), la losa maciza y nervada (matriz de conceptos de una zona), el relleno de azotea y compactado (elementos separados de la losa) y la escalera forjada (sale de la diferencia de cotas de las zonas).
 */

import { useBibliotecaDeElementosApiV1BibliotecaDeElementosGet } from '@/api/generado/biblioteca-de-elementos/biblioteca-de-elementos';

import { TarjetaBaston } from './TarjetaBaston';
import { TarjetaElementoEstructural } from './TarjetaElementoEstructural';
import { TarjetaEstructura } from './TarjetaEstructura';
import { TarjetaLosa } from './TarjetaLosa';
import { TarjetaEscalera } from './TarjetaEscalera';
import { TarjetaRelleno } from './TarjetaRelleno';

import { TarjetaMuroCimentacion } from './TarjetaMuroCimentacion';
import { TarjetaMuroContencion } from './TarjetaMuroContencion';
import { TarjetaMuroSillar } from './TarjetaMuroSillar';
import { TarjetaMuroTabique } from './TarjetaMuroTabique';

const TIPO_DE_TABIQUE = 'tabique';
const TIPO_DE_SILLAR = 'sillar';
const TIPO_DE_BASTON = 'baston';
const TIPO_DE_LOSA = 'losa_de_concreto';
const TIPO_DE_RELLENO = 'relleno';
const TIPO_DE_ESCALERA = 'escalera';
const TIPOS_LINEALES = new Set(['lineal_estructural', 'zapata_aislada', 'columna_de_concreto']);

export function PantallaDeElementos({
  clave,
  rol,
  obraId = '',
}: {
  readonly clave: string | null;
  readonly rol?: string | null;
  /** La obra actual: los cálculos de los elementos leen sus drivers. */
  readonly obraId?: string;
}) {
  const biblioteca = useBibliotecaDeElementosApiV1BibliotecaDeElementosGet();
  // Los castillos, aparentes y columnas forjadas (3A) comparten la tarjeta de estructura.
  const esDeEstructura = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && e.tipo === 'estructura_de_catalogo')),
  );
  const esLineal = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && TIPOS_LINEALES.has(e.tipo))),
  );
  const esDeTabique = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && e.tipo === TIPO_DE_TABIQUE)),
  );
  const esDeSillar = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && e.tipo === TIPO_DE_SILLAR)),
  );
  const esBaston = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && e.tipo === TIPO_DE_BASTON)),
  );
  const esLosa = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && e.tipo === TIPO_DE_LOSA)),
  );
  const esRelleno = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && e.tipo === TIPO_DE_RELLENO)),
  );
  const esEscalera = (biblioteca.data ?? []).some((c) =>
    c.subcategorias.some((s) => s.elementos.some((e) => e.clave === clave && e.tipo === TIPO_DE_ESCALERA)),
  );
  return (
    <section className="pantalla-elementos" role="region" id="area-elementos" aria-label="Elementos">
      <div className="pantalla-elementos__tarjeta">
        {clave === 'MCT-01010' ? (
          <TarjetaMuroContencion clave={clave} />
        ) : clave && esDeEstructura ? (
          <TarjetaEstructura clave={clave} obraId={obraId} />
        ) : clave && esDeTabique ? (
          <TarjetaMuroTabique key={clave} clave={clave} />
        ) : clave && esDeSillar ? (
          <TarjetaMuroSillar key={clave} clave={clave} obraId={obraId} />
        ) : clave && esLosa ? (
          <TarjetaLosa key={clave} clave={clave} rol={rol} obraId={obraId} />
        ) : clave && esRelleno ? (
          <TarjetaRelleno key={clave} clave={clave} rol={rol} />
        ) : clave && esEscalera ? (
          <TarjetaEscalera key={clave} clave={clave} rol={rol} />
        ) : clave && esBaston ? (
          <TarjetaBaston key={clave} clave={clave} obraId={obraId} />
        ) : clave && esLineal ? (
          <TarjetaElementoEstructural key={clave} clave={clave} rol={rol} obraId={obraId} />
        ) : clave === 'CIM-01010' ? (
          <TarjetaMuroCimentacion clave={clave} />
        ) : (
          <div className="empty">
            <div className="empty-title">Elige un elemento de la biblioteca</div>
            <div className="empty-sub">Su tarjeta aparece aquí.</div>
          </div>
        )}
      </div>
    </section>
  );
}
