import { Link, Outlet } from 'react-router-dom';
import { Toast, ToastProvider } from './components/Toast';

export default function App() {
  return (
    <ToastProvider>
      <div className="min-h-screen flex flex-col">
        <header className="bg-forest text-chalk-white border-b-4 border-chalk-yellow">
          <div className="mx-auto max-w-6xl px-6 py-3 flex items-center justify-between">
            <Link to="/" className="text-base font-medium hover:text-chalk-yellow">
              🎬 autoSolverVideo
            </Link>
            <nav className="text-sm">
              <Link to="/" className="text-chalk-yellow hover:underline">
                Jobs
              </Link>
            </nav>
          </div>
        </header>
        <main className="flex-1 mx-auto max-w-6xl w-full px-6 py-6">
          <Outlet />
        </main>
        <Toast />
      </div>
    </ToastProvider>
  );
}
