/**
 * Modal centrado (DESIGN_SYSTEM.md §4: `.scrim` + `.modal`).
 *
 * Se usa para confirmaciones cortas que piden un dato (motivo de rechazo,
 * comentario de validación…). Cierra con clic en el `scrim` o con `Esc`.
 */

import { useEffect, type ReactNode } from 'react';

interface Props {
  readonly titulo: string;
  readonly onCerrar: () => void;
  readonly children: ReactNode;
}

export function Modal({ titulo, onCerrar, children }: Props) {
  useEffect(() => {
    function alTeclear(evento: KeyboardEvent) {
      if (evento.key === 'Escape') onCerrar();
    }
    window.addEventListener('keydown', alTeclear);
    return () => window.removeEventListener('keydown', alTeclear);
  }, [onCerrar]);

  return (
    <div className="scrim" onClick={onCerrar}>
      <div
        className="modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
      >
        <div className="sheet__header">
          <h2 className="sheet__title">{titulo}</h2>
          <button type="button" className="btn btn--ghost btn--icon" onClick={onCerrar} aria-label="Cerrar">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
