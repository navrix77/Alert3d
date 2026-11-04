import { BlurView } from 'expo-blur';
import type { ReactNode } from 'react';
import { Platform, Pressable, type PressableProps, StyleSheet, View, type ViewStyle, type StyleProp } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

import { C, R, SPRING } from '../lib/theme';

/**
 * «Рідке скло»: розмиття фону (iOS — нативний матеріал; Android — напівпрозора підкладка),
 * тонка світла окантовка й відблиск зверху.
 */
export function Glass({ children, style, radius = R.lg, intensity = 40 }: { children?: ReactNode; style?: StyleProp<ViewStyle>; radius?: number; intensity?: number }) {
  return (
    <View style={[styles.shadow, { borderRadius: radius }, style]}>
      <View style={[StyleSheet.absoluteFill, { borderRadius: radius, overflow: 'hidden' }]}>
        {Platform.OS === 'ios' ? (
          <BlurView tint="systemUltraThinMaterialDark" intensity={intensity} style={StyleSheet.absoluteFill} />
        ) : (
          <View style={[StyleSheet.absoluteFill, { backgroundColor: C.glassFillAndroid }]} />
        )}
        <View style={[StyleSheet.absoluteFill, { backgroundColor: C.glassFill }]} />
        <View style={styles.sheen} />
      </View>
      <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.edge, { borderRadius: radius }]} />
      {children}
    </View>
  );
}

/** Кнопка зі «стисканням» на пружині. */
export function SpringButton({ children, style, ...rest }: PressableProps & { style?: StyleProp<ViewStyle>; children: ReactNode }) {
  const s = useSharedValue(1);
  const a = useAnimatedStyle(() => ({ transform: [{ scale: s.value }] }));
  return (
    <Pressable
      {...rest}
      onPressIn={(e) => {
        s.value = withSpring(0.94, SPRING);
        rest.onPressIn?.(e);
      }}
      onPressOut={(e) => {
        s.value = withSpring(1, SPRING);
        rest.onPressOut?.(e);
      }}
    >
      <Animated.View style={[a, style]}>{children}</Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  shadow: {
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 12 },
    elevation: 10,
  },
  edge: { borderWidth: StyleSheet.hairlineWidth, borderColor: C.hairStrong },
  sheen: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    height: 1,
    backgroundColor: 'rgba(255,255,255,0.28)',
  },
});
