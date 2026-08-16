/**
 * Publicar una versión nueva del CPU — `POST /conceptos/{id}/cpu` (§11.2,
 * solo Control de obra).
 *
 * Lo normal es publicar **sin capturar precio**: el backend explota el
 * concepto y guarda lo que salga, que es lo que dice el contrato ("si se
 * omite —lo normal—, el CPU se calcula de la explosión del concepto §7.3").
 * El precio explícito existe para el caso en que el APU no está cargado y
 * hay que fijar un número a mano; entonces van los dos —total y destajo—,
 * porque el §7.3 pide el desglose completo.
 *
 * Publicar **retira** la versión vigente anterior, que se queda en el
 * histórico (§10.8): la respuesta trae qué versiones se retiraron.
 */

import { useState, type FormEvent } from 'react';

import { usePublicarCpuApiV1ConceptosConceptoIdCpuPost } from '@/api/generado/catalogos/catalogos';
import type { PrecioUnitarioRespuesta, VersionPublicadaRespuesta } from '@/api/generado/modelo';
import type { ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { fmtMXN } from '@/lib/formato';
import { CampoTexto } from './Campos';
import { peticionVersionCPU, precioIncompleto, type FormularioVersionCPU } from './formulario';

interface Props {
  readonly conceptoId: string;
  readonly clave: string;
  /** CPU recalculado de la explosión de hoy: lo que se publicará por omisión. */
  readonly calculado: PrecioUnitarioRespuesta;
  readonly varianteInicial: string;
  readonly onCerrar: () => void;
  readonly onPublicada: (publicada: VersionPublicadaRespuesta) => void;
}

const VACIO: FormularioVersionCPU = { variante: '', precioUnitario: '', precioDestajo: '' };

export function NuevaVersionCPU({
  conceptoId,
  clave,
  calculado,
  varianteInicial,
  onCerrar,
  onPublicada,
}: Props) {
  const [formulario, setFormulario] = useState<FormularioVersionCPU>({
    ...VACIO,
    variante: varianteInicial,
  });
  const [error, setError] = useState<{ mensaje: string; campo?: string } | null>(null);

  const publicar = usePublicarCpuApiV1ConceptosConceptoIdCpuPost<ErrorApi>({
    mutation: {
      onSuccess: (respuesta) => {
        setError(null);
        onPublicada(respuesta);
      },
      onError: (err) => setError({ mensaje: err.message, campo: err.campo }),
    },
  });

  const incompleto = precioIncompleto(formulario);
  const puedeEnviar = !incompleto && !publicar.isPending;

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (!puedeEnviar) return;
    publicar.mutate({ conceptoId, data: peticionVersionCPU(formulario) });
  }

  return (
    <Modal titulo={`Publicar CPU · ${clave}`} onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          <div className="card">
            <div className="card__header">
              <div>
                <h3 className="card__title">Se publicará este precio</h3>
                <div className="card__sub">
                  Calculado desde la explosión de hoy (§7.3). Deja los campos de precio vacíos
                  para publicarlo tal cual.
                </div>
              </div>
            </div>
            <div className="card__body col gap-4">
              <Cifra etiqueta="Total (CPU)" valor={calculado.total} />
              <Cifra etiqueta="Destajo" valor={calculado.destajo} />
              <Cifra etiqueta="Materiales y demás" valor={calculado.materiales} />
            </div>
          </div>

          <CampoTexto
            id="cpu-variante"
            etiqueta="Variante"
            valor={formulario.variante}
            onCambio={(variante) => setFormulario((f) => ({ ...f, variante }))}
            mono
            marcador="Receta base"
            pista="Receta alterna del concepto (§10.1). Vacío = receta base."
          />

          <div className="row gap-12">
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="cpu-precio-unitario"
                etiqueta="Precio unitario (opcional)"
                valor={formulario.precioUnitario}
                onCambio={(precioUnitario) => setFormulario((f) => ({ ...f, precioUnitario }))}
                tipo="number"
                mono
                paso="any"
                minimo="0"
              />
            </div>
            <div style={{ flex: 1 }}>
              <CampoTexto
                id="cpu-precio-destajo"
                etiqueta="Precio destajo (opcional)"
                valor={formulario.precioDestajo}
                onCambio={(precioDestajo) => setFormulario((f) => ({ ...f, precioDestajo }))}
                tipo="number"
                mono
                paso="any"
                minimo="0"
              />
            </div>
          </div>

          {incompleto && (
            <div className="text-mute text-sm" role="status">
              Si capturas un precio explícito, captura los dos: el §7.3 pide el desglose
              completo (destajo dentro del total).
            </div>
          )}

          {error && <ErrorBanner mensaje={error.mensaje} campo={error.campo} />}
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puedeEnviar}>
            {publicar.isPending ? 'Publicando…' : 'Publicar versión'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Cifra({ etiqueta, valor }: { readonly etiqueta: string; readonly valor: string }) {
  return (
    <div className="row" style={{ justifyContent: 'space-between', gap: 12 }}>
      <span className="text-mute text-sm">{etiqueta}</span>
      <span className="text-sm mono tnum">{fmtMXN(valor)}</span>
    </div>
  );
}
