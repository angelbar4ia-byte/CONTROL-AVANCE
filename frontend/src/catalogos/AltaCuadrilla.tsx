/**
 * Alta de cuadrilla — `POST /api/v1/cuadrillas` (§11.2, solo Control de obra).
 *
 * Alta manual **mínima** (clave, nombre, unidad): la composición y el PU
 * versionado se cargan por archivo (`CABECERAS_CUADRILLAS.xlsx`, §10.6,
 * pantalla de Cargas de datos), no aquí. Esta pantalla es para dar de alta
 * una cuadrilla a mano antes de que el archivo la referencie, o para las que
 * nunca llevan destajo con composición capturada.
 */

import { useState, type FormEvent } from 'react';

import { useCrearCuadrillaApiV1CuadrillasPost } from '@/api/generado/catalogos/catalogos';
import type { UnidadRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto } from './Campos';
import { peticionCuadrilla, type FormularioCuadrilla } from './formulario';

const VACIO: FormularioCuadrilla = { clave: '', nombre: '', unidadId: '' };

interface Props {
  readonly unidades: readonly UnidadRespuesta[];
  readonly onCerrar: () => void;
  readonly onCreada: () => void;
}

export function AltaCuadrilla({ unidades, onCerrar, onCreada }: Props) {
  const [formulario, setFormulario] = useState<FormularioCuadrilla>(VACIO);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearCuadrillaApiV1CuadrillasPost<ErrorApi>({
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
    crear.mutate({ data: peticionCuadrilla(formulario) });
  }

  return (
    <Modal titulo="Nueva cuadrilla" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoTexto
            id="cuadrilla-clave"
            etiqueta="Clave"
            valor={formulario.clave}
            onCambio={(clave) => setFormulario((f) => ({ ...f, clave }))}
            mono
            requerido
            marcador="CUA0001"
            pista="Única en el catálogo; es la que manda en todo cruce (§3.3)."
          />
          <CampoTexto
            id="cuadrilla-nombre"
            etiqueta="Nombre"
            valor={formulario.nombre}
            onCambio={(nombre) => setFormulario((f) => ({ ...f, nombre }))}
            requerido
            marcador="Oficial albañil + ayudante"
          />
          <CampoSelect
            id="cuadrilla-unidad"
            etiqueta="Unidad del PU"
            valor={formulario.unidadId}
            onCambio={(unidadId) => setFormulario((f) => ({ ...f, unidadId }))}
            opciones={unidades.map((unidad) => ({
              valor: unidad.id,
              etiqueta: `${unidad.clave} · ${unidad.nombre}`,
            }))}
            vacio="Sin definir"
            pista="A qué se refiere su precio unitario (p.ej. jornal, §10.6)."
          />

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending ? 'Creando…' : 'Crear cuadrilla'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
