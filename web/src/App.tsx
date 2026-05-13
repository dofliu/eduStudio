import { Link, Outlet } from 'react-router-dom';
import { Toast, ToastProvider } from './components/Toast';
import { VoicePicker } from './components/VoicePicker';

export default function App() {
  return (
    <ToastProvider>
      <div className="min-h-screen flex flex-col">
        <header className="bg-forest text-chalk-white border-b-4 border-chalk-yellow">
          <div className="mx-auto max-w-6xl px-6 py-3 flex items-center justify-between gap-4">
            <Link to="/" className="text-base font-medium hover:text-chalk-yellow shrink-0">
              🎬 autoSolverVideo
            </Link>
            <div className="flex-1" />
            {/* PR-3l: 全域聲音 picker, 切了影響後續 render */}
            <VoicePicker />
            <nav className="text-sm shrink-0 flex gap-3">
              <Link to="/" className="text-chalk-yellow hover:underline">
                Jobs
              </Link>
              <Link to="/proposals" className="text-chalk-yellow hover:underline">
                Proposals
              </Link>
              <Link to="/library" className="text-chalk-yellow hover:underline">
                Library
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
