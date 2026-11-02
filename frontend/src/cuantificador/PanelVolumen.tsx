/**
 * «Calcular volumen»: una calculadora sobre el trazo elegido.
 *
 * Polígono → área × espesor. Línea → longitud × ancho × alto. La base sale del
 * trazo (y de la escala del plano); lo demás se teclea. No guarda nada: el
 * resultado se copia a donde haga falta. La cantidad que cuenta para la obra
 * sigue siendo la que calcula el servidor al enlazar el trazo.
 */

import { X } from 'lucide-react';
import { useState } from 'react';

import { fmtNum } from '@/lib/formato';
import type { GeometriaGeoJson } from './geometria';
import { baseDeVolumen, numeroTecleado, volumenDe } from './volumen';

interface Props {
  /** El trazo elegido, o `null` si no hay ninguno. */
  readonly trazo: { readonly id: string; readonly geometry: GeometriaGeoJson; readonly nombre: string } | null;
  readonly escalaMPorUnidad: number | null;
  readonly onCerrar: () => void;
}

function Campo({
  id,
  etiqueta,
  valor,
  onCambio,
}: {
  readonly id: string;
  readonly etiqueta: string;
  readonly valor: string;
  readonly onCambio: (v: string) => void;
}) {
  return (
    <label className="volumen__campo" htmlFor={id}>
      <span>{etiqueta}</span>
      <input
        id={id}
        className="input"
        inputMode="decimal"
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
      />
    </label>
  );
}

export function PanelVolumen({ trazo, escalaMPorUnidad, onCerrar }: Props) {
  const [espesor, setEspesor] = useState('0.10');
  const [ancho, setAncho] = useState('0.20');
  const [alto, setAlto] = useState('0.40');
  const [descuento, setDescuento] = useState('');
  const [copiado, setCopiado] = useState(false);

  const base = trazo ? baseDeVolumen(trazo.geometry, escalaMPorUnidad) : null;
  const factores =
    base?.tipo === 'area' ? [numeroTecleado(espesor)] : [numeroTecleado(ancho), numeroTecleado(alto)];
  const volumen = base ? volumenDe(base.valor, factores, numeroTecleado(descuento)) : 0;
  const enUnidadesDePlano = base !== null && (base.unidad === 'u²' || base.unidad === 'u');
  const unidadVolumen = enUnidadesDePlano ? 'u³' : 'm³';

  async function copiar() {
    try {
      await navigator.clipboard.writeText(volumen.toFixed(3));
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1500);
    } catch {
      setCopiado(false);
    }
  }

  return (
    <section className="volumen" aria-label="Calcular volumen">
      <header className="volumen__cabecera">
        <strong>Calcular volumen</strong>
        <button type="button" className="btn-icono" aria-label="Cerrar el cálculo de volumen" onClick={onCerrar}>
          <X size={15} aria-hidden />
        </button>
      </header>
      <div className="volumen__cuerpo">
        {trazo === null ? (
          <p className="text-mute text-sm">Elige un trazo en el plano (herramienta Seleccionar).</p>
        ) : base === null ? (
          <p className="text-mute text-sm">«{trazo.nombre}» es un punto: no tiene área ni longitud.</p>
        ) : (
          <>
            <div className="text-sm">
              Trazo: <strong>{trazo.nombre}</strong>
            </div>
            <div className="volumen__base">
              <span>{base.tipo === 'area' ? 'Área' : 'Longitud'}</span>
              <span className="mono" data-testid="volumen-base">
                {fmtNum(base.valor)} {base.unidad}
              </span>
            </div>
            {base.tipo === 'area' ? (
              <Campo id="vol-espesor" etiqueta="Espesor (m)" valor={espesor} onCambio={setEspesor} />
            ) : (
              <>
                <Campo id="vol-ancho" etiqueta="Ancho (m)" valor={ancho} onCambio={setAncho} />
                <Campo id="vol-alto" etiqueta="Alto (m)" valor={alto} onCambio={setAlto} />
              </>
            )}
            <Campo id="vol-descuento" etiqueta={`Descuento (${unidadVolumen})`} valor={descuento} onCambio={setDescuento} />
            <div className="volumen__resultado">
              <span>Volumen</span>
              <strong className="mono" data-testid="volumen-resultado">
                {fmtNum(volumen)} {unidadVolumen}
              </strong>
            </div>
            {enUnidadesDePlano && (
              <p className="text-mute text-xs">
                El plano no está calibrado: el resultado está en unidades de plano, no en metros.
              </p>
            )}
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button type="button" className="btn btn--sm" onClick={() => void copiar()}>
                {copiado ? 'Copiado' : 'Copiar'}
              </button>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
