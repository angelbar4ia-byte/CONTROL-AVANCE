/**
 * Generador de ids locales.
 *
 * PowerSync agrega implícitamente una columna `id` (texto) a cada tabla del
 * esquema y espera que el cliente la genere al insertar (así puede escribir
 * offline sin esperar un id autogenerado por Postgres). No se usa
 * `crypto.randomUUID`: Hermes no lo expone sin polyfill, así que este es un
 * generador de respaldo — no criptográfico, solo necesita ser único por
 * dispositivo para no chocar en la cola de subida.
 */
export function generarId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
