import { createBrowserRouter, Navigate } from 'react-router-dom';
import { AppShell } from '@/layouts/AppShell';
import { ChatPage } from '@/pages/ChatPage';
import { PaperReadingPage } from '@/pages/PaperReadingPage';
import { PapersPage } from '@/pages/PapersPage';
import { ArtifactsPage } from '@/pages/ArtifactsPage';
import { ArtifactDetailPage } from '@/pages/ArtifactDetailPage';
import { SettingsPage } from '@/pages/SettingsPage';
import { ErrorBoundary } from '@/components/ErrorBoundary';

export const router = createBrowserRouter([
  {
    path: '/',
    element: (
      <ErrorBoundary>
        <AppShell />
      </ErrorBoundary>
    ),
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: 'chat', element: <ChatPage /> },
      { path: 'reading/:paperId', element: <PaperReadingPage /> },
      { path: 'papers', element: <PapersPage /> },
      { path: 'artifacts', element: <ArtifactsPage /> },
      { path: 'artifacts/:artifactId', element: <ArtifactDetailPage /> },
      { path: 'settings', element: <SettingsPage /> },
    ],
  },
]);
