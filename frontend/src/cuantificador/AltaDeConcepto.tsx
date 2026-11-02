/**
 * Un concepto que nace desde el cuantificador (entrega 5): medir pide a veces algo que el catálogo
 * todavía no tiene. Se da de alta aquí y entra a la obra **sin cantidad** —llega midiendo, y lo
 * medido es el presupuesto—, como adicional. Sin botón de guardar: el concepto se crea en cuanto se
 * elige su unidad con la clave y la descripción puestas (o con Intro), y queda seleccionado.
 *
 * La unidad no es un adorno: decide el tipo de medición del concepto (m² área, m lineal, pza conteo).
 */

import { Plus, X } from 'lucide-react';
import { useState, type KeyboardEvent } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useListarEtapasApiV1EtapasGet, useListarUnidadesApiV1UnidadesGet } from '@/api/generado/catalogos/catalogos';
import { useCrearConceptoEnLaObraApiV1ObrasObraIdConceptosNuevosPost } from '@/api/generado/partes/partes';

interface Props {
  readonly obraId: string;
  /** Ya creado: el árbol se vuelve a leer y el concepto nuevo queda activo. */
  readonly onCreado: (actividadId: string, clave: string) => void;
  readonly onError: (mensaje: string) => void;
}

export function AltaDeConcepto({ obraId, onCreado, onError }: Props) {
  const [abierto, setAbierto] = useState(false);
  const [clave, setClave] = useState('');
  const [descripcion, setDescripcion] = useState('');
  const [etapaId, setEtapaId] = useState('');
  const [unidadId, setUnidadId] = useState('');
  const unidades = useListarUnidadesApiV1UnidadesGet(undefined, { query: { enabled: abierto, staleTime: 60_000 } });
  const etapas = useListarEtapasApiV1EtapasGet({ query: { enabled: abierto, staleTime: 60_000 } });
  const crear = useCrearConceptoEnLaObraApiV1ObrasObraIdConceptosNuevosPost<ErrorApi>();

  const reiniciar = () => {
    setClave('');
    setDescripcion('');
    setEtapaId('');
    setUnidadId('');
  };

  async function crearYa(unidad: string) {
    if (clave.trim() === '' || descripcion.trim() === '' || unidad === '' || crear.isPending) return;
    try {
      const r = await crear.mutateAsync({
        obraId,
        data: {
          clave: clave.trim(),
          descripcion: descripcion.trim(),
          unidad_id: unidad,
          etapa_id: etapaId === '' ? undefined : etapaId,
        },
      });
      reiniciar();
      setAbierto(false);
      onCreado(r.actividad_id, r.clave);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'No se pudo crear el concepto.');
      setUnidadId('');
    }
  }

  const alIntro = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      void crearYa(unidadId);
    }
  };

  if (!abierto) {
    return (
      <button
        type="button"
        className="btn btn--ghost btn--sm"
        aria-label="Nuevo concepto"
        onClick={() => setAbierto(true)}
      >
        <Plus size={13} aria-hidden /> Concepto
      </button>
    );
  }

  return (
    <form
      className="alta-concepto"
      aria-label="Nuevo concepto"
      onSubmit={(e) => e.preventDefault()}
    >
      <div className="alta-concepto__titulo">
        <span>Nuevo concepto</span>
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          aria-label="Cerrar nuevo concepto"
          onClick={() => {
            reiniciar();
            setAbierto(false);
          }}
        >
          <X size={13} aria-hidden />
        </button>
      </div>
      <label>
        Clave
        <input value={clave} maxLength={60} onChange={(e) => setClave(e.target.value)} onKeyDown={alIntro} />
      </label>
      <label>
        Descripción
        <input value={descripcion} onChange={(e) => setDescripcion(e.target.value)} onKeyDown={alIntro} />
      </label>
      <label>
        Etapa
        <select value={etapaId} onChange={(e) => setEtapaId(e.target.value)}>
          <option value="">Suelto (sin etapa)</option>
          {(etapas.data ?? []).map((et) => (
            <option key={et.id} value={et.id}>
              {et.clave} · {et.descripcion}
            </option>
          ))}
        </select>
      </label>
      <label>
        Unidad
        <select
          value={unidadId}
          disabled={crear.isPending}
          onChange={(e) => {
            setUnidadId(e.target.value);
            void crearYa(e.target.value);
          }}
        >
          <option value="">Elige para crear…</option>
          {(unidades.data ?? []).map((u) => (
            <option key={u.id} value={u.id}>
              {u.clave} · {u.nombre}
            </option>
          ))}
        </select>
      </label>
      <p className="text-mute text-sm" style={{ margin: 0 }}>
        Se crea al elegir la unidad; llega sin cantidad y se mide en el plano.
      </p>
    </form>
  );
}
