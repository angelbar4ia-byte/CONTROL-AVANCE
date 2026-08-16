/**
 * Alta de cluster (manzana) — `POST /api/v1/clusters` (§11.2, roles C y SI).
 *
 * Campos del §7.2: `proyecto_id`, `clave`, `nombre`. El cluster siempre
 * cuelga de un proyecto, así que el select de proyecto es obligatorio.
 */

import { useState, type FormEvent } from 'react';

import { useCrearClusterApiV1ClustersPost } from '@/api/generado/proyectos/proyectos';
import type { ProyectoRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto } from './Campos';

interface Props {
  readonly proyectos: readonly ProyectoRespuesta[];
  /** Proyecto preseleccionado (el del filtro o el nodo abierto). */
  readonly proyectoInicial?: string;
  readonly onCerrar: () => void;
  readonly onCreado: () => void;
}

export function AltaCluster({ proyectos, proyectoInicial = '', onCerrar, onCreado }: Props) {
  const [proyectoId, setProyectoId] = useState(proyectoInicial);
  const [clave, setClave] = useState('');
  const [nombre, setNombre] = useState('');
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearClusterApiV1ClustersPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCreado();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const puedeEnviar =
    proyectoId !== '' && clave.trim() !== '' && nombre.trim() !== '' && !crear.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    crear.mutate({
      data: { proyecto_id: proyectoId, clave: clave.trim(), nombre: nombre.trim() },
    });
  }

  return (
    <Modal titulo="Nuevo cluster" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoSelect
            id="cluster-proyecto"
            etiqueta="Proyecto"
            valor={proyectoId}
            onCambio={setProyectoId}
            opciones={proyectos.map((proyecto) => ({
              valor: proyecto.id,
              etiqueta: `${proyecto.clave} · ${proyecto.nombre}`,
            }))}
            vacio="Selecciona un proyecto"
            requerido
          />
          <CampoTexto
            id="cluster-clave"
            etiqueta="Clave"
            valor={clave}
            onCambio={setClave}
            mono
            requerido
            pista="Prefijo de la clave de obra: CLUSTER + LOTE (§10.1)."
          />
          <CampoTexto
            id="cluster-nombre"
            etiqueta="Nombre (manzana)"
            valor={nombre}
            onCambio={setNombre}
            requerido
          />

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending ? 'Creando…' : 'Crear cluster'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
