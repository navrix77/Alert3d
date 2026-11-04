/** Типи JSON, який віддає сервер «Тривоги» (GET /api/state і WebSocket /ws). */

export type TargetType = 'shahed' | 'jet' | 'molniya' | 'cruise' | 'ballistic';
export type TrackStatus = 'active' | 'lost' | 'closed';
export type LonLat = [number, number];

export interface Launch {
  site: string;
  lat: number;
  lon: number;
  kind?: string;
  t: number | null;
  est: boolean;
  carrier: string | null;
  srcs: string[];
  link: string | null;
  p: number;
  id?: string | null;
  count?: number | null;
}

export interface Track {
  id: string;
  type: TargetType;
  name?: string;
  count: number | null;
  status: TrackStatus;
  lat: number;
  lon: number;
  hd: number | null;
  speed: number;
  conf: number;
  next: string | null;
  route_names: string[];
  route: LonLat[];
  trail: [number, number, number][];
  first: number;
  last: number;
  srcs: string[];
  links: string[];
  from?: string | null;
  launch: Launch | null;
  /** [lon, lat, назва, t] — перша фіксація цілі */
  entry: [number, number, string, number] | null;
  pred: 'channels' | 'learned' | 'learned-origin' | null;
  pred_p: number | null;
  pos_est: boolean;
  ts: number;
}

export interface Zone {
  places: [number, number, string][];
  t: number;
  platform: string | null;
}

export interface LaunchEvent {
  id: string;
  site: string;
  lat: number;
  lon: number;
  kind?: string;
  t: number;
  type: TargetType | null;
  count: number | null;
  carrier: string | null;
  srcs: string[];
  links: string[];
  tracks: number;
}

export interface Official {
  levels: Record<string, 1 | 2>;
  raion_levels: Record<string, 1 | 2>;
  points: [number, number, string, 1 | 2][];
  raions?: string[];
  updated?: number;
  ok?: boolean;
  error?: string | null;
  source?: string;
}

export interface SourceInfo {
  name: string;
  rel: number;
  prior?: number;
  official?: boolean;
  url?: string | null;
}

export interface Health {
  telegram?: boolean;
  channels?: { live: number; channels: number; fast_every?: number; all_every?: number };
  replay?: boolean;
  alerts?: boolean;
  uptime?: number;
  version?: string;
}

export interface Snapshot {
  now: number;
  tracks: Track[];
  zones: Zone[];
  launches: LaunchEvent[];
  levels?: Record<string, 1 | 2>;
  official?: Official;
  sources: Record<string, SourceInfo>;
  health?: Health;
  last_update?: number;
}

export type ConnState = 'connecting' | 'live' | 'offline';
