/**
 * Guardar el trazo que se acaba de dibujar, con los enlaces que lo conectan al
 * presupuesto (`POST /planos/{id}/trazos`, MODELO.md §1b).
 *
 * «Un trazo, varios enlaces»: el área de un muro da el piso, el perímetro da el
 * zoclo. Cada fila de este formulario es un enlace; el servidor los registra
 * todos en una transacción y recalcula la cantidad de cada actividad tocada.
 *
 * Enlazar a una **actividad** compara la medida contra `cant_base` y nunca la
 * reemplaza: la diferencia es candidata de desviación, no corrección
 * automática. Enlazar a un nodo de prototipo («diseño nuevo») es de Control y
 * Super intendente y no se ofrece aquí todavía.
 */

import { useState, type FormEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useRegistrarTrazoApiV1PlanosPlanoIdTrazosPost } from '@/api/generado/cuantificacion/cuantificacion';
import type { ActividadRespuesta, TrazoRespuesta } from '@/api/generado/modelo';
import { OpcionesDeMatriz } from './MatricesDeActividad';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import {
  MEDIDAS_POR_HERRAMIENTA,
  aWkt,
  longitudLocal,
  medidaLocal,
  type HerramientaDeTrazo,
  type MedidaDeTrazo,
  type Punto,
} from './geometria';
import { fmtNum } from '@/lib/formato';
import { NOMBRE_DE_FORMA, type Alineacion, type Forma } from './formas';
import { etiquetaMedida } from './reglas';

type Fuente = 'pdf' | 'dwg' | 'ifc';

/** Un nodo del prototipo al que se puede enlazar (camino «diseño nuevo»). */
export interface NodoDePrototipo {
  readonly id: string;
  readonly etiqueta: string;
}

interface FilaEnlace {
  readonly clave: number;
  /** A qué se enlaza: una actividad de la obra o un nodo del prototipo. */
  readonly destino: 'actividad' | 'prototipo';
  readonly actividadId: string;
  /** Si se mide una matriz interna de la actividad (D-583); vacío = la actividad entera. */
  readonly matrizId?: string;
  readonly medida: MedidaDeTrazo;
  readonly factor: string;
}

interface Props {
  readonly planoId: string;
  readonly versionPlano: number;
  readonly herramienta: HerramientaDeTrazo;
  readonly puntos: readonly Punto[];
  /** Grosor en metros de una línea (un muro), o `null` si es una línea simple. */
  readonly grosorM?: number | null;
  /** De qué lado del eje queda el cuerpo del muro; va con `grosorM`. */
  readonly alineacion?: Alineacion | null;
  /** Grosor en unidades de plano, para la vista previa del área de un muro. */
  readonly grosorU?: number | null;
  /** La forma con la que se estampó el polígono (castillo, columna...), si nació de un punto con forma. */
  readonly forma?: Forma | null;
  readonly actividades: readonly ActividadRespuesta[];
  /** Actividad con la que arranca el primer enlace (la herramienta puntual, D-532). */
  readonly actividadInicial?: string;
  /**
   * Nodos del prototipo, o `null` si este rol no puede enlazarlos. Enlazar a un
   * nodo de prototipo es de Control de obra y Super intendente (el servidor lo
   * impone con 403; aquí solo no se ofrece lo que fallaría).
   */
  readonly nodosDePrototipo: readonly NodoDePrototipo[] | null;
  readonly onCerrar: () => void;
  readonly onGuardado: (resultado: TrazoRespuesta) => void;
}

const NOMBRE_FORMA: Record<HerramientaDeTrazo, string> = {
  poligono: 'Polígono',
  linea: 'Línea',
  punto: 'Punto',
};

function etiquetaActividad(a: ActividadRespuesta): string {
  const donde = [a.nivel_clave, a.etapa_clave].filter(Boolean).join(' · ');
  const que = a.concepto_clave ?? a.descripcion ?? 'Actividad';
  return donde ? `${que} — ${donde}` : String(que);
}

export function AltaTrazo({
  planoId,
  versionPlano,
  herramienta,
  puntos,
  grosorM = null,
  alineacion = null,
  grosorU = null,
  forma = null,
  actividades,
  actividadInicial,
  nodosDePrototipo,
  onCerrar,
  onGuardado,
}: Props) {
  const conGrosor = herramienta === 'linea' && grosorM !== null;
  // Un muro (línea con grosor) mide también su área; una forma estampada es lo que se cuenta.
  const medidas: readonly MedidaDeTrazo[] = conGrosor
    ? ['area', 'longitud', 'conteo']
    : forma !== null
      ? ['conteo', 'area', 'perimetro']
      : MEDIDAS_POR_HERRAMIENTA[herramienta];
  const [fuente, setFuente] = useState<Fuente>('pdf');
  const [capa, setCapa] = useState('');
  const [filas, setFilas] = useState<readonly FilaEnlace[]>([
    { clave: 0, destino: 'actividad', actividadId: actividadInicial ?? '', medida: medidas[0] as MedidaDeTrazo, factor: '1' },
  ]);
  const [siguienteClave, setSiguienteClave] = useState(1);
  const [error, setError] = useState<string | null>(null);

  const registrar = useRegistrarTrazoApiV1PlanosPlanoIdTrazosPost<ErrorApi>();

  function cambiar(clave: number, cambios: Partial<FilaEnlace>) {
    setFilas((actuales) => actuales.map((f) => (f.clave === clave ? { ...f, ...cambios } : f)));
  }

  function agregarFila() {
    setFilas((actuales) => [
      ...actuales,
      { clave: siguienteClave, destino: 'actividad', actividadId: '', medida: medidas[0] as MedidaDeTrazo, factor: '1' },
    ]);
    setSiguienteClave((n) => n + 1);
  }

  async function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    setError(null);

    // Una fila sin actividad es una fila a medias, no «sin enlace»: quien no
    // quiere enlazar la quita. Mandarla vacía daría un 422 sin decir cuál.
    if (filas.some((f) => f.actividadId === '')) {
      setError('Cada enlace necesita un destino; quita las filas que no vayas a usar.');
      return;
    }
    for (const f of filas) {
      const factor = Number(f.factor);
      if (!(factor > 0)) {
        setError('El factor debe ser un número mayor que cero.');
        return;
      }
      // Mismo criterio que `domain.cuantificacion.reglas`: un conteo ya es un
      // número de instancias, no una medida continua.
      if (f.medida === 'conteo' && !Number.isInteger(factor)) {
        setError('Un enlace de conteo lleva un factor entero: ya cuenta instancias.');
        return;
      }
    }

    try {
      const resultado = await registrar.mutateAsync({
        planoId,
        data: {
          version_plano: versionPlano,
          fuente,
          capa: capa.trim() === '' ? null : capa.trim(),
          geometria_wkt: aWkt(herramienta, puntos),
          ...(conGrosor && alineacion !== null ? { grosor_m: String(grosorM), alineacion } : {}),
          ...(forma !== null
            ? {
                forma: {
                  tipo: forma.tipo,
                  ancho_m: String(forma.anchoM),
                  alto_m: String(forma.altoM),
                  rotacion_grados: String(forma.rotacionGrados),
                  ...(forma.nombre ? { nombre: forma.nombre } : {}),
                  ...(forma.tipo === 'libre' && forma.vertices
                    ? { vertices: forma.vertices.map((v) => [v[0], v[1]] as [number, number]) }
                    : {}),
                },
              }
            : {}),
          enlaces: filas.map((f) => ({
            medida: f.medida,
            factor: f.factor,
            ...(f.destino === 'actividad'
              ? {
                  actividad_id: f.actividadId,
                  ...(f.matrizId ? { matriz_concepto_id: f.matrizId } : {}),
                }
              : { prototipo_nodo_id: f.actividadId }),
          })),
        },
      });
      onGuardado(resultado);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'No se pudo guardar el trazo.');
    }
  }

  return (
    <Sheet
      titulo={`Guardar ${NOMBRE_FORMA[herramienta].toLowerCase()}`}
      subtitulo="POST /planos/{id}/trazos · MODELO §1b"
      onCerrar={onCerrar}
    >
      <form onSubmit={(e) => void alEnviar(e)}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          {conGrosor && (
            <div className="text-sm" data-testid="aviso-grosor">
              Línea con grosor de <strong>{grosorM} m</strong>, cuerpo a la{' '}
              <strong>{alineacion === 'centro' ? 'mitad del eje' : alineacion}</strong>: mide su largo y
              también largo × grosor.
            </div>
          )}
          {forma !== null && (
            <div className="text-sm" data-testid="aviso-forma">
              {forma.nombre ?? NOMBRE_DE_FORMA[forma.tipo]} de {forma.anchoM} × {forma.altoM} m: se
              guarda como un polígono centrado donde hiciste clic.
            </div>
          )}

          <div className="field">
            <label className="field__label" htmlFor="trazo-fuente">
              Archivo de origen
            </label>
            <select
              id="trazo-fuente"
              className="select"
              value={fuente}
              onChange={(e) => setFuente(e.target.value as Fuente)}
            >
              <option value="pdf">PDF</option>
              <option value="dwg">DWG</option>
              <option value="ifc">IFC</option>
            </select>
            <div className="field__hint">
              Decide la precedencia al reemplazar una medida: IFC &gt; DWG &gt; PDF.
            </div>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="trazo-capa">
              Capa <span className="text-mute">(opcional)</span>
            </label>
            <input
              id="trazo-capa"
              className="input"
              value={capa}
              onChange={(e) => setCapa(e.target.value)}
            />
          </div>

          <div className="col">
            <div className="field__label">Enlaces a actividades</div>
            {filas.map((f, i) => {
              const local =
                conGrosor && f.medida === 'area' && grosorU !== null
                  ? longitudLocal(puntos) * grosorU
                  : medidaLocal(herramienta, f.medida, puntos);
              return (
                <div key={f.clave} className="card">
                  <div className="card__body col">
                    {nodosDePrototipo !== null && (
                      <div className="field">
                        <label className="field__label" htmlFor={`enlace-destino-${f.clave}`}>
                          Enlazar a
                        </label>
                        <select
                          id={`enlace-destino-${f.clave}`}
                          className="select"
                          value={f.destino}
                          onChange={(e) =>
                            cambiar(f.clave, {
                              destino: e.target.value as FilaEnlace['destino'],
                              actividadId: '',
                            })
                          }
                        >
                          <option value="actividad">Una actividad de la obra</option>
                          <option value="prototipo">Un nodo del prototipo (diseño nuevo)</option>
                        </select>
                      </div>
                    )}
                    <div className="field">
                      <label className="field__label" htmlFor={`enlace-actividad-${f.clave}`}>
                        {f.destino === 'actividad' ? 'Actividad' : 'Nodo'} {i + 1}
                      </label>
                      <select
                        id={`enlace-actividad-${f.clave}`}
                        className="select"
                        value={f.actividadId}
                        onChange={(e) => cambiar(f.clave, { actividadId: e.target.value, matrizId: '' })}
                      >
                        <option value="">
                          {f.destino === 'actividad' ? 'Elige una actividad…' : 'Elige un nodo…'}
                        </option>
                        {f.destino === 'actividad'
                          ? actividades.map((a) => (
                              <option key={a.id} value={a.id}>
                                {etiquetaActividad(a)}
                              </option>
                            ))
                          : (nodosDePrototipo ?? []).map((n) => (
                              <option key={n.id} value={n.id}>
                                {n.etiqueta}
                              </option>
                            ))}
                      </select>
                      {f.destino === 'actividad' && f.actividadId !== '' && (
                        <div className="field" style={{ marginTop: 6 }}>
                          <label className="field__label" htmlFor={`enlace-matriz-${f.clave}`}>
                            Qué se mide {i + 1}
                          </label>
                          <select
                            id={`enlace-matriz-${f.clave}`}
                            className="select"
                            value={f.matrizId ?? ''}
                            onChange={(e) => cambiar(f.clave, { matrizId: e.target.value })}
                          >
                            <option value="">La actividad entera</option>
                            <OpcionesDeMatriz actividadId={f.actividadId} />
                          </select>
                        </div>
                      )}
                      {f.destino === 'prototipo' && (
                        <div className="field__hint" role="note">
                          Sobrescribe la cantidad del nodo del prototipo, y la comparten todas
                          las obras de ese prototipo.
                        </div>
                      )}
                    </div>
                    <div className="row">
                      <div className="field" style={{ flex: 1 }}>
                        <label className="field__label" htmlFor={`enlace-medida-${f.clave}`}>
                          Medida
                        </label>
                        <select
                          id={`enlace-medida-${f.clave}`}
                          className="select"
                          value={f.medida}
                          onChange={(e) =>
                            cambiar(f.clave, { medida: e.target.value as MedidaDeTrazo })
                          }
                        >
                          {medidas.map((m) => (
                            <option key={m} value={m}>
                              {etiquetaMedida(m)}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="field" style={{ flex: 1 }}>
                        <label className="field__label" htmlFor={`enlace-factor-${f.clave}`}>
                          Factor
                        </label>
                        <input
                          id={`enlace-factor-${f.clave}`}
                          className="input"
                          inputMode="decimal"
                          value={f.factor}
                          onChange={(e) => cambiar(f.clave, { factor: e.target.value })}
                        />
                      </div>
                    </div>
                    <div className="row">
                      <span className="text-mute text-xs" style={{ flex: 1 }}>
                        Vista previa en unidades de plano: {fmtNum(local)}. La cantidad
                        la calcula el servidor al guardar.
                      </span>
                      {filas.length > 1 && (
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => setFilas((a) => a.filter((x) => x.clave !== f.clave))}
                        >
                          Quitar
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
            <button type="button" className="btn btn--sm" onClick={agregarFila}>
              + Otro enlace
            </button>
          </div>
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={registrar.isPending}>
            {registrar.isPending ? 'Guardando…' : 'Guardar trazo'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
