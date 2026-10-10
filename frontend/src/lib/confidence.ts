export type Band = 'high' | 'medium' | 'low';

/** Mirrors backend `app.domain.confidence.confidence_band`. */
export const LOW_BAND_CEILING = 0.5;

export function confidenceBand(confidence: number, threshold: number): Band {
  if (confidence >= threshold) return 'high';
  if (confidence >= LOW_BAND_CEILING) return 'medium';
  return 'low';
}

export const bandLabel: Record<Band, string> = {
  high: 'High confidence',
  medium: 'Check this value',
  low: 'Low confidence',
};
