import { Loader2 } from 'lucide-react';
import type { DocumentStatus } from '@/api/types';
import { Badge, type BadgeProps } from '@/components/ui/badge';

const config: Record<DocumentStatus, { label: string; variant: BadgeProps['variant'] }> = {
  queued: { label: 'Queued', variant: 'secondary' },
  processing: { label: 'Processing', variant: 'default' },
  needs_review: { label: 'Needs review', variant: 'warning' },
  extracted: { label: 'Ready', variant: 'success' },
  approved: { label: 'Approved', variant: 'success' },
  failed: { label: 'Failed', variant: 'destructive' },
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const { label, variant } = config[status];
  const busy = status === 'queued' || status === 'processing';
  return (
    <Badge variant={variant} data-status={status}>
      {busy && <Loader2 className="size-3 animate-spin" aria-hidden />}
      {label}
    </Badge>
  );
}
