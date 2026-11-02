/**
 * Conteo automático por plantilla: la zona que se marcó con dos clics es el símbolo (una salida, una
 * luminaria); se buscan sus coincidencias en la imagen del plano y se ven en el plano de antemano.
 * Se ajusta qué tan parecido debe ser y se **propone** el resultado: las coincidencias entran como
 * propuestas por revisar, que no suman nada hasta que alguien las acepta.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useProponerTrazosApiV1PlanosPlanoIdPropuestasPost } from '@/api/generado/propuestas/propuestas';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import type { Punto } from './geometria';
import { cargarImagenGris } from './imagenGris';
import { buscarPlantilla, factorDeReduccion, plantillaConForma, recortar, type Coincidencia } from './plantilla';

interface ActividadDeConteo {
  readonly id: string;
  readonly etiqueta: string;
}

interface Props {
  readonly planoId: string;
  readonly fondoUrl: string;
  readonly puntoA: Punto;
  readonly puntoB: Punto;
  readonly actividades: readonly ActividadDeConteo[];
  readonly actividadInicialId?: string;
  /** Las coincidencias de ahora (en unidades de plano, el centro de cada una), para verlas en el plano. */
  readonly onVistaPrevia: (centros: readonly Punto[]) => void;
  readonly onCerrar: () => void;
  readonly onPropuestas: (cuantas: number) => void;
}

interface Hallazgo {
  readonly centros: readonly (readonly [number, number, number])[]; // x, y (plano) y puntaje
}

export function ConteoAutomatico({
  planoId,
  fondoUrl,
  puntoA,
  puntoB,
  actividades,
  actividadInicialId,
  onVistaPrevia,
  onCerrar,
  onPropuestas,
}: Props) {
  const [estado, setEstado] = useState<'buscando' | 'listo' | 'error'>('buscando');
  const [error, setError] = useState<string | null>(null);
  const [hallazgo, setHallazgo] = useState<Hallazgo | null>(null);
  const [umbral, setUmbral] = useState(85);
  const [actividadId, setActividadId] = useState(actividadInicialId ?? actividades[0]?.id ?? '');
  const proponer = useProponerTrazosApiV1PlanosPlanoIdPropuestasPost<ErrorApi>();
  const vigente = useRef(true);

  const x = Math.min(puntoA[0], puntoB[0]);
  const y = Math.min(puntoA[1], puntoB[1]);
  const ancho = Math.abs(puntoA[0] - puntoB[0]);
  const alto = Math.abs(puntoA[1] - puntoB[1]);

  useEffect(() => {
    vigente.current = true;
    (async () => {
      try {
        const reducida = await cargarImagenGris(fondoUrl, (w, h) => factorDeReduccion(ancho, alto, w, h));
        const f = reducida.factor;
        const plantilla = recortar(reducida.gris, x / f, y / f, ancho / f, alto / f);
        if (plantilla.ancho < 4 || plantilla.alto < 4) throw new Error('El símbolo marcado es muy chico: marca una zona más grande.');
        if (!plantillaConForma(plantilla)) throw new Error('La zona marcada está lisa: marca el símbolo con un poco de su entorno.');
        const coincidencias: Coincidencia[] = await buscarPlantilla(reducida.gris, plantilla, {
          minimo: 0.55,
          ceder: () => new Promise((ok) => setTimeout(ok, 0)),
        });
        if (!vigente.current) return;
        setHallazgo({
          centros: coincidencias.map((c) => [(c.x + plantilla.ancho / 2) * f, (c.y + plantilla.alto / 2) * f, c.puntaje] as const),
        });
        setEstado('listo');
      } catch (err) {
        if (!vigente.current) return;
        setError(err instanceof Error ? err.message : 'No se pudo buscar el símbolo.');
        setEstado('error');
      }
    })();
    return () => {
      vigente.current = false;
    };
  }, [fondoUrl, x, y, ancho, alto]);

  const vistas = useMemo(
    () => (hallazgo?.centros ?? []).filter((c) => c[2] * 100 >= umbral),
    [hallazgo, umbral],
  );
  useEffect(() => {
    onVistaPrevia(vistas.map((c) => [c[0], c[1]] as Punto));
  }, [vistas, onVistaPrevia]);
  useEffect(() => () => onVistaPrevia([]), [onVistaPrevia]);

  async function aProponer() {
    if (vistas.length === 0 || actividadId === '') return;
    setError(null);
    try {
      await proponer.mutateAsync({
        planoId,
        data: {
          actividad_id: actividadId,
          medida: 'conteo',
          origen: 'conteo_auto',
          propuestas: vistas.map((c) => ({ wkt: `POINT(${c[0].toFixed(3)} ${c[1].toFixed(3)})`, confianza: Math.min(1, c[2]).toFixed(4) })),
        },
      });
      onPropuestas(vistas.length);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudieron proponer las coincidencias.');
    }
  }

  return (
    <Sheet titulo="Conteo automático" subtitulo="Busca los símbolos iguales al que marcaste" onCerrar={onCerrar}>
      <div className="sheet__body col gap-12">
        {error && <ErrorBanner mensaje={error} />}
        {estado === 'buscando' && <p className="text-sm">Buscando coincidencias…</p>}
        {estado === 'listo' && (
          <>
            <p className="text-sm" data-testid="coincidencias">
              <strong>{vistas.length}</strong> {vistas.length === 1 ? 'coincidencia' : 'coincidencias'} con parecido de {umbral} % o más
              (se ven en el plano).
            </p>
            <label className="field">
              <span className="field__label">Qué tan parecido ({umbral} %)</span>
              <input
                type="range"
                min={55}
                max={99}
                value={umbral}
                aria-label="Qué tan parecido"
                onChange={(e) => setUmbral(Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span className="field__label">Para el concepto</span>
              <select className="select" value={actividadId} onChange={(e) => setActividadId(e.target.value)} aria-label="Concepto que se cuenta">
                {actividades.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.etiqueta}
                  </option>
                ))}
              </select>
            </label>
            <p className="text-mute text-xs">
              Entran como <strong>propuestas por revisar</strong>: no suman nada hasta que las aceptes. Las que no sean el símbolo, las
              descartas con un clic.
            </p>
          </>
        )}
      </div>
      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button
          type="button"
          className="btn btn--primary"
          disabled={estado !== 'listo' || vistas.length === 0 || actividadId === '' || proponer.isPending}
          onClick={() => void aProponer()}
        >
          {proponer.isPending ? 'Proponiendo…' : `Proponer ${vistas.length}`}
        </button>
      </div>
    </Sheet>
  );
}
