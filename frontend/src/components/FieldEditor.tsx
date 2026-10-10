import { forwardRef, useId } from 'react';
import type { ValidationIssue } from '@/api/types';
import { Input } from '@/components/ui/input';
import { confidenceBand } from '@/lib/confidence';
import type { FieldKind } from '@/lib/fields';
import { cn } from '@/lib/utils';
import { ConfidenceChip } from './ConfidenceChip';

export interface FieldEditorProps extends React.InputHTMLAttributes<HTMLInputElement> {
  path: string;
  label: string;
  kind: FieldKind;
  confidence: number;
  threshold: number;
  verified?: boolean;
  issues?: ValidationIssue[];
  error?: string;
  mono?: boolean;
  compact?: boolean;
  saving?: boolean;
}

/** Labelled input with confidence chip and inline validation; ref/props come from react-hook-form. */
export const FieldEditor = forwardRef<HTMLInputElement, FieldEditorProps>(function FieldEditor(
  {
    path,
    label,
    kind,
    confidence,
    threshold,
    verified = false,
    issues = [],
    error,
    mono = false,
    compact = false,
    saving = false,
    className,
    ...inputProps
  },
  ref,
) {
  const id = useId();
  const messageId = `${id}-msg`;
  const band = confidenceBand(confidence, threshold);
  const needsAttention = !verified && (band !== 'high' || issues.length > 0);
  const messages = [...(error ? [error] : []), ...issues.map((i) => i.message)];

  return (
    <div className={cn('space-y-1.5', className)} data-field={path}>
      <div className={cn('flex items-center justify-between gap-2', compact && 'sr-only')}>
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        <ConfidenceChip confidence={confidence} threshold={threshold} verified={verified} />
      </div>
      <div className="relative">
        <Input
          ref={ref}
          id={id}
          name={path}
          inputMode={kind === 'number' ? 'decimal' : undefined}
          placeholder={kind === 'date' ? 'YYYY-MM-DD' : kind === 'number' ? '0.00' : '—'}
          autoComplete="off"
          spellCheck={false}
          aria-invalid={messages.length > 0}
          aria-describedby={messages.length ? messageId : undefined}
          data-attention={needsAttention}
          data-band={verified ? 'verified' : band}
          className={cn(
            mono && 'font-mono',
            kind === 'number' && 'text-right tabular-nums',
            needsAttention && band === 'low' && 'border-destructive/60 bg-destructive/5',
            needsAttention && band === 'medium' && 'border-warning/60 bg-warning/5',
            saving && 'opacity-70',
          )}
          {...inputProps}
        />
        {compact && (
          <span className="pointer-events-none absolute -top-2 right-1">
            <ConfidenceChip confidence={confidence} threshold={threshold} verified={verified} />
          </span>
        )}
      </div>
      {messages.length > 0 && (
        <ul id={messageId} className="space-y-0.5 text-xs text-destructive">
          {messages.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ul>
      )}
    </div>
  );
});
