import { AlertTriangle } from 'lucide-react';
import type { ValidationIssue } from '@/api/types';
import { fieldLabel } from '@/lib/fields';

interface Props {
  issues: ValidationIssue[];
  onSelectField?: (path: string) => void;
}

export function ValidationMessages({ issues, onSelectField }: Props) {
  if (!issues.length) return null;
  return (
    <section
      aria-labelledby="validation-heading"
      className="rounded-lg border border-destructive/30 bg-destructive/5 p-4"
    >
      <h2
        id="validation-heading"
        className="flex items-center gap-2 text-sm font-semibold text-destructive"
      >
        <AlertTriangle className="size-4" aria-hidden />
        {issues.length === 1 ? '1 validation issue' : `${issues.length} validation issues`}
      </h2>
      <ul className="mt-2 space-y-2 text-sm">
        {issues.map((issue, i) => (
          <li key={`${issue.code}-${i}`} data-code={issue.code}>
            <p>{issue.message}</p>
            {issue.fields.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {issue.fields.slice(0, 6).map((path) => (
                  <button
                    key={path}
                    type="button"
                    className="rounded border bg-background px-1.5 py-0.5 text-xs text-muted-foreground hover:text-foreground"
                    onClick={() => onSelectField?.(path)}
                  >
                    {fieldLabel(path)}
                  </button>
                ))}
                {issue.fields.length > 6 && (
                  <span className="text-xs text-muted-foreground">
                    +{issue.fields.length - 6} more
                  </span>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
