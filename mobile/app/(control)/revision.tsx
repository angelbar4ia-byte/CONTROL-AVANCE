/**
 * Revisión física en campo — Control de obra (§7.8, §12.5).
 *
 * La pantalla vive en `src/pantallas/Revision.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para Control de obra.
 */

import { Revision } from '@/pantallas/Revision';

export default function Pantalla() {
  return <Revision />;
}
