import { FileUp } from 'lucide-react';
import { useId, useRef, useState } from 'react';
import { ACCEPTED_TYPES, partitionFiles, type RejectedFile } from '@/lib/uploads';
import { cn } from '@/lib/utils';

interface Props {
  onFiles: (accepted: File[], rejected: RejectedFile[]) => void;
  disabled?: boolean;
}

export function UploadDropzone({ onFiles, disabled = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const hintId = useId();

  const handle = (list: FileList | null) => {
    if (!list || disabled) return;
    const { accepted, rejected } = partitionFiles(Array.from(list));
    onFiles(accepted, rejected);
  };

  return (
    <div
      data-testid="dropzone"
      data-dragging={dragging}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => {
        setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        handle(e.dataTransfer.files);
      }}
      className={cn(
        'relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors',
        dragging
          ? 'border-primary bg-accent'
          : 'border-input hover:border-primary/60 hover:bg-muted/40',
        disabled && 'pointer-events-none opacity-60',
      )}
    >
      <div className="rounded-full bg-primary/10 p-3 text-primary">
        <FileUp className="size-6" aria-hidden />
      </div>
      <div>
        <p className="text-base font-medium">
          Drop invoices here or{' '}
          <button
            type="button"
            className="text-primary underline-offset-4 hover:underline"
            onClick={() => inputRef.current?.click()}
          >
            browse files
          </button>
        </p>
        <p id={hintId} className="mt-1 text-sm text-muted-foreground">
          PDF, PNG, JPEG, TIFF or WebP · up to 10 MB each · multiple files welcome
        </p>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPTED_TYPES.join(',')}
        aria-label="Upload invoice files"
        aria-describedby={hintId}
        className="sr-only"
        disabled={disabled}
        onChange={(e) => {
          handle(e.target.files);
          e.target.value = '';
        }}
      />
    </div>
  );
}
