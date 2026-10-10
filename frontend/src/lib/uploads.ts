export const ACCEPTED_TYPES = [
  'application/pdf',
  'image/png',
  'image/jpeg',
  'image/tiff',
  'image/webp',
];
export const MAX_BYTES = 10 * 1024 * 1024;

export interface RejectedFile {
  file: File;
  reason: string;
}

/** Client-side pre-check; the API re-validates type (magic bytes) and size. */
export function partitionFiles(files: File[]): { accepted: File[]; rejected: RejectedFile[] } {
  const accepted: File[] = [];
  const rejected: RejectedFile[] = [];
  for (const file of files) {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      rejected.push({ file, reason: 'Unsupported file type' });
    } else if (file.size > MAX_BYTES) {
      rejected.push({ file, reason: 'File is larger than 10 MB' });
    } else if (file.size === 0) {
      rejected.push({ file, reason: 'File is empty' });
    } else {
      accepted.push(file);
    }
  }
  return { accepted, rejected };
}
