// 공정/파라미터/탐지패턴의 한국어 표시명 — UI 전역에서 공유

export const STATION_LABELS: Record<string, string> = {
  coating: "코팅",
  calendering: "캘린더링",
  slitting: "슬리팅",
  winding: "권취",
};

export const PARAM_LABELS: Record<string, string> = {
  line_speed: "라인 속도",
  coating_thickness: "코팅 두께",
  coating_weight: "도포량",
  dry_temp_zone1: "건조로 1구간 온도",
  dry_temp_zone2: "건조로 2구간 온도",
  dry_temp_zone3: "건조로 3구간 온도",
  tension_supply: "공급부 장력",
  tension_winding: "권취부 장력",
  slurry_viscosity: "슬러리 점도",
  roll_pressure: "롤 압력",
  roll_temperature: "롤 온도",
  electrode_density: "전극 밀도",
  thickness_before: "압연 전 두께",
  thickness_after: "압연 후 두께",
  tension: "장력",
  slit_width_dev: "절단 폭 편차",
  blade_pressure: "칼날 압력",
  winding_speed: "권취 속도",
  roll_diameter: "롤 직경",
  alignment_offset: "정렬 오차",
  multivariate: "다변량 패턴",
};

export const PATTERN_LABELS: Record<string, string> = {
  LAYER1_ZSCORE: "급변 (Z-score)",
  LAYER1_EWMA: "드리프트 (EWMA 제어차트)",
  LAYER1_THRESHOLD: "정상범위 이탈",
  LAYER3_ISOLATION_FOREST: "다변량 이상 (Isolation Forest)",
};

export const stationLabel = (s: string) => STATION_LABELS[s] ?? s;
export const paramLabel = (p: string) => PARAM_LABELS[p] ?? p;
export const patternLabel = (p: string) => PATTERN_LABELS[p] ?? p;

/** 값 크기에 맞는 자릿수: 3050.123 → "3050", 95.4321 → "95.43", 1.6789 → "1.679" */
export function fmtValue(v: number): string {
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toFixed(0);
  if (abs >= 10) return v.toFixed(2);
  return v.toFixed(3);
}
