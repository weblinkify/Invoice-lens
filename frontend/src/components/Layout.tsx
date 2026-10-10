import { FileText, Moon, ScanSearch, Settings, Sun, Upload } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { useSettings } from '@/api/hooks';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useTheme } from '@/hooks/useTheme';
import { cn } from '@/lib/utils';

const NAV = [
  { to: '/', label: 'Upload', icon: Upload, end: true },
  { to: '/documents', label: 'Documents', icon: FileText, end: false },
  { to: '/settings', label: 'Settings', icon: Settings, end: false },
];

export function Layout() {
  const { theme, toggle } = useTheme();
  const settings = useSettings();

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b bg-background/85 backdrop-blur">
        <div className="container flex h-14 items-center gap-4">
          <NavLink to="/" className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="rounded-md bg-primary p-1 text-primary-foreground">
              <ScanSearch className="size-4" aria-hidden />
            </span>
            InvoiceLens
          </NavLink>
          <nav aria-label="Main" className="flex items-center gap-1">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground',
                    isActive && 'bg-muted font-medium text-foreground',
                  )
                }
              >
                <Icon className="size-4" aria-hidden />
                <span className="hidden sm:inline">{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            {settings.data && (
              <Badge variant="secondary" className="hidden md:inline-flex" title="LLM provider">
                LLM: {settings.data.llm_provider}
                {settings.data.demo_mode ? ' · demo' : ''}
              </Badge>
            )}
            <Button
              variant="ghost"
              size="icon"
              onClick={toggle}
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {theme === 'dark' ? <Sun /> : <Moon />}
            </Button>
          </div>
        </div>
      </header>
      <main id="main" className="container flex-1 py-6">
        <Outlet />
      </main>
      <footer className="border-t py-4 text-center text-xs text-muted-foreground">
        InvoiceLens · OCR + LLM extraction with human-in-the-loop review
      </footer>
    </div>
  );
}
