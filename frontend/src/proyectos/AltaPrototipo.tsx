/**
 * Alta de prototipo (modelo de casa) — `POST /api/v1/prototipos` (§11.2,
 * roles C y SI).
 *
 * Campos del §7.2: `proyecto_id`, `clave`, `nombre`, `m2`, `niveles`,
 * `recamaras`. El prototipo es la raíz del árbol que recorre el Workflow A
 * (§11.3 A.2), así que sin él una obra no puede generar actividades.
 */

import { useState, type FormEvent } from 'react';

import { useCrearPrototipoApiV1PrototiposPost } from '@/api/generado/proyectos/proyectos';
import type { ProyectoRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto } from './Campos';
import { numeroOpcional } from './formulario';

interface Props {
  readonly proyectos: readonly ProyectoRespuesta[];
  readonly proyectoInicial?: string;
  readonly onCerrar: () => void;
  readonly onCreado: () => void;
}

export function AltaPrototipo({ proyectos, proyectoInicial = '', onCerrar, onCreado }: Props) {
  const [proyectoId, setProyectoId] = useState(proyectoInicial);
  const [clave, setClave] = useState('');
  const [nombre, setNombre] = useState('');
  const [m2, setM2] = useState('');
  const [niveles, setNiveles] = useState('');
  const [recamaras, setRecamaras] = useState('');
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearPrototipoApiV1PrototiposPost<ErrorApi>({
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
      data: {
        proyecto_id: proyectoId,
        clave: clave.trim(),
        nombre: nombre.trim(),
        m2: numeroOpcional(m2),
        niveles: numeroOpcional(niveles),
        recamaras: numeroOpcional(recamaras),
      },
    });
  }

  return (
    <Modal titulo="Nuevo prototipo" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoSelect
            id="prototipo-proyecto"
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
            id="prototipo-clave"
            etiqueta="Clave"
            valor={clave}
            onCambio={setClave}
            mono
            requerido
            marcador="CAS-…"
            pista="Los prototipos usan el prefijo CAS (§10.1)."
          />
          <CampoTexto
            id="prototipo-nombre"
            etiqueta="Nombre"
            valor={nombre}
            onCambio={setNombre}
            requerido
          />
          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="prototipo-m2"
                etiqueta="m²"
                valor={m2}
                onCambio={setM2}
                tipo="number"
                mono
                paso="any"
                minimo="0"
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="prototipo-niveles"
                etiqueta="Niveles"
                valor={niveles}
                onCambio={setNiveles}
                tipo="number"
                mono
                paso="1"
                minimo="0"
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="prototipo-recamaras"
                etiqueta="Recámaras"
                valor={recamaras}
                onCambio={setRecamaras}
                tipo="number"
                mono
                paso="1"
                minimo="0"
              />
            </div>
          </div>

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending ? 'Creando…' : 'Crear prototipo'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
