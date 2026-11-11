/**
 * El paramétrico de muro (F-22, D-645): cómo se construye el muro y qué capas de acabado lleva, con Sí/No por cara.
 *
 * - **Confinado**: con cadenas y castillos aún sin ubicar; para algo rápido.
 * - **Con cadena**: los castillos ya se conocen y se colocan; restan de los m² del muro.
 * - **Tabique**: sin cadenas ni castillos. **Sillar**, **pretil** y **barda**: cada uno su propio driver del catálogo.
 *
 * Acabado: obra gris, obra blanca y pintura, interior y fachada. El revestimiento no es una capa aquí: es un concepto del
 * catálogo con su largo y su altura. Solo clasifica: no cambia lo que mide el muro.
 */

import type { ErrorApi } from '@/api/cliente';
import {
  getVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGetQueryKey,
  useFijarClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionPut,
  useVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import { queryClient } from '@/app/queryClient';

export type TipoDeMuro = 'confinado' | 'con_cadena' | 'tabique' | 'sillar' | 'pretil' | 'barda';
export type Acabado = Record<'interior' | 'fachada', Record<'gris' | 'blanca' | 'pintura', boolean>>;

export const TIPOS_DE_MURO: readonly { clave: TipoDeMuro; nombre: string; ayuda: string }[] = [
  { clave: 'confinado', nombre: 'Confinado', ayuda: 'Con cadenas y castillos aún sin ubicar: para algo rápido.' },
  { clave: 'con_cadena', nombre: 'Con cadena', ayuda: 'Los castillos ya se conocen: se colocan y restan de los m² del muro.' },
  { clave: 'tabique', nombre: 'Tabique', ayuda: 'Sin cadenas ni castillos.' },
  { clave: 'sillar', nombre: 'Sillar', ayuda: 'Muro de sillar.' },
  { clave: 'pretil', nombre: 'Pretil', ayuda: 'Muro de azotea.' },
  { clave: 'barda', nombre: 'Barda', ayuda: 'Muro perimetral.' },
];

const CAPAS = [
  ['gris', 'Obra gris'],
  ['blanca', 'Obra blanca'],
  ['pintura', 'Pintura'],
] as const;
const CARAS = [
  ['interior', 'Interior'],
  ['fachada', 'Fachada'],
] as const;

/** Nace con obra gris, obra blanca y pintura en Sí en las dos caras. */
export function acabadoPorDefecto(): Acabado {
  return {
    interior: { gris: true, blanca: true, pintura: true },
    fachada: { gris: true, blanca: true, pintura: true },
  };
}

interface Props {
  readonly tipo: TipoDeMuro | null;
  readonly acabado: Acabado;
  readonly onTipo: (tipo: TipoDeMuro | null) => void;
  readonly onAcabado: (acabado: Acabado) => void;
  readonly ocupado?: boolean;
}

export function ClasificacionDeMuro({ tipo, acabado, onTipo, onAcabado, ocupado = false }: Props) {
  const ayuda = TIPOS_DE_MURO.find((t) => t.clave === tipo)?.ayuda;
  return (
    <div className="clasificacion-muro">
      <div className="opciones__titulo">Tipo de muro</div>
      <div className="opciones__fila" role="group" aria-label="Tipo de muro">
        {TIPOS_DE_MURO.map((t) => (
          <button
            key={t.clave}
            type="button"
            className={tipo === t.clave ? 'chip is-active' : 'chip'}
            aria-pressed={tipo === t.clave}
            disabled={ocupado}
            title={t.ayuda}
            onClick={() => onTipo(tipo === t.clave ? null : t.clave)}
          >
            {t.nombre}
          </button>
        ))}
      </div>
      {ayuda && <p className="text-mute text-xs">{ayuda}</p>}
      {tipo && (
        <>
          <div className="opciones__titulo">Acabado</div>
          <table className="clasificacion-muro__acabado" aria-label="Acabado del muro por capa y cara">
            <thead>
              <tr>
                <th />
                {CARAS.map(([cara, nombre]) => (
                  <th key={cara}>{nombre}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {CAPAS.map(([capa, nombre]) => (
                <tr key={capa}>
                  <th scope="row">{nombre}</th>
                  {CARAS.map(([cara, nombreCara]) => (
                    <td key={cara}>
                      <input
                        type="checkbox"
                        aria-label={`${nombre}, ${nombreCara.toLowerCase()}`}
                        checked={acabado[cara][capa]}
                        disabled={ocupado}
                        onChange={(e) => onAcabado({ ...acabado, [cara]: { ...acabado[cara], [capa]: e.target.checked } })}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-mute text-xs">El revestimiento es un concepto del catálogo con su largo y su altura, no una capa.</p>
        </>
      )}
    </div>
  );
}

/** En el detalle de un muro ya trazado: lee su clasificación y cambia el tipo o una capa al momento. */
export function ClasificacionDelMuro({
  trazoId,
  onCambio,
  onError,
}: {
  readonly trazoId: string;
  readonly onCambio: (aviso: string) => void;
  readonly onError: (mensaje: string) => void;
}) {
  const consulta = useVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGet(trazoId);
  const fijar = useFijarClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionPut<ErrorApi>();
  const tipo = (consulta.data?.tipo ?? null) as TipoDeMuro | null;
  const acabado = (consulta.data?.acabado as Acabado | null | undefined) ?? acabadoPorDefecto();

  async function guardar(nuevoTipo: TipoDeMuro | null, nuevoAcabado: Acabado) {
    try {
      await fijar.mutateAsync({ trazoId, data: { tipo: nuevoTipo, acabado: nuevoTipo ? nuevoAcabado : null } });
      void queryClient.invalidateQueries({
        queryKey: getVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGetQueryKey(trazoId),
      });
      onCambio(nuevoTipo ? `Muro ${TIPOS_DE_MURO.find((t) => t.clave === nuevoTipo)?.nombre.toLowerCase()}.` : 'Muro sin tipo.');
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo clasificar el muro.');
    }
  }

  return (
    <ClasificacionDeMuro
      tipo={tipo}
      acabado={acabado}
      ocupado={fijar.isPending || consulta.isLoading}
      onTipo={(t) => void guardar(t, acabado)}
      onAcabado={(a) => void guardar(tipo, a)}
    />
  );
}
