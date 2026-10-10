import { AlertCircle, ArrowLeft, Download, Loader2, RotateCcw } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { downloadExport, fileUrl } from '@/api/client';
import { useDocument, useExtraction, useReprocess } from '@/api/hooks';
import { isProcessing } from '@/api/types';
import { DocumentViewer, type Highlight } from '@/components/DocumentViewer';
import { ReviewForm } from '@/components/ReviewForm';
import { StatusBadge } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { fieldLabel, getField } from '@/lib/fields';
import { formatDateTime } from '@/lib/utils';

export function ReviewPage() {
  const { id = '' } = useParams<{ id: string }>();
  const doc = useDocument(id);
  const status = doc.data?.status;
  const ready = status !== undefined && !isProcessing(status) && status !== 'failed';
  const extraction = useExtraction(id, ready);
  const reprocess = useReprocess(id);
  const [focused, setFocused] = useState<string | null>(null);

  const highlight = useMemo<Highlight | null>(() => {
    if (!focused || !extraction.data) return null;
    const field = getField(extraction.data.data, focused);
    if (!field?.bbox || !field.source_page) return null;
    return { page: field.source_page, bbox: field.bbox, label: fieldLabel(focused) };
  }, [focused, extraction.data]);

  if (doc.isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-20 text-center" role="alert">
        <AlertCircle className="size-8 text-destructive" aria-hidden />
        <p className="font-medium">{doc.error.message}</p>
        <Button asChild variant="outline">
          <Link to="/documents">Back to documents</Link>
        </Button>
      </div>
    );
  }

  if (!doc.data) return <Skeleton className="h-[70vh] w-full" />;
  const d = doc.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <Link
            to="/documents"
            className="mb-1 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" aria-hidden /> Documents
          </Link>
          <h1 className="flex flex-wrap items-center gap-2 text-xl font-bold tracking-tight">
            <span className="truncate">{d.filename}</span>
            <StatusBadge status={d.status} />
          </h1>
          <p className="text-xs text-muted-foreground">
            Uploaded {formatDateTime(d.created_at)}
            {d.ocr_method && ` · OCR: ${d.ocr_method.replace('_', ' ')}`}
            {extraction.data && ` · Extracted by ${extraction.data.provider}`}
            {d.approved_at && ` · Approved ${formatDateTime(d.approved_at)}`}
          </p>
        </div>
        {d.status === 'approved' && (
          <Button
            variant="outline"
            onClick={() => {
              downloadExport('csv', [d.id]).then(
                (name) => toast.success(`Exported ${name}`),
                (err: unknown) => toast.error(err instanceof Error ? err.message : 'Export failed'),
              );
            }}
          >
            <Download aria-hidden /> Export CSV
          </Button>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        <div className="lg:sticky lg:top-20 lg:h-[calc(100vh-7rem)]">
          <DocumentViewer
            url={fileUrl(d.id)}
            contentType={d.content_type}
            filename={d.filename}
            highlight={highlight}
          />
        </div>
        <div>
          {isProcessing(d.status) && (
            <div className="space-y-3 rounded-lg border bg-card p-6" aria-busy="true">
              <p className="flex items-center gap-2 font-medium">
                <Loader2 className="size-4 animate-spin" aria-hidden /> Reading the invoice…
              </p>
              <p className="text-sm text-muted-foreground">
                OCR, field extraction and validation usually take a few seconds.
              </p>
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          )}
          {d.status === 'failed' && (
            <div
              className="space-y-3 rounded-lg border border-destructive/40 bg-destructive/5 p-6"
              role="alert"
            >
              <p className="font-medium text-destructive">Extraction failed</p>
              <p className="text-sm">{d.error}</p>
              <Button
                variant="outline"
                disabled={reprocess.isPending}
                onClick={() => {
                  reprocess.mutate(undefined, { onSuccess: () => void doc.refetch() });
                }}
              >
                <RotateCcw aria-hidden /> Try again
              </Button>
            </div>
          )}
          {ready && !extraction.data && <Skeleton className="h-[60vh] w-full" />}
          {extraction.data && (
            <ReviewForm
              documentId={d.id}
              extraction={extraction.data}
              locked={d.status === 'approved'}
              onFieldFocus={setFocused}
            />
          )}
        </div>
      </div>
    </div>
  );
}
