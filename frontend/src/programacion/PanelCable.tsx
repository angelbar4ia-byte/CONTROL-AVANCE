/**
 * Inspector del cable seleccionado en el canvas (§7.5).
 *
 * ## Por qué existe
 *
 * Las acciones sobre una dependencia —quitarla, retiparla, moverle el lag— ya
 * vivían en el borrador y ya se llegaba a ellas desde el inspector de la caja,
 * pero **sólo por la sucesora**: había que saber cuál de las dos puntas del
 * cable es la que lo lista, seleccionarla, y buscar el renglón correcto entre
 * sus predecesoras. En el canvas el usuario está mirando el cable; que el gesto
 * tenga que empezar en otro lado es lo que el jefe de obra reportó como "falta
 * acción o botón para desconectar o cambiar de tipo de liga".
 *
 * Aquí no se duplica nada: se despachan las mismas acciones `desconectar`,
 * `ligar` y `lag` de `borrador.ts`, así que son deshacibles con Ctrl+Z igual
 * que si se hubieran hecho desde la caja, y siguen sin viajar al backend hasta
 * el único POST de guardado.
 *
 * ## Lo que cada acción puede romper
 *
 * Retipar y mover el lag no cambian el conjunto de aristas: el cable ya existía
 * y sigue apuntando en el mismo sentido, así que no pueden cerrar un ciclo.
 * **Invertir** sí puede —le da la vuelta a la flecha—, y por eso es la única de
 * las cuatro que se ofrece deshabilitada cuando cerraría uno, explicando por
 * qué en vez de dejar que el 422 aparezca al guardar (§6).
 */

import { ArrowLeftRight, Trash2 } from 'lucide-react';

import { fmtNum } from '@/lib/formato';
import { cerrariaCiclo } from './ciclos';
import {
  aristas,
  buscarCable,
  TIPOS_LIGA,
  type Borrador,
  type TipoLiga,
} from './grafo';
import { nombreCorto } from './planificacion';
import { ayudaTipoDependencia, etiquetaTipoDependencia } from './reglas';

interface Props {
  readonly borrador: Borrador;
  readonly desde: string;
  readonly hasta: string;
  readonly onTipoLiga: (desde: string, hasta: string, tipo: TipoLiga) => void;
  readonly onLag: (desde: string, hasta: string, lagDias: number) => void;
  readonly onDesconectar: (desde: string, hasta: string) => void;
  readonly onInvertir: (desde: string, hasta: string) => void;
  readonly onSeleccionarCaja: (cajaId: string) => void;
}

export function PanelCable({
  borrador,
  desde,
  hasta,
  onTipoLiga,
  onLag,
  onDesconectar,
  onInvertir,
  onSeleccionarCaja,
}: Props) {
  const porId = new Map(borrador.cajas.map((caja) => [caja.id, caja]));
  const cable = buscarCable(borrador, desde, hasta);

  if (cable === null) {
    return (
      <aside className="panel-prog__lado" aria-label="Dependencia">
        <div className="text-sm text-mute">
          Esa dependencia ya no existe; se quitó del borrador.
        </div>
      </aside>
    );
  }

  const predecesora = nombreCorto(porId.get(desde));
  const sucesora = nombreCorto(porId.get(hasta));
  // El cable actual no cuenta para la comprobación: el camino que se busca al
  // invertirlo sería él mismo.
  const restantes = aristas(borrador).filter(
    (arista) => !(arista.desde === desde && arista.hasta === hasta),
  );
  const invertirCierraCiclo = cerrariaCiclo(restantes, hasta, desde);
  const inversoYaExiste = buscarCable(borrador, hasta, desde) !== null;
  const puedeInvertir = !invertirCierraCiclo && !inversoYaExiste;

  return (
    <aside className="panel-prog__lado" aria-label={`Dependencia ${predecesora} → ${sucesora}`}>
      <div>
        <div className="page__eyebrow mono">Dependencia</div>
        <div className="text-sm text-mute">
          {etiquetaTipoDependencia(cable.tipo)} — {ayudaTipoDependencia(cable.tipo)}
        </div>
      </div>

      <div className="col gap-2">
        <span className="field__label">Predecesora</span>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          style={{ justifyContent: 'flex-start' }}
          onClick={() => onSeleccionarCaja(desde)}
          title="Ir a la predecesora"
        >
          {predecesora}
        </button>
        <span className="field__label">Sucesora</span>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          style={{ justifyContent: 'flex-start' }}
          onClick={() => onSeleccionarCaja(hasta)}
          title="Ir a la sucesora"
        >
          {sucesora}
        </button>
      </div>

      <div className="sep" />

      <div className="row gap-8" style={{ flexWrap: 'wrap' }}>
        <div className="field" style={{ flex: 2, minWidth: 150 }}>
          <label className="field__label" htmlFor="cable-tipo">
            Tipo de liga
          </label>
          <select
            id="cable-tipo"
            className="select"
            value={cable.tipo}
            title={ayudaTipoDependencia(cable.tipo)}
            onChange={(e) => onTipoLiga(desde, hasta, e.target.value as TipoLiga)}
          >
            {TIPOS_LIGA.map((tipo) => (
              <option key={tipo} value={tipo}>
                {tipo} · {etiquetaTipoDependencia(tipo)}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ flex: 1, minWidth: 84 }}>
          <label className="field__label" htmlFor="cable-lag">
            Lag (días)
          </label>
          <input
            id="cable-lag"
            className="input input--mono"
            type="number"
            step="0.5"
            value={cable.lagDias}
            title="Días de desfase de la relación; puede ser negativo"
            onChange={(e) => onLag(desde, hasta, Number(e.target.value))}
          />
        </div>
      </div>

      {cable.lagDias !== 0 && (
        <div className="field__hint">
          La sucesora se corre {fmtNum(cable.lagDias)} d respecto de lo que marca el tipo.
        </div>
      )}

      <div className="sep" />

      <div className="row gap-4" style={{ flexWrap: 'wrap' }}>
        <button
          type="button"
          className="btn btn--sm"
          disabled={!puedeInvertir}
          title={
            invertirCierraCiclo
              ? 'Invertirla cerraría un ciclo de precedencias: el backend rechazaría el programa completo (§6).'
              : inversoYaExiste
                ? 'Ya hay una dependencia en el sentido contrario entre estas dos actividades.'
                : 'Cambia el sentido de la flecha conservando tipo y lag'
          }
          onClick={() => onInvertir(desde, hasta)}
        >
          <ArrowLeftRight size={13} aria-hidden /> Invertir sentido
        </button>
        <button
          type="button"
          className="btn btn--sm btn--danger"
          title="Quitar la dependencia (Supr)"
          onClick={() => onDesconectar(desde, hasta)}
        >
          <Trash2 size={13} aria-hidden /> Desconectar
        </button>
      </div>

      <div className="field__hint">
        Todo esto vive en el borrador: Ctrl+Z lo deshace y nada viaja hasta guardar la
        versión (§7.5).
      </div>
    </aside>
  );
}
