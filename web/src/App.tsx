import { Outlet } from 'react-router-dom';
import { Toast, ToastProvider } from './components/Toast';
import { Sidebar } from './components/ui/Sidebar';

export default function App() {
  return (
    <ToastProvider>
      <div className="min-h-screen flex bg-paper">
        <Sidebar />
        <main className="flex-1 flex flex-col overflow-hidden min-w-0">
          <Outlet />
        </main>
        <Toast />
      </div>
    </ToastProvider>
  );
}
