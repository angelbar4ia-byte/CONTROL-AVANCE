/**
 * Los elementos con peso (migración 0089): el castillo K1, la varilla 3/8. Un elemento dice cuánto
 * pesa por pieza, por metro o por m²; una medición con ese elemento, asignada a un concepto en kg o
 * ton «con el peso», suma cantidad × peso. Control de obra y Costos ponen el peso (cambia cantidades de
 * presupuesto); el resto los ve.
 *
 * **No hay botones de guardar**: cada cambio —el nombre, el peso— llega a la API al salir del campo o
 * al dar Enter, y la fila nueva se crea sola cuando ya tiene nombre y peso. Al cambiar un peso, lo
 * asignado con él se rehace en el servidor.
 */

import { Trash2 } from 'lucide-react';
import { useState, type KeyboardEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import {
  useActualizarElementoApiV1ElementosElementoIdPatch,
  useCrearElementoApiV1ElementosPost,
  useEliminarElementoApiV1ElementosElementoIdDelete,
} from '@/api/generado/mediciones/mediciones';
import type { ElementoRespuesta } from '@/api/generado/modelo';
import { numeroTecleado } from './volumen';
import { NOMBRE_DE_TIPO_DE_MEDICION, type TipoDeMedicionSombra } from './mediciones';

/** kg por qué: la unidad del peso de cada tipo. */
export const UNIDAD_DEL_PESO: Readonly<Record<TipoDeMedicionSombra, string>> = {
  conteo: 'kg/pza',
  lineal: 'kg/m',
  area: 'kg/m²',
};

interface Props {
  readonly elementos: readonly ElementoRespuesta[];
  readonly puedePonerPeso: boolean;
  readonly onCambio: (aviso?: string) => void;
  readonly onError: (mensaje: string) => void;
}

function enEnter(e: KeyboardEvent<HTMLInputElement>) {
  if (e.key === 'Enter') e.currentTarget.blur();
}

export function PanelDeElementos({ elementos, puedePonerPeso, onCambio, onError }: Props) {
  const crear = useCrearElementoApiV1ElementosPost<ErrorApi>();
  const actualizar = useActualizarElementoApiV1ElementosElementoIdPatch<ErrorApi>();
  const eliminar = useEliminarElementoApiV1ElementosElementoIdDelete<ErrorApi>();
  const [nuevo, setNuevo] = useState({ nombre: '', tipo: 'conteo' as TipoDeMedicionSombra, peso: '' });
  const [pesos, setPesos] = useState<Readonly<Record<string, string>>>({});
  const [nombres, setNombres] = useState<Readonly<Record<string, string>>>({});

  async function guardarPeso(e: ElementoRespuesta) {
    const texto = pesos[e.id];
    if (texto === undefined) return;
    const peso = numeroTecleado(texto);
    setPesos(({ [e.id]: _quitado, ...resto }) => resto);
    if (!(peso > 0)) {
      onError('El peso debe ser un número mayor que cero.');
      return;
    }
    if (peso === Number(e.peso_kg)) return;
    try {
      await actualizar.mutateAsync({ elementoId: e.id, data: { peso_kg: String(peso) } });
      onCambio(`Peso de «${e.nombre}»: ${peso} ${UNIDAD_DEL_PESO[e.tipo]}. Lo asignado con su peso se recalculó.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo cambiar el peso.');
    }
  }

  async function guardarNombre(e: ElementoRespuesta) {
    const texto = nombres[e.id];
    if (texto === undefined) return;
    setNombres(({ [e.id]: _quitado, ...resto }) => resto);
    if (texto.trim() === '' || texto.trim() === e.nombre) return;
    try {
      await actualizar.mutateAsync({ elementoId: e.id, data: { nombre: texto.trim() } });
      onCambio(`Elemento renombrado a «${texto.trim()}».`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo renombrar.');
    }
  }

  async function borrar(e: ElementoRespuesta) {
    try {
      await eliminar.mutateAsync({ elementoId: e.id });
      onCambio(`Elemento «${e.nombre}» borrado.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo borrar el elemento.');
    }
  }

  /** La fila nueva se crea sola cuando ya tiene nombre y peso y se sale de ella. */
  async function crearSiEstaCompleta() {
    const peso = numeroTecleado(nuevo.peso);
    if (nuevo.nombre.trim() === '' || !(peso > 0) || crear.isPending) return;
    try {
      await crear.mutateAsync({ data: { nombre: nuevo.nombre.trim(), tipo: nuevo.tipo, peso_kg: String(peso) } });
      setNuevo({ nombre: '', tipo: nuevo.tipo, peso: '' });
      onCambio(`Elemento «${nuevo.nombre.trim()}» creado.`);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear el elemento.');
    }
  }

  return (
    <details className="elementos" open>
      <summary>
        Elementos con peso <span className="estacion__contador">{elementos.length}</span>
      </summary>
      <p className="text-mute text-xs elementos__ayuda">
        K1 pesa tanto por pieza; una medición con ese elemento alimenta un concepto en kg o ton con su peso.
        {puedePonerPeso ? ' Los cambios se guardan solos.' : ' El peso lo ponen Control de obra y Costos.'}
      </p>
      <ul className="elementos__lista" aria-label="Elementos con peso">
        {elementos.map((e) => (
          <li key={e.id} className="elementos__fila">
            {puedePonerPeso ? (
              <input
                className="input elementos__nombre"
                aria-label={`Nombre del elemento ${e.nombre}`}
                value={nombres[e.id] ?? e.nombre}
                onChange={(ev) => setNombres({ ...nombres, [e.id]: ev.target.value })}
                onBlur={() => void guardarNombre(e)}
                onKeyDown={enEnter}
              />
            ) : (
              <span className="elementos__nombre">{e.nombre}</span>
            )}
            <span className="badge badge--outline">{NOMBRE_DE_TIPO_DE_MEDICION[e.tipo]}</span>
            {puedePonerPeso ? (
              <input
                className="input elementos__peso"
                aria-label={`Peso de ${e.nombre} (${UNIDAD_DEL_PESO[e.tipo]})`}
                inputMode="decimal"
                value={pesos[e.id] ?? String(Number(e.peso_kg))}
                onChange={(ev) => setPesos({ ...pesos, [e.id]: ev.target.value })}
                onBlur={() => void guardarPeso(e)}
                onKeyDown={enEnter}
              />
            ) : (
              <span className="mono">{Number(e.peso_kg)}</span>
            )}
            <span className="text-mute text-xs">{UNIDAD_DEL_PESO[e.tipo]}</span>
            {puedePonerPeso && (
              <button
                type="button"
                className="btn-icono btn-icono--chico btn-icono--peligro"
                aria-label={`Borrar el elemento ${e.nombre}`}
                title={e.n_mediciones > 0 ? 'Lo usan mediciones: quedarán sin elemento' : 'Borrar'}
                onClick={() => void borrar(e)}
              >
                <Trash2 size={13} aria-hidden />
              </button>
            )}
          </li>
        ))}
        {puedePonerPeso && (
          <li
            className="elementos__fila elementos__fila--nueva"
            aria-label="Elemento nuevo"
            onBlur={(ev) => {
              // Se crea al salir de la fila (no al pasar de un campo a otro de ella).
              if (!ev.currentTarget.contains(ev.relatedTarget as Node | null)) void crearSiEstaCompleta();
            }}
          >
            <input
              className="input elementos__nombre"
              placeholder="Castillo K1…"
              aria-label="Nombre del elemento nuevo"
              value={nuevo.nombre}
              onChange={(ev) => setNuevo({ ...nuevo, nombre: ev.target.value })}
              onKeyDown={enEnter}
            />
            <select
              className="select elementos__tipo"
              aria-label="Tipo del elemento nuevo"
              value={nuevo.tipo}
              onChange={(ev) => setNuevo({ ...nuevo, tipo: ev.target.value as TipoDeMedicionSombra })}
            >
              <option value="conteo">por pieza</option>
              <option value="lineal">por metro</option>
              <option value="area">por m²</option>
            </select>
            <input
              className="input elementos__peso"
              placeholder="38"
              inputMode="decimal"
              aria-label={`Peso del elemento nuevo (${UNIDAD_DEL_PESO[nuevo.tipo]})`}
              value={nuevo.peso}
              onChange={(ev) => setNuevo({ ...nuevo, peso: ev.target.value })}
              onKeyDown={enEnter}
            />
            <span className="text-mute text-xs">{UNIDAD_DEL_PESO[nuevo.tipo]}</span>
          </li>
        )}
      </ul>
    </details>
  );
}
