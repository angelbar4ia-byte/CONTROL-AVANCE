/**
 * Alta de concepto — `POST /api/v1/conceptos` (§11.2, solo Control de obra).
 *
 * El `tipo` es lo que permite **anidar** (§7.3): un `auxiliar` o una
 * `matriz` son los conceptos que otros conceptos meten dentro de su
 * explosión. Es un invariante del §8.7 (los cuatro valores están en código),
 * por eso es un selector cerrado y no texto libre.
 *
 * La composición del APU no se captura aquí: el alta crea el concepto y su
 * explosión entra por el cargador de CPU (§10.6, `CABECERAS_CPU.xlsx`).
 */

import { useState, type FormEvent } from 'react';

import { useCrearConceptoApiV1ConceptosPost } from '@/api/generado/catalogos/catalogos';
import { TipoConcepto } from '@/api/generado/modelo';
import type { FamiliaRespuesta, UnidadRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoSelect, CampoTexto } from './Campos';
import { peticionConcepto, type FormularioConcepto } from './formulario';
import { etiquetaTipoConcepto } from './reglas';

const TIPOS: readonly TipoConcepto[] = [
  TipoConcepto.concepto,
  TipoConcepto.auxiliar,
  TipoConcepto.matriz,
  TipoConcepto.basico,
];

const VACIO: FormularioConcepto = {
  clave: '',
  descripcion: '',
  tipo: TipoConcepto.concepto,
  unidadId: '',
  familiaId: '',
};

interface Props {
  readonly unidades: readonly UnidadRespuesta[];
  readonly familias: readonly FamiliaRespuesta[];
  readonly onCerrar: () => void;
  readonly onCreado: () => void;
}

export function AltaConcepto({ unidades, familias, onCerrar, onCreado }: Props) {
  const [formulario, setFormulario] = useState<FormularioConcepto>(VACIO);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearConceptoApiV1ConceptosPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onCreado();
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const puedeEnviar =
    formulario.clave.trim() !== '' && formulario.descripcion.trim() !== '' && !crear.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    crear.mutate({ data: peticionConcepto(formulario) });
  }

  return (
    <Modal titulo="Nuevo concepto" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoTexto
            id="concepto-clave"
            etiqueta="Clave"
            valor={formulario.clave}
            onCambio={(clave) => setFormulario((f) => ({ ...f, clave }))}
            mono
            requerido
            marcador="EST-…"
            pista="Los conceptos usan el prefijo EST (§10.1)."
          />
          <CampoTexto
            id="concepto-descripcion"
            etiqueta="Descripción"
            valor={formulario.descripcion}
            onCambio={(descripcion) => setFormulario((f) => ({ ...f, descripcion }))}
            requerido
          />
          <CampoSelect
            id="concepto-tipo"
            etiqueta="Tipo"
            valor={formulario.tipo}
            onCambio={(tipo) => setFormulario((f) => ({ ...f, tipo: tipo as TipoConcepto }))}
            opciones={TIPOS.map((tipo) => ({
              valor: tipo,
              etiqueta: etiquetaTipoConcepto(tipo),
            }))}
            pista="Auxiliar y matriz son los que otros conceptos anidan en su explosión (§7.3)."
          />
          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoSelect
                id="concepto-unidad"
                etiqueta="Unidad"
                valor={formulario.unidadId}
                onCambio={(unidadId) => setFormulario((f) => ({ ...f, unidadId }))}
                opciones={unidades.map((unidad) => ({
                  valor: unidad.id,
                  etiqueta: `${unidad.clave} · ${unidad.nombre}`,
                }))}
                vacio="Sin unidad"
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoSelect
                id="concepto-familia"
                etiqueta="Familia"
                valor={formulario.familiaId}
                onCambio={(familiaId) => setFormulario((f) => ({ ...f, familiaId }))}
                opciones={familias.map((familia) => ({
                  valor: familia.id,
                  etiqueta: `${familia.clave} · ${familia.nombre}`,
                }))}
                vacio="Sin familia"
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
            {crear.isPending ? 'Creando…' : 'Crear concepto'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
