/**
 * El paramétrico de muro (F-22, D-645): cómo se construye el muro y qué capas de acabado lleva, con Sí/No por cara.
 *
 * - **Confinado**: con cadenas y castillos aún sin ubicar; para algo rápido.
 * - **Con cadena**: los castillos ya se conocen y se colocan; restan de los m² del muro.
 * - **Tabique**: sin cadenas ni castillos.
 *
 * Pretil y barda ya no son tipos: son la **ubicación** del muro, y el sillar es su **material** (0133). El muro puede elegir una
 * **plantilla** del Artefacto (tipo, material, ubicación y los elementos que lleva).
 *
 * Acabado: obra gris, obra blanca y pintura, interior y fachada. El revestimiento no es una capa aquí: es un concepto del
 * catálogo con su largo y su altura. Solo clasifica: no cambia lo que mide el muro.
 */

import type { ErrorApi } from '@/api/cliente';
import type { ClasificacionDeMuroPeticion } from '@/api/generado/modelo';
import {
  useCatalogoDelArtefactoApiV1MuroArtefactoCatalogoGet,
  useElegirPlantillaDelTrazoApiV1TrazosTrazoIdMuroPlantillaPut,
  useListarPlantillasApiV1MuroPlantillasGet,
} from '@/api/generado/artefacto-de-muros/artefacto-de-muros';
import {
  getVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGetQueryKey,
  useFijarClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionPut,
  useVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGet,
} from '@/api/generado/cuantificacion/cuantificacion';
import { queryClient } from '@/app/queryClient';

import { CambioDePlantilla } from './CambioDePlantilla';
import { ColocacionDeLaPlantilla } from './ColocacionDeLaPlantilla';
import { useState } from 'react';

export type TipoDeMuro = 'confinado' | 'con_cadena' | 'tabique';
export type Acabado = Record<'interior' | 'fachada', Record<'gris' | 'blanca' | 'pintura', boolean>>;

export const TIPOS_DE_MURO: readonly { clave: TipoDeMuro; nombre: string; ayuda: string }[] = [
  { clave: 'confinado', nombre: 'Confinado', ayuda: 'Sin plano estructural: la plantilla propone (estima) los castillos por regla; no se colocan en el plano.' },
  { clave: 'con_cadena', nombre: 'Con cadena', ayuda: 'Con plano estructural («muros y cadena»): los castillos reales se siembran uno por uno, cada uno de su tipo K, y restan de los m² del muro.' },
  { clave: 'tabique', nombre: 'Tabique', ayuda: 'Sin cadenas ni castillos.' },
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
  /** Al TRAZAR un muro: la plantilla con que nace (se elige, y sus castillos ubicados se colocan al guardarlo). Sin esto no se ofrece. */
  readonly plantillas?: readonly { readonly id: string; readonly nombre: string; readonly version: number; readonly validacion: string }[];
  readonly plantillaId?: string | null;
  readonly onPlantilla?: (id: string | null) => void;
}

export function ClasificacionDeMuro({ tipo, acabado, onTipo, onAcabado, ocupado = false, plantillas, plantillaId = null, onPlantilla }: Props) {
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
      {tipo && plantillas && onPlantilla && (
        <label className="mct__campo">
          Plantilla de muro
          <select
            className="input"
            aria-label="Plantilla del muro nuevo"
            value={plantillaId ?? ''}
            disabled={ocupado}
            onChange={(e) => onPlantilla(e.target.value || null)}
          >
            <option value="">Sin plantilla</option>
            {plantillas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre} · v{p.version}
                {p.validacion === 'validada' ? '' : ' (por validar)'}
              </option>
            ))}
          </select>
        </label>
      )}
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

/** En el detalle de un muro ya trazado: lee su clasificación y cambia el tipo, el material, la ubicación, la plantilla o una capa al momento. */
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
  const catalogo = useCatalogoDelArtefactoApiV1MuroArtefactoCatalogoGet();
  const plantillas = useListarPlantillasApiV1MuroPlantillasGet();
  const fijar = useFijarClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionPut<ErrorApi>();
  const elegir = useElegirPlantillaDelTrazoApiV1TrazosTrazoIdMuroPlantillaPut<ErrorApi>();
  // Cambiar una plantilla por otra pide ver antes qué cambia (la elección inicial y desligarla siguen siendo inmediatas).
  const [haciaId, setHaciaId] = useState<string | null>(null);
  const tipo = (consulta.data?.tipo ?? null) as TipoDeMuro | null;
  const material = consulta.data?.material ?? '';
  const ubicacion = consulta.data?.ubicacion ?? '';
  const plantillaId = consulta.data?.plantilla_id ?? '';
  const acabado = (consulta.data?.acabado as Acabado | null | undefined) ?? acabadoPorDefecto();
  const plantilla = (plantillas.data ?? []).find((p) => p.id === plantillaId);

  function refrescar() {
    void queryClient.invalidateQueries({
      queryKey: getVerClasificacionDeMuroApiV1TrazosTrazoIdMuroClasificacionGetQueryKey(trazoId),
    });
  }

  async function guardar(cambios: { tipo?: TipoDeMuro | null; material?: string; ubicacion?: string; acabado?: Acabado }, aviso: string) {
    const nuevoTipo = cambios.tipo === undefined ? tipo : cambios.tipo;
    try {
      await fijar.mutateAsync({
        trazoId,
        data: {
          tipo: nuevoTipo,
          material: nuevoTipo ? (cambios.material ?? material) || null : null,
          ubicacion: nuevoTipo ? (((cambios.ubicacion ?? ubicacion) || null) as ClasificacionDeMuroPeticion['ubicacion']) : null,
          acabado: nuevoTipo ? (cambios.acabado ?? acabado) : null,
        },
      });
      refrescar();
      onCambio(aviso);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo clasificar el muro.');
    }
  }

  async function elegirPlantilla(id: string) {
    if (plantillaId && id && id !== plantillaId) {
      setHaciaId(id);
      return;
    }
    setHaciaId(null);
    try {
      await elegir.mutateAsync({ trazoId, data: { plantilla_id: id || null } });
      refrescar();
      onCambio(id ? 'Plantilla de muro elegida.' : 'Muro sin plantilla.');
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo elegir la plantilla.');
    }
  }

  const ocupado = fijar.isPending || elegir.isPending || consulta.isLoading;
  return (
    <>
      <ClasificacionDeMuro
        tipo={tipo}
        acabado={acabado}
        ocupado={ocupado}
        onTipo={(t) => void guardar({ tipo: t }, t ? `Muro ${TIPOS_DE_MURO.find((x) => x.clave === t)?.nombre.toLowerCase()}.` : 'Muro sin tipo.')}
        onAcabado={(a) => void guardar({ acabado: a }, 'Acabado del muro.')}
      />
      {consulta.data?.tipo_por_confirmar && (
        <p className="text-xs mct__aviso" role="status">
          Este muro era «sillar»: se dejó confinado por prudencia. Confirma si es confinado o tabique.
        </p>
      )}
      {tipo && (
        <div className="clasificacion-muro__artefacto">
          <label className="mct__campo">
            Material del muro
            <select
              className="input"
              aria-label="Material del muro"
              value={material}
              disabled={ocupado}
              onChange={(e) => void guardar({ material: e.target.value }, 'Material del muro.')}
            >
              <option value="">Sin material</option>
              {(catalogo.data?.materiales ?? []).map((m) => (
                <option key={m.clave} value={m.clave}>
                  {m.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className="mct__campo">
            Ubicación del muro
            <select
              className="input"
              aria-label="Ubicación del muro"
              value={ubicacion}
              disabled={ocupado}
              onChange={(e) => void guardar({ ubicacion: e.target.value }, 'Ubicación del muro.')}
            >
              <option value="">Sin ubicación</option>
              {(catalogo.data?.ubicaciones ?? []).map((u) => (
                <option key={u.clave} value={u.clave}>
                  {u.nombre}
                </option>
              ))}
            </select>
          </label>
          <label className="mct__campo">
            Plantilla de muro
            <select
              className="input"
              aria-label="Plantilla de muro"
              value={haciaId ?? plantillaId}
              disabled={ocupado}
              onChange={(e) => void elegirPlantilla(e.target.value)}
            >
              <option value="">Sin plantilla</option>
              {(plantillas.data ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre} · v{p.version}
                  {p.validacion === 'validada' ? '' : ' (por validar)'}
                </option>
              ))}
              {plantillaId && !plantilla && <option value={plantillaId}>Una versión anterior</option>}
            </select>
          </label>
          {plantilla && plantilla.validacion !== 'validada' && (
            <p className="text-xs mct__aviso">La plantilla aún está por validar: es provisional.</p>
          )}
          {haciaId && (
            <CambioDePlantilla
              key={haciaId}
              trazoId={trazoId}
              haciaId={haciaId}
              onCancelar={() => setHaciaId(null)}
              onCambiado={(aviso) => {
                setHaciaId(null);
                refrescar();
                onCambio(aviso);
              }}
              onError={onError}
            />
          )}
          {plantillaId && <ColocacionDeLaPlantilla key={plantillaId} trazoId={trazoId} onCambio={onCambio} onError={onError} />}
        </div>
      )}
    </>
  );
}
