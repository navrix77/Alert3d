import type { TargetType } from './types';

export const TYPE_COLOR: Record<TargetType, string> = {
  shahed: '#FF9F2E',
  jet: '#FF5FA2',
  molniya: '#FFD84A',
  cruise: '#FF4B3E',
  ballistic: '#C77DFF',
};

export const TYPE_NAME: Record<TargetType, string> = {
  shahed: 'Шахед',
  jet: 'Реактивний БпЛА',
  molniya: '«Молнія»',
  cruise: 'Крилата ракета',
  ballistic: 'Балістика',
};

export const TYPES = Object.keys(TYPE_COLOR) as TargetType[];

export const C = {
  bg: '#07090E',
  ink: '#F5F7FB',
  ink2: 'rgba(235,240,250,0.68)',
  ink3: 'rgba(235,240,250,0.42)',
  hair: 'rgba(255,255,255,0.14)',
  hairStrong: 'rgba(255,255,255,0.24)',
  glassFill: 'rgba(18,22,32,0.42)',
  glassFillAndroid: 'rgba(16,19,28,0.86)',
  red: '#C8102E',
  redHot: '#FF3B4E',
  amber: '#E8B300',
  green: '#3DDC97',
  blue: '#6EA8FF',
  gray: '#8A93A5',
};

export const R = { sm: 12, md: 18, lg: 26, xl: 34 };

export const SPRING = { damping: 18, stiffness: 180, mass: 0.9 };
export const SPRING_SOFT = { damping: 22, stiffness: 120, mass: 1 };

/** Шрифт підписів на карті (гліфи OpenFreeMap, кирилиця є). */
export const MAP_FONT = ['Noto Sans Bold'];
export const GLYPHS = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf';
export const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

export const DEFAULT_SERVER = 'http://192.168.1.100:8090';
export const ALERT_KM = 15;
