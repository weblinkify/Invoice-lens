import { Download, FileSpreadsheet, Inbox, Search } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { downloadExport } from '@/api/client';
import { useDocuments, useSettings } from '@/api/hooks';
import type { DocumentListQuery, DocumentStatus } from '@/api/types';
import { ConfidenceChip } from '@/components/ConfidenceChip';
import { StatusBadge } from '@/components/StatusBadge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatDateTime, formatMoney } from '@/lib/utils';

const PAGE_SIZE = 20;
const STATUSES: { value: DocumentStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'needs_review', label: 'Needs review' },
  { value: 'extracted', label: 'Ready' },
  { value: 'approved', label: 'Approved' },
  { value: 'processing', label: 'Processing' },
  { value: 'failed', label: 'Failed' },
];

export function DocumentsPage() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState<DocumentStatus | ''>('');
  const [needsReview, setNeedsReview] = useState(false);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [exporting, setExporting] = useState(false);
  const navigate = useNavigate();
  const threshold = useSettings().data?.confidence_threshold ?? 0.8;

  const query: DocumentListQuery = {
    page,
    page_size: PAGE_SIZE,
    ...(status ? { status } : {}),
    ...(needsReview ? { needs_review: true } : {}),
    ...(search.trim() ? { q: search.trim() } : {}),
  };
  const { data, isLoading, isError, error } = useDocuments(query);
  const items = data?.items ?? [];
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const allSelected = items.length > 0 && items.every((d) => selected.has(d.id));

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const exportAs = async (format: 'csv' | 'xlsx') => {
    setExporting(true);
    try {
      const name = await downloadExport(format, selected.size ? [...selected] : undefined);
      toast.success(`Exported ${name}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Export failed');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Documents</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} document${data.total === 1 ? '' : 's'}` : 'Loading…'}
            {selected.size > 0 && ` · ${selected.size} selected`}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" disabled={exporting} onClick={() => void exportAs('csv')}>
            <Download aria-hidden /> {selected.size ? 'Export selected CSV' : 'Export approved CSV'}
          </Button>
          <Button variant="outline" disabled={exporting} onClick={() => void exportAs('xlsx')}>
            <FileSpreadsheet aria-hidden /> Excel
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-card p-3">
        <div className="relative min-w-[220px] flex-1">
          <Search
            className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground"
            aria-hidden
          />
          <Input
            aria-label="Search by file name or invoice number"
            placeholder="Search file name or invoice number"
            className="pl-8"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <Select
          aria-label="Filter by status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as DocumentStatus | '');
            setPage(1);
          }}
        >
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
        <label className="flex items-center gap-2 text-sm">
          <Switch
            checked={needsReview}
            label="Only documents that need review"
            onCheckedChange={(v) => {
              setNeedsReview(v);
              setPage(1);
            }}
          />
          Needs review only
        </label>
      </div>

      <div className="rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <input
                  type="checkbox"
                  aria-label="Select all on this page"
                  checked={allSelected}
                  onChange={() => {
                    setSelected((prev) => {
                      const next = new Set(prev);
                      for (const d of items) {
                        if (allSelected) next.delete(d.id);
                        else next.add(d.id);
                      }
                      return next;
                    });
                  }}
                />
              </TableHead>
              <TableHead>File</TableHead>
              <TableHead>Vendor</TableHead>
              <TableHead>Invoice #</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Lowest confidence</TableHead>
              <TableHead>Uploaded</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading &&
              Array.from({ length: 4 }, (_, i) => (
                <TableRow key={i}>
                  <TableCell colSpan={8}>
                    <Skeleton className="h-5 w-full" />
                  </TableCell>
                </TableRow>
              ))}
            {items.map((d) => (
              <TableRow
                key={d.id}
                data-state={selected.has(d.id) ? 'selected' : undefined}
                className="cursor-pointer"
                onClick={() => {
                  void navigate(`/documents/${d.id}`);
                }}
              >
                <TableCell
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                >
                  <input
                    type="checkbox"
                    aria-label={`Select ${d.filename}`}
                    checked={selected.has(d.id)}
                    onChange={() => {
                      toggle(d.id);
                    }}
                  />
                </TableCell>
                <TableCell className="max-w-[220px]">
                  <Link
                    to={`/documents/${d.id}`}
                    className="block truncate font-medium hover:underline"
                    onClick={(e) => {
                      e.stopPropagation();
                    }}
                  >
                    {d.filename}
                  </Link>
                </TableCell>
                <TableCell className="max-w-[180px] truncate">{d.vendor_name ?? '—'}</TableCell>
                <TableCell className="font-mono text-xs">{d.invoice_number ?? '—'}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {formatMoney(d.total, d.currency)}
                </TableCell>
                <TableCell>
                  <StatusBadge status={d.status} />
                </TableCell>
                <TableCell>
                  {d.min_confidence !== null && d.status !== 'approved' ? (
                    <ConfidenceChip confidence={d.min_confidence} threshold={threshold} />
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-muted-foreground">
                  {formatDateTime(d.created_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {isError && (
          <p className="p-6 text-center text-sm text-destructive" role="alert">
            {error.message}
          </p>
        )}
        {!isLoading && !isError && items.length === 0 && (
          <div className="flex flex-col items-center gap-2 p-10 text-center text-muted-foreground">
            <Inbox className="size-8" aria-hidden />
            <p>No documents match these filters.</p>
            <Button asChild variant="link">
              <Link to="/">Upload an invoice</Link>
            </Button>
          </div>
        )}
      </div>

      {pages > 1 && (
        <nav aria-label="Pagination" className="flex items-center justify-end gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => {
              setPage((p) => p - 1);
            }}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {pages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= pages}
            onClick={() => {
              setPage((p) => p + 1);
            }}
          >
            Next
          </Button>
        </nav>
      )}
    </div>
  );
}
