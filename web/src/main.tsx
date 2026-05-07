import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Route, Routes, Navigate } from 'react-router-dom';
import App from './App';
import JobsIndex from './pages/JobsIndex';
import JobEditor from './pages/JobEditor';
import './index.css';

// basename="/ui" 對齊 vite.config.ts 的 base, 讓 React Router 在 /ui/jobs 等
// 路徑下正常運作 (FastAPI mount 於 /ui/*)
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename="/ui">
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<JobsIndex />} />
          <Route path="jobs/:jobId" element={<JobEditor />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
