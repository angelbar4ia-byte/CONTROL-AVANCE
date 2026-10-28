/**
 * Escala automática: la escala que propone el texto de la hoja del PDF («ESC. 1:50»). Solo propone;
 * aplicar es una decisión de quien mira, con la cobertura de la hoja a la vista para juzgar si el
 * cuadro de título dice la verdad (un PDF exportado «ajustado a la hoja» no está a escala de impresión).
 * Se aplica por el mismo camino de la calibración manual (`PUT /planos/{id}/escala`) y recalcula todo.
 */

import { useEffect, useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useCalibrarEscalaApiV1PlanosPlanoIdEscalaPut } from '@/api/generado/cuantificacion/cuantificacion';
import type { EscalaRespuesta } from '@/api/generado/modelo';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { fmtNum } from '@/lib/formato';
import { Sheet } from '@/lib/Sheet';
import { candidatosDeEscala, coberturaDeLaHoja, metrosPorUnidad, type CandidatoDeEscala } from './escalaAuto';
import { ESCALA_PDF, textoDeLaHoja } from './pdf';

interface Props {
  readonly planoId: string;
  /** La URL firmada del PDF del plano. */
  readonly urlDelPdf: string;
  /** La escala que ya tenía el plano, si la tenía. */
  readonly escalaActual: number | null;
  readonly onCerrar: () => void;
  readonly onAplicada: (respuesta: EscalaRespuesta) => void;
}

/** Dos puntos de referencia a 1 000 unidades de plano: la escala sale de los metros que se les dan. */
const LARGO_DE_REFERENCIA = 1000;

export function ProponerEscala({ planoId, urlDelPdf, escalaActual, onCerrar, onAplicada }: Props) {
  const [hoja, setHoja] = useState<{ candidatos: CandidatoDeEscala[]; anchoPt: number; altoPt: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elegida, setElegida] = useState<number | null>(null);
  const calibrar = useCalibrarEscalaApiV1PlanosPlanoIdEscalaPut<ErrorApi>();

  useEffect(() => {
    let vigente = true;
    textoDeLaHoja(urlDelPdf).then(
      (r) => {
        if (!vigente) return;
        const candidatos = candidatosDeEscala(r.textos);
        setHoja({ candidatos, anchoPt: r.anchoPt, altoPt: r.altoPt });
        setElegida(candidatos[0]?.denominador ?? null);
      },
      (err: unknown) => vigente && setError(err instanceof Error ? err.message : 'No se pudo leer el PDF.'),
    );
    return () => {
      vigente = false;
    };
  }, [urlDelPdf]);

  async function aplicar() {
    if (elegida === null) return;
    setError(null);
    const porUnidad = metrosPorUnidad(elegida, ESCALA_PDF);
    try {
      const r = await calibrar.mutateAsync({
        planoId,
        data: {
          punto_a: [0, 0],
          punto_b: [LARGO_DE_REFERENCIA, 0],
          distancia_m: (porUnidad * LARGO_DE_REFERENCIA).toFixed(6),
        },
      });
      onAplicada(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo aplicar la escala.');
    }
  }

  const cobertura = hoja && elegida !== null ? coberturaDeLaHoja(hoja.anchoPt, hoja.altoPt, elegida) : null;

  return (
    <Sheet titulo="Proponer la escala" subtitulo="Leída del texto de la hoja" onCerrar={onCerrar}>
      <div className="sheet__body col gap-12">
        {error && <ErrorBanner mensaje={error} />}
        {hoja === null && !error && <p className="text-sm">Leyendo la hoja…</p>}
        {hoja !== null && hoja.candidatos.length === 0 && (
          <p className="text-sm">
            No encontré una escala escrita en la hoja. Calibra con una cota conocida (herramienta «Calibrar escala»).
          </p>
        )}
        {hoja !== null && hoja.candidatos.length > 0 && (
          <>
            <p className="text-sm">
              Esto dice la hoja. Elige la escala del plano; <strong>no se aplica hasta que la confirmes</strong>.
            </p>
            <div role="radiogroup" aria-label="Escalas encontradas" className="col gap-4">
              {hoja.candidatos.map((c) => (
                <label key={c.denominador} className="row gap-8">
                  <input
                    type="radio"
                    name="escala-propuesta"
                    checked={elegida === c.denominador}
                    onChange={() => setElegida(c.denominador)}
                  />
                  <span>
                    <strong>1:{c.denominador}</strong> <span className="text-mute text-xs">«{c.texto}»</span>
                    {c.rotulada && <span className="badge badge--outline">dice «escala»</span>}
                    {c.veces > 1 && <span className="text-mute text-xs"> · aparece {c.veces} veces</span>}
                  </span>
                </label>
              ))}
            </div>
            {cobertura && elegida !== null && (
              <div className="text-sm" data-testid="cobertura-de-la-hoja">
                1 unidad de plano = {metrosPorUnidad(elegida, ESCALA_PDF).toPrecision(4)} m. La hoja cubriría{' '}
                <strong>
                  {fmtNum(cobertura.ancho)} × {fmtNum(cobertura.alto)} m
                </strong>
                : si no es razonable para este plano, el PDF no está a su tamaño de impresión; calibra con una cota.
              </div>
            )}
            {escalaActual !== null && (
              <div className="text-mute text-xs">
                Este plano ya estaba calibrado (1 unidad = {escalaActual} m). Aplicar reemplaza esa escala y recalcula
                todas las cantidades medidas en él.
              </div>
            )}
          </>
        )}
      </div>
      <div className="sheet__footer">
        <button type="button" className="btn" onClick={onCerrar}>
          Cancelar
        </button>
        <button type="button" className="btn btn--primary" disabled={elegida === null || calibrar.isPending} onClick={() => void aplicar()}>
          {calibrar.isPending ? 'Aplicando…' : 'Aplicar esta escala'}
        </button>
      </div>
    </Sheet>
  );
}
