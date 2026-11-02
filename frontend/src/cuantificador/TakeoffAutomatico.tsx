/**
 * Takeoff automático (Fase 3): propone **áreas** (las zonas cerradas por líneas oscuras: cuartos) o
 * **muros** (trazos macizos largos) a partir de la imagen del plano. Se ve de antemano sobre el plano,
 * se ajusta con tres controles y se **propone**: lo que entra son propuestas por revisar, que no suman
 * nada hasta que alguien las acepta. Los muros se detectan como trazos macizos: un muro dibujado con
 * dos líneas finas no se reconoce.
 */

import { useEffect, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useProponerTrazosApiV1PlanosPlanoIdPropuestasPost } from '@/api/generado/propuestas/propuestas';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { cargarImagenGris, type ImagenReducida } from './imagenGris';
import type { GeometriaGeoJson } from './geometria';
import { binarizar, contornoDe, muros, regionesCerradas, simplificar } from './takeoff';

type Modo = 'areas' | 'muros';

interface ActividadPropuesta {
  readonly id: string;
  readonly etiqueta: string;
  /** Cómo se mide el concepto: un área o un largo (por su unidad). */
  readonly tipo: string | null;
}

interface Props {
  readonly planoId: string;
  readonly fondoUrl: string;
  readonly actividades: readonly ActividadPropuesta[];
  /** Metros por unidad de plano, si el plano está calibrado: los límites se piden en metros. */
  readonly escalaMPorUnidad: number | null;
  readonly onVistaPrevia: (geometrias: readonly GeometriaGeoJson[]) => void;
  readonly onCerrar: () => void;
  readonly onPropuestas: (cuantas: number, descartadas: number) => void;
}

const LADO_MAXIMO = 1500;

interface Hallazgo {
  readonly modo: Modo;
  readonly geometrias: readonly GeometriaGeoJson[];
  readonly wkt: readonly string[];
}

const anillo = (puntos: readonly (readonly [number, number])[]) => [...puntos, puntos[0] as readonly [number, number]];

export function TakeoffAutomatico({ planoId, fondoUrl, actividades, escalaMPorUnidad, onVistaPrevia, onCerrar, onPropuestas }: Props) {
  const calibrado = escalaMPorUnidad !== null && escalaMPorUnidad > 0;
  const [modo, setModo] = useState<Modo>('areas');
  const [oscuridad, setOscuridad] = useState(110);
  const [cierre, setCierre] = useState(calibrado ? 0.9 : 8);
  // Cada modo tiene su propio mínimo: 2 m² (o 1 500 u²) de área, o 1 m (o 60 u) de largo de muro.
  const [minimoArea, setMinimoArea] = useState(calibrado ? 2 : 1500);
  const [minimoMuro, setMinimoMuro] = useState(calibrado ? 1 : 60);
  const minimo = modo === 'areas' ? minimoArea : minimoMuro;
  const setMinimo = modo === 'areas' ? setMinimoArea : setMinimoMuro;
  const [imagen, setImagen] = useState<ImagenReducida | null>(null);
  const [hallazgo, setHallazgo] = useState<Hallazgo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actividadId, setActividadId] = useState('');
  const proponer = useProponerTrazosApiV1PlanosPlanoIdPropuestasPost<ErrorApi>();
  const vigente = useRef(true);

  const tipoNecesario = modo === 'areas' ? 'area' : 'lineal';
  const candidatas = actividades.filter((a) => a.tipo === tipoNecesario);
  useEffect(() => {
    if (!candidatas.some((a) => a.id === actividadId)) setActividadId(candidatas[0]?.id ?? '');
  }, [candidatas, actividadId]);

  useEffect(() => {
    vigente.current = true;
    cargarImagenGris(fondoUrl, (w, h) => Math.ceil(Math.max(w, h) / LADO_MAXIMO)).then(
      (r) => vigente.current && setImagen(r),
      (err: unknown) => vigente.current && setError(err instanceof Error ? err.message : 'No se pudo leer la imagen.'),
    );
    return () => {
      vigente.current = false;
    };
  }, [fondoUrl]);

  // La búsqueda, con un respiro tras cada ajuste para no recalcular a cada pixel del control.
  useEffect(() => {
    if (!imagen) return;
    const espera = setTimeout(() => {
      const f = imagen.factor;
      const escala = escalaMPorUnidad as number;
      const deUnidades = (valor: number) => (calibrado ? valor / escala : valor); // un largo: metros → unidades de plano
      const lineas = binarizar(imagen.gris, oscuridad);
      try {
        if (modo === 'areas') {
          const areaMinPx = (calibrado ? minimo / (escala * escala) : minimo) / (f * f); // un área: m² → unidades² → píxeles²
          const regiones = regionesCerradas(lineas, {
            cierre: Math.max(0, Math.round(deUnidades(cierre) / f)),
            areaMin: Math.max(20, areaMinPx),
            areaMax: lineas.datos.length * 0.6,
          }).slice(0, 400);
          const poligonos = regiones
            .map((r) => simplificar(contornoDe(r.mascara, lineas.ancho, lineas.alto), 1.5).map((p) => [p[0] * f, p[1] * f] as const))
            .filter((p) => p.length >= 3);
          setHallazgo({
            modo,
            geometrias: poligonos.map((p) => ({ type: 'Polygon', coordinates: [anillo(p).map((q) => [q[0], q[1]])] }) as GeometriaGeoJson),
            wkt: poligonos.map((p) => `POLYGON((${anillo(p).map((q) => `${q[0].toFixed(2)} ${q[1].toFixed(2)}`).join(', ')}))`),
          });
        } else {
          const largoMinPx = Math.max(4, Math.round(deUnidades(minimo) / f));
          const lista = muros(lineas, { largoMin: largoMinPx, gruesoMin: Math.max(2, Math.round(deUnidades(0.08) / f)) }).slice(0, 400);
          setHallazgo({
            modo,
            geometrias: lista.map((m) => ({ type: 'LineString', coordinates: [[m.desde[0] * f, m.desde[1] * f], [m.hasta[0] * f, m.hasta[1] * f]] }) as GeometriaGeoJson),
            wkt: lista.map((m) => `LINESTRING(${(m.desde[0] * f).toFixed(2)} ${(m.desde[1] * f).toFixed(2)}, ${(m.hasta[0] * f).toFixed(2)} ${(m.hasta[1] * f).toFixed(2)})`),
          });
        }
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'No se pudo analizar el plano.');
      }
    }, 250);
    return () => clearTimeout(espera);
  }, [imagen, modo, oscuridad, cierre, minimo, calibrado, escalaMPorUnidad]);

  useEffect(() => {
    onVistaPrevia(hallazgo?.geometrias ?? []);
  }, [hallazgo, onVistaPrevia]);
  useEffect(() => () => onVistaPrevia([]), [onVistaPrevia]);

  const n = hallazgo?.wkt.length ?? 0;
  async function aProponer() {
    if (!hallazgo || n === 0 || actividadId === '') return;
    setError(null);
    try {
      const r = await proponer.mutateAsync({
        planoId,
        data: {
          actividad_id: actividadId,
          medida: modo === 'areas' ? 'area' : 'longitud',
          origen: 'takeoff',
          propuestas: hallazgo.wkt.map((wkt) => ({ wkt })),
        },
      });
      onPropuestas(r.trazo_ids.length, r.descartadas ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron proponer.');
    }
  }

  const unidad = modo === 'areas' ? (calibrado ? 'm²' : 'u²') : calibrado ? 'm' : 'u';
  return (
    <Sheet titulo="Takeoff automático" subtitulo="Propone áreas y muros que encuentra en la imagen" onCerrar={onCerrar}>
      <div className="sheet__body col gap-12">
        {error && <ErrorBanner mensaje={error} />}
        <div role="radiogroup" aria-label="Qué buscar" className="row gap-8">
          <label className="row gap-4">
            <input type="radio" name="takeoff-modo" checked={modo === 'areas'} onChange={() => setModo('areas')} /> Áreas (cuartos cerrados)
          </label>
          <label className="row gap-4">
            <input type="radio" name="takeoff-modo" checked={modo === 'muros'} onChange={() => setModo('muros')} /> Muros macizos
          </label>
        </div>
        {!imagen && !error && <p className="text-sm">Leyendo la imagen…</p>}
        {imagen && (
          <>
            <p className="text-sm" data-testid="hallazgos">
              <strong>{n}</strong> {modo === 'areas' ? (n === 1 ? 'zona cerrada' : 'zonas cerradas') : n === 1 ? 'muro' : 'muros'} (se ven en el plano).
            </p>
            <label className="field">
              <span className="field__label">Qué tan oscura es la línea ({oscuridad})</span>
              <input type="range" min={40} max={220} value={oscuridad} aria-label="Oscuridad de la línea" onChange={(e) => setOscuridad(Number(e.target.value))} />
            </label>
            {modo === 'areas' && (
              <label className="field">
                <span className="field__label">Cerrar aberturas de hasta ({unidad === 'm²' ? 'm' : 'u'})</span>
                <input className="input" type="number" min={0} step="any" value={cierre} aria-label="Cerrar aberturas" onChange={(e) => setCierre(Number(e.target.value))} />
              </label>
            )}
            <label className="field">
              <span className="field__label">{modo === 'areas' ? `Área mínima (${unidad})` : `Largo mínimo (${unidad})`}</span>
              <input className="input" type="number" min={0} step="any" value={minimo} aria-label="Mínimo" onChange={(e) => setMinimo(Number(e.target.value))} />
            </label>
            <label className="field">
              <span className="field__label">Para el concepto</span>
              <select className="select" value={actividadId} onChange={(e) => setActividadId(e.target.value)} aria-label="Concepto que se mide">
                {candidatas.length === 0 && <option value="">No hay un concepto de {modo === 'areas' ? 'área' : 'largo'} en la obra</option>}
                {candidatas.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.etiqueta}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-mute text-xs">
              Entran como <strong>propuestas por revisar</strong>: no suman nada hasta que las aceptes; descarta con un clic las que no sean.
              {!calibrado && ' El plano no está calibrado: los límites están en unidades de plano.'}
            </p>
          </>
        )}
      </div>
      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button type="button" className="btn btn--primary" disabled={n === 0 || actividadId === '' || proponer.isPending} onClick={() => void aProponer()}>
          {proponer.isPending ? 'Proponiendo…' : `Proponer ${n}`}
        </button>
      </div>
    </Sheet>
  );
}
