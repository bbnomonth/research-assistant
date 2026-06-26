import { create } from 'zustand';
import type {
  ArtifactSummary,
  ChatMode,
  Paper,
  Project,
  RuntimeSettings,
  Session,
} from '@/types/api';

export interface ChatTurnAttachment {
  type: 'search_results' | 'artifact' | 'evidence';
  data: unknown;
}

export interface EvidenceAttachmentData {
  paper_id: string;
  pages?: number[];
  evidence_id?: string;
  feedback?: string;
  next_question?: string;
}

export interface ArtifactAttachmentData {
  artifact_id: string;
  artifact_type?: string;
  title?: string;
}

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  mode?: ChatMode;
  projectId?: string;
  sessionId?: string;
  paperId?: string;
  pending?: boolean;
  error?: string;
  errorCode?: string;
  attachments?: ChatTurnAttachment[];
}

interface AppState {
  // Backend runtime info
  settings: RuntimeSettings | null;
  setSettings: (s: RuntimeSettings) => void;

  // Projects
  projects: Project[];
  setProjects: (items: Project[]) => void;
  upsertProject: (item: Project) => void;

  activeProjectId: string | null;
  setActiveProjectId: (id: string | null) => void;

  // Sessions
  sessionsByProject: Record<string, Session[]>;
  setSessions: (projectId: string, sessions: Session[]) => void;

  // Papers for active project
  papers: Paper[];
  setPapers: (papers: Paper[]) => void;
  activePaperId: string | null;
  setActivePaperId: (id: string | null) => void;

  // Chat state per session
  turnsBySession: Record<string, ChatTurn[]>;
  appendTurn: (sessionId: string, turn: ChatTurn) => void;
  patchTurn: (sessionId: string, turnId: string, patch: Partial<ChatTurn>) => void;
  appendAttachment: (
    sessionId: string,
    turnId: string,
    attachment: ChatTurnAttachment,
  ) => void;
  moveTurns: (
    fromSessionId: string,
    toSessionId: string,
    projectId: string,
  ) => void;

  // Artifacts cache
  artifactsByProject: Record<string, ArtifactSummary[]>;
  setArtifacts: (projectId: string, list: ArtifactSummary[]) => void;

  // Streaming
  streaming: boolean;
  streamingSessionId: string | null;
  setStreaming: (sessionId: string | null) => void;

  reset: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  settings: null,
  setSettings: (s) => set({ settings: s }),

  projects: [],
  setProjects: (items) => set({ projects: items }),
  upsertProject: (item) =>
    set((state) => {
      const idx = state.projects.findIndex((p) => p.id === item.id);
      const next = [...state.projects];
      if (idx >= 0) {
        next[idx] = item;
      } else {
        next.unshift(item);
      }
      next.sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
      return { projects: next };
    }),

  activeProjectId: null,
  setActiveProjectId: (id) => set({ activeProjectId: id }),

  sessionsByProject: {},
  setSessions: (projectId, sessions) =>
    set((state) => ({
      sessionsByProject: { ...state.sessionsByProject, [projectId]: sessions },
    })),

  papers: [],
  setPapers: (papers) => set({ papers }),
  activePaperId: null,
  setActivePaperId: (id) => set({ activePaperId: id }),

  turnsBySession: {},
  appendTurn: (sessionId, turn) =>
    set((state) => {
      const list = state.turnsBySession[sessionId] ?? [];
      return {
        turnsBySession: {
          ...state.turnsBySession,
          [sessionId]: [...list, turn],
        },
      };
    }),
  patchTurn: (sessionId, turnId, patch) =>
    set((state) => {
      const list = state.turnsBySession[sessionId] ?? [];
      return {
        turnsBySession: {
          ...state.turnsBySession,
          [sessionId]: list.map((t) => (t.id === turnId ? { ...t, ...patch } : t)),
        },
      };
    }),
  appendAttachment: (sessionId, turnId, attachment) =>
    set((state) => {
      const list = state.turnsBySession[sessionId] ?? [];
      return {
        turnsBySession: {
          ...state.turnsBySession,
          [sessionId]: list.map((t) =>
            t.id === turnId
              ? { ...t, attachments: [...(t.attachments ?? []), attachment] }
              : t,
          ),
        },
      };
    }),
  moveTurns: (fromSessionId, toSessionId, projectId) =>
    set((state) => {
      if (fromSessionId === toSessionId) {
        return {};
      }
      const source = state.turnsBySession[fromSessionId] ?? [];
      const existing = state.turnsBySession[toSessionId] ?? [];
      const turnsBySession = { ...state.turnsBySession };
      delete turnsBySession[fromSessionId];
      turnsBySession[toSessionId] = [
        ...existing,
        ...source.map((turn) => ({
          ...turn,
          projectId,
          sessionId: toSessionId,
        })),
      ];
      return { turnsBySession };
    }),

  artifactsByProject: {},
  setArtifacts: (projectId, list) =>
    set((state) => ({
      artifactsByProject: { ...state.artifactsByProject, [projectId]: list },
    })),

  streaming: false,
  streamingSessionId: null,
  setStreaming: (sessionId) =>
    set({ streaming: sessionId !== null, streamingSessionId: sessionId }),

  reset: () =>
    set({
      settings: null,
      projects: [],
      activeProjectId: null,
      sessionsByProject: {},
      papers: [],
      activePaperId: null,
      turnsBySession: {},
      artifactsByProject: {},
      streaming: false,
      streamingSessionId: null,
    }),
}));
