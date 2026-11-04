import { BlurMask, Canvas, Circle, Group, RadialGradient, vec } from '@shopify/react-native-skia';
import { useEffect } from 'react';
import { Easing, useDerivedValue, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';

export type OrbTone = 'calm' | 'watch' | 'danger' | 'unknown';

const TONE: Record<OrbTone, { core: string; glow: string; period: number }> = {
  calm: { core: '#3DDC97', glow: 'rgba(61,220,151,0.55)', period: 3600 },
  watch: { core: '#F5C23D', glow: 'rgba(245,194,61,0.6)', period: 2200 },
  danger: { core: '#FF3B4E', glow: 'rgba(255,59,78,0.75)', period: 1100 },
  unknown: { core: '#8A93A5', glow: 'rgba(138,147,165,0.45)', period: 4200 },
};

/**
 * «Дихаюча» сфера статусу (Skia): внутрішнє ядро з радіальним градієнтом і розмитий ореол,
 * що пульсує тим частіше, чим ближче загроза.
 */
export function StatusOrb({ tone, size = 44 }: { tone: OrbTone; size?: number }) {
  const t = useSharedValue(0);
  const cfg = TONE[tone];

  useEffect(() => {
    t.value = 0;
    t.value = withRepeat(withTiming(1, { duration: cfg.period, easing: Easing.inOut(Easing.sin) }), -1, true);
  }, [cfg.period, t]);

  const c = size / 2;
  const glowR = useDerivedValue(() => size * (0.3 + 0.12 * t.value));
  const glowOpacity = useDerivedValue(() => 0.55 + 0.45 * t.value);
  const coreR = useDerivedValue(() => size * (0.2 + 0.025 * t.value));

  return (
    <Canvas style={{ width: size, height: size }}>
      <Group opacity={glowOpacity}>
        <Circle cx={c} cy={c} r={glowR} color={cfg.glow}>
          <BlurMask blur={size * 0.16} style="normal" />
        </Circle>
      </Group>
      <Circle cx={c} cy={c} r={coreR}>
        <RadialGradient c={vec(c - size * 0.06, c - size * 0.07)} r={size * 0.26} colors={['#FFFFFF', cfg.core, cfg.core]} positions={[0, 0.35, 1]} />
      </Circle>
    </Canvas>
  );
}
