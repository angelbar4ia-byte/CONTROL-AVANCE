/**
 * Fotos — la cola de evidencias hacia R2 (§12.5).
 *
 * La pantalla vive en `src/pantallas/FotosPendientes.tsx`: es compartida entre roles
 * (§5.3) y esta ruta solo la monta para Control de obra.
 */

import { FotosPendientes } from '@/pantallas/FotosPendientes';

export default function Pantalla() {
  return <FotosPendientes />;
}
