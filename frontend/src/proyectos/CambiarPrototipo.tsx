/**
 * Cambiar el prototipo de una obra que sigue en diseño (cerebro D-626). Se ofrece desde Presupuesto y desde
 * Cuantificador: lo diseñado se borra como al reiniciar y se generan las partidas del prototipo nuevo.
 */

import { useState } from 'react';

import type { ErrorApi } from '@/api/cliente';
import { useCambiarPrototipoApiV1ObrasObraIdPrototipoPost } from '@/api/generado/arbol-de-la-obra/arbol-de-la-obra';
import type { ObraRespuesta, PrototipoRespuesta } from '@/api/generado/modelo';
import { useListarObrasApiV1ObrasGet } from '@/api/generado/obras/obras';
import { useListarPrototiposApiV1PrototiposGet } from '@/api/generado/proyectos/proyectos';
import { ErrorBanner } from '@/lib/ErrorBanner';
import { Modal } from '@/lib/Modal';
import { SelectorObra } from '@/lib/SelectorObra';

interface Props {
  /** La obra ya elegida (Cuantificador); sin ella se pide (Presupuesto). */
  readonly obraId?: string;
  readonly onCerrar: () => void;
  readonly onCambiado: (aviso: string) => void;
}

export function CambiarPrototipo({ obraId: fija, onCerrar, onCambiado }: Props) {
  const [elegida, setElegida] = useState(fija ?? '');
  const [prototipoId, setPrototipoId] = useState('');
  const [clave, setClave] = useState('');
  const [error, setError] = useState<string | null>(null);
  const obraId = fija ?? elegida;

  const obras = useListarObrasApiV1ObrasGet<ObraRespuesta[], ErrorApi>();
  const obra = (obras.data ?? []).find((o) => o.id === obraId);
  const catalogo = useListarPrototiposApiV1PrototiposGet<PrototipoRespuesta[], ErrorApi>({});
  const cambiar = useCambiarPrototipoApiV1ObrasObraIdPrototipoPost<ErrorApi>({
    mutation: {
      onError: (e) => setError(e.message),
      onSuccess: (r) =>
        onCambiado(
          `Prototipo cambiado: se borraron ${r.actividades} partidas y ${r.trazos} trazos. ` +
            (r.motivo_sin_generar
              ? `No se generaron partidas: ${r.motivo_sin_generar}`
              : `Se generaron ${r.actividades_generadas} partidas del prototipo nuevo.`),
        ),
    },
  });

  const claveOk = obra !== undefined && clave.trim().toUpperCase() === obra.clave.trim().toUpperCase();
  const puede = obraId !== '' && prototipoId !== '' && claveOk && !cambiar.isPending;

  return (
    <Modal titulo="Cambiar prototipo" onCerrar={onCerrar}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          cambiar.mutate({ obraId, data: { prototipo_id: prototipoId, clave } });
        }}
      >
        <div className="sheet__body col gap-12">
          <p className="text-mute text-sm">
            Solo mientras la obra sigue en diseño. Se borra lo diseñado (partidas, trazos y mediciones) y se generan las
            partidas del prototipo nuevo.
          </p>
          {error && <ErrorBanner mensaje={error} />}
          {fija === undefined && <SelectorObra id="cp-obra" etiqueta="Obra" valor={elegida} onCambio={setElegida} requerido />}
          <div className="field">
            <label className="field__label" htmlFor="cp-prototipo">
              Prototipo nuevo
            </label>
            <select id="cp-prototipo" className="select" value={prototipoId} onChange={(e) => setPrototipoId(e.target.value)} required>
              <option value="">Elige un prototipo…</option>
              {(catalogo.data ?? [])
                .filter((p) => p.id !== obra?.prototipo_id)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.clave} · {p.nombre}
                  </option>
                ))}
            </select>
          </div>
          <div className="field">
            <label className="field__label" htmlFor="cp-clave">
              Para confirmar, escribe la clave de la obra{obra ? `: ${obra.clave}` : ''}
            </label>
            <input id="cp-clave" className="input mono" value={clave} onChange={(e) => setClave(e.target.value)} />
          </div>
        </div>
        <div className="sheet__footer">
          <button type="button" className="btn" onClick={onCerrar}>
            Cancelar
          </button>
          <button type="submit" className="btn btn--primary" disabled={!puede}>
            {cambiar.isPending ? 'Cambiando…' : 'Cambiar prototipo'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
