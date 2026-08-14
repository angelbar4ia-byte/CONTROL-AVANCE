import { Text, View } from 'react-native';

export default function Pantalla() {
  return (
    <View className="flex-1 bg-bg px-5 pt-14">
      <Text className="text-2xl text-text">Torre de control</Text>
      <Text className="mt-2 text-md text-text-mute">Estado de las obras de mis clusters (§4).</Text>
    </View>
  );
}
