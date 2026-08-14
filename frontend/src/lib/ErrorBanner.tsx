/**
 * Banner de error de una mutación contra la API.
 *
 * Spec §11.2 (`problem+json`) · agente Web (`MD/04-web.md`): cero lógica de
 * negocio, solo presenta lo que `ErrorApi` (`api/cliente.ts`) ya interpretó
 * del `problem+json` del backend — incluido `campo` cuando el backend marca
 * qué dato violó una regla (§6).
 */

interface Props {
  readonly mensaje: string;
  readonly campo?: string;
}

export function ErrorBanner({ mensaje, campo }: Props) {
  return (
    <div
      className="text-sm"
      role="alert"
      style={{
        color: 'var(--c-danger)',
        background: 'var(--c-danger-soft)',
        border: '1px solid var(--c-danger)',
        borderRadius: 'var(--r-md)',
        padding: '8px 12px',
      }}
    >
      {campo ? `${campo}: ` : ''}
      {mensaje}
    </div>
  );
}
