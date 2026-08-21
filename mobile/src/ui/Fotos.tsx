/**
 * Selector de evidencia fotográfica para un formulario de campo (§12.5).
 *
 * Solo elige y muestra: **no** encola. La cola necesita el id de la entidad
 * dueña (`registro_avance`, `revision_fisica`, `incidencia`) y ese id no
 * existe hasta que el formulario se guarda. El orden es: elegir → guardar la
 * entidad → encolar las fotos contra su id, y así una foto nunca queda
 * apuntando a una entidad que el usuario acabó cancelando.
 */

import { useState } from 'react';
import { Image, Pressable, ScrollView, Text, View } from 'react-native';
import { Camera, ImagePlus, X } from 'lucide-react-native';

import { tomarFoto, type FotoTomada, type Origen } from '@/evidencias/captura';
import { TOKENS } from '@/lib/tabs';

interface Props {
  readonly fotos: readonly FotoTomada[];
  readonly onCambio: (fotos: FotoTomada[]) => void;
  readonly deshabilitado?: boolean;
  /** Tope de fotos. Sin límite si no se pasa. */
  readonly maximo?: number;
}

export function Fotos({ fotos, onCambio, deshabilitado = false, maximo }: Props) {
  const [ocupado, setOcupado] = useState(false);
  const lleno = maximo !== undefined && fotos.length >= maximo;

  async function agregar(origen: Origen) {
    if (ocupado || deshabilitado || lleno) return;
    setOcupado(true);
    try {
      const foto = await tomarFoto(origen);
      if (foto) onCambio([...fotos, foto]);
    } finally {
      setOcupado(false);
    }
  }

  function quitar(uri: string) {
    onCambio(fotos.filter((f) => f.uri !== uri));
  }

  return (
    <View>
      <View className="flex-row gap-2">
        <Pressable
          onPress={() => void agregar('camara')}
          disabled={deshabilitado || ocupado || lleno}
          className="h-fila flex-1 flex-row items-center justify-center gap-2 rounded-md border border-line bg-surface active:opacity-70 disabled:opacity-50"
        >
          <Camera size={18} color={TOKENS.textMute} strokeWidth={1.6} />
          <Text className="text-sm text-text-soft">Cámara</Text>
        </Pressable>

        <Pressable
          onPress={() => void agregar('galeria')}
          disabled={deshabilitado || ocupado || lleno}
          className="h-fila flex-1 flex-row items-center justify-center gap-2 rounded-md border border-line bg-surface active:opacity-70 disabled:opacity-50"
        >
          <ImagePlus size={18} color={TOKENS.textMute} strokeWidth={1.6} />
          <Text className="text-sm text-text-soft">Galería</Text>
        </Pressable>
      </View>

      {fotos.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} className="mt-3">
          <View className="flex-row gap-2">
            {fotos.map((foto) => (
              <View key={foto.uri} className="relative">
                <Image
                  source={{ uri: foto.uri }}
                  className="h-20 w-20 rounded-md bg-elev"
                  resizeMode="cover"
                />
                {deshabilitado ? null : (
                  <Pressable
                    onPress={() => quitar(foto.uri)}
                    className="absolute -right-1.5 -top-1.5 h-6 w-6 items-center justify-center rounded-full bg-surface border border-line active:opacity-70"
                  >
                    <X size={14} color={TOKENS.textMute} strokeWidth={2} />
                  </Pressable>
                )}
              </View>
            ))}
          </View>
        </ScrollView>
      ) : null}

      {lleno ? (
        <Text className="mt-2 text-xs text-text-mute">Máximo {maximo} fotos por registro.</Text>
      ) : null}

      <Text className="mt-2 text-xs text-text-mute">
        Las fotos se suben solas cuando haya señal; no viajan por la API (§12.5).
      </Text>
    </View>
  );
}
