/**
 * Incidencias — Supervisor: atiende, cierra y rechaza (§11.3 F.3, F.4).
 *
 * La pantalla vive en `src/pantallas/Incidencias.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para el Supervisor.
 */

import { Incidencias } from '@/pantallas/Incidencias';

export default function Pantalla() {
  return <Incidencias papel="supervisor" />;
}
