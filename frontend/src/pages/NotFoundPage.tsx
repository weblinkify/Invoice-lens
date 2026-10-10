import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center gap-3 py-24 text-center">
      <p className="text-sm font-semibold text-primary">404</p>
      <h1 className="text-2xl font-bold">Page not found</h1>
      <Button asChild variant="outline">
        <Link to="/">Back to upload</Link>
      </Button>
    </div>
  );
}
