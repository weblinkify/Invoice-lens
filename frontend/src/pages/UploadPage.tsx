import {
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  Sparkles,
  Webhook,
  XCircle,
} from 'lucide-react';
import { useCallback, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useDocument, useLoadSample, useSamples } from '@/api/hooks';
import { uploadWithProgress } from '@/api/client';
import { isProcessing } from '@/api/types';
import { StatusBadge } from '@/components/StatusBadge';
import { UploadDropzone } from '@/components/UploadDropzone';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import type { RejectedFile } from '@/lib/uploads';
import { formatBytes } from '@/lib/utils';

interface UploadEntry {
  key: string;
  name: string;
  size: number;
  progress: number;
  documentId?: string;
  error?: string;
}

/** Demo sample with clear review work (OCR-style error on a low-confidence field). */
export const PREFERRED_SAMPLE = 'invoice_02_modern_se.pdf';

function UploadRow({ entry }: { entry: UploadEntry }) {
  return (
    <li className="flex items-center gap-3 rounded-lg border bg-card p-3" data-testid="upload-row">
      <FileText className="size-5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-medium">{entry.name}</p>
          <span className="text-xs text-muted-foreground">{formatBytes(entry.size)}</span>
        </div>
        {entry.error ? (
          <p className="mt-1 flex items-center gap-1 text-xs text-destructive" role="alert">
            <XCircle className="size-3.5" aria-hidden /> {entry.error}
          </p>
        ) : entry.documentId ? (
          <DocumentProgress id={entry.documentId} />
        ) : (
          <Progress
            value={entry.progress * 100}
            label={`Uploading ${entry.name}`}
            className="mt-2"
          />
        )}
      </div>
    </li>
  );
}

function DocumentProgress({ id }: { id: string }) {
  const { data } = useDocument(id);
  if (!data) return <p className="mt-1 text-xs text-muted-foreground">Uploaded</p>;
  return (
    <div className="mt-1 flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <StatusBadge status={data.status} />
        {data.status === 'failed' && <span className="text-xs text-destructive">{data.error}</span>}
      </div>
      {!isProcessing(data.status) && data.status !== 'failed' && (
        <Link
          to={`/documents/${id}`}
          className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
        >
          Review <ArrowRight className="size-3.5" aria-hidden />
        </Link>
      )}
    </div>
  );
}

export function UploadPage() {
  const [entries, setEntries] = useState<UploadEntry[]>([]);
  const samples = useSamples();
  const loadSample = useLoadSample();
  const navigate = useNavigate();

  const update = useCallback((key: string, patch: Partial<UploadEntry>) => {
    setEntries((prev) => prev.map((e) => (e.key === key ? { ...e, ...patch } : e)));
  }, []);

  const onFiles = (accepted: File[], rejected: RejectedFile[]) => {
    const stamp = Date.now();
    const fresh: UploadEntry[] = [
      ...accepted.map((f, i) => ({
        key: `${stamp}-${i}`,
        name: f.name,
        size: f.size,
        progress: 0,
      })),
      ...rejected.map((r, i) => ({
        key: `${stamp}-r${i}`,
        name: r.file.name,
        size: r.file.size,
        progress: 0,
        error: r.reason,
      })),
    ];
    setEntries((prev) => [...fresh, ...prev]);
    accepted.forEach((file, i) => {
      const key = `${stamp}-${i}`;
      uploadWithProgress(file, (p) => {
        update(key, { progress: p });
      })
        .then((res) => {
          update(key, { documentId: res.id });
        })
        .catch((err: unknown) => {
          update(key, { error: err instanceof Error ? err.message : 'Upload failed' });
        });
    });
  };

  const trySample = () => {
    const list = samples.data ?? [];
    const name = list.find((s) => s.name === PREFERRED_SAMPLE)?.name ?? list[0]?.name;
    if (!name) {
      toast.error('No sample invoices are available');
      return;
    }
    loadSample.mutate(name, {
      onSuccess: (res) => {
        navigate(`/documents/${res.id}`);
      },
      onError: (err) => toast.error(err.message),
    });
  };

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <section className="space-y-4 pt-4 text-center">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Turn invoices into clean, verified data
        </h1>
        <p className="mx-auto max-w-2xl text-muted-foreground">
          Upload PDFs or scans. InvoiceLens reads every field, checks the maths, flags anything it
          is unsure about, and sends approved invoices straight to your ERP.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button
            size="lg"
            onClick={trySample}
            disabled={loadSample.isPending || samples.isLoading}
          >
            <Sparkles aria-hidden />{' '}
            {loadSample.isPending ? 'Loading sample…' : 'Try with sample invoice'}
          </Button>
          <Button size="lg" variant="outline" asChild>
            <Link to="/documents">View documents</Link>
          </Button>
        </div>
      </section>

      <UploadDropzone onFiles={onFiles} />

      {entries.length > 0 && (
        <section aria-labelledby="uploads-heading" className="space-y-2">
          <h2 id="uploads-heading" className="text-sm font-semibold text-muted-foreground">
            This session
          </h2>
          <ul className="space-y-2" aria-live="polite">
            {entries.map((e) => (
              <UploadRow key={e.key} entry={e} />
            ))}
          </ul>
        </section>
      )}

      <section className="grid gap-4 sm:grid-cols-3">
        {[
          {
            icon: Clock,
            title: 'Minutes, not hours',
            text: 'Fields, line items and totals extracted in seconds per invoice.',
          },
          {
            icon: CheckCircle2,
            title: 'Trust, but verify',
            text: 'Per-field confidence and arithmetic checks focus your review where it matters.',
          },
          {
            icon: Webhook,
            title: 'Straight to your ERP',
            text: 'Export CSV/Excel or push signed webhooks the moment you approve.',
          },
        ].map(({ icon: Icon, title, text }) => (
          <Card key={title}>
            <CardHeader>
              <Icon className="size-5 text-primary" aria-hidden />
              <CardTitle className="text-sm">{title}</CardTitle>
              <CardDescription>{text}</CardDescription>
            </CardHeader>
            <CardContent />
          </Card>
        ))}
      </section>
    </div>
  );
}
