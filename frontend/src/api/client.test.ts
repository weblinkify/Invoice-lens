import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { ApiError, downloadExport, fileUrl, unwrap, uploadWithProgress } from './client';

describe('api client helpers', () => {
  it('unwrap returns data or throws ApiError', () => {
    const ok = new Response(null, { status: 200 });
    expect(unwrap({ data: 1, response: ok })).toBe(1);
    const problem = { type: 't', title: 'Bad', status: 400, detail: 'Nope', instance: '/x' };
    expect(() => unwrap({ error: problem, response: new Response(null, { status: 400 }) })).toThrow(
      'Nope',
    );
  });

  it('builds file urls', () => {
    expect(fileUrl('a b')).toMatch(/\/api\/v1\/documents\/a%20b\/file$/);
  });

  it('uploads with progress', async () => {
    const progress: number[] = [];
    const file = new File(['%PDF-1.4'], 'x.pdf', { type: 'application/pdf' });
    const res = await uploadWithProgress(file, (p) => progress.push(p));
    expect(res.id).toMatch(/^new-/);
    expect(progress.at(-1)).toBe(1);
  });

  it('rejects uploads with the problem detail', async () => {
    await expect(uploadWithProgress(new File([], 'e.pdf'), () => undefined)).rejects.toMatchObject({
      status: 422,
      message: 'The uploaded file is empty',
    });
  });

  it('downloads exports using the server filename', async () => {
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    await expect(downloadExport('csv', ['doc-1'])).resolves.toBe('invoicelens-mock.csv');
    expect(click).toHaveBeenCalled();
  });

  it('reports export errors', async () => {
    server.use(
      http.get('*/api/v1/exports', () =>
        HttpResponse.json(
          { type: 't', title: 'x', status: 404, detail: 'None found', instance: '/' },
          { status: 404 },
        ),
      ),
    );
    await expect(downloadExport('xlsx')).rejects.toBeInstanceOf(ApiError);
    server.use(http.get('*/api/v1/exports', () => new HttpResponse('boom', { status: 500 })));
    await expect(downloadExport('csv')).rejects.toThrow('Export failed');
  });
});
