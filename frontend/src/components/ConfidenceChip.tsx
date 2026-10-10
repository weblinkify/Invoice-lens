import { CheckCircle2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { bandLabel, confidenceBand } from '@/lib/confidence';
import { pct } from '@/lib/utils';

interface Props {
  confidence: number;
  threshold: number;
  verified?: boolean;
}

const variant = { high: 'success', medium: 'warning', low: 'destructive' } as const;

export function ConfidenceChip({ confidence, threshold, verified = false }: Props) {
  if (verified) {
    return (
      <Badge variant="success" aria-label="Verified by reviewer" title="Verified by reviewer">
        <CheckCircle2 className="size-3" aria-hidden /> Verified
      </Badge>
    );
  }
  const band = confidenceBand(confidence, threshold);
  return (
    <Badge
      variant={variant[band]}
      data-band={band}
      title={bandLabel[band]}
      aria-label={`Confidence ${pct(confidence)}, ${bandLabel[band].toLowerCase()}`}
    >
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {pct(confidence)}
    </Badge>
  );
}
