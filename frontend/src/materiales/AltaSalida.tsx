/**
 * Alta de salida de almacén — `POST /obras/{id}/salidas` (§11.2, §7.7).
 *
 * Solo Control de obra registra movimientos (§4, §11.2). El formulario
 * traduce a DTO en `formulario.ts` y no decide nada: el signo contra el
 * motivo (409) y el IVA (§3.5) son del backend; aquí solo se **avisa** si el
 * signo capturado no concuerda con el del motivo elegido (§10.5).
 */

import { useMemo, useState, type FormEvent } from 'react';

import { useRegistrarSalidaApiV1ObrasObraIdSalidasPost } from '@/api/generado/materiales/materiales';
import {
  useListarContratistasApiV1ContratistasGet,
  useListarConceptosApiV1ConceptosGet,
  useListarMaterialesApiV1MaterialesGet,
} from '@/api/generado/catalogos/catalogos';
import { claveDeIdempotencia, type ErrorApi } from '@/api/cliente';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Sheet } from '@/lib/Sheet';
import { SelectorObra } from '@/lib/SelectorObra';
import { useMotivosAlmacen } from './catalogoMotivos';
import {
  formularioSalidaVacio,
  hoyISO,
  peticionDeSalida,
  salidaCompleta,
  type FormularioSalida,
} from './formulario';
import { etiquetaSigno, signoCoincide } from './reglas';

interface Props {
  /** Obra preseleccionada por la pantalla que abre el cajón. */
  readonly obraIdInicial: string;
  readonly onCerrar: () => void;
  readonly onRegistrada: () => void;
}

export function AltaSalida({ obraIdInicial, onCerrar, onRegistrada }: Props) {
  const [obraId, setObraId] = useState(obraIdInicial);
  const [formulario, setFormulario] = useState<FormularioSalida>(() =>
    formularioSalidaVacio(hoyISO()),
  );
  const [error, setError] = useState<string | null>(null);

  const materiales = useListarMaterialesApiV1MaterialesGet();
  const motivos = useMotivosAlmacen();
  const conceptos = useListarConceptosApiV1ConceptosGet();
  const contratistas = useListarContratistasApiV1ContratistasGet();

  // `Idempotency-Key` fija por operación (regla 1 del ROADMAP): se genera al
  // montar y se manda igual en cada intento. Generarla dentro de `peticion` no
  // desduplicaría nada — y esto es además lo que protege del doble clic.
  const clave = useMemo(claveDeIdempotencia, []);

  const registrar = useRegistrarSalidaApiV1ObrasObraIdSalidasPost<ErrorApi>({
    mutation: {
      onSuccess: () => {
        setError(null);
        onRegistrada();
      },
      onError: (err) => setError(err.message),
    },
    request: { headers: { 'Idempotency-Key': clave } },
  });

  function cambiar<K extends keyof FormularioSalida>(campo: K, valor: FormularioSalida[K]) {
    setFormulario((previo) => ({ ...previo, [campo]: valor }));
  }

  const motivo = (motivos.data ?? []).find((m) => m.id === formulario.motivoId);
  const avisoSigno =
    motivo !== undefined && !signoCoincide(motivo.signo, formulario.cantidad);

  function alEnviar(evento: FormEvent) {
    evento.preventDefault();
    if (obraId === '' || !salidaCompleta(formulario)) return;
    registrar.mutate({ obraId, data: peticionDeSalida(formulario) });
  }

  return (
    <Sheet titulo="Registrar salida de almacén" subtitulo="POST /obras/{id}/salidas · §7.7" onCerrar={onCerrar}>
      <form onSubmit={alEnviar}>
        <div className="sheet__body col gap-12">
          {error && <ErrorBanner mensaje={error} />}

          <SelectorObra id="salida-obra" etiqueta="Obra" valor={obraId} onCambio={setObraId} requerido />

          <div className="field">
            <label className="field__label" htmlFor="salida-insumo">
              Material
            </label>
            <select
              id="salida-insumo"
              className="select"
              required
              value={formulario.insumoId}
              onChange={(e) => cambiar('insumoId', e.target.value)}
            >
              <option value="">Elige un material…</option>
              {(materiales.data ?? []).map((material) => (
                <option key={material.id} value={material.id}>
                  {material.clave} · {material.descripcion}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="salida-motivo">
              Motivo
            </label>
            <select
              id="salida-motivo"
              className="select"
              required
              value={formulario.motivoId}
              onChange={(e) => cambiar('motivoId', e.target.value)}
            >
              <option value="">Elige un motivo…</option>
              {(motivos.data ?? []).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.clave} · {m.descripcion}
                </option>
              ))}
            </select>
            <div className="field__hint">
              {motivo
                ? `Signo ${etiquetaSigno(motivo.signo)} · bucket ${motivo.bucket} (§10.5).`
                : 'El motivo clasifica el bucket de KPI; el signo viene con la cantidad (§10.5).'}
            </div>
          </div>

          <div className="row gap-12">
            <div className="field w-full">
              <label className="field__label" htmlFor="salida-cantidad">
                Cantidad (con signo)
              </label>
              <input
                id="salida-cantidad"
                className="input input--mono"
                inputMode="decimal"
                required
                value={formulario.cantidad}
                onChange={(e) => cambiar('cantidad', e.target.value)}
                placeholder="-12.5"
              />
            </div>
            <div className="field w-full">
              <label className="field__label" htmlFor="salida-costo">
                Costo (sin IVA, con signo)
              </label>
              <input
                id="salida-costo"
                className="input input--mono"
                inputMode="decimal"
                value={formulario.costo}
                onChange={(e) => cambiar('costo', e.target.value)}
                placeholder="-1450.00"
              />
              <div className="field__hint">
                Los costos van sin IVA; el backend agrega la tasa por clase de
                material (§3.5, §10.6).
              </div>
            </div>
          </div>

          {avisoSigno && motivo && (
            <div className="badge badge--warn" role="status">
              El motivo «{motivo.clave}» es de signo {etiquetaSigno(motivo.signo)}; el
              servidor rechaza (409) una cantidad con el signo contrario (§10.5).
            </div>
          )}

          <div className="field">
            <label className="field__label" htmlFor="salida-fecha">
              Fecha
            </label>
            <input
              id="salida-fecha"
              className="input"
              type="date"
              required
              value={formulario.fecha}
              onChange={(e) => cambiar('fecha', e.target.value)}
            />
          </div>

          <div className="field">
            <label className="field__label" htmlFor="salida-concepto">
              Concepto (opcional)
            </label>
            <select
              id="salida-concepto"
              className="select"
              value={formulario.conceptoId}
              onChange={(e) => cambiar('conceptoId', e.target.value)}
            >
              <option value="">Sin liga a concepto</option>
              {(conceptos.data ?? []).map((concepto) => (
                <option key={concepto.id} value={concepto.id}>
                  {concepto.clave} · {concepto.descripcion}
                </option>
              ))}
            </select>
            <div className="field__hint">Liga al concepto vía «Referencia» (§10.6).</div>
          </div>

          <div className="field">
            <label className="field__label" htmlFor="salida-contratista">
              Contratista (opcional)
            </label>
            <select
              id="salida-contratista"
              className="select"
              value={formulario.contratistaId}
              onChange={(e) => cambiar('contratistaId', e.target.value)}
            >
              <option value="">Sin contratista</option>
              {(contratistas.data ?? []).map((contratista) => (
                <option key={contratista.id} value={contratista.id}>
                  {contratista.clave} · {contratista.razon_social}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button
            type="submit"
            className="btn btn--accent"
            disabled={registrar.isPending || obraId === '' || !salidaCompleta(formulario)}
          >
            {registrar.isPending ? 'Registrando…' : 'Registrar salida'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}
