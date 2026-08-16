/**
 * Cajón derecho (DESIGN_SYSTEM.md §4: `.scrim` + `.sheet`, ancho 480).
 *
 * Es el patrón de **drill-down** del sistema de diseño: la lista se queda
 * visible a la izquierda y el detalle se abre a un lado, en vez de navegar a
 * otra pantalla. Cierra con clic en el `scrim` o con `Esc`, igual que el
 * `Modal`.
 */

import { useEffect, type ReactNode } from 'react';

interface Props {
  readonly titulo: string;
  /** Línea secundaria del encabezado (clave, estatus…). */
  readonly subtitulo?: string;
  readonly onCerrar: () => void;
  readonly children: ReactNode;
}

export function Sheet({ titulo, subtitulo, onCerrar, children }: Props) {
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
        className="sheet"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
      >
        <div className="sheet__header">
          <div>
            <h2 className="sheet__title">{titulo}</h2>
            {subtitulo !== undefined && (
              <div className="text-mute text-xs mono">{subtitulo}</div>
            )}
          </div>
          <button
            type="button"
            className="btn btn--ghost btn--icon"
            onClick={onCerrar}
            aria-label="Cerrar"
          >
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
