import { View } from 'react-native';

import { Encabezado } from '@/ui/Encabezado';

export default function Pantalla() {
  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Encabezado
        eyebrow="Supervisor"
        titulo="Ruta crítica"
        descripcion="Ruta crítica por obra (§6)."
      />
    </View>
  );
}
