/**
 * La columna derecha cuando se elige un trabajo: el detalle de un destajo (cantidades, importe,
 * capacidad, duración, jornales) o de una cuadrilla, y —para Control de obra— la edición.
 *
 * **No hay botones de guardar**: el rendimiento teórico y el costo por día se guardan al salir del
 * campo o con Enter; la cuadrilla, al elegirla. Lo que se cambia es del **catálogo** (el destajo y
 * la cuadrilla se comparten entre conceptos y obras), no de esta obra.
 */

import { useState, type KeyboardEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useAsignarCostoDeJornadaApiV1CuadrillasCuadrillaIdCostoJornadaPut,
  useAsignarCuadrillaADestajoApiV1DestajosInsumoIdCuadrillaPut,
} from '@/api/generado/catalogos/catalogos';
import type { CuadrillaRespuesta, TrabajoDeObraRespuesta } from '@/api/generado/modelo';
import { fmtMXN, fmtNum } from '@/lib/formato';
import { numeroTecleado } from './volumen';
import type { CuadrillaDeLaObra, TrabajoElegido } from './PanelDeTrabajos';
import { calcularTrabajo, cantidadDelConcepto } from './trabajos';

interface Props {
  readonly elegido: TrabajoElegido;
  readonly trabajos: readonly TrabajoDeObraRespuesta[];
  readonly cuadrillasDeLaObra: readonly CuadrillaDeLaObra[];
  /** Todas las cuadrillas del catálogo (para elegir una); solo las ve Control de obra. */
  readonly cuadrillasDelCatalogo: readonly CuadrillaRespuesta[];
  readonly medidaPorActividad: ReadonlyMap<string, string | number | null | undefined>;
  readonly puedeEditar: boolean;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
  readonly onVerConcepto: (actividadId: string) => void;
}

const enEnter = (e: KeyboardEvent<HTMLInputElement>) => {
  if (e.key === 'Enter') e.currentTarget.blur();
};

function Fila({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  return (
    <>
      <span className="text-mute">{etiqueta}</span>
      <span className="mono" style={{ textAlign: 'right' }}>{valor}</span>
    </>
  );
}

export function EditorDeTrabajo(props: Props) {
  return props.elegido.tipo === 'cuadrilla' ? <EditorDeCuadrilla {...props} elegido={props.elegido} /> : <EditorDeDestajo {...props} elegido={props.elegido} />;
}

function EditorDeDestajo({
  elegido,
  trabajos,
  cuadrillasDelCatalogo,
  medidaPorActividad,
  puedeEditar,
  onCambio,
  onError,
  onVerConcepto,
}: Props & { readonly elegido: Extract<TrabajoElegido, { tipo: 'destajo' }> }) {
  const asignar = useAsignarCuadrillaADestajoApiV1DestajosInsumoIdCuadrillaPut<ErrorApi>();
  const [rendimiento, setRendimiento] = useState<string | null>(null);
  const t = trabajos.find((x) => x.actividad_id === elegido.actividadId && x.insumo_id === elegido.insumoId);
  if (!t) return <div className="text-mute text-sm">Este trabajo ya no está en la obra.</div>;

  const concepto = cantidadDelConcepto(medidaPorActividad.get(t.actividad_id), t.cantidad_presupuestada);
  const c = calcularTrabajo(t, concepto);
  const unidad = t.unidad ?? '';
  const teoricoActual = t.rendimiento_teorico != null ? String(Number(t.rendimiento_teorico)) : '';

  async function guardar(datos: { cuadrilla_id?: string | null; rendimiento_teorico?: string | null }, aviso: string) {
    if (!t) return;
    try {
      await asignar.mutateAsync({
        insumoId: t.insumo_id,
        data: {
          cuadrilla_id: datos.cuadrilla_id !== undefined ? datos.cuadrilla_id : (t.cuadrilla_id ?? null),
          rendimiento_teorico: datos.rendimiento_teorico !== undefined ? datos.rendimiento_teorico : (t.rendimiento_teorico ?? null),
        },
      });
      onCambio(aviso);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo guardar el trabajo.');
    }
  }

  function alSalirDelRendimiento() {
    if (rendimiento === null) return;
    const texto = rendimiento;
    setRendimiento(null);
    if (texto.trim() === teoricoActual) return;
    if (texto.trim() === '') {
      void guardar({ rendimiento_teorico: null }, `Rendimiento teórico de ${t?.clave} quitado.`);
      return;
    }
    const n = numeroTecleado(texto);
    if (!(n > 0)) {
      onError('El rendimiento debe ser un número mayor que cero.');
      return;
    }
    void guardar({ rendimiento_teorico: String(n) }, `Rendimiento teórico de ${t?.clave}: ${n} ${unidad}/día.`);
  }

  return (
    <div className="col gap-8">
      <div className="kv" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '4px 8px' }}>
        <Fila etiqueta="Destajo" valor={`${t.clave} · ${t.descripcion}`} />
        <Fila etiqueta="Concepto" valor={`${t.concepto_clave ?? '—'} · ${t.concepto_descripcion ?? ''}`} />
        <Fila etiqueta="Cantidad del concepto" valor={`${fmtNum(concepto.valor)} ${t.concepto_unidad ?? ''} (${concepto.fuente})`} />
        <Fila etiqueta="Cantidad del destajo" valor={`${fmtNum(c.cantidad)} ${unidad}${Number(t.factor) !== 1 ? ` · ${fmtNum(t.factor)} ${unidad} por ${t.concepto_unidad ?? 'unidad'}` : ''}`} />
        <Fila etiqueta="Precio" valor={`${fmtMXN(t.precio)} por ${unidad}`} />
        <Fila etiqueta="Importe" valor={fmtMXN(c.importe)} />
        <Fila etiqueta="Capacidad" valor={c.capacidadPorDia !== null ? `${fmtNum(c.capacidadPorDia)} ${unidad} por día (${c.origenDeLaCapacidad})` : '—'} />
        <Fila etiqueta="Duración" valor={c.dias !== null ? `${fmtNum(c.dias)} días` : '—'} />
        <Fila etiqueta="Jornales de la cuadrilla" valor={fmtMXN(c.jornales)} />
        <Fila etiqueta="Importe − jornales" valor={fmtMXN(c.diferencia)} />
      </div>

      <div className="text-xs text-mute" style={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em' }}>
        Cuadrilla y rendimiento
      </div>

      {puedeEditar ? (
        <>
          <label className="field">
            <span className="field__label">Cuadrilla</span>
            <select
              className="select"
              aria-label="Cuadrilla del destajo"
              value={t.cuadrilla_id ?? ''}
              disabled={asignar.isPending}
              onChange={(e) => {
                const id = e.target.value === '' ? null : e.target.value;
                const nombre = cuadrillasDelCatalogo.find((q) => q.id === id)?.nombre;
                void guardar({ cuadrilla_id: id }, id ? `${t.clave} ahora trabaja con ${nombre ?? 'la cuadrilla'}.` : `${t.clave} quedó sin cuadrilla.`);
              }}
            >
              <option value="">Sin cuadrilla</option>
              {cuadrillasDelCatalogo.map((q) => (
                <option key={q.id} value={q.id}>{q.nombre}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field__label">Rendimiento teórico ({unidad}/día)</span>
            <input
              className="input"
              inputMode="decimal"
              aria-label="Rendimiento teórico"
              placeholder="sin capturar"
              value={rendimiento ?? teoricoActual}
              disabled={asignar.isPending}
              onChange={(e) => setRendimiento(e.target.value)}
              onBlur={alSalirDelRendimiento}
              onKeyDown={enEnter}
            />
          </label>
        </>
      ) : (
        <div className="kv" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '4px 8px' }}>
          <Fila etiqueta="Cuadrilla" valor={t.cuadrilla_nombre ?? 'Sin cuadrilla'} />
          <Fila etiqueta="Rendimiento teórico" valor={t.rendimiento_teorico != null ? `${fmtNum(t.rendimiento_teorico)} ${unidad}/día` : '—'} />
        </div>
      )}

      <div className="kv" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '4px 8px' }}>
        <Fila etiqueta="Rendimiento calculado" valor={t.rendimiento_calculado != null ? `${fmtNum(t.rendimiento_calculado)} ${unidad}/día` : '—'} />
        <Fila etiqueta="Jornadas por unidad" valor={t.jornadas_por_unidad != null ? fmtNum(t.jornadas_por_unidad) : '—'} />
        <Fila etiqueta="Teórico ÷ calculado" valor={t.razon_teorico_calculado != null ? fmtNum(t.razon_teorico_calculado) : '—'} />
      </div>

      <button type="button" className="btn btn--sm" onClick={() => onVerConcepto(t.actividad_id)}>
        Ver el concepto
      </button>

      <div className="text-mute text-xs">
        Tres rendimientos: el <b>calculado</b> nunca se captura (costo de la cuadrilla ÷ precio del destajo); el{' '}
        <b>teórico</b> es la semilla y se puede corregir aquí. Si falta el teórico, la duración usa el calculado.
        {puedeEditar && (
          <> Lo que cambies es del catálogo: vale para todas las obras y conceptos que usan este destajo.</>
        )}
      </div>
    </div>
  );
}

function EditorDeCuadrilla({
  elegido,
  trabajos,
  cuadrillasDeLaObra,
  puedeEditar,
  onCambio,
  onError,
}: Props & { readonly elegido: Extract<TrabajoElegido, { tipo: 'cuadrilla' }> }) {
  const costo = useAsignarCostoDeJornadaApiV1CuadrillasCuadrillaIdCostoJornadaPut<ErrorApi>();
  const [texto, setTexto] = useState<string | null>(null);
  const q = cuadrillasDeLaObra.find((x) => x.id === elegido.id);
  if (!q) return <div className="text-mute text-sm">Esta cuadrilla ya no trabaja en esta obra.</div>;
  const actual = q.costoJornada !== null ? String(q.costoJornada) : '';
  const destajos = trabajos.filter((t) => t.cuadrilla_id === q.id);
  const claves = [...new Set(destajos.map((t) => t.clave))].sort();

  async function alSalir() {
    if (texto === null) return;
    const valor = texto.trim();
    setTexto(null);
    if (valor === actual) return;
    const n = valor === '' ? null : numeroTecleado(valor);
    if (n !== null && !(n > 0)) {
      onError('El costo por día debe ser un número mayor que cero.');
      return;
    }
    try {
      await costo.mutateAsync({ cuadrillaId: q!.id, data: { costo_jornada: n === null ? null : String(n) } });
      onCambio(n === null ? `Costo por día de ${q!.nombre} quitado.` : `Costo por día de ${q!.nombre}: ${fmtMXN(n)}.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo guardar el costo.');
    }
  }

  return (
    <div className="col gap-8">
      <div className="kv" style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '4px 8px' }}>
        <Fila etiqueta="Cuadrilla" valor={q.nombre} />
        <Fila etiqueta="Costo por día" valor={q.costoJornada !== null ? fmtMXN(q.costoJornada) : '—'} />
        <Fila etiqueta="Trabaja en" valor={claves.join(', ') || 'ningún destajo'} />
      </div>
      {puedeEditar && (
        <label className="field">
          <span className="field__label">Costo por día ($)</span>
          <input
            className="input"
            inputMode="decimal"
            aria-label="Costo por día de la cuadrilla"
            placeholder="sin capturar"
            value={texto ?? actual}
            disabled={costo.isPending}
            onChange={(e) => setTexto(e.target.value)}
            onBlur={() => void alSalir()}
            onKeyDown={enEnter}
          />
        </label>
      )}
      <div className="text-mute text-xs">
        La cuadrilla es <b>capacidad</b>: da cuánto rinde por día. El precio del destajo no cambia aunque cambie la
        cuadrilla.
        {puedeEditar && <> Su costo por día es del catálogo: vale para todas las obras.</>}
      </div>
    </div>
  );
}
