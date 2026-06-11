export interface ProcessReading {
  time: string;
  line_id: number;
  station: string;
  param: string;
  value: number;
  unit: string;
}

export interface AnomalyEvent {
  id: number;
  detected_at: string;
  line_id: number;
  station: string;
  severity: "INFO" | "WARNING" | "CRITICAL";
  param: string;
  value: number;
  threshold_low: number | null;
  threshold_high: number | null;
  pattern_type: string | null;
  resolved_at: string | null;
}

export interface Equipment {
  id: number;
  name: string;
  line_id: number;
  station: string;
  last_maintenance: string | null;
  next_maintenance: string | null;
  total_hours: number;
}

export interface MaintenanceReport {
  id: number;
  generated_at: string;
  equipment_id: number;
  equipment_name: string;
  risk_score: number;
  similar_case_date: string | null;
  llm_summary: string | null;
}

export interface CorrelationPair {
  param_a: string;
  param_b: string;
  r: number;
  p_value: number;
  interpretation: string;
}

// Rolling buffer type for real-time charts
export type ParamBuffer = Record<string, { time: string; value: number }[]>;

export interface FailureAlertEvidence {
  kind: string;
  pair?: string;
  param?: string;
  [key: string]: unknown;
}

export interface FailureAlert {
  id: number;
  signature_id: string;
  name?: string;
  line_id: number;
  severity: "WARNING" | "CRITICAL";
  confidence: number;
  state: "RAISED" | "ACTIVE" | "RESOLVED";
  evidence: FailureAlertEvidence[];
  raised_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  acked_by?: string | null;
  acked_at?: string | null;
  action?: string;
  equipment_ids?: number[];
}

export interface FailureAlertWsMessage {
  type: "failure_alert";
  event: "RAISED" | "ACTIVE" | "UPDATED" | "RESOLVED";
  alert_id: number;
  signature_id: string;
  name: string;
  severity: "WARNING" | "CRITICAL";
  state: "RAISED" | "ACTIVE" | "RESOLVED";
  line_id: number;
  confidence: number;
  raised_at: string;
  last_seen_at: string;
  resolved_at: string | null;
  evidence: FailureAlertEvidence[];
  action: string;
  equipment_ids: number[];
}
