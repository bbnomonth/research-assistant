import type {
  Artifact,
  ArtifactSummary,
  ArtifactUpdateRequest,
  ChatMode,
  DiagnosticResult,
  EvidenceSearchResponse,
  FrameworkCardRequest,
  FrameworkCardResponse,
  GuidedReadingCardRequest,
  GuidedReadingCardResponse,
  HealthResponse,
  Message,
  Paper,
  PaperComparisonRequest,
  PaperComparisonResponse,
  Project,
  ProjectUpdateRequest,
  QuickAnalysisResponse,
  RuntimeSettings,
  Session,
  SessionUpdateRequest,
  StreamEvent,
  TaskRecord,
  TopicGuidanceCardRequest,
  TopicGuidanceCardResponse,
  UploadResponse,
} from '@/types/api';

const BASE = import.meta.env.VITE_BACKEND_URL ?? '';

function logRequest(method: string, path: string, status: number, ms: number): void {
  const level = status >= 500 ? 'error' : status >= 400 ? 'warn' : 'info';
  // eslint-disable-next-line no-console
  console[level](`[api] ${method} ${path} -> ${status} in ${ms.toFixed(0)}ms`);
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase();
  const start = performance.now();
  const hasBody = init.body !== undefined && init.body !== null;
  const headers = {
    ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
    ...(init.headers ?? {}),
  };
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers,
    });
  } catch (err) {
    logRequest(method, path, 0, performance.now() - start);
    throw new Error(
      `无法连接后端服务（${path}）：${(err as Error).message || '网络错误'}`,
    );
  }
  const elapsed = performance.now() - start;
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body && typeof body === 'object' && 'detail' in body) {
        const value = (body as { detail: unknown }).detail;
        detail = typeof value === 'string' ? value : JSON.stringify(value);
      }
    } catch {
      // ignore body parse errors and use status text
    }
    logRequest(method, path, response.status, elapsed);
    throw new Error(detail);
  }
  logRequest(method, path, response.status, elapsed);
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

async function uploadFile(
  path: string,
  file: File,
  fields: Record<string, string> = {},
): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  for (const [key, value] of Object.entries(fields)) {
    form.append(key, value);
  }
  const response = await fetch(`${BASE}${path}`, { method: 'POST', body: form });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail =
        typeof body.detail === 'string'
          ? body.detail
          : JSON.stringify(body.detail ?? body);
    } catch {
      // ignore
    }
    throw new Error(detail);
  }
  return (await response.json()) as UploadResponse;
}

export interface ChatStreamHandle {
  close: () => void;
}

export function streamChat(
  payload: {
    content: string;
    project_id?: string | null;
    session_id?: string | null;
    paper_id?: string | null;
    mode_override?: ChatMode | null;
  },
  handlers: {
    onEvent: (event: StreamEvent) => void;
    onError?: (message: string) => void;
    onClose?: () => void;
  },
): ChatStreamHandle {
  const controller = new AbortController();

  const run = async () => {
    let response: Response;
    try {
      response = await fetch(`${BASE}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      handlers.onError?.('无法连接到后端服务，请确认服务已启动。');
      handlers.onClose?.();
      return;
    }

    if (!response.ok || !response.body) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        detail =
          typeof body.detail === 'string'
            ? body.detail
            : JSON.stringify(body.detail ?? body);
      } catch {
        // ignore
      }
      handlers.onError?.(detail || '请求失败');
      handlers.onClose?.();
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let sepIndex: number;
        while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
          const rawEvent = buffer.slice(0, sepIndex);
          buffer = buffer.slice(sepIndex + 2);
          const lines = rawEvent.split('\n');
          let eventName = 'message';
          const dataLines: string[] = [];
          for (const line of lines) {
            if (line.startsWith('event:')) {
              eventName = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).trim());
            }
          }
          const dataText = dataLines.join('\n');
          if (!dataText) continue;
          try {
            const data = JSON.parse(dataText) as Record<string, unknown>;
            handlers.onEvent({
              event: eventName as StreamEvent['event'],
              data,
            });
          } catch {
            // skip malformed event
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        handlers.onError?.('连接中断，请稍后重试。');
      }
    } finally {
      handlers.onClose?.();
    }
  };

  void run();

  return {
    close: () => controller.abort(),
  };
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),

  listProjects: () => request<{ projects: Project[] }>('/api/projects'),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  updateProject: (id: string, body: ProjectUpdateRequest) =>
    request<Project>(`/api/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteProject: (id: string) =>
    request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
  listProjectSessions: (id: string) =>
    request<{ sessions: Session[] }>(`/api/projects/${id}/sessions`),
  listProjectPapers: (id: string) =>
    request<{ papers: Paper[] }>(`/api/projects/${id}/papers`),
  listSessionMessages: (id: string) =>
    request<{ messages: Message[] }>(`/api/sessions/${id}/messages`),
  renameSession: (id: string, body: SessionUpdateRequest) =>
    request<Session>(`/api/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  deleteSession: (id: string) =>
    request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),

  uploadPdf: (file: File, projectId?: string) =>
    uploadFile('/api/papers/upload', file, projectId ? { project_id: projectId } : {}),
  getPaper: (paperId: string) => request<Paper>(`/api/papers/${paperId}`),
  searchEvidence: (paperId: string, query: string) =>
    request<EvidenceSearchResponse>(
      `/api/papers/${paperId}/evidence?q=${encodeURIComponent(query)}`,
    ),
  paperPdfUrl: (paperId: string) => `${BASE}/api/papers/${paperId}/pdf`,
  importArxivPdf: (paperId: string) =>
    request<UploadResponse>(`/api/papers/${paperId}/import-pdf`, { method: 'POST' }),
  quickAnalysis: (paperId: string) =>
    request<QuickAnalysisResponse>(
      `/api/papers/${paperId}/quick-analysis`,
      { method: 'POST' },
    ),
  comparePapers: (body: PaperComparisonRequest) =>
    request<PaperComparisonResponse>('/api/papers/compare', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createFrameworkCard: (body: FrameworkCardRequest) =>
    request<FrameworkCardResponse>('/api/chat/framework/card', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createTopicGuidanceCard: (body: TopicGuidanceCardRequest) =>
    request<TopicGuidanceCardResponse>('/api/chat/topic/card', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createGuidedReadingCard: (body: GuidedReadingCardRequest) =>
    request<GuidedReadingCardResponse>('/api/chat/guided-reading/card', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  favoritePaper: (body: { project_id: string; arxiv_id: string; favorited: boolean }) =>
    request<{ ok: boolean; favorited?: boolean; message?: string }>(
      '/api/papers/favorite',
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    ),

  getTask: (id: string) => request<TaskRecord>(`/api/tasks/${id}`),
  cancelTask: (id: string) =>
    request<TaskRecord>(`/api/tasks/${id}/cancel`, { method: 'POST' }),
  retryTask: (id: string) =>
    request<TaskRecord>(`/api/tasks/${id}/retry`, { method: 'POST' }),

  listProjectArtifacts: (projectId: string) =>
    request<{ artifacts: ArtifactSummary[] }>(
      `/api/projects/${projectId}/artifacts`,
    ),
  getArtifact: (id: string) => request<Artifact>(`/api/artifacts/${id}`),
  deleteArtifact: (id: string) =>
    request<void>(`/api/artifacts/${id}`, { method: 'DELETE' }),
  updateArtifact: (id: string, body: ArtifactUpdateRequest) =>
    request<Artifact>(`/api/artifacts/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  exportArtifactMarkdownUrl: (id: string) =>
    `${BASE}/api/artifacts/${id}/markdown`,

  getRuntimeSettings: () => request<RuntimeSettings>('/api/system/settings'),
  checkStorage: () =>
    request<DiagnosticResult>('/api/system/check-storage', { method: 'POST' }),
  checkOcr: () =>
    request<DiagnosticResult>('/api/system/check-ocr', { method: 'POST' }),
  checkModel: () =>
    request<DiagnosticResult>('/api/system/check-model', { method: 'POST' }),
  wipeData: () =>
    request<{
      wiped: boolean;
      removed_uploads: number;
      removed_messages: number;
      removed_sessions: number;
      removed_projects: number;
      message?: string;
    }>('/api/system/wipe-data', { method: 'POST' }),
};

export type Api = typeof api;
