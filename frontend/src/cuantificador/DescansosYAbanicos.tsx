/**
 * Descansos propios y escalones de abanico de una escalera (Fase 4d), dentro de la fila de la escalera del panel de zonas.
 *
 * - **Descansos**: uno por posición entre rampas (1 = entre la 1.ª y la 2.ª), con su largo (en el sentido de la marcha), su ancho transversal, su espesor y el giro del
 *   recorrido (0°, 90° o 180°). Lo que se deja vacío toma la omisión de la escalera. Una posición sin descanso propio conserva el descanso implícito de siempre. Un
 *   polígono del plano (que se asigna por la API) manda sobre largo × ancho: aquí se muestra y se conserva. Se pagan con EJ-820 por m² (propuesto, sin precio).
 * - **Abanico**: un grupo de escalones en giro, de peldaño trapezoidal: el fondo del peldaño en el borde interior y en el exterior, y el radio de la línea de huella
 *   medido desde el borde interior (supuesto editable: 0.35 m). Los escalones de abanico son parte de los peldaños del desnivel: restan de los rectos, no se suman.
 *
 * No calcula nada: pinta lo que responde el servidor (el cálculo de la escalera). Solo Control de obra escribe; los demás roles leen.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useCambiarAbanicosApiV1EscalerasDeZonaEscaleraIdAbanicosPut,
  useCambiarDescansosApiV1EscalerasDeZonaEscaleraIdDescansosPut,
} from '@/api/generado/escaleras/escaleras';
import type { AbanicoDeLaPeticion, DescansoDeLaPeticion, EscaleraDeLaZonaCalculada } from '@/api/generado/modelo';
import { queryClient } from '@/app/queryClient';

function mensaje(err: unknown, defecto: string): string {
  return err instanceof Error ? err.message : defecto;
}

function num(n: number | null | undefined, dec = 2): string {
  return n === null || n === undefined || !Number.isFinite(n)
    ? '—'
    : n.toLocaleString('es-MX', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function refrescar() {
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('zonas-de-losa') });
  // Lo que paga la escalera de cada espacio cambia con sus piezas: los espacios y las partidas se vuelven a leer.
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/espacios') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/cuantificacion') });
  void queryClient.invalidateQueries({ predicate: (q) => JSON.stringify(q.queryKey).includes('/biblioteca-de-elementos') });
}

/** Un campo numérico: vacío = el de omisión (`undefined`); lo que no es un número válido, `null`. */
function opcional(texto: string): number | undefined | null {
  if (texto.trim() === '') return undefined;
  const n = Number(texto.trim().replace(',', '.'));
  return Number.isFinite(n) && n > 0 ? n : null;
}

const NOMBRE_DEL_ORIGEN_DEL_DESCANSO: Record<string, string> = {
  implicito: 'implícito (ancho × largo del descanso)',
  dimensiones: 'sus medidas',
  plano: 'polígono del plano',
};

interface Comun {
  readonly e: EscaleraDeLaZonaCalculada;
  readonly numero: number;
  readonly puedeEditar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}

// ── Descansos ───────────────────────────────────────────────────────────────────────────────────────

interface BorradorDeDescanso {
  posicion: string;
  giro: string;
  largo: string;
  ancho: string;
  espesor: string;
  trazo: string | null;
}

const texto = (n: number | null | undefined) => (n === null || n === undefined ? '' : String(n));

export function DescansosDeLaEscalera({ e, numero, puedeEditar, onCambio, onError }: Comun) {
  // Al guardar, el servidor devuelve las filas y el panel cambia de `key`: el borrador vuelve a salir de lo guardado.
  const llave = JSON.stringify((e.descansos ?? []).map((d) => [d.id, d.posicion, d.giro_grados, d.largo_m, d.ancho_m, d.espesor_m, d.trazo_id]));
  const rampas = e.calculo?.parametros.rampas ?? 1;
  return <CuerpoDeLosDescansos key={`${llave}-${rampas}`} e={e} numero={numero} puedeEditar={puedeEditar} onCambio={onCambio} onError={onError} rampas={rampas} />;
}

function CuerpoDeLosDescansos({ e, numero, puedeEditar, onCambio, onError, rampas }: Comun & { readonly rampas: number }) {
  const cambiar = useCambiarDescansosApiV1EscalerasDeZonaEscaleraIdDescansosPut<ErrorApi>();
  const [filas, setFilas] = useState<BorradorDeDescanso[]>(() =>
    (e.descansos ?? []).map((d) => ({
      posicion: String(d.posicion), giro: String(d.giro_grados), largo: texto(d.largo_m), ancho: texto(d.ancho_m), espesor: texto(d.espesor_m), trazo: d.trazo_id ?? null,
    })),
  );
  const detalle = e.calculo?.geometria.descansos_detalle ?? [];
  const libres = Array.from({ length: Math.max(rampas - 1, 0) }, (_, i) => i + 1).filter((p) => !filas.some((f) => f.posicion === String(p)));

  function cambiarFila(i: number, parte: Partial<BorradorDeDescanso>) {
    setFilas((previas) => previas.map((f, j) => (j === i ? { ...f, ...parte } : f)));
  }

  async function guardar() {
    const cuerpo: DescansoDeLaPeticion[] = [];
    for (const f of filas) {
      const medidas = [opcional(f.largo), opcional(f.ancho), opcional(f.espesor)];
      if (medidas.includes(null)) {
        onError('Una medida del descanso no es un número válido.');
        return;
      }
      const [largo, ancho, espesor] = medidas as (number | undefined)[];
      cuerpo.push({
        posicion: Number(f.posicion),
        giro_grados: Number(f.giro) as DescansoDeLaPeticion['giro_grados'],
        ...(largo === undefined ? {} : { largo_m: largo }),
        ...(ancho === undefined ? {} : { ancho_m: ancho }),
        ...(espesor === undefined ? {} : { espesor_m: espesor }),
        ...(f.trazo ? { trazo_id: f.trazo } : {}),
      });
    }
    try {
      await cambiar.mutateAsync({ escaleraId: e.id, data: { descansos: cuerpo } });
      refrescar();
      onCambio(cuerpo.length === 0 ? `Escalera ${numero}: vuelve al descanso implícito.` : `Descansos de la escalera ${numero} guardados.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudieron guardar los descansos.'));
    }
  }

  return (
    <div className="mct__bloque" role="group" aria-label={`Descansos de la escalera ${numero}`} data-testid={`descansos-de-la-escalera-${numero}`}>
      <strong className="text-sm">Descansos entre rampas</strong>
      {rampas < 2 ? (
        <p className="text-mute text-xs">Con una sola rampa no hay descanso: sube las rampas de la escalera para poner uno.</p>
      ) : (
        <>
          <p className="text-mute text-xs">
            Cada descanso va entre dos rampas. Sin medidas propias vale el ancho de la escalera por el largo del descanso; si gira 180° son dos anchos. Se paga con EJ-820 por m²
            (propuesto, sin precio).
          </p>
          {filas.map((f, i) => {
            const n = i + 1;
            const nombre = (campo: string) => `${campo} del descanso ${n} de la escalera ${numero}`;
            return (
              <div key={`${f.posicion}-${i}`} className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }} data-descanso-posicion={f.posicion}>
                <label className="mct__campo">
                  Posición
                  <select className="input" aria-label={nombre('Posición')} disabled={!puedeEditar} value={f.posicion} onChange={(x) => cambiarFila(i, { posicion: x.target.value })}>
                    {Array.from({ length: rampas - 1 }, (_, k) => k + 1).map((p) => (
                      <option key={p} value={p} disabled={p !== Number(f.posicion) && filas.some((o) => o.posicion === String(p))}>
                        Entre la rampa {p} y la {p + 1}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="mct__campo">
                  Giro
                  <select className="input" aria-label={nombre('Giro')} disabled={!puedeEditar} value={f.giro} onChange={(x) => cambiarFila(i, { giro: x.target.value })}>
                    <option value="0">Recto (0°)</option>
                    <option value="90">Cambio de dirección (90°)</option>
                    <option value="180">Vuelta (180°)</option>
                  </select>
                </label>
                <label className="mct__campo">
                  Largo (m)
                  <input className="input" inputMode="decimal" aria-label={nombre('Largo')} disabled={!puedeEditar || f.trazo !== null} placeholder="el de la escalera" value={f.trazo ? '' : f.largo} onChange={(x) => cambiarFila(i, { largo: x.target.value })} />
                </label>
                <label className="mct__campo">
                  Ancho transversal (m)
                  <input className="input" inputMode="decimal" aria-label={nombre('Ancho')} disabled={!puedeEditar || f.trazo !== null} placeholder="el de la escalera" value={f.trazo ? '' : f.ancho} onChange={(x) => cambiarFila(i, { ancho: x.target.value })} />
                </label>
                <label className="mct__campo">
                  Espesor (m)
                  <input className="input" inputMode="decimal" aria-label={nombre('Espesor')} disabled={!puedeEditar} placeholder="el de la escalera" value={f.espesor} onChange={(x) => cambiarFila(i, { espesor: x.target.value })} />
                </label>
                {f.trazo && <span className="badge badge--outline">área de un polígono del plano</span>}
                {puedeEditar && (
                  <button type="button" className="btn btn--sm" aria-label={`Quitar el descanso ${n} de la escalera ${numero}`} onClick={() => setFilas((previas) => previas.filter((_, j) => j !== i))}>
                    Quitar
                  </button>
                )}
              </div>
            );
          })}
          {filas.length === 0 && <p className="text-mute text-xs">Sin descansos propios: cada posición lleva el descanso implícito.</p>}
          {puedeEditar && (
            <div className="row" style={{ gap: 6 }}>
              <button
                type="button"
                className="btn btn--sm"
                aria-label={`Agregar un descanso a la escalera ${numero}`}
                disabled={libres.length === 0}
                onClick={() => setFilas((previas) => [...previas, { posicion: String(libres[0]), giro: '90', largo: '', ancho: '', espesor: '', trazo: null }])}
              >
                Agregar un descanso
              </button>
              <button type="button" className="btn btn--sm" aria-label={`Guardar los descansos de la escalera ${numero}`} disabled={cambiar.isPending} onClick={() => void guardar()}>
                Guardar los descansos
              </button>
            </div>
          )}
          {detalle.length > 0 && (
            <table className="table" aria-label={`Detalle de los descansos (escalera ${numero})`}>
              <thead>
                <tr>
                  <th>Posición</th>
                  <th>Giro</th>
                  <th>Área</th>
                  <th>Concreto</th>
                  <th>De dónde sale</th>
                </tr>
              </thead>
              <tbody>
                {detalle.map((d) => (
                  <tr key={d.posicion} data-posicion={d.posicion} data-origen={d.origen}>
                    <td>
                      Rampa {d.posicion} a {d.posicion + 1}
                    </td>
                    <td className="mono">{d.giro_grados === null || d.giro_grados === undefined ? '—' : `${d.giro_grados}°`}</td>
                    <td className="mono">{num(d.area_m2)} m²</td>
                    <td className="mono">{num(d.volumen_m3, 3)} m³</td>
                    <td>{NOMBRE_DEL_ORIGEN_DEL_DESCANSO[d.origen] ?? d.origen}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}

// ── Escalones de abanico ────────────────────────────────────────────────────────────────────────────

interface BorradorDeAbanico {
  posicion: string;
  escalones: string;
  interior: string;
  exterior: string;
  radio: string;
}

export function AbanicosDeLaEscalera({ e, numero, puedeEditar, onCambio, onError }: Comun) {
  const llave = JSON.stringify((e.abanicos ?? []).map((a) => [a.id, a.posicion, a.escalones, a.ancho_interior_m, a.ancho_exterior_m, a.radio_huella_m]));
  const rampas = e.calculo?.parametros.rampas ?? 1;
  return <CuerpoDeLosAbanicos key={`${llave}-${rampas}`} e={e} numero={numero} puedeEditar={puedeEditar} onCambio={onCambio} onError={onError} rampas={rampas} />;
}

function CuerpoDeLosAbanicos({ e, numero, puedeEditar, onCambio, onError, rampas }: Comun & { readonly rampas: number }) {
  const cambiar = useCambiarAbanicosApiV1EscalerasDeZonaEscaleraIdAbanicosPut<ErrorApi>();
  const [filas, setFilas] = useState<BorradorDeAbanico[]>(() =>
    (e.abanicos ?? []).map((a) => ({
      posicion: String(a.posicion), escalones: String(a.escalones), interior: String(a.ancho_interior_m), exterior: String(a.ancho_exterior_m), radio: String(a.radio_huella_m),
    })),
  );
  const g = e.calculo?.geometria;
  const calculados = g?.abanicos ?? [];
  const libres = Array.from({ length: rampas + 1 }, (_, i) => i).filter((p) => !filas.some((f) => f.posicion === String(p)));

  function cambiarFila(i: number, parte: Partial<BorradorDeAbanico>) {
    setFilas((previas) => previas.map((f, j) => (j === i ? { ...f, ...parte } : f)));
  }

  async function guardar() {
    const cuerpo: AbanicoDeLaPeticion[] = [];
    for (const f of filas) {
      const interior = opcional(f.interior);
      const exterior = opcional(f.exterior);
      const radio = opcional(f.radio);
      const escalones = Number(f.escalones);
      if (interior === undefined || interior === null || exterior === undefined || exterior === null || radio === null || !Number.isInteger(escalones) || escalones < 1) {
        onError('Revisa el abanico: los escalones son un entero y los fondos de los bordes interior y exterior, números mayores que cero.');
        return;
      }
      cuerpo.push({ posicion: Number(f.posicion), escalones, ancho_interior_m: interior, ancho_exterior_m: exterior, ...(radio === undefined ? {} : { radio_huella_m: radio }) });
    }
    try {
      await cambiar.mutateAsync({ escaleraId: e.id, data: { abanicos: cuerpo } });
      refrescar();
      onCambio(cuerpo.length === 0 ? `Escalera ${numero}: sin escalones de abanico.` : `Escalones de abanico de la escalera ${numero} guardados.`);
    } catch (err) {
      onError(mensaje(err, 'No se pudieron guardar los escalones de abanico.'));
    }
  }

  return (
    <div className="mct__bloque" role="group" aria-label={`Escalones de abanico de la escalera ${numero}`} data-testid={`abanicos-de-la-escalera-${numero}`}>
      <strong className="text-sm">Escalones de abanico</strong>
      <p className="text-mute text-xs">
        Escalones en giro, de peldaño trapezoidal: el fondo en el borde interior y en el exterior. La línea de huella se mide a 35 cm del borde interior (supuesto editable).
        Forman parte de los peldaños del desnivel: restan de los rectos, no se suman.
      </p>
      {filas.map((f, i) => {
        const n = i + 1;
        const nombre = (campo: string) => `${campo} del abanico ${n} de la escalera ${numero}`;
        return (
          <div key={`${f.posicion}-${i}`} className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }} data-abanico-posicion={f.posicion}>
            <label className="mct__campo">
              Posición
              <select className="input" aria-label={nombre('Posición')} disabled={!puedeEditar} value={f.posicion} onChange={(x) => cambiarFila(i, { posicion: x.target.value })}>
                {Array.from({ length: rampas + 1 }, (_, k) => k).map((p) => (
                  <option key={p} value={p} disabled={p !== Number(f.posicion) && filas.some((o) => o.posicion === String(p))}>
                    {p === 0 ? 'Antes de la rampa 1' : `Después de la rampa ${p}`}
                  </option>
                ))}
              </select>
            </label>
            <label className="mct__campo">
              Escalones
              <input className="input" inputMode="numeric" aria-label={nombre('Escalones')} disabled={!puedeEditar} value={f.escalones} onChange={(x) => cambiarFila(i, { escalones: x.target.value })} />
            </label>
            <label className="mct__campo">
              Fondo en el borde interior (m)
              <input className="input" inputMode="decimal" aria-label={nombre('Fondo en el borde interior')} disabled={!puedeEditar} value={f.interior} onChange={(x) => cambiarFila(i, { interior: x.target.value })} />
            </label>
            <label className="mct__campo">
              Fondo en el borde exterior (m)
              <input className="input" inputMode="decimal" aria-label={nombre('Fondo en el borde exterior')} disabled={!puedeEditar} value={f.exterior} onChange={(x) => cambiarFila(i, { exterior: x.target.value })} />
            </label>
            <label className="mct__campo">
              Radio de la línea de huella (m)
              <input className="input" inputMode="decimal" aria-label={nombre('Radio de la línea de huella')} disabled={!puedeEditar} placeholder="0.35" value={f.radio} onChange={(x) => cambiarFila(i, { radio: x.target.value })} />
            </label>
            {puedeEditar && (
              <button type="button" className="btn btn--sm" aria-label={`Quitar el abanico ${n} de la escalera ${numero}`} onClick={() => setFilas((previas) => previas.filter((_, j) => j !== i))}>
                Quitar
              </button>
            )}
          </div>
        );
      })}
      {filas.length === 0 && <p className="text-mute text-xs">Sin escalones de abanico: todos los peldaños son rectos.</p>}
      {puedeEditar && (
        <div className="row" style={{ gap: 6 }}>
          <button
            type="button"
            className="btn btn--sm"
            aria-label={`Agregar un abanico a la escalera ${numero}`}
            disabled={libres.length === 0}
            onClick={() => setFilas((previas) => [...previas, { posicion: String(libres[0]), escalones: '3', interior: '0.15', exterior: '0.75', radio: '' }])}
          >
            Agregar un abanico
          </button>
          <button type="button" className="btn btn--sm" aria-label={`Guardar los abanicos de la escalera ${numero}`} disabled={cambiar.isPending} onClick={() => void guardar()}>
            Guardar los abanicos
          </button>
        </div>
      )}
      {g && calculados.length > 0 && (
        <>
          <p className="text-sm" data-testid={`abanico-resumen-${numero}`}>
            {g.peldanos_de_abanico} de abanico + {g.peldanos_rectos} rectos = {g.peldanos} peldaños · abanico {num(g.area_de_abanico_m2)} m² en planta · {num(g.escalones_de_abanico_de_catalogo)} pza de
            EST-01510 (rectos {num(g.escalones_rectos_de_catalogo)})
          </p>
          <table className="table" aria-label={`Detalle de los abanicos (escalera ${numero})`}>
            <thead>
              <tr>
                <th>Posición</th>
                <th>Escalones</th>
                <th>Huella en la línea</th>
                <th>Gira</th>
                <th>Área en planta</th>
                <th>Piezas</th>
              </tr>
            </thead>
            <tbody>
              {calculados.map((a) => (
                <tr key={a.posicion} data-posicion={a.posicion}>
                  <td>{a.posicion === 0 ? 'Antes de la rampa 1' : `Después de la rampa ${a.posicion}`}</td>
                  <td className="mono">{a.escalones}</td>
                  <td className="mono">
                    {num(a.huella_en_la_linea_m * 100, 1)} cm (a {num(a.radio_huella_m * 100, 0)} cm del borde interior)
                  </td>
                  <td className="mono">{num(a.giro_total_grados, 1)}°</td>
                  <td className="mono">{num(a.area_en_planta_m2)} m²</td>
                  <td className="mono">{num(a.escalones_de_catalogo)} pza</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
