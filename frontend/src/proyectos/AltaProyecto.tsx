/**
 * Alta de proyecto — `POST /api/v1/proyectos` (§11.2, roles C y SI).
 *
 * Campos del §7.2: `clave`, `nombre`, `ubicacion`, `inicio`, `fin_estimado`.
 * La validación autoritativa (clave única §3.3, coherencia de fechas §7.2)
 * es del backend; aquí solo se marcan los obligatorios del contrato.
 */

import { useState, type FormEvent } from 'react';

import { useCrearProyectoApiV1ProyectosPost } from '@/api/generado/proyectos/proyectos';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoTexto } from './Campos';
import { textoOpcional } from './formulario';

interface Props {
  readonly onCerrar: () => void;
  readonly onCreado: () => void;
}

export function AltaProyecto({ onCerrar, onCreado }: Props) {
  const [clave, setClave] = useState('');
  const [nombre, setNombre] = useState('');
  const [ubicacion, setUbicacion] = useState('');
  const [inicio, setInicio] = useState('');
  const [finEstimado, setFinEstimado] = useState('');
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearProyectoApiV1ProyectosPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCreado();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const puedeEnviar = clave.trim() !== '' && nombre.trim() !== '' && !crear.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    crear.mutate({
      data: {
        clave: clave.trim(),
        nombre: nombre.trim(),
        ubicacion: textoOpcional(ubicacion),
        inicio: textoOpcional(inicio),
        fin_estimado: textoOpcional(finEstimado),
      },
    });
  }

  return (
    <Modal titulo="Nuevo proyecto" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoTexto
            id="proyecto-clave"
            etiqueta="Clave"
            valor={clave}
            onCambio={setClave}
            mono
            requerido
            pista="Clave única del proyecto (§3.3)."
          />
          <CampoTexto
            id="proyecto-nombre"
            etiqueta="Nombre"
            valor={nombre}
            onCambio={setNombre}
            requerido
          />
          <CampoTexto
            id="proyecto-ubicacion"
            etiqueta="Ubicación"
            valor={ubicacion}
            onCambio={setUbicacion}
          />
          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="proyecto-inicio"
                etiqueta="Inicio"
                valor={inicio}
                onCambio={setInicio}
                tipo="date"
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="proyecto-fin"
                etiqueta="Fin estimado"
                valor={finEstimado}
                onCambio={setFinEstimado}
                tipo="date"
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
            {crear.isPending ? 'Creando…' : 'Crear proyecto'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
