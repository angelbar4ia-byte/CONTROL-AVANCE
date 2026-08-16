/**
 * Alta de familia — `POST /api/v1/familias` (§11.2, solo Control de obra).
 *
 * La familia es un **árbol** (`parent_id`, §7.3) y es la que **siembra el
 * IVA** de sus materiales: §3.5 — "valor inicial derivado de la familia
 * (gravada → activada; Pétreos / Jardinería → desactivada); override por
 * material". Aquí se captura ese valor inicial; la tasa (16%) y qué familias
 * están exentas son configurables y viven en BD (§8.7), no en este
 * formulario.
 *
 * `aplica_a` separa familias de **materiales** de familias de **conceptos**
 * (§10.1): son dos catálogos distintos con el mismo árbol.
 */

import { useState, type FormEvent } from 'react';

import { useCrearFamiliaApiV1FamiliasPost } from '@/api/generado/catalogos/catalogos';
import type { FamiliaRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoCheck, CampoSelect, CampoTexto } from './Campos';
import { peticionFamilia, type FormularioFamilia } from './formulario';

const VACIO: FormularioFamilia = {
  clave: '',
  nombre: '',
  parentId: '',
  aplicaA: 'material',
  ivaAplica: true,
};

interface Props {
  readonly familias: readonly FamiliaRespuesta[];
  readonly onCerrar: () => void;
  readonly onCreada: () => void;
}

export function AltaFamilia({ familias, onCerrar, onCreada }: Props) {
  const [formulario, setFormulario] = useState<FormularioFamilia>(VACIO);
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const crear = useCrearFamiliaApiV1FamiliasPost<ErrorApi>({
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
    crear.mutate({ data: peticionFamilia(formulario) });
  }

  // El padre solo puede ser una familia del mismo lado del catálogo: una
  // familia de conceptos no cuelga de una de materiales (§10.1).
  const posiblesPadres = familias.filter(
    (familia) => (familia.aplica_a ?? 'material') === formulario.aplicaA,
  );

  return (
    <Modal titulo="Nueva familia" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoTexto
            id="familia-clave"
            etiqueta="Clave"
            valor={formulario.clave}
            onCambio={(clave) => setFormulario((f) => ({ ...f, clave }))}
            mono
            requerido
            pista="Única en el catálogo (§3.3)."
          />
          <CampoTexto
            id="familia-nombre"
            etiqueta="Nombre"
            valor={formulario.nombre}
            onCambio={(nombre) => setFormulario((f) => ({ ...f, nombre }))}
            requerido
            marcador="Pétreos"
          />
          <CampoSelect
            id="familia-aplica"
            etiqueta="Aplica a"
            valor={formulario.aplicaA}
            onCambio={(aplicaA) =>
              setFormulario((f) => ({ ...f, aplicaA, parentId: '' }))
            }
            opciones={[
              { valor: 'material', etiqueta: 'Materiales' },
              { valor: 'concepto', etiqueta: 'Conceptos' },
            ]}
            pista="Familias de materiales y de conceptos son catálogos distintos (§10.1)."
          />
          <CampoSelect
            id="familia-padre"
            etiqueta="Familia padre"
            valor={formulario.parentId}
            onCambio={(parentId) => setFormulario((f) => ({ ...f, parentId }))}
            opciones={posiblesPadres.map((familia) => ({
              valor: familia.id,
              etiqueta: `${familia.clave} · ${familia.nombre}`,
            }))}
            vacio="Sin padre (raíz del árbol)"
          />
          <CampoCheck
            id="familia-iva"
            etiqueta="Los materiales de esta familia llevan IVA"
            valor={formulario.ivaAplica}
            onCambio={(ivaAplica) => setFormulario((f) => ({ ...f, ivaAplica }))}
            pista="Valor inicial de sus materiales; cada uno puede sobrescribirlo (§3.5). Pétreos y Jardinería van desactivadas."
          />

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {crear.isPending ? 'Creando…' : 'Crear familia'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
