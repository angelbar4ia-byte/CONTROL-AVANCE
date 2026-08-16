/**
 * Alta de unidad — `POST /api/v1/unidades` (§11.2, solo Control de obra).
 *
 * `Unidad` es **semilla editable** (§8.7): el código trae el valor por
 * defecto, la lista viva vive en BD y el usuario la extiende desde
 * Configuración sin tocar código. Por eso esta pantalla existe.
 *
 * Los **sinónimos** son el mecanismo del §3.5 (`pza→PZ`, `m2→M2`): alias que
 * cruzan a la misma unidad al homologar (§10.3).
 */

import { useState, type FormEvent } from 'react';

import { useCrearUnidadApiV1UnidadesPost } from '@/api/generado/catalogos/catalogos';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoArea, CampoTexto } from './Campos';
import { peticionUnidad, type FormularioUnidad } from './formulario';

const VACIO: FormularioUnidad = { clave: '', nombre: '', sinonimos: '', factor: '' };

interface Props {
  readonly onCerrar: () => void;
  readonly onCreada: () => void;
}

export function AltaUnidad({ onCerrar, onCreada }: Props) {
  const [formulario, setFormulario] = useState<FormularioUnidad>(VACIO);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearUnidadApiV1UnidadesPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCreada();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const puedeEnviar =
    formulario.clave.trim() !== '' && formulario.nombre.trim() !== '' && !crear.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    crear.mutate({ data: peticionUnidad(formulario) });
  }

  return (
    <Modal titulo="Nueva unidad" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoTexto
            id="unidad-clave"
            etiqueta="Clave"
            valor={formulario.clave}
            onCambio={(clave) => setFormulario((f) => ({ ...f, clave }))}
            mono
            requerido
            marcador="M2"
            pista="Única en el catálogo; es la que manda en todo cruce (§3.3)."
          />
          <CampoTexto
            id="unidad-nombre"
            etiqueta="Nombre"
            valor={formulario.nombre}
            onCambio={(nombre) => setFormulario((f) => ({ ...f, nombre }))}
            requerido
            marcador="Metro cuadrado"
          />
          <CampoArea
            id="unidad-sinonimos"
            etiqueta="Sinónimos"
            valor={formulario.sinonimos}
            onCambio={(sinonimos) => setFormulario((f) => ({ ...f, sinonimos }))}
            marcador={'m2\nmts2'}
            pista="Uno por línea o separados por coma. Alias que cruzan a esta unidad (§3.5, §10.3)."
          />
          <CampoTexto
            id="unidad-factor"
            etiqueta="Factor de conversión"
            valor={formulario.factor}
            onCambio={(factor) => setFormulario((f) => ({ ...f, factor }))}
            tipo="number"
            mono
            paso="any"
            minimo="0"
            pista="Equivalencia o presentación; se define al homologar (§3.5)."
          />

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending ? 'Creando…' : 'Crear unidad'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
