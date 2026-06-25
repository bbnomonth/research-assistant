import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  List,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  App as AntdApp,
} from 'antd';
import {
  SendOutlined,
  ReloadOutlined,
  StopOutlined,
  ReadOutlined,
  SearchOutlined,
  ExperimentOutlined,
  EditOutlined,
  DeleteOutlined,
  CheckOutlined,
  CloseOutlined,
  PlusOutlined,
  FileSearchOutlined,
  RobotOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { api, streamChat, type ChatStreamHandle } from '@/api/client';
import { useAppStore, type ChatTurn, type ChatTurnAttachment } from '@/store/app';
import type {
  ChatMode,
  LiteratureDiscoveryResult,
  Message,
  Paper,
  Session,
} from '@/types/api';
import { CHAT_MODE_LABEL } from '@/types/api';
import { describeMode } from '@/utils/chat';
import { isUploaded } from '@/utils/paper';
import {
  removeLiveMessageDuplicates,
  resolveChatTarget,
  resolveRenderSessionId,
} from '@/utils/sessionFlow';
import { SearchResults } from '@/components/SearchResults';
import {
  StageProgress,
  type StreamingStages,
  useAutoScroll,
} from '@/components/StageProgress';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';

const { TextArea } = Input;

type ChatModeFilter = 'all' | ChatMode;

interface AttachmentSearchResults {
  type: 'search_results';
  data: unknown;
}
interface AttachmentArtifact {
  type: 'artifact';
  data: { artifact_id: string; artifact_type?: string; title?: string };
}
interface AttachmentEvidence {
  type: 'evidence';
  data: { paper_id: string; pages?: number[] };
}
type Attachment = AttachmentSearchResults | AttachmentArtifact | AttachmentEvidence;

interface PendingSend {
  content: string;
  projectId: string | null;
  sessionId: string | null;
  localSessionId: string;
  paperId: string | null;
  modeOverride?: ChatMode;
  turnId: string;
  replyId: string;
}

export function ChatPage() {
  const { message: toast } = AntdApp.useApp();
  const {
    activeProjectId,
    setActiveProjectId,
    projects,
    setProjects,
    sessionsByProject,
    setSessions,
    papers,
    setPapers,
    turnsBySession,
    appendTurn,
    patchTurn,
    appendAttachment,
    moveTurns,
    streaming,
    setStreaming,
  } = useAppStore();

  const navigate = useNavigate();

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [modeFilter, setModeFilter] = useState<ChatModeFilter>('all');
  const [input, setInput] = useState('');
  const [guidedPaperId, setGuidedPaperId] = useState<string | null>(null);
  const [forcePaperReading, setForcePaperReading] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [stages, setStages] = useState<StreamingStages>({});
  const [lastSend, setLastSend] = useState<PendingSend | null>(null);
  const [renamingSessionId, setRenamingSessionId] = useState<string | null>(null);

  const streamRef = useRef<ChatStreamHandle | null>(null);
  const scrollRef = useAutoScroll<HTMLDivElement>([
    turnsBySession,
    messages,
    streaming,
    stages,
  ]);

  const sessions: Session[] = useMemo(
    () => (activeProjectId ? sessionsByProject[activeProjectId] ?? [] : []),
    [activeProjectId, sessionsByProject],
  );

  useEffect(() => {
    if (!activeProjectId) {
      setActiveSessionId(null);
      setMessages([]);
      return;
    }
    setActiveSessionId(null);
    void loadSessions(activeProjectId);
    void loadPapers(activeProjectId);
  }, [activeProjectId]);

  useEffect(() => {
    if (!activeProjectId || sessions.length === 0) {
      setActiveSessionId(null);
      setMessages([]);
      return;
    }
    setActiveSessionId(sessions[0].id);
  }, [activeProjectId, sessions]);

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      return;
    }
    void loadMessages(activeSessionId);
  }, [activeSessionId]);

  const filteredTurns = useMemo(() => {
    const list = activeSessionId ? turnsBySession[activeSessionId] ?? [] : [];
    if (modeFilter === 'all') return list;
    return list.filter(
      (t) => t.mode === modeFilter || (t.role === 'user' && !t.mode),
    );
  }, [turnsBySession, activeSessionId, modeFilter]);

  const visibleMessages = useMemo(() => {
    const turns = activeSessionId
      ? turnsBySession[activeSessionId] ?? []
      : [];
    const deduped = removeLiveMessageDuplicates(messages, turns);
    if (modeFilter === 'all') return deduped;
    return deduped.filter(
      (message) =>
        message.role === 'user' || message.mode === modeFilter,
    );
  }, [messages, turnsBySession, activeSessionId, modeFilter]);

  const ensureProjectAndSession = async () => {
    let availableProjects = projects;
    if (!activeProjectId && projects.length === 0) {
      const response = await api.listProjects();
      availableProjects = response.projects;
      useAppStore.getState().setProjects(availableProjects);
    }
    return resolveChatTarget(
      activeProjectId,
      activeSessionId,
      availableProjects,
    );
  };

  const loadSessions = async (projectId: string) => {
    setLoadingSessions(true);
    try {
      const res = await api.listProjectSessions(projectId);
      setSessions(projectId, res.sessions);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoadingSessions(false);
    }
  };

  const loadPapers = async (projectId: string) => {
    try {
      const res = await api.listProjectPapers(projectId);
      setPapers(res.papers);
    } catch (err) {
      console.error(err);
      setPapers([]);
    }
  };

  const loadMessages = async (sessionId: string) => {
    setLoadingMessages(true);
    try {
      const res = await api.listSessionMessages(sessionId);
      setMessages(res.messages);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoadingMessages(false);
    }
  };

  const startStream = (params: PendingSend) => {
    setStages({});
    setStreaming(params.localSessionId);
    setLastSend(params);
    let renderSessionId = params.localSessionId;
    let resolvedProjectId = params.projectId;
    let resolvedSessionId = params.sessionId;

    const handle = streamChat(
      {
        content: params.content,
        project_id: params.projectId,
        session_id: params.sessionId,
        paper_id: params.paperId ?? undefined,
        mode_override: params.modeOverride ?? null,
      },
      {
        onEvent: (event) => {
          switch (event.event) {
            case 'mode': {
              const mode = event.data.mode as ChatMode;
              patchTurn(renderSessionId, params.replyId, { mode });
              break;
            }
            case 'metadata': {
              const metaSession = event.data.session_id as string;
              const metaProject = event.data.project_id as string;
              const metaTitle = event.data.title as string | undefined;
              if (metaSession && metaSession !== renderSessionId) {
                moveTurns(renderSessionId, metaSession, metaProject);
                renderSessionId = metaSession;
              }
              resolvedProjectId = metaProject;
              resolvedSessionId = metaSession;
              setActiveProjectId(metaProject);
              setActiveSessionId(metaSession);
              void api.listProjects().then((response) => {
                setProjects(response.projects);
              });
              if (metaTitle) {
                const state = useAppStore.getState();
                const currentSessions =
                  state.sessionsByProject[metaProject] ?? [];
                const existing = currentSessions.find(
                  (s) => s.id === metaSession,
                );
                if (!existing || existing.title !== metaTitle) {
                  if (existing) {
                    const updated = currentSessions.map((s) =>
                      s.id === metaSession ? { ...s, title: metaTitle } : s,
                    );
                    setSessions(metaProject, updated);
                  } else {
                    const placeholder: Session = {
                      id: metaSession,
                      project_id: metaProject,
                      title: metaTitle,
                      summary: '',
                      created_at: new Date().toISOString(),
                      updated_at: new Date().toISOString(),
                    };
                    setSessions(metaProject, [
                      placeholder,
                      ...currentSessions,
                    ]);
                  }
                }
              }
              setLastSend({
                ...params,
                projectId: metaProject,
                sessionId: metaSession,
                localSessionId: metaSession,
              });
              patchTurn(renderSessionId, params.replyId, {
                projectId: metaProject,
                sessionId: metaSession,
              });
              break;
            }
            case 'stage': {
              const name = event.data.name as keyof StreamingStages | undefined;
              if (name) {
                setStages((prev) => ({
                  ...prev,
                  [mapStageName(name)]: event.data.label as string,
                }));
              }
              break;
            }
            case 'token': {
              const token = (event.data.content as string) ?? '';
              const current =
                useAppStore.getState().turnsBySession[renderSessionId] ?? [];
              const target = current.find((t) => t.id === params.replyId);
              patchTurn(renderSessionId, params.replyId, {
                content: (target?.content ?? '') + token,
              });
              break;
            }
            case 'search_results': {
              appendAttachment(renderSessionId, params.replyId, {
                type: 'search_results',
                data: event.data as unknown as LiteratureDiscoveryResult,
              });
              break;
            }
            case 'evidence': {
              appendAttachment(renderSessionId, params.replyId, {
                type: 'evidence',
                data: event.data as AttachmentEvidence['data'],
              });
              break;
            }
            case 'artifact': {
              appendAttachment(renderSessionId, params.replyId, {
                type: 'artifact',
                data: event.data as AttachmentArtifact['data'],
              });
              break;
            }
            case 'done': {
              const current =
                useAppStore.getState().turnsBySession[renderSessionId] ?? [];
              const target = current.find((t) => t.id === params.replyId);
              const finalContent =
                (event.data.content as string | undefined) ??
                target?.content ??
                '';
              patchTurn(renderSessionId, params.replyId, {
                content: finalContent,
                pending: false,
              });
              break;
            }
            case 'error': {
              patchTurn(renderSessionId, params.replyId, {
                pending: false,
                error: (event.data.message as string) ?? '对话出现错误',
                errorCode: (event.data.code as string) ?? 'UNKNOWN',
              });
              break;
            }
            default:
              break;
          }
        },
        onError: (msg) => {
          patchTurn(renderSessionId, params.replyId, {
            pending: false,
            error: msg,
          });
        },
        onClose: () => {
          patchTurn(renderSessionId, params.replyId, { pending: false });
          setStreaming(null);
          streamRef.current = null;
          if (resolvedProjectId) void loadSessions(resolvedProjectId);
          if (resolvedSessionId) void loadMessages(resolvedSessionId);
        },
      },
    );
    streamRef.current = handle;
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || streaming) return;
    try {
      const ctx = await ensureProjectAndSession();
      const turnId = `local-${Date.now()}`;
      const projectId = ctx.projectId;
      const sessionId = ctx.sessionId;

      const turnSessionId = resolveRenderSessionId(sessionId, turnId);
      appendTurn(turnSessionId, {
        id: turnId,
        role: 'user',
        content: trimmed,
        projectId: projectId ?? undefined,
        sessionId: turnSessionId,
      });
      setInput('');

      const replyId = `assistant-${Date.now()}`;
      appendTurn(turnSessionId, {
        id: replyId,
        role: 'assistant',
        content: '',
        pending: true,
        projectId: projectId ?? undefined,
        sessionId: turnSessionId,
        attachments: [],
      });

      const modeOverride: ChatMode | undefined = forcePaperReading
        ? 'paper_reading'
        : undefined;

      startStream({
        content: trimmed,
        projectId,
        sessionId,
        localSessionId: turnSessionId,
        paperId: forcePaperReading ? guidedPaperId : null,
        modeOverride,
        turnId,
        replyId,
      });
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const handleStop = () => {
    streamRef.current?.close();
    streamRef.current = null;
    setStreaming(null);
  };

  const handleRetry = () => {
    if (!lastSend || streaming) return;
    patchTurn(lastSend.localSessionId, lastSend.replyId, {
      content: '',
      pending: true,
      error: undefined,
      attachments: [],
    });
    startStream(lastSend);
  };

  const handleNewSession = () => {
    setActiveSessionId(null);
    setMessages([]);
  };

  const handleRenameSession = async (sessionId: string, title: string) => {
    const updated = await api.renameSession(sessionId, { title });
    if (activeProjectId) {
      const current = sessionsByProject[activeProjectId] ?? [];
      const next = current.map((s) => (s.id === sessionId ? updated : s));
      setSessions(activeProjectId, next);
    }
    setRenamingSessionId(null);
    toast.success('已更新会话标题');
  };

  const handleDeleteSession = async (sessionId: string) => {
    await api.deleteSession(sessionId);
    if (activeProjectId) {
      const current = sessionsByProject[activeProjectId] ?? [];
      const next = current.filter((s) => s.id !== sessionId);
      setSessions(activeProjectId, next);
    }
    if (activeSessionId === sessionId) {
      setActiveSessionId(null);
      setMessages([]);
    }
    setSelectedSessionIds((prev) => {
      const next = new Set(prev);
      next.delete(sessionId);
      return next;
    });
    toast.success('会话已删除');
  };

  const handleBatchDeleteSessions = async () => {
    const ids = Array.from(selectedSessionIds);
    await Promise.all(ids.map((id) => api.deleteSession(id)));
    if (activeProjectId) {
      const current = sessionsByProject[activeProjectId] ?? [];
      const next = current.filter((s) => !selectedSessionIds.has(s.id));
      setSessions(activeProjectId, next);
    }
    if (activeSessionId && selectedSessionIds.has(activeSessionId)) {
      setActiveSessionId(null);
      setMessages([]);
    }
    setSelectedSessionIds(new Set());
    toast.success(`已删除 ${ids.length} 个会话`);
  };

  const [selectedSessionIds, setSelectedSessionIds] = useState<Set<string>>(new Set());

  const handleQuickTemplate = (template: string) => {
    setInput((prev) => (prev ? `${prev}\n${template}` : template));
  };

  const trimmedInput = input.trim();
  const canSend =
    trimmedInput.length > 0 &&
    !streaming &&
    (!forcePaperReading || !!guidedPaperId);

  if (!activeProjectId && projects.length === 0) {
    return (
      <Card>
        <Empty description="还没有任何项目。在下方输入第一条研究问题，系统会自动创建默认项目。" />
        <div style={{ marginTop: 16 }}>
          <ChatComposer
            input={input}
            onInputChange={setInput}
            onSend={handleSend}
            onStop={handleStop}
            onRetry={handleRetry}
            canRetry={false}
            streaming={streaming}
            canSend={canSend}
            forcePaperReading={forcePaperReading}
            onTogglePaperReading={(checked) => {
              setForcePaperReading(checked);
              if (!checked) setGuidedPaperId(null);
            }}
            guidedPaperId={guidedPaperId}
            onGuidedPaperChange={setGuidedPaperId}
            papers={papers}
            stages={stages}
          />
        </div>
      </Card>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 16 }}>
      <Card
        title={
          <Space size={6}>
            <ReadOutlined />
            <span>会话</span>
            <Typography.Text type="secondary" style={{ fontSize: 12, fontWeight: 'normal' }}>
              {sessions.length}
            </Typography.Text>
          </Space>
        }
        size="small"
        loading={loadingSessions}
        extra={
          selectedSessionIds.size > 0 ? (
            <Space size={4}>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                已选 {selectedSessionIds.size}
              </Typography.Text>
              <Popconfirm
                title={`确定删除这 ${selectedSessionIds.size} 个会话？`}
                description="会话内的消息记录也会一并移除。"
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                onConfirm={handleBatchDeleteSessions}
              >
                <Button size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </Space>
          ) : (
            <Tooltip title="新建会话">
              <Button
                size="small"
                type="text"
                icon={<PlusOutlined />}
                onClick={handleNewSession}
              />
            </Tooltip>
          )
        }
        styles={{ body: { padding: 8 } }}
      >
        <SessionList
          sessions={sessions}
          activeId={activeSessionId}
          selectedIds={selectedSessionIds}
          onSelect={(id) => {
            setRenamingSessionId(null);
            setActiveSessionId(id);
          }}
          onRename={handleRenameSession}
          onDelete={handleDeleteSession}
          renamingId={renamingSessionId}
          onStartRename={setRenamingSessionId}
          onCancelRename={() => setRenamingSessionId(null)}
          onToggleSelect={(id, checked) => {
            setSelectedSessionIds((prev) => {
              const next = new Set(prev);
              checked ? next.add(id) : next.delete(id);
              return next;
            });
          }}
          onToggleAll={(checked) => {
            if (checked) {
              setSelectedSessionIds(new Set(sessions.map((s) => s.id)));
            } else {
              setSelectedSessionIds(new Set());
            }
          }}
        />
      </Card>

      <Card
        title={
          <Space wrap>
            <span>对话工作台</span>
            <Badge
              status={streaming ? 'processing' : 'success'}
              text={streaming ? '正在生成…' : '空闲'}
            />
            <Segmented
              size="small"
              value={modeFilter}
              onChange={(v) => setModeFilter(v as ChatModeFilter)}
              options={[
                { label: '全部', value: 'all' },
                { label: '检索', value: 'literature_discovery' },
                { label: '精读', value: 'paper_reading' },
                { label: '诊断', value: 'research_diagnosis' },
              ]}
            />
          </Space>
        }
        styles={{
          body: {
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 180px)',
          },
        }}
      >
        <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', paddingRight: 8 }}>
          {loadingMessages ? (
            <div style={{ textAlign: 'center', padding: 24 }}>
              <Spin />
            </div>
          ) : visibleMessages.length === 0 && filteredTurns.length === 0 ? (
            <WelcomeCard onTemplate={handleQuickTemplate} />
          ) : (
            <>
              {visibleMessages.map((item) => (
                <ChatMessage key={item.id} message={item} projectId={activeProjectId} />
              ))}
              {filteredTurns.map((item) => (
                <ChatMessage
                  key={item.id}
                  turn={item}
                  projectId={activeProjectId}
                  onRetry={handleRetry}
                  onPickPaper={() => navigate('/papers')}
                />
              ))}
            </>
          )}
        </div>
        <ChatComposer
          input={input}
          onInputChange={setInput}
          onSend={handleSend}
          onStop={handleStop}
          onRetry={handleRetry}
          canRetry={!!lastSend && !streaming}
          streaming={streaming}
          canSend={canSend}
          forcePaperReading={forcePaperReading}
          onTogglePaperReading={(checked) => {
            setForcePaperReading(checked);
            if (!checked) setGuidedPaperId(null);
          }}
          guidedPaperId={guidedPaperId}
          onGuidedPaperChange={setGuidedPaperId}
          papers={papers}
          stages={stages}
        />
      </Card>
    </div>
  );
}

function mapStageName(name: string): keyof StreamingStages {
  switch (name) {
    case 'query_generation':
      return 'queryGeneration';
    case 'arxiv_search':
      return 'paperSearch';
    case 'recommendation':
      return 'recommendation';
    case 'persistence':
      return 'persistence';
    case 'evidence_collection':
      return 'evidenceCollection';
    case 'diagnosis':
      return 'diagnosis';
    case 'reading_guidance':
      return 'readingGuidance';
    default:
      return 'queryGeneration';
  }
}

// ─── Claude-style Chat Message ────────────────────────────────────────────────

interface ChatMessageProps {
  message?: Message;
  turn?: ChatTurn;
  projectId?: string | null;
  onRetry?: () => void;
  onPickPaper?: () => void;
}

function ChatMessage({ message, turn, projectId, onRetry, onPickPaper }: ChatMessageProps) {
  const navigate = useNavigate();
  const isUser = message ? message.role === 'user' : turn?.role === 'user';
  const content = message?.content ?? turn?.content ?? '';
  const pending = turn?.pending ?? false;
  const error = turn?.error;
  const errorCode = turn?.errorCode;
  const mode = (message?.mode as ChatMode | undefined) ?? turn?.mode;
  const attachments = turn?.attachments ?? [];

  const goToPapers = () => {
    if (onPickPaper) onPickPaper();
    else navigate('/papers');
  };

  if (isUser) {
    return (
      <div className="chat-message-row user-row">
        <div className="chat-bubble user-bubble">{content}</div>
        <div className="chat-avatar">
          <div className="avatar-circle user-avatar-bg">
            <UserOutlined />
          </div>
        </div>
      </div>
    );
  }

  const { label, color } = describeMode(mode);
  return (
    <div className="chat-message-row assistant-row">
      <div className="chat-avatar">
        <div className="avatar-circle assistant-avatar-bg">
          <RobotOutlined />
        </div>
      </div>
      <div className="chat-bubble-group">
        {mode && (
          <div className="chat-mode-tag">
            <Tag color={color} style={{ margin: 0 }}>{label}</Tag>
            {pending && <Tag color="processing" style={{ margin: 0 }}>生成中</Tag>}
          </div>
        )}
        {error && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 8 }}
            message={error}
            description={
              <Space size={8} wrap style={{ marginTop: 6 }}>
                {errorCode === 'PAPER_NOT_PARSED' ? (
                  <Button size="small" type="primary" onClick={goToPapers}>
                    查看论文状态
                  </Button>
                ) : errorCode === 'PAPER_READING_REQUIRES_PAPER' ? (
                  <Button size="small" type="primary" onClick={goToPapers}>
                    选择论文
                  </Button>
                ) : errorCode === 'MODEL_NOT_CONFIGURED' ? (
                  <Button size="small" type="primary" onClick={() => navigate('/settings')}>
                    配置 API Key
                  </Button>
                ) : null}
                {onRetry && (
                  <Button size="small" icon={<ReloadOutlined />} onClick={onRetry}>
                    重试
                  </Button>
                )}
              </Space>
            }
          />
        )}
        <div className="assistant-bubble">
          {content || pending ? (
            <ClaudeStreamingContent content={content} pending={pending} />
          ) : (
            <span className="empty-reply">(空回复)</span>
          )}
        </div>
        {attachments.length > 0 && (
          <div className="chat-attachments">
            {attachments.map((att, idx) => (
              <AttachmentView key={`${att.type}-${idx}`} attachment={att as Attachment} projectId={projectId} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Claude-style Streaming Content ───────────────────────────────────────────

function ClaudeStreamingContent({ content, pending }: { content: string; pending: boolean }) {
  return (
    <div className="streaming-content">
      <MarkdownRenderer content={content} />
      {pending && <ClaudeTypingIndicator />}
    </div>
  );
}

function ClaudeTypingIndicator() {
  return (
    <span className="claude-typing-indicator" aria-label="AI is thinking">
      <style>{`
        .claude-typing-indicator {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          margin-left: 2px;
          vertical-align: middle;
        }
        .claude-typing-dot {
          width: 4px;
          height: 4px;
          border-radius: 50%;
          background: #8c8c8c;
          animation: claude-typing-bounce 1.2s ease-in-out infinite;
        }
        .claude-typing-dot:nth-child(1) { animation-delay: 0ms; }
        .claude-typing-dot:nth-child(2) { animation-delay: 160ms; }
        .claude-typing-dot:nth-child(3) { animation-delay: 320ms; }
        .claude-cursor {
          display: inline-block;
          width: 2px;
          height: 15px;
          background: #2f54eb;
          margin-left: 2px;
          vertical-align: middle;
          animation: claude-cursor-blink 0.8s step-end infinite;
        }
        @keyframes claude-typing-bounce {
          0%, 100% { transform: translateY(0); opacity: 0.4; }
          50% { transform: translateY(-5px); opacity: 1; }
        }
        @keyframes claude-cursor-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
      <span className="claude-typing-dot" />
      <span className="claude-typing-dot" />
      <span className="claude-typing-dot" />
      <span className="claude-cursor" />
    </span>
  );
}

// ─── Session List ─────────────────────────────────────────────────────────────

function SessionList({
  sessions,
  activeId,
  selectedIds,
  onSelect,
  onRename,
  onDelete,
  renamingId,
  onStartRename,
  onCancelRename,
  onToggleSelect,
  onToggleAll,
}: {
  sessions: Session[];
  activeId: string | null;
  selectedIds: Set<string>;
  onSelect: (id: string) => void;
  onRename: (id: string, title: string) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
  renamingId: string | null;
  onStartRename: (id: string) => void;
  onCancelRename: () => void;
  onToggleSelect: (id: string, checked: boolean) => void;
  onToggleAll: (checked: boolean) => void;
}) {
  const [draft, setDraft] = useState<string>('');
  const { message: toast } = AntdApp.useApp();

  const allSelected = sessions.length > 0 && selectedIds.size === sessions.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < sessions.length;

  if (!sessions.length) {
    return (
      <Typography.Paragraph
        type="secondary"
        style={{ fontSize: 12, padding: 12, textAlign: 'center', margin: 0 }}
      >
        暂无会话
      </Typography.Paragraph>
    );
  }

  const handleStart = (session: Session) => {
    setDraft(session.title || '新会话');
    onStartRename(session.id);
  };

  const handleConfirm = async (id: string) => {
    const trimmed = draft.trim();
    if (!trimmed) {
      toast.error('会话标题不能为空');
      return;
    }
    try {
      await onRename(id, trimmed);
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  return (
    <>
      {selectedIds.size > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 8px 8px',
            fontSize: 12,
            color: '#fa8c16',
          }}
        >
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            已选 {selectedIds.size} 项
          </Typography.Text>
        </div>
      )}
      <List
        size="small"
        dataSource={sessions}
        split={false}
        rowKey={(item) => item.id}
        renderItem={(item) => {
          const isActive = item.id === activeId;
          const isRenaming = renamingId === item.id;
          const isSelected = selectedIds.has(item.id);
          const title = item.title || '新会话';
          const updated = item.updated_at ? new Date(item.updated_at) : null;

          if (isRenaming) {
          return (
            <div
              style={{
                background: '#e6f4ff',
                padding: '6px 8px',
                borderRadius: 6,
                marginBottom: 4,
              }}
            >
              <Input
                size="small"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                autoFocus
                onPressEnter={() => void handleConfirm(item.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') onCancelRename();
                }}
              />
              <Space size={4} style={{ marginTop: 4 }}>
                <Button
                  size="small"
                  type="primary"
                  icon={<CheckOutlined />}
                  onClick={() => void handleConfirm(item.id)}
                >
                  保存
                </Button>
                <Button
                  size="small"
                  icon={<CloseOutlined />}
                  onClick={onCancelRename}
                >
                  取消
                </Button>
              </Space>
            </div>
          );
        }

        return (
          <div
            onClick={() => onSelect(item.id)}
            style={{
              cursor: 'pointer',
              background: isActive ? '#e6f4ff' : isSelected ? '#f0f5ff' : 'transparent',
              padding: '8px 10px',
              borderRadius: 6,
              marginBottom: 2,
              border: isActive ? '1px solid #91caff' : isSelected ? '1px solid #d9d9d9' : '1px solid transparent',
              transition: 'background 120ms',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
            onMouseEnter={(e) => {
              if (!isActive && !isSelected) e.currentTarget.style.background = '#f5f7fb';
            }}
            onMouseLeave={(e) => {
              if (!isActive && !isSelected) e.currentTarget.style.background = 'transparent';
            }}
          >
            <Checkbox
              checked={isSelected}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => onToggleSelect(item.id, e.target.checked)}
              style={{ flexShrink: 0 }}
            />
            <div style={{ flex: 1, minWidth: 0 }}>
              <Typography.Text
                style={{ fontSize: 13, display: 'block' }}
                ellipsis
              >
                {title}
              </Typography.Text>
              {updated && (
                <Typography.Text
                  type="secondary"
                  style={{ fontSize: 11, display: 'block' }}
                >
                  {formatRelativeTime(updated)}
                </Typography.Text>
              )}
            </div>
            <Space
              size={2}
              onClick={(e) => e.stopPropagation()}
              style={{ opacity: 1, transition: 'opacity 120ms' }}
              className="session-actions"
            >
              <Tooltip title="重命名">
                <Button
                  size="small"
                  type="text"
                  icon={<EditOutlined />}
                  onClick={() => handleStart(item)}
                />
              </Tooltip>
              <Popconfirm
                title="删除该会话？"
                description="会话内的消息记录也会一并移除。"
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                onConfirm={() => onDelete(item.id)}
              >
                <Tooltip title="删除">
                  <Button
                    size="small"
                    type="text"
                    danger
                    icon={<DeleteOutlined />}
                  />
                </Tooltip>
              </Popconfirm>
            </Space>
          </div>
        );
      }}
    />
    </>
  );
}

function formatRelativeTime(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return '刚刚';
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffHour = Math.floor(diffMin / 60);
  if (diffHour < 24) return `${diffHour} 小时前`;
  const diffDay = Math.floor(diffHour / 24);
  if (diffDay < 7) return `${diffDay} 天前`;
  return date.toLocaleDateString('zh-CN');
}

// ─── Attachment View ──────────────────────────────────────────────────────────

function AttachmentView({ attachment, projectId }: { attachment: Attachment; projectId?: string | null }) {
  if (attachment.type === 'search_results') {
    return <SearchResults data={attachment.data} activeProjectId={projectId} />;
  }
  if (attachment.type === 'artifact') {
    const data = attachment.data as { artifact_id: string; artifact_type?: string; title?: string };
    const typeLabel: Record<string, string> = {
      literature_card: '文献卡片',
      paper_comparison: '论文对比',
      research_diagnosis: '研究诊断',
      guided_reading_note: '精读笔记',
    };
    const id = data.artifact_id as string;
    return (
      <Alert
        type="success"
        showIcon
        message={
          <Space>
            <span>已生成成果</span>
            <Tag color="green">{typeLabel[data.artifact_type ?? ''] ?? data.artifact_type}</Tag>
            <a
              href={`/artifacts/${id}`}
              onClick={(e) => {
                e.preventDefault();
                window.history.pushState({}, '', `/artifacts/${id}`);
                window.dispatchEvent(new PopStateEvent('popstate'));
              }}
            >
              {data.title || '查看成果'} →
            </a>
          </Space>
        }
      />
    );
  }
  const data = attachment.data as { paper_id: string; pages?: number[] };
  return (
    <Alert
      type="info"
      showIcon
      message={
        <Space>
          <FileSearchOutlined />
          <span>引用了第 {data.pages?.join('、') || '—'} 页的内容</span>
        </Space>
      }
    />
  );
}

// ─── Chat Composer ────────────────────────────────────────────────────────────

interface ChatComposerProps {
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onStop: () => void;
  onRetry: () => void;
  canRetry: boolean;
  streaming: boolean;
  canSend: boolean;
  forcePaperReading: boolean;
  onTogglePaperReading: (checked: boolean) => void;
  guidedPaperId: string | null;
  onGuidedPaperChange: (id: string | null) => void;
  papers: Paper[];
  stages: StreamingStages;
}

const INPUT_MAX_LENGTH = 4000;

function ChatComposer({
  input,
  onInputChange,
  onSend,
  onStop,
  onRetry,
  canRetry,
  streaming,
  canSend,
  forcePaperReading,
  onTogglePaperReading,
  guidedPaperId,
  onGuidedPaperChange,
  papers,
  stages,
}: ChatComposerProps) {
  const libraryPapers = papers.filter((paper) => paper.favorited || isUploaded(paper));
  return (
    <div
      style={{
        marginTop: 12,
        paddingTop: 12,
        borderTop: '1px solid #f0f0f0',
      }}
    >
      <Space wrap style={{ marginBottom: 8 }}>
        <Checkbox
          checked={forcePaperReading}
          onChange={(e) => onTogglePaperReading(e.target.checked)}
        >
          使用论文库精读
        </Checkbox>
        {forcePaperReading && (
          <Select
            size="small"
            value={guidedPaperId ?? undefined}
            placeholder="从论文库选择要精读的论文"
            style={{ minWidth: 260 }}
            onChange={onGuidedPaperChange}
            options={libraryPapers.map((p) => ({
              value: p.id,
              label: `${p.title}（${p.arxiv_id}）`,
            }))}
            notFoundContent={
              <span style={{ fontSize: 12 }}>
                当前项目还没有可精读论文，请先在"论文库"上传 PDF，或收藏检索结果后导入解析。
              </span>
            }
          />
        )}
      </Space>
      <TextArea
        value={input}
        onChange={(e) => onInputChange(e.target.value.slice(0, INPUT_MAX_LENGTH))}
        autoSize={{ minRows: 3, maxRows: 10 }}
        placeholder={
          forcePaperReading
            ? '输入你的当前理解或直接说"开始精读"，系统会按研究问题、方法、贡献、局限逐步引导…'
            : '描述你当前的研究问题或想探索的主题…'
        }
        disabled={streaming}
        maxLength={INPUT_MAX_LENGTH}
        showCount={false}
        onPressEnter={(e) => {
          if (!e.shiftKey) {
            e.preventDefault();
            if (canSend) onSend();
          }
        }}
      />
      <div
        style={{
          marginTop: 8,
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
        }}
      >
        <Space>
          {canRetry && (
            <Button icon={<ReloadOutlined />} onClick={onRetry}>
              重试上次
            </Button>
          )}
          {streaming ? (
            <Button danger icon={<StopOutlined />} onClick={onStop}>
              停止生成
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<SendOutlined />}
              disabled={!canSend}
              onClick={onSend}
            >
              发送
            </Button>
          )}
        </Space>
      </div>
      <StageProgress stages={stages} />
    </div>
  );
}

// ─── Welcome Card ────────────────────────────────────────────────────────────

function WelcomeCard({ onTemplate }: { onTemplate: (text: string) => void }) {
  const cards: { title: string; icon: React.ReactNode; text: string; tag: string; color: string }[] = [
    {
      title: '文献查找',
      icon: <SearchOutlined style={{ fontSize: 22, color: '#722ed1' }} />,
      text: '请帮我检索关于「车辆路径优化」的最新论文。',
      tag: '文献发现',
      color: 'purple',
    },
    {
      title: '研究选题诊断',
      icon: <ExperimentOutlined style={{ fontSize: 22, color: '#fa8c16' }} />,
      text: '请诊断我的研究选题：基于强化学习的城市配送路径优化。',
      tag: '诊断',
      color: 'orange',
    },
    {
      title: '论文库精读',
      icon: <ReadOutlined style={{ fontSize: 22, color: '#52c41a' }} />,
      text: '请带我精读这篇论文，先定位研究问题，再梳理方法、贡献和局限。',
      tag: '精读',
      color: 'green',
    },
  ];
  return (
    <div
      style={{
        background: 'linear-gradient(180deg, #f0f5ff 0%, #ffffff 100%)',
        borderRadius: 12,
        padding: 28,
        border: '1px solid #e6ebf5',
      }}
    >
      <Space align="start" size={12}>
        <span style={{ fontSize: 32 }}>👋</span>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            开始你的第一次研究对话
          </Typography.Title>
          <Typography.Text type="secondary">
            从以下推荐任务开始，或描述你的研究主题。
          </Typography.Text>
        </div>
      </Space>
      <div
        style={{
          marginTop: 20,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
          gap: 12,
        }}
      >
        {cards.map((c) => (
          <div
            key={c.title}
            role="button"
            tabIndex={0}
            onClick={() => onTemplate(c.text)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') onTemplate(c.text);
            }}
            style={{
              cursor: 'pointer',
              background: '#fff',
              border: '1px solid #e6ebf5',
              borderRadius: 10,
              padding: 16,
              transition: 'transform 120ms ease, box-shadow 120ms ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = '0 4px 16px rgba(47,84,235,0.10)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = 'none';
            }}
          >
            <Space align="center">
              {c.icon}
              <Typography.Text strong>{c.title}</Typography.Text>
              <Tag color={c.color}>{c.tag}</Tag>
            </Space>
            <Typography.Paragraph
              type="secondary"
              style={{ marginTop: 8, marginBottom: 0, fontSize: 12 }}
            >
              {c.text}
            </Typography.Paragraph>
          </div>
        ))}
      </div>
    </div>
  );
}

export type { Attachment, AttachmentArtifact, AttachmentEvidence, AttachmentSearchResults };
