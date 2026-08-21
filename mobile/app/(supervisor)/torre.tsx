/**
 * Torre de control — Supervisor (§5.2, §11.2).
 *
 * La pantalla vive en `src/pantallas/Torre.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para el Supervisor.
 */

import { Torre } from '@/pantallas/Torre';

export default function Pantalla() {
  return <Torre />;
}
