/**
 * Alta de insumo o de material — `POST /api/v1/insumos` y `/materiales`
 * (§11.2, solo Control de obra).
 *
 * Es un solo formulario porque es una sola entidad: §7.3 dice "**Material** =
 * `Insumo` con `tipo = material`", y el contrato lo repite ("`POST
 * /materiales` — mismo cuerpo, sin `tipo`: es siempre `material`"). El tipo
 * lo fija la pestaña desde la que se abre (Materiales, Mano de obra,
 * Equipo, Herramienta, Subcontrato) — no se elige aquí, así que Materiales
 * usa esa ruta y las demás usan la genérica con `tipo` fijo.
 *
 * El **IVA** tiene tres estados, no dos: heredar de la familia (`null` en el
 * contrato), gravar u exentar como override (§3.5).
 */

import { useState, type FormEvent } from 'react';

import {
  useCrearInsumoApiV1InsumosPost,
  useCrearMaterialApiV1MaterialesPost,
} from '@/api/generado/catalogos/catalogos';
import { TipoInsumo } from '@/api/generado/modelo';
import type { FamiliaRespuesta, UnidadRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { CampoIva, CampoSelect, CampoTexto } from './Campos';
import { peticionInsumo, peticionMaterial, type FormularioInsumo } from './formulario';

interface Props {
  readonly unidades: readonly UnidadRespuesta[];
  readonly familias: readonly FamiliaRespuesta[];
  /** El tipo lo fija la pestaña de origen (§7.3); `material` usa
   * `POST /materiales`, el resto `POST /insumos` con este `tipo`. */
  readonly tipoFijo: TipoInsumo;
  /** Título del modal, p.ej. "Nueva mano de obra" — ya en el género
   * correcto (Catálogos.tsx lo resuelve, aquí no se adivina gramática). */
  readonly titulo: string;
  readonly onCerrar: () => void;
  readonly onCreado: () => void;
}

export function AltaInsumo({ unidades, familias, tipoFijo, titulo, onCerrar, onCreado }: Props) {
  const [formulario, setFormulario] = useState<FormularioInsumo>({
    clave: '',
    descripcion: '',
    tipo: tipoFijo,
    unidadId: '',
    familiaId: '',
    costoBase: '',
    iva: '',
    factorConversion: '',
  });
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  function alFallar(err: ErrorApi) {
    setError({ mensaje: err.message, campo: err.campo });
  }

  function alLograr() {
    setError(null);
    onCreado();
  }

  const crearInsumo = useCrearInsumoApiV1InsumosPost<ErrorApi>({
    mutation: { onSuccess: alLograr, onError: alFallar },
  });

  const crearMaterial = useCrearMaterialApiV1MaterialesPost<ErrorApi>({
    mutation: { onSuccess: alLograr, onError: alFallar },
  });

  const enviando = crearInsumo.isPending || crearMaterial.isPending;
  const puedeEnviar =
    formulario.clave.trim() !== '' && formulario.descripcion.trim() !== '' && !enviando;
  const tituloBoton = titulo.replace(/^Nuevo\b/, 'Crear').replace(/^Nueva\b/, 'Crear');

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;

    if (tipoFijo === TipoInsumo.material) {
      crearMaterial.mutate({ data: peticionMaterial(formulario) });
      return;
    }
    crearInsumo.mutate({ data: peticionInsumo(formulario) });
  }

  const familia = familias.find((f) => f.id === formulario.familiaId);

  return (
    <Modal titulo={titulo} onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <CampoTexto
            id="insumo-clave"
            etiqueta="Clave"
            valor={formulario.clave}
            onCambio={(clave) => setFormulario((f) => ({ ...f, clave }))}
            mono
            requerido
            pista="Única en el catálogo; es la que cruza con almacén y con el APU (§3.3, §10.6)."
          />
          <CampoTexto
            id="insumo-descripcion"
            etiqueta="Descripción"
            valor={formulario.descripcion}
            onCambio={(descripcion) => setFormulario((f) => ({ ...f, descripcion }))}
            requerido
          />

          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoSelect
                id="insumo-unidad"
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
                id="insumo-familia"
                etiqueta="Familia"
                valor={formulario.familiaId}
                onCambio={(familiaId) => setFormulario((f) => ({ ...f, familiaId }))}
                opciones={familias.map((f) => ({
                  valor: f.id,
                  etiqueta: `${f.clave} · ${f.nombre}`,
                }))}
                vacio="Sin familia"
              />
            </div>
          </div>

          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="insumo-costo"
                etiqueta="Costo base"
                valor={formulario.costoBase}
                onCambio={(costoBase) => setFormulario((f) => ({ ...f, costoBase }))}
                tipo="number"
                mono
                paso="any"
                minimo="0"
                pista="Precio de catálogo. El costo vigente lo actualiza el almacén (§10.5)."
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="insumo-factor"
                etiqueta="Factor de conversión"
                valor={formulario.factorConversion}
                onCambio={(factorConversion) =>
                  setFormulario((f) => ({ ...f, factorConversion }))
                }
                tipo="number"
                mono
                paso="any"
                minimo="0"
              />
            </div>
          </div>

          <CampoIva
            id="insumo-iva"
            valor={formulario.iva}
            onCambio={(iva) => setFormulario((f) => ({ ...f, iva }))}
            heredado={familia?.iva_aplica ?? null}
          />

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {enviando ? 'Creando…' : tituloBoton}
          </button>
        </div>
      </form>
    </Modal>
  );
}
