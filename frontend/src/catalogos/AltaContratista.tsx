/**
 * Alta de contratista — `POST /api/v1/contratistas` (§11.2, solo Control de
 * obra).
 *
 * §10.1 lo lista como catálogo compartido: "clave, nombre/razón social,
 * alias (mapeo), activo". Los **alias** no se capturan aquí: son mapeos de
 * archivos externos y se resuelven en la bandeja de pendientes (§10.3).
 *
 * La `calificacion` tampoco: la asigna la evaluación (§7.3, Workflow H), no
 * el alta.
 */

import { useState, type FormEvent } from 'react';

import { useCrearContratistaApiV1ContratistasPost } from '@/api/generado/catalogos/catalogos';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoTexto } from './Campos';
import { peticionContratista, type FormularioContratista } from './formulario';

const VACIO: FormularioContratista = {
  clave: '',
  razonSocial: '',
  rfc: '',
  contacto: '',
  telefono: '',
  email: '',
};

interface Props {
  readonly onCerrar: () => void;
  readonly onCreado: () => void;
}

export function AltaContratista({ onCerrar, onCreado }: Props) {
  const [formulario, setFormulario] = useState<FormularioContratista>(VACIO);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearContratistaApiV1ContratistasPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCreado();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const puedeEnviar =
    formulario.clave.trim() !== '' && formulario.razonSocial.trim() !== '' && !crear.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    crear.mutate({ data: peticionContratista(formulario) });
  }

  return (
    <Modal titulo="Nuevo contratista" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoTexto
            id="contratista-clave"
            etiqueta="Clave"
            valor={formulario.clave}
            onCambio={(clave) => setFormulario((f) => ({ ...f, clave }))}
            mono
            requerido
            pista="Única; las variantes de nombre se homologan contra ella (§3.3, §10.3)."
          />
          <CampoTexto
            id="contratista-razon"
            etiqueta="Razón social"
            valor={formulario.razonSocial}
            onCambio={(razonSocial) => setFormulario((f) => ({ ...f, razonSocial }))}
            requerido
          />
          <CampoTexto
            id="contratista-rfc"
            etiqueta="RFC"
            valor={formulario.rfc}
            onCambio={(rfc) => setFormulario((f) => ({ ...f, rfc }))}
            mono
          />
          <CampoTexto
            id="contratista-contacto"
            etiqueta="Contacto"
            valor={formulario.contacto}
            onCambio={(contacto) => setFormulario((f) => ({ ...f, contacto }))}
          />
          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="contratista-telefono"
                etiqueta="Teléfono"
                valor={formulario.telefono}
                onCambio={(telefono) => setFormulario((f) => ({ ...f, telefono }))}
                mono
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="contratista-email"
                etiqueta="Email"
                valor={formulario.email}
                onCambio={(email) => setFormulario((f) => ({ ...f, email }))}
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
            {crear.isPending ? 'Creando…' : 'Crear contratista'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
