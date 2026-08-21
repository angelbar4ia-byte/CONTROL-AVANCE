/**
 * Cierres — Supervisor: autoriza o rechaza (§11.3 C.2).
 *
 * La pantalla vive en `src/pantallas/Cierres.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para el Supervisor.
 */

import { Cierres } from '@/pantallas/Cierres';

export default function Pantalla() {
  return <Cierres />;
}
