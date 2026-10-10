import { zodResolver } from '@hookform/resolvers/zod';
import { BarChart3, KeyRound, Plus, Send, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useForm, useWatch } from 'react-hook-form';
import { toast } from 'sonner';
import {
  useAccuracy,
  useCreateWebhook,
  useDeleteWebhook,
  useDeliveries,
  useSettings,
  useTestWebhook,
  useToggleWebhook,
  useUpdateSettings,
  useWebhooks,
} from '@/api/hooks';
import type { WebhookEndpoint } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { formatDateTime, pct } from '@/lib/utils';
import {
  thresholdSchema,
  webhookSchema,
  type ThresholdFormValues,
  type WebhookFormValues,
} from '@/lib/validation';

function randomSecret(): string {
  const bytes = new Uint8Array(24);
  crypto.getRandomValues(bytes);
  return `whsec_${Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')}`;
}

function ThresholdCard() {
  const settings = useSettings();
  const update = useUpdateSettings();
  const form = useForm<ThresholdFormValues>({
    resolver: zodResolver(thresholdSchema),
    defaultValues: { threshold: 0.8 },
  });
  const { reset } = form;
  useEffect(() => {
    if (settings.data) reset({ threshold: settings.data.confidence_threshold });
  }, [settings.data, reset]);
  const value = useWatch({ control: form.control, name: 'threshold' });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Review threshold</CardTitle>
        <CardDescription>
          Fields below this confidence are highlighted and send the invoice to review. Changing it
          re-scores existing documents.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          className="flex flex-wrap items-end gap-4"
          onSubmit={form.handleSubmit((v) => {
            update.mutate(v.threshold, {
              onSuccess: () => toast.success(`Threshold set to ${pct(v.threshold)}`),
              onError: (err) => toast.error(err.message),
            });
          })}
        >
          <div className="min-w-[220px] flex-1 space-y-2">
            <Label htmlFor="threshold">
              Confidence threshold: {Number.isFinite(value) ? pct(value) : '—'}
            </Label>
            <input
              id="threshold"
              type="range"
              min={0.05}
              max={1}
              step={0.05}
              className="w-full accent-[hsl(var(--primary))]"
              {...form.register('threshold', { valueAsNumber: true })}
            />
            {form.formState.errors.threshold && (
              <p className="text-xs text-destructive">{form.formState.errors.threshold.message}</p>
            )}
          </div>
          <Button type="submit" disabled={update.isPending || settings.isLoading}>
            {update.isPending ? 'Saving…' : 'Save'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function DeliveryLog({ endpoint }: { endpoint: WebhookEndpoint }) {
  const deliveries = useDeliveries(endpoint.id, true);
  if (deliveries.isLoading) return <Skeleton className="h-6 w-full" />;
  const rows = deliveries.data ?? [];
  if (!rows.length) return <p className="text-xs text-muted-foreground">No deliveries yet.</p>;
  return (
    <ul className="space-y-1 text-xs">
      {rows.slice(0, 5).map((d) => (
        <li key={d.id} className="flex flex-wrap items-center gap-2">
          <Badge
            variant={
              d.status === 'succeeded'
                ? 'success'
                : d.status === 'failed'
                  ? 'destructive'
                  : 'secondary'
            }
          >
            {d.status}
          </Badge>
          <span className="font-mono">{d.event}</span>
          <span className="text-muted-foreground">
            {d.attempts} attempt{d.attempts === 1 ? '' : 's'}
            {d.last_status_code !== null && ` · HTTP ${d.last_status_code}`} ·{' '}
            {formatDateTime(d.created_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function WebhookRow({ endpoint }: { endpoint: WebhookEndpoint }) {
  const test = useTestWebhook();
  const remove = useDeleteWebhook();
  const toggle = useToggleWebhook();
  const [showLog, setShowLog] = useState(false);

  return (
    <li className="space-y-2 rounded-lg border p-3" data-testid="webhook-row">
      <div className="flex flex-wrap items-center gap-3">
        <Switch
          checked={endpoint.active}
          label={`Enable ${endpoint.url}`}
          onCheckedChange={(active) => {
            toggle.mutate({ id: endpoint.id, active });
          }}
        />
        <div className="min-w-0 flex-1">
          <p className="truncate font-mono text-sm">{endpoint.url}</p>
          <p className="text-xs text-muted-foreground">
            {endpoint.description ?? 'No description'} · secret {endpoint.secret_hint}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={test.isPending}
          onClick={() => {
            test.mutate(endpoint.id, {
              onSuccess: (d) => {
                setShowLog(true);
                if (d.status === 'succeeded')
                  toast.success(`Ping delivered (HTTP ${d.last_status_code ?? '?'})`);
                else toast.error(`Ping failed: ${d.last_error ?? 'unknown error'}`);
              },
              onError: (err) => toast.error(err.message),
            });
          }}
        >
          <Send aria-hidden /> {test.isPending ? 'Sending…' : 'Send test'}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            setShowLog((v) => !v);
          }}
          aria-expanded={showLog}
        >
          Log
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Delete webhook ${endpoint.url}`}
          disabled={remove.isPending}
          onClick={() => {
            remove.mutate(endpoint.id, { onSuccess: () => toast.success('Webhook removed') });
          }}
        >
          <Trash2 className="text-destructive" />
        </Button>
      </div>
      {showLog && <DeliveryLog endpoint={endpoint} />}
    </li>
  );
}

function WebhooksCard() {
  const webhooks = useWebhooks();
  const create = useCreateWebhook();
  const form = useForm<WebhookFormValues>({
    resolver: zodResolver(webhookSchema),
    defaultValues: { url: '', secret: '', description: '' },
  });
  const { errors } = form.formState;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Webhook endpoints</CardTitle>
        <CardDescription>
          Approved invoices are POSTed as JSON, signed with HMAC-SHA256 in the{' '}
          <code className="rounded bg-muted px-1">X-InvoiceLens-Signature</code> header, and retried
          with exponential backoff.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {webhooks.isLoading && <Skeleton className="h-14 w-full" />}
        {webhooks.data && webhooks.data.length > 0 && (
          <ul className="space-y-2">
            {webhooks.data.map((ep) => (
              <WebhookRow key={ep.id} endpoint={ep} />
            ))}
          </ul>
        )}
        {webhooks.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">No endpoints yet — add your ERP below.</p>
        )}
        <form
          className="grid gap-3 rounded-lg border border-dashed p-3 md:grid-cols-[2fr_1.4fr_1fr_auto] md:items-start"
          aria-label="Add webhook endpoint"
          onSubmit={form.handleSubmit((values) => {
            create.mutate(
              {
                url: values.url,
                secret: values.secret,
                description: values.description || null,
                active: true,
              },
              {
                onSuccess: () => {
                  form.reset();
                  toast.success('Webhook added');
                },
                onError: (err) => toast.error(err.message),
              },
            );
          })}
        >
          <div className="space-y-1">
            <Label htmlFor="wh-url">Endpoint URL</Label>
            <Input
              id="wh-url"
              placeholder="https://erp.example.com/webhooks/invoices"
              aria-invalid={!!errors.url}
              {...form.register('url')}
            />
            {errors.url && <p className="text-xs text-destructive">{errors.url.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="wh-secret">Signing secret</Label>
            <div className="flex gap-1">
              <Input
                id="wh-secret"
                className="font-mono"
                aria-invalid={!!errors.secret}
                {...form.register('secret')}
              />
              <Button
                variant="outline"
                size="icon"
                aria-label="Generate secret"
                onClick={() => {
                  form.setValue('secret', randomSecret(), { shouldValidate: true });
                }}
              >
                <KeyRound />
              </Button>
            </div>
            {errors.secret && <p className="text-xs text-destructive">{errors.secret.message}</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="wh-desc">Description</Label>
            <Input id="wh-desc" placeholder="Accounting ERP" {...form.register('description')} />
          </div>
          <Button type="submit" className="md:mt-6" disabled={create.isPending}>
            <Plus aria-hidden /> Add
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function AccuracyCard() {
  const [run, setRun] = useState(false);
  const accuracy = useAccuracy(run);
  const report = accuracy.data;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Extraction accuracy</CardTitle>
        <CardDescription>
          Runs the full pipeline over the bundled sample invoices and compares every field with
          ground truth.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button
          variant="outline"
          onClick={() => {
            if (run) void accuracy.refetch();
            setRun(true);
          }}
          disabled={accuracy.isFetching}
        >
          <BarChart3 aria-hidden /> {accuracy.isFetching ? 'Evaluating…' : 'Run accuracy check'}
        </Button>
        {report && (
          <div className="space-y-2 text-sm">
            <p>
              <span className="text-2xl font-bold">{pct(report.accuracy)}</span> field accuracy
              across {report.documents} invoices ({report.fields_correct}/{report.fields_total}{' '}
              fields) · {pct(report.review_rate)} routed to review · provider{' '}
              <code>{report.provider}</code>
            </p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-3">
              {report.per_field.map((f) => (
                <div key={f.field} className="flex justify-between gap-2 border-b py-1 text-xs">
                  <span className="truncate">{f.field}</span>
                  <span className="tabular-nums">{pct(f.accuracy)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {accuracy.isError && <p className="text-sm text-destructive">{accuracy.error.message}</p>}
      </CardContent>
    </Card>
  );
}

export function SettingsPage() {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Review rules and integrations.</p>
      </div>
      <ThresholdCard />
      <WebhooksCard />
      <AccuracyCard />
    </div>
  );
}
