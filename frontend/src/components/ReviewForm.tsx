import { CheckCheck, CornerDownLeft, Keyboard, Loader2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useForm, type FieldPath } from 'react-hook-form';
import { toast } from 'sonner';
import { useApprove, useCorrectFields } from '@/api/hooks';
import type { Extraction, ValidationIssue } from '@/api/types';
import { Button } from '@/components/ui/button';
import {
  allFieldPaths,
  fieldKind,
  fromInputValue,
  getField,
  HEADER_FIELDS,
  LINE_ITEM_FIELDS,
  SECTIONS,
  toInputValue,
} from '@/lib/fields';
import { toFormValues, type LineValues, type ReviewValues } from '@/lib/reviewForm';
import { validateField } from '@/lib/validation';
import { FieldEditor } from './FieldEditor';
import { ValidationMessages } from './ValidationMessages';

function normalize(path: string, raw: string): string {
  const value = fromInputValue(fieldKind(path), raw);
  return value === null ? '' : String(value);
}

interface Props {
  documentId: string;
  extraction: Extraction;
  locked: boolean;
  onFieldFocus: (path: string | null) => void;
}

export function ReviewForm({ documentId, extraction, locked, onFieldFocus }: Props) {
  const { data, threshold, corrected_fields: corrected } = extraction;
  const formRef = useRef<HTMLFormElement>(null);
  const correct = useCorrectFields(documentId);
  const approve = useApprove(documentId);
  const {
    register,
    reset,
    trigger,
    getValues,
    formState: { errors },
  } = useForm<ReviewValues>({ defaultValues: toFormValues(data), mode: 'onBlur' });

  useEffect(() => {
    reset(toFormValues(data), { keepDirtyValues: true });
  }, [data, reset]);

  const issuesByField = useMemo(() => {
    const map = new Map<string, ValidationIssue[]>();
    for (const issue of data.validation_issues) {
      for (const path of issue.fields) map.set(path, [...(map.get(path) ?? []), issue]);
    }
    return map;
  }, [data.validation_issues]);

  const serverValue = useCallback(
    (path: string) => normalize(path, toInputValue(getField(data, path)?.value)),
    [data],
  );

  const errorFor = (path: string): string | undefined => {
    const parts = path.split('.');
    if (parts.length === 3) {
      const row = errors.line_items?.[Number(parts[1])];
      const err = row?.[parts[2] as keyof LineValues];
      return err?.message;
    }
    return errors[path as keyof Omit<ReviewValues, 'line_items'>]?.message;
  };

  const valueAt = (path: string): string => {
    const value: unknown = getValues(path as FieldPath<ReviewValues>);
    return typeof value === 'string' ? value : '';
  };

  /** Save one field. `confirm` also saves an unchanged value (marks it verified). */
  const saveField = async (path: string, confirm = false): Promise<void> => {
    if (locked) return;
    const formPath = path as FieldPath<ReviewValues>;
    if (!(await trigger(formPath))) return;
    const raw = valueAt(path);
    const unchanged = normalize(path, raw) === serverValue(path);
    if (unchanged && (!confirm || corrected.includes(path))) return;
    try {
      await correct.mutateAsync({
        corrections: [{ field: path, value: fromInputValue(fieldKind(path), raw) }],
      });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save the field');
    }
  };

  const dirtyPaths = (): string[] =>
    allFieldPaths(data).filter((p) => normalize(p, valueAt(p)) !== serverValue(p));

  const focusNextAttention = (from: Element | null): boolean => {
    const inputs = Array.from(
      formRef.current?.querySelectorAll<HTMLInputElement>('input[data-attention="true"]') ?? [],
    );
    const next = inputs.find((el) =>
      from ? Boolean(from.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) : true,
    );
    if (!next) return false;
    next.focus();
    next.select();
    return true;
  };

  const handleApprove = async () => {
    if (locked || approve.isPending) return;
    const pending = dirtyPaths();
    if (pending.length) {
      const valid = await trigger(pending as FieldPath<ReviewValues>[]);
      if (!valid) {
        toast.error('Fix the highlighted fields before approving');
        return;
      }
      await correct.mutateAsync({
        corrections: pending.map((p) => ({
          field: p,
          value: fromInputValue(fieldKind(p), valueAt(p)),
        })),
      });
    }
    approve.mutate(undefined, {
      onSuccess: () => toast.success('Invoice approved and sent to connected systems'),
      onError: (err) => toast.error(err.message),
    });
  };

  const approveRef = useRef(handleApprove);
  useEffect(() => {
    approveRef.current = handleApprove;
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        void approveRef.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
    };
  }, []);

  const attentionCount = allFieldPaths(data).filter((p) => {
    const f = getField(data, p);
    return f && !corrected.includes(p) && (f.confidence < threshold || issuesByField.has(p));
  }).length;

  const fieldProps = (path: string) => {
    const field = getField(data, path);
    const formPath = path as FieldPath<ReviewValues>;
    const reg = register(formPath, {
      validate: (v: unknown) =>
        validateField(path, fieldKind(path), typeof v === 'string' ? v : ''),
    });
    return {
      ...reg,
      path,
      kind: fieldKind(path),
      confidence: field?.confidence ?? 0,
      threshold,
      verified: corrected.includes(path),
      issues: issuesByField.get(path) ?? [],
      error: errorFor(path),
      readOnly: locked,
      saving: correct.isPending && correct.variables.corrections.some((c) => c.field === path),
      onFocus: () => {
        onFieldFocus(path);
      },
      onBlur: async (e: React.FocusEvent<HTMLInputElement>) => {
        await reg.onBlur(e);
        await saveField(path);
      },
      onKeyDown: (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          void saveField(path, true).then(() => focusNextAttention(e.currentTarget));
        }
      },
    };
  };

  return (
    <form
      ref={formRef}
      aria-label="Extracted invoice fields"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
      }}
      onKeyDown={(e) => {
        if (e.key === 'Tab' && !e.shiftKey && focusNextAttention(document.activeElement)) {
          e.preventDefault();
        }
      }}
      className="space-y-5"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card p-3">
        <p className="text-sm" aria-live="polite" data-testid="review-status">
          {locked ? (
            <span className="font-medium text-success">Approved — fields are locked.</span>
          ) : attentionCount ? (
            <>
              <span className="font-semibold">{attentionCount}</span> field
              {attentionCount === 1 ? '' : 's'} to check
            </>
          ) : (
            <span className="text-success">All fields look good.</span>
          )}
          {correct.isPending && (
            <span className="ml-2 inline-flex items-center gap-1 text-muted-foreground">
              <Loader2 className="size-3 animate-spin" aria-hidden /> Saving…
            </span>
          )}
        </p>
        <div className="flex gap-2">
          {!locked && attentionCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                focusNextAttention(null);
              }}
            >
              Next to check <kbd className="rounded border px-1 text-[10px]">Tab</kbd>
            </Button>
          )}
          <Button
            size="sm"
            onClick={() => void handleApprove()}
            disabled={locked || approve.isPending}
            aria-keyshortcuts="Control+Enter"
          >
            <CheckCheck aria-hidden />
            {approve.isPending ? 'Approving…' : locked ? 'Approved' : 'Approve'}
            {!locked && (
              <kbd className="rounded border border-primary-foreground/40 px-1 text-[10px]">
                Ctrl ↵
              </kbd>
            )}
          </Button>
        </div>
      </div>

      <ValidationMessages
        issues={data.validation_issues}
        onSelectField={(path) => {
          formRef.current?.querySelector<HTMLInputElement>(`input[name="${path}"]`)?.focus();
        }}
      />

      {SECTIONS.map((section) => (
        <fieldset key={section} className="rounded-lg border bg-card p-4">
          <legend className="px-1 text-sm font-semibold">{section}</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            {HEADER_FIELDS.filter((f) => f.section === section).map((f) => (
              <FieldEditor key={f.name} label={f.label} mono={f.mono} {...fieldProps(f.name)} />
            ))}
          </div>
        </fieldset>
      ))}

      <fieldset className="rounded-lg border bg-card p-4">
        <legend className="px-1 text-sm font-semibold">
          Line items ({data.line_items.length})
        </legend>
        {data.line_items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No line items were found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="w-8 pb-2">#</th>
                  {LINE_ITEM_FIELDS.map((f) => (
                    <th key={f.name} className={f.kind === 'number' ? 'pb-2 text-right' : 'pb-2'}>
                      {f.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.line_items.map((_, i) => (
                  <tr key={i} className="align-top">
                    <td className="pt-3 text-muted-foreground">{i + 1}</td>
                    {LINE_ITEM_FIELDS.map((f) => (
                      <td key={f.name} className={f.name === 'description' ? 'w-[38%] p-1' : 'p-1'}>
                        <FieldEditor
                          compact
                          label={`Line ${i + 1} ${f.label}`}
                          {...fieldProps(`line_items.${i}.${f.name}`)}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </fieldset>

      <aside className="flex flex-wrap gap-x-5 gap-y-1 rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1 font-medium">
          <Keyboard className="size-3.5" aria-hidden /> Shortcuts
        </span>
        <span>
          <kbd className="rounded border bg-background px-1">Tab</kbd> next field to check
        </span>
        <span>
          <kbd className="rounded border bg-background px-1">
            <CornerDownLeft className="inline size-3" aria-hidden />
          </kbd>{' '}
          save / confirm value
        </span>
        <span>
          <kbd className="rounded border bg-background px-1">Ctrl</kbd>+
          <kbd className="rounded border bg-background px-1">Enter</kbd> approve
        </span>
      </aside>
    </form>
  );
}
