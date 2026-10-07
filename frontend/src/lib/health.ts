/**
 * Display rules for the business-health card. The scores themselves come from
 * the API (backend/app/health.py); this only decides how a number is shown.
 *
 * A score is null when the business has too little data for it, and that has
 * to read as "not enough data", never as a score of zero.
 */

export type HealthScore = number | null;

export interface Health {
  overall: HealthScore;
  inventory: HealthScore;
  revenue: HealthScore;
  profitability: HealthScore;
  cashFlow: HealthScore;
}

export type HealthTone = "success" | "warning" | "destructive" | "default";

/** The bands match the backend's cap: "Fair" is exactly 30 points wide. */
export function healthTone(score: HealthScore): HealthTone {
  if (score === null) return "default";
  if (score >= 70) return "success";
  if (score >= 40) return "warning";
  return "destructive";
}

export function healthLabel(score: HealthScore): string {
  if (score === null) return "Not enough data";
  if (score >= 70) return "Healthy";
  if (score >= 40) return "Fair";
  return "At risk";
}

/** The CSS colour token for a score's bar, or null for an empty track. */
export function healthColor(score: HealthScore): string | null {
  const tone = healthTone(score);
  return tone === "default" ? null : `--${tone}`;
}
