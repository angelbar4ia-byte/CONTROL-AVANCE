/**
 * Inspector de lo seleccionado en el canvas: una caja o un cable (§7.5).
 *
 * Lo que no cabe en la caja sin volverla ilegible —duración, frente, tramos,
 * la lista de predecesoras con su tipo y su lag— se edita aquí, al lado y sin
 * tapar el grafo. Es el mismo criterio del cajón de detalle del resto del
 * panel, pero fijo: mientras se arma un programa se salta de caja en caja
 * decenas de veces y abrir y cerrar un `Sheet` en cada salto sobra.
 *
 * Sin selección muestra el resumen del programa, que es lo que se quiere ver
 * cuando no se está editando nada en concreto.
 */

import { Trash2 } from 'lucide-react';

import type { FrenteRespuesta } from '@/api/generado/modelo';
import { fmtNum } from '@/lib/formato';
import { EditorTramos } from './EditorTramos';
import { spanDeCaja, TIPOS_LIGA, type Borrador, type Caja, type TipoLiga } from './grafo';
import { nombreCorto, type Colocacion } from './planificacion';
import { ayudaTipoDependencia, etiquetaTipoDependencia } from './reglas';
import type { Tramo } from './tramos';

interface Props {
  readonly borrador: Borrador;
  readonly caja: Caja | null;
  readonly frentes: readonly FrenteRespuesta[];
  readonly colocado: ReadonlyMap<string, Colocacion>;
  readonly duracionPrograma: number;
  readonly cicloDetectado: readonly string[] | null;
  readonly onDuracion: (cajaId: string, duracionDias: number | null) => void;
  readonly onFrente: (cajaId: string, frenteId: string | null) => void;
  readonly onTramos: (cajaId: string, tramos: readonly Tramo[]) => void;
  readonly onTipoLiga: (desde: string, hasta: string, tipo: TipoLiga) => void;
  readonly onLag: (desde: string, hasta: string, lagDias: number) => void;
  readonly onDesconectar: (desde: string, hasta: string) => void;
  readonly onSeleccionar: (cajaId: string) => void;
  readonly onGesto: () => void;
}

export function PanelCaja({
  borrador,
  caja,
  frentes,
  colocado,
  duracionPrograma,
  cicloDetectado,
  onDuracion,
  onFrente,
  onTramos,
  onTipoLiga,
  onLag,
  onDesconectar,
  onSeleccionar,
  onGesto,
}: Props) {
  const porId = new Map(borrador.cajas.map((c) => [c.id, c]));

  if (caja === null) {
    const renglones = borrador.cajas.filter((c) => c.duracionDias !== null).length;
    const partidas = borrador.cajas.filter((c) => c.tramos.length > 0).length;
    return (
      <aside className="panel-prog__lado" aria-label="Resumen del programa">
        <div>
          <div className="page__eyebrow mono">Programa</div>
          <div className="text-sm text-mute">
            Selecciona una caja para capturar su duración, su frente y sus tramos. Doble
            clic en una etapa entra a sus conceptos.
          </div>
        </div>
        <div className="sep" />
        <dl className="col gap-4 text-sm">
          <Dato etiqueta="Cajas del árbol" valor={String(borrador.cajas.length)} />
          <Dato etiqueta="Con duración" valor={String(renglones)} />
          <Dato etiqueta="Partidas en tramos" valor={String(partidas)} />
          <Dato etiqueta="Duración del programa" valor={`${fmtNum(duracionPrograma)} d`} />
        </dl>
        {cicloDetectado !== null && (
          <div className="badge badge--danger" role="alert">
            Hay un ciclo de precedencias:{' '}
            {cicloDetectado.map((id) => nombreCorto(porId.get(id))).join(' → ')}
          </div>
        )}
      </aside>
    );
  }

  const colocacion = colocado.get(caja.id);

  return (
    <aside className="panel-prog__lado" aria-label={`Actividad ${caja.nombre}`}>
      <div>
        <div className="page__eyebrow mono">
          {caja.tipo === 'etapa' ? 'Etapa constructiva' : 'Concepto'}
          {caja.clave !== null && ` · ${caja.clave}`}
        </div>
        <div style={{ fontWeight: 500 }}>{caja.nombre}</div>
      </div>

      <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
        <div className="field" style={{ flex: 1, minWidth: 110 }}>
          <label className="field__label" htmlFor="caja-duracion">
            Duración (días)
          </label>
          <input
            id="caja-duracion"
            className="input input--mono"
            type="number"
            step="0.5"
            min="0"
            value={caja.duracionDias ?? ''}
            // Con tramos la duración es la suma y no se captura por separado;
            // tener dos cifras editables garantiza que un día discrepen (§7.6).
            disabled={caja.tramos.length > 0}
            placeholder="sin capturar"
            onChange={(e) => {
              onGesto();
              const valor = e.target.value.trim();
              onDuracion(caja.id, valor === '' ? null : Number(valor));
            }}
          />
          {caja.tramos.length > 0 && (
            <div className="field__hint">Es la suma de los tramos (§7.6).</div>
          )}
        </div>
        <div className="field" style={{ flex: 1, minWidth: 130 }}>
          <label className="field__label" htmlFor="caja-frente">
            Frente
          </label>
          <select
            id="caja-frente"
            className="select"
            value={caja.frenteId ?? ''}
            onChange={(e) => {
              onGesto();
              onFrente(caja.id, e.target.value === '' ? null : e.target.value);
            }}
          >
            <option value="">Sin frente</option>
            {frentes.map((frente) => (
              <option key={frente.id} value={frente.id}>
                {frente.clave} · {frente.nombre}
              </option>
            ))}
          </select>
        </div>
      </div>

      {caja.duracionDias !== null && (
        <dl className="col gap-2 text-xs text-mute">
          <Dato etiqueta="Span en calendario" valor={`${fmtNum(spanDeCaja(caja))} d`} />
          {colocacion && (
            <Dato
              etiqueta="Arranque relativo"
              valor={`día ${fmtNum(colocacion.inicioDias)} → ${fmtNum(colocacion.finDias)}`}
            />
          )}
        </dl>
      )}

      <div className="sep" />

      <EditorTramos
        duracionDias={caja.duracionDias ?? 0}
        tramos={caja.tramos}
        onCambio={(tramos) => onTramos(caja.id, tramos)}
        onGesto={onGesto}
      />

      <div className="sep" />

      <div className="col gap-4">
        <span className="field__label">Predecesoras ({caja.entradas.length})</span>
        {caja.entradas.length === 0 && (
          <div className="field__hint">
            Sin predecesoras: arranca al inicio del programa. Se ligan arrastrando de un
            anclaje de otra caja a uno de esta.
          </div>
        )}
        {caja.entradas.map((cable) => (
          <div key={cable.desde} className="col gap-2">
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              style={{ justifyContent: 'flex-start' }}
              onClick={() => onSeleccionar(cable.desde)}
              title="Ir a la predecesora"
            >
              {nombreCorto(porId.get(cable.desde))}
            </button>
            <div className="row gap-4">
              <select
                className="select"
                style={{ flex: 2 }}
                value={cable.tipo}
                aria-label={`Tipo de liga con ${nombreCorto(porId.get(cable.desde))}`}
                title={ayudaTipoDependencia(cable.tipo)}
                onChange={(e) => {
                  onGesto();
                  onTipoLiga(cable.desde, caja.id, e.target.value as TipoLiga);
                }}
              >
                {TIPOS_LIGA.map((tipo) => (
                  <option key={tipo} value={tipo}>
                    {tipo} · {etiquetaTipoDependencia(tipo)}
                  </option>
                ))}
              </select>
              <input
                className="input input--mono"
                style={{ flex: 1, minWidth: 64 }}
                type="number"
                step="0.5"
                value={cable.lagDias}
                aria-label={`Lag con ${nombreCorto(porId.get(cable.desde))}`}
                title="Días de desfase de la relación; puede ser negativo"
                onChange={(e) => {
                  onGesto();
                  onLag(cable.desde, caja.id, Number(e.target.value));
                }}
              />
              <button
                type="button"
                className="btn btn--ghost btn--sm btn--icon"
                aria-label={`Quitar la liga con ${nombreCorto(porId.get(cable.desde))}`}
                onClick={() => {
                  onGesto();
                  onDesconectar(cable.desde, caja.id);
                }}
              >
                <Trash2 size={13} aria-hidden />
              </button>
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
}

function Dato({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  return (
    <div className="row" style={{ justifyContent: 'space-between' }}>
      <dt className="text-mute">{etiqueta}</dt>
      <dd className="mono tnum">{valor}</dd>
    </div>
  );
}
