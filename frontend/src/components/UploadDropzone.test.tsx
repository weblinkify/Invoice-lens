import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MAX_BYTES, partitionFiles } from '@/lib/uploads';
import { UploadDropzone } from './UploadDropzone';

const pdf = (name = 'a.pdf', size = 10) =>
  new File([new Uint8Array(size)], name, { type: 'application/pdf' });

describe('partitionFiles', () => {
  it('accepts supported files and explains rejections', () => {
    const big = pdf('big.pdf');
    Object.defineProperty(big, 'size', { value: MAX_BYTES + 1 });
    const { accepted, rejected } = partitionFiles([
      pdf(),
      new File(['x'], 'notes.txt', { type: 'text/plain' }),
      big,
      pdf('empty.pdf', 0),
    ]);
    expect(accepted.map((f) => f.name)).toEqual(['a.pdf']);
    expect(rejected.map((r) => [r.file.name, r.reason])).toEqual([
      ['notes.txt', 'Unsupported file type'],
      ['big.pdf', 'File is larger than 10 MB'],
      ['empty.pdf', 'File is empty'],
    ]);
  });
});

describe('UploadDropzone', () => {
  it('uploads through the accessible file input', async () => {
    const onFiles = vi.fn();
    render(<UploadDropzone onFiles={onFiles} />);
    await userEvent.upload(screen.getByLabelText('Upload invoice files'), [
      pdf('one.pdf'),
      pdf('two.pdf'),
    ]);
    expect(onFiles).toHaveBeenCalledWith([expect.any(File), expect.any(File)], []);
  });

  it('handles drag and drop with visual state', () => {
    const onFiles = vi.fn();
    render(<UploadDropzone onFiles={onFiles} />);
    const zone = screen.getByTestId('dropzone');
    fireEvent.dragOver(zone);
    expect(zone).toHaveAttribute('data-dragging', 'true');
    fireEvent.dragLeave(zone);
    expect(zone).toHaveAttribute('data-dragging', 'false');
    fireEvent.drop(zone, { dataTransfer: { files: [pdf()] } });
    expect(onFiles).toHaveBeenCalledTimes(1);
  });

  it('ignores files when disabled', () => {
    const onFiles = vi.fn();
    render(<UploadDropzone onFiles={onFiles} disabled />);
    fireEvent.drop(screen.getByTestId('dropzone'), { dataTransfer: { files: [pdf()] } });
    expect(onFiles).not.toHaveBeenCalled();
  });

  it('opens the file picker from the browse button', async () => {
    render(<UploadDropzone onFiles={vi.fn()} />);
    const input = screen.getByLabelText<HTMLInputElement>('Upload invoice files');
    const click = vi.spyOn(input, 'click');
    await userEvent.click(screen.getByRole('button', { name: 'browse files' }));
    expect(click).toHaveBeenCalled();
  });
});
