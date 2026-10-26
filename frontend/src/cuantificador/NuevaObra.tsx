/**
 * Escenario «Nuevo» (cerebro WORKFLOWS.md §8.9; D-571, D-574): se entra por el cuantificador y la
 * obra se crea desde aquí, sin prototipo de dónde copiar.
 *
 * Se elige el **catálogo base de 1 o de 2 plantas** —los dos tipos de prototipo—: se forma
 * con la estructura y los conceptos de ese prototipo, **sin cantidades**. Crear la obra y su
 * presupuesto es un solo acto: aquí se crea y se genera. Las cantidades llegan midiendo, y en
 * esta obra lo que se mide **es** el presupuesto.
 */

import { useMemo, useState, type FormEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { Rol } from '@/api/generado/modelo';
import type { ClusterRespuesta, ProyectoRespuesta, UsuarioRespuesta } from '@/api/generado/modelo';
import { useGenerarObraApiV1ObrasObraIdGenerarPost } from '@/api/generado/obras/obras';
import {
  useCatalogosBaseApiV1CatalogosBaseGet,
  useCrearObraDesdeCatalogoBaseApiV1ObrasDesdeCatalogoBasePost,
} from '@/api/generado/partes/partes';
import {
  useListarClustersApiV1ClustersGet,
  useListarProyectosApiV1ProyectosGet,
} from '@/api/generado/proyectos/proyectos';
import { useListarUsuariosApiV1UsuariosGet } from '@/api/generado/usuarios/usuarios';
import { claveDeIdempotencia } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto } from '@/proyectos/Campos';
import { opcionesCluster } from '@/proyectos/AltaObra';
import { textoOpcional } from '@/proyectos/formulario';

interface Props {
  readonly onCerrar: () => void;
  /** La obra ya está creada y generada: se abre en el cuantificador. */
  readonly onCreada: (obraId: string) => void;
}

export function NuevaObra({ onCerrar, onCreada }: Props) {
  const [clusterId, setClusterId] = useState('');
  const [clave, setClave] = useState('');
  const [plantas, setPlantas] = useState<1 | 2>(1);
  const [residenteId, setResidenteId] = useState('');
  const [error, setError] = useState<string | null>(null);
  // Una clave por intento: un doble clic no deja dos obras.
  const idem = useMemo(claveDeIdempotencia, []);

  const proyectos = useListarProyectosApiV1ProyectosGet<ProyectoRespuesta[], ErrorApi>();
  const clusters = useListarClustersApiV1ClustersGet<ClusterRespuesta[], ErrorApi>();
  const catalogos = useCatalogosBaseApiV1CatalogosBaseGet();
  const usuarios = useListarUsuariosApiV1UsuariosGet<UsuarioRespuesta[], ErrorApi>({ rol: Rol.residente });
  const residentes = useMemo(
    () => (usuarios.data ?? []).filter((u) => u.estatus === 'activo'),
    [usuarios.data],
  );

  const generar = useGenerarObraApiV1ObrasObraIdGenerarPost<ErrorApi>({
    mutation: { onError: (e) => setError(`La obra se creó, pero no se pudo generar: ${e.message}`) },
  });
  const crear = useCrearObraDesdeCatalogoBaseApiV1ObrasDesdeCatalogoBasePost<ErrorApi>({
    mutation: {
      onError: (e) => setError(e.message),
      onSuccess: (obra) =>
        generar.mutate(
          { obraId: obra.obra_id, data: { modo_pago: 'destajo' } },
          { onSuccess: () => onCreada(obra.obra_id) },
        ),
    },
    request: { headers: { 'Idempotency-Key': idem } },
  });

  const elegido = (catalogos.data ?? []).find((c) => c.plantas === plantas);
  const puedeEnviar =
    clusterId !== '' && clave.trim() !== '' && elegido?.disponible === true && !crear.isPending && !generar.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    setError(null);
    crear.mutate({
      data: {
        cluster_id: clusterId,
        clave: clave.trim(),
        plantas,
        residente_id: textoOpcional(residenteId),
      },
    });
  }

  return (
    <Modal titulo="Nueva obra desde el cuantificador" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <p className="text-mute text-sm">
            Una obra cuyo proyecto es diferente de todos los prototipos. Se forma su catálogo con la estructura y
            los conceptos de un prototipo, <strong>sin cantidades</strong>: llegan midiendo, y lo que mides es el
            presupuesto.
          </p>
          {error && <ErrorBanner mensaje={error} />}
          <CampoSelect
            id="nueva-cluster"
            etiqueta="Cluster"
            valor={clusterId}
            onCambio={setClusterId}
            opciones={opcionesCluster(proyectos.data ?? [], clusters.data ?? [])}
            vacio="Selecciona un cluster"
            requerido
          />
          <CampoTexto
            id="nueva-clave"
            etiqueta="Clave"
            valor={clave}
            onCambio={setClave}
            mono
            requerido
            marcador="FRESNO 01"
            pista="CLUSTER + LOTE (§10.1)."
          />
          <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className="field__label">Catálogo base de cuantificación</legend>
            <div className="row gap-12" style={{ flexWrap: 'wrap' }}>
              {(catalogos.data ?? []).map((c) => (
                <label key={c.plantas} className="row gap-4" style={{ alignItems: 'flex-start' }}>
                  <input
                    type="radio"
                    name="nueva-plantas"
                    checked={plantas === c.plantas}
                    disabled={!c.disponible}
                    onChange={() => setPlantas(c.plantas as 1 | 2)}
                  />
                  <span className="col">
                    <span className="text-sm">{c.plantas === 1 ? '1 planta' : '2 plantas'}</span>
                    <span className="text-xs text-mute">
                      {c.disponible
                        ? `Plazo base ${c.plazo_base_semanas} semanas · de ${c.prototipo_clave} (${c.n_nodos} nodos)`
                        : 'Sin prototipo con estructura de dónde formarlo'}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <CampoSelect
            id="nueva-residente"
            etiqueta="Residente"
            valor={residenteId}
            onCambio={setResidenteId}
            opciones={residentes.map((r) => ({ valor: r.id, etiqueta: r.nombre }))}
            vacio="Sin residente por ahora"
          />
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending || generar.isPending ? 'Creando…' : 'Crear y empezar a medir'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
