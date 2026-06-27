import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
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
  Popover,
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
  BulbOutlined,
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
const BOT_AVATAR_STORAGE_KEY = 'research-agent.botAvatar';

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
interface AttachmentFrameworkCardOffer {
  type: 'framework_card_offer';
  data: { project_id: string; session_id: string; title?: string };
}
interface AttachmentTopicGuidanceCardOffer {
  type: 'topic_guidance_card_offer';
  data: { project_id: string; session_id: string; title?: string };
}
interface AttachmentGuidedReadingCardOffer {
  type: 'guided_reading_card_offer';
  data: { project_id: string; session_id: string; paper_id?: string; title?: string };
}
type Attachment =
  | AttachmentSearchResults
  | AttachmentArtifact
  | AttachmentEvidence
  | AttachmentFrameworkCardOffer
  | AttachmentTopicGuidanceCardOffer
  | AttachmentGuidedReadingCardOffer;

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
    streamingSessionIds,
    setStreaming,
    clearStreaming,
  } = useAppStore();

  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedProjectId = searchParams.get('project');
  const requestedSessionId = searchParams.get('session');

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [guidedPaperId, setGuidedPaperId] = useState<string | null>(null);
  const [forcePaperReading, setForcePaperReading] = useState(false);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [stages, setStages] = useState<StreamingStages>({});
  const [lastSend, setLastSend] = useState<PendingSend | null>(null);
  const [renamingSessionId, setRenamingSessionId] = useState<string | null>(null);
  const [composingNewSession, setComposingNewSession] = useState(false);
  const [botAvatar, setBotAvatar] = useState<string>(() =>
    window.localStorage.getItem(BOT_AVATAR_STORAGE_KEY) ?? '',
  );

  const streamsRef = useRef<Record<string, ChatStreamHandle>>({});
  const activeSessionIdRef = useRef<string | null>(null);
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
    activeSessionIdRef.current = activeSessionId;
  }, [activeSessionId]);
  const currentSessionStreaming = activeSessionId
    ? streamingSessionIds.includes(activeSessionId)
    : false;
  useEffect(() => {
    if (requestedProjectId && requestedProjectId !== activeProjectId) {
      setActiveProjectId(requestedProjectId);
    }
  }, [activeProjectId, requestedProjectId, setActiveProjectId]);

  useEffect(() => {
    if (!activeProjectId) {
      setActiveSessionId(null);
      setMessages([]);
      setComposingNewSession(false);
      return;
    }
    setActiveSessionId(null);
    setComposingNewSession(false);
    void loadSessions(activeProjectId);
    void loadPapers(activeProjectId);
  }, [activeProjectId]);

  useEffect(() => {
    if (composingNewSession) {
      setActiveSessionId(null);
      setMessages([]);
      return;
    }
    if (!activeProjectId || sessions.length === 0) {
      setActiveSessionId(null);
      setMessages([]);
      return;
    }
    if (
      requestedSessionId &&
      (!requestedProjectId || requestedProjectId === activeProjectId)
    ) {
      const requestedSession = sessions.find(
        (session) => session.id === requestedSessionId,
      );
      if (requestedSession) {
        setActiveSessionId(requestedSession.id);
        setSearchParams({}, { replace: true });
        return;
      }
    }
    if (activeSessionId && sessions.some((session) => session.id === activeSessionId)) {
      return;
    }
    setActiveSessionId(sessions[0].id);
  }, [
    activeProjectId,
    sessions,
    activeSessionId,
    composingNewSession,
    requestedProjectId,
    requestedSessionId,
    setSearchParams,
  ]);

  useEffect(() => {
    if (!activeSessionId) {
      setMessages([]);
      return;
    }
    if (isLocalSessionId(activeSessionId)) {
      setMessages([]);
      return;
    }
    void loadMessages(activeSessionId);
  }, [activeSessionId]);

  const filteredTurns = useMemo(() => {
    return activeSessionId ? turnsBySession[activeSessionId] ?? [] : [];
  }, [turnsBySession, activeSessionId]);

  const visibleMessages = useMemo(() => {
    const turns = activeSessionId
      ? turnsBySession[activeSessionId] ?? []
      : [];
    return removeLiveMessageDuplicates(messages, turns);
  }, [messages, turnsBySession, activeSessionId]);

  const showWelcomeCard =
    !currentSessionStreaming && visibleMessages.length === 0 && filteredTurns.length === 0;
  const workspaceStatus = useMemo(
    () =>
      resolveWorkspaceStatus({
        currentSessionStreaming,
        turns: filteredTurns,
      }),
    [currentSessionStreaming, filteredTurns],
  );

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
    let streamKey = params.localSessionId;
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
                const currentHandle = streamsRef.current[streamKey];
                if (currentHandle) {
                  delete streamsRef.current[streamKey];
                  streamsRef.current[metaSession] = currentHandle;
                }
                clearStreaming(streamKey);
                setStreaming(metaSession);
                renderSessionId = metaSession;
                streamKey = metaSession;
              }
              resolvedProjectId = metaProject;
              resolvedSessionId = metaSession;
              setActiveProjectId(metaProject);
              if (activeSessionIdRef.current === params.localSessionId) {
                setActiveSessionId(metaSession);
              }
              void api.listProjects().then((response) => {
                setProjects(response.projects);
              });
              if (metaTitle) {
                const state = useAppStore.getState();
                const currentSessions =
                  state.sessionsByProject[metaProject] ?? [];
                const withoutLocal = currentSessions.filter(
                  (s) => s.id !== params.localSessionId && s.id !== metaSession,
                );
                const existing = currentSessions.find(
                  (s) => s.id === metaSession,
                );
                const resolvedSession: Session = {
                  id: metaSession,
                  project_id: metaProject,
                  title: metaTitle,
                  summary: existing?.summary ?? '',
                  created_at: existing?.created_at ?? new Date().toISOString(),
                  updated_at: new Date().toISOString(),
                };
                setSessions(metaProject, [resolvedSession, ...withoutLocal]);
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
            case 'framework_card_offer': {
              appendAttachment(renderSessionId, params.replyId, {
                type: 'framework_card_offer',
                data: event.data as AttachmentFrameworkCardOffer['data'],
              });
              break;
            }
            case 'topic_guidance_card_offer': {
              appendAttachment(renderSessionId, params.replyId, {
                type: 'topic_guidance_card_offer',
                data: event.data as AttachmentTopicGuidanceCardOffer['data'],
              });
              break;
            }
            case 'guided_reading_card_offer': {
              appendAttachment(renderSessionId, params.replyId, {
                type: 'guided_reading_card_offer',
                data: event.data as AttachmentGuidedReadingCardOffer['data'],
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
          clearStreaming(streamKey);
          delete streamsRef.current[streamKey];
          if (resolvedProjectId) void loadSessions(resolvedProjectId);
          if (resolvedSessionId && activeSessionIdRef.current === resolvedSessionId) {
            void loadMessages(resolvedSessionId);
          }
        },
      },
    );
    streamsRef.current[streamKey] = handle;
  };

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || currentSessionStreaming) return;
    try {
      const ctx = await ensureProjectAndSession();
      const turnId = `local-${Date.now()}`;
      const projectId = ctx.projectId;
      const sessionId = ctx.sessionId;
      const readingPaper =
        forcePaperReading && guidedPaperId
          ? papers.find((paper) => paper.id === guidedPaperId)
          : null;

      const turnSessionId = resolveRenderSessionId(sessionId, turnId);
      setComposingNewSession(false);
      setActiveSessionId(turnSessionId);
      if (projectId && !sessionId) {
        const now = new Date().toISOString();
        const current = useAppStore.getState().sessionsByProject[projectId] ?? [];
        if (!current.some((session) => session.id === turnSessionId)) {
          setSessions(projectId, [
            {
              id: turnSessionId,
              project_id: projectId,
              title: deriveLocalSessionTitle(trimmed),
              summary: '',
              created_at: now,
              updated_at: now,
            },
            ...current,
          ]);
        }
      }
      appendTurn(turnSessionId, {
        id: turnId,
        role: 'user',
        content: trimmed,
        projectId: projectId ?? undefined,
        sessionId: turnSessionId,
        paperId: readingPaper?.id,
        paperTitle: readingPaper?.title,
        paperArxivId: readingPaper?.arxiv_id,
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
    if (!activeSessionId) return;
    streamsRef.current[activeSessionId]?.close();
    delete streamsRef.current[activeSessionId];
    clearStreaming(activeSessionId);
  };

  const handleRetry = () => {
    if (!lastSend || streamingSessionIds.includes(lastSend.localSessionId)) return;
    patchTurn(lastSend.localSessionId, lastSend.replyId, {
      content: '',
      pending: true,
      error: undefined,
      attachments: [],
    });
    startStream(lastSend);
  };

  const handleNewSession = () => {
    setComposingNewSession(true);
    setActiveSessionId(null);
    setMessages([]);
    setStages({});
    setRenamingSessionId(null);
    setSelectedSessionIds(new Set());
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
      setComposingNewSession(true);
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

  const handleBotAvatarChange = (value: string) => {
    const next = value.trim().slice(0, 2);
    setBotAvatar(next);
    if (next) {
      window.localStorage.setItem(BOT_AVATAR_STORAGE_KEY, next);
    } else {
      window.localStorage.removeItem(BOT_AVATAR_STORAGE_KEY);
    }
  };

  const handleBotAvatarFile = (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      toast.warning('请选择图片文件');
      return;
    }
    if (file.size > 512 * 1024) {
      toast.warning('头像图片请小于 512KB');
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      if (!result) return;
      setBotAvatar(result);
      window.localStorage.setItem(BOT_AVATAR_STORAGE_KEY, result);
    };
    reader.readAsDataURL(file);
  };

  const trimmedInput = input.trim();
  const canSend =
    trimmedInput.length > 0 &&
    !currentSessionStreaming &&
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
            streaming={currentSessionStreaming}
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
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '260px minmax(0, 1fr)',
        gap: 16,
      }}
    >
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
            setComposingNewSession(false);
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
              color={workspaceStatus.color}
              text={workspaceStatus.text}
            />
            <Popover
              trigger="click"
              placement="bottomRight"
              content={
                <Space direction="vertical" size={8}>
                  <Input
                    size="small"
                    value={botAvatar.startsWith('data:image/') ? '' : botAvatar}
                    maxLength={2}
                    placeholder="头像文字"
                    allowClear
                    onChange={(e) => handleBotAvatarChange(e.target.value)}
                    style={{ width: 120 }}
                  />
                  <input
                    type="file"
                    accept="image/*"
                    onChange={(e) => handleBotAvatarFile(e.target.files?.[0])}
                    style={{ width: 160, fontSize: 12 }}
                  />
                  <Button size="small" onClick={() => handleBotAvatarChange('')}>
                    恢复默认
                  </Button>
                </Space>
              }
            >
              <Tooltip title="设置机器人头像">
                <Button size="small" icon={<RobotOutlined />} />
              </Tooltip>
            </Popover>
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
          ) : showWelcomeCard ? (
            <WelcomeCard onTemplate={handleQuickTemplate} />
          ) : (
            <>
              {visibleMessages.map((item) => (
                <ChatMessage
                  key={item.id}
                  message={item}
                  projectId={activeProjectId}
                  botAvatar={botAvatar}
                />
              ))}
              {filteredTurns.map((item) => (
                <ChatMessage
                  key={item.id}
                  turn={item}
                  projectId={activeProjectId}
                  botAvatar={botAvatar}
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
          canRetry={!!lastSend && !currentSessionStreaming}
          streaming={currentSessionStreaming}
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
  botAvatar?: string;
  onRetry?: () => void;
  onPickPaper?: () => void;
}

function ChatMessage({
  message,
  turn,
  projectId,
  botAvatar,
  onRetry,
  onPickPaper,
}: ChatMessageProps) {
  const navigate = useNavigate();
  const isUser = message ? message.role === 'user' : turn?.role === 'user';
  const content = message?.content ?? turn?.content ?? '';
  const paperCard = resolveMessagePaperCard(message, turn);
  const pending = turn?.pending ?? false;
  const error = turn?.error;
  const errorCode = turn?.errorCode;
  const mode = (message?.mode as ChatMode | undefined) ?? turn?.mode;
  const attachments = turn?.attachments ?? messageAttachments(message);

  const goToPapers = () => {
    if (onPickPaper) onPickPaper();
    else navigate('/papers');
  };

  if (isUser) {
    return (
      <div className="chat-message-row user-row">
        <div className="user-message-stack">
          {paperCard && (
            <PaperReadingChip
              paper={paperCard}
              onClick={() => {
                const session = turn?.sessionId ?? message?.session_id;
                const search = session ? `?session=${encodeURIComponent(session)}` : '';
                navigate(`/reading/${paperCard.id}${search}`);
              }}
            />
          )}
          <div className="chat-bubble user-bubble">{content}</div>
        </div>
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
          {botAvatar?.startsWith('data:image/') ? (
            <img className="custom-bot-avatar-image" src={botAvatar} alt="机器人头像" />
          ) : botAvatar ? (
            <span className="custom-bot-avatar">{botAvatar}</span>
          ) : (
            <RobotOutlined />
          )}
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

function messageAttachments(message?: Message): Attachment[] {
  if (!message?.metadata || typeof message.metadata !== 'object') return [];
  const attachments: Attachment[] = [];
  if (message.metadata.search_results) {
    attachments.push({
      type: 'search_results',
      data: message.metadata.search_results,
    });
  }
  return attachments;
}

interface WorkspaceStatus {
  text: string;
  color: string;
}

function resolveWorkspaceStatus({
  currentSessionStreaming,
  turns,
}: {
  currentSessionStreaming: boolean;
  turns: ChatTurn[];
}): WorkspaceStatus {
  if (!currentSessionStreaming) return { text: '空闲', color: '#52c41a' };
  const liveMode =
    [...turns].reverse().find((turn) => turn.pending && turn.mode)?.mode ??
    [...turns].reverse().find((turn) => turn.mode)?.mode;
  return workspaceGeneratingStatus(liveMode);
}

function workspaceGeneratingStatus(mode: ChatMode | string | undefined): WorkspaceStatus {
  if (mode === 'framework_building') {
    return { text: '框架搭建中', color: '#fa8c16' };
  }
  if (mode === 'topic_guidance') {
    return { text: '选题指导中', color: '#2f54eb' };
  }
  if (mode === 'literature_discovery') {
    return { text: '文献检索中', color: '#722ed1' };
  }
  if (mode === 'paper_reading') {
    return { text: '文献解读中', color: '#13a8a8' };
  }
  return { text: '自由问答中', color: '#1677ff' };
}

interface MessagePaperCard {
  id: string;
  title: string;
  arxivId?: string;
}

function resolveMessagePaperCard(
  message?: Message,
  turn?: ChatTurn,
): MessagePaperCard | null {
  if (turn?.paperId) {
    return {
      id: turn.paperId,
      title: turn.paperTitle || turn.paperArxivId || '论文文档',
      arxivId: turn.paperArxivId,
    };
  }
  const metadata = message?.metadata;
  const paperId =
    typeof metadata?.paper_id === 'string' ? metadata.paper_id : undefined;
  if (!paperId) return null;
  const paperTitle =
    typeof metadata?.paper_title === 'string' ? metadata.paper_title : undefined;
  const arxivId =
    typeof metadata?.paper_arxiv_id === 'string'
      ? metadata.paper_arxiv_id
      : undefined;
  return {
    id: paperId,
    title: paperTitle || arxivId || '论文文档',
    arxivId,
  };
}

function PaperReadingChip({
  paper,
  onClick,
}: {
  paper: MessagePaperCard;
  onClick: () => void;
}) {
  return (
    <button className="paper-reading-chip" type="button" onClick={onClick}>
      <FileSearchOutlined className="paper-reading-chip-icon" />
      <span className="paper-reading-chip-text">
        <span className="paper-reading-chip-title">{paper.title}</span>
        <span className="paper-reading-chip-type">PDF</span>
      </span>
    </button>
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

function deriveLocalSessionTitle(content: string): string {
  const normalized = content.replace(/\s+/g, ' ').trim();
  if (!normalized) return '新会话';
  return normalized.length > 18 ? `${normalized.slice(0, 17)}…` : normalized;
}

function isLocalSessionId(sessionId: string): boolean {
  return sessionId.startsWith('local-') || sessionId.startsWith('assistant-');
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
      guided_reading_note: '精读笔记',
      topic_guidance_plan: '选题方案',
      framework_card: '框架卡片',
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
  if (attachment.type === 'framework_card_offer') {
    return <FrameworkCardOffer data={attachment.data} />;
  }
  if (attachment.type === 'topic_guidance_card_offer') {
    return <TopicGuidanceCardOffer data={attachment.data} />;
  }
  if (attachment.type === 'guided_reading_card_offer') {
    return <GuidedReadingCardOffer data={attachment.data} />;
  }
  return null;
}

function GuidedReadingCardOffer({
  data,
}: {
  data: { project_id: string; session_id: string; paper_id?: string; title?: string };
}) {
  const { message: toast } = AntdApp.useApp();
  const [creating, setCreating] = useState(false);
  const [artifact, setArtifact] = useState<{
    id: string;
    title: string;
    artifact_type: string;
  } | null>(null);

  const createCard = async () => {
    if (creating || artifact) return;
    setCreating(true);
    try {
      const created = await api.createGuidedReadingCard({
        project_id: data.project_id,
        session_id: data.session_id,
      });
      setArtifact({
        id: created.id,
        title: created.title,
        artifact_type: created.artifact_type,
      });
      toast.success('已整理为精读卡片');
    } catch (err) {
      toast.error((err as Error).message || '整理精读卡片失败');
    } finally {
      setCreating(false);
    }
  };

  if (artifact) {
    return (
      <Alert
        type="success"
        showIcon
        message={
          <Space>
            <span>已生成成果</span>
            <Tag color="green">精读卡片</Tag>
            <a
              href={`/artifacts/${artifact.id}`}
              onClick={(e) => {
                e.preventDefault();
                window.history.pushState({}, '', `/artifacts/${artifact.id}`);
                window.dispatchEvent(new PopStateEvent('popstate'));
              }}
            >
              {artifact.title || '查看成果'} →
            </a>
          </Space>
        }
      />
    );
  }

  return (
    <Alert
      type="info"
      showIcon
      message={
        <Space wrap>
          <span>已完成本轮论文精读，是否整理为项目成果卡片？</span>
          <Button size="small" type="primary" loading={creating} onClick={createCard}>
            整理为精读卡片
          </Button>
        </Space>
      }
    />
  );
}

function TopicGuidanceCardOffer({
  data,
}: {
  data: AttachmentTopicGuidanceCardOffer['data'];
}) {
  const { message: toast } = AntdApp.useApp();
  const [creating, setCreating] = useState(false);
  const [artifact, setArtifact] = useState<{
    id: string;
    title: string;
    artifact_type: string;
  } | null>(null);

  const createCard = async () => {
    if (creating || artifact) return;
    setCreating(true);
    try {
      const created = await api.createTopicGuidanceCard({
        project_id: data.project_id,
        session_id: data.session_id,
      });
      setArtifact({
        id: created.id,
        title: created.title,
        artifact_type: created.artifact_type,
      });
      toast.success('已整理为选题卡片');
    } catch (err) {
      toast.error((err as Error).message || '整理选题卡片失败');
    } finally {
      setCreating(false);
    }
  };

  if (artifact) {
    return (
      <Alert
        type="success"
        showIcon
        message={
          <Space>
            <span>已生成成果</span>
            <Tag color="green">选题卡片</Tag>
            <a
              href={`/artifacts/${artifact.id}`}
              onClick={(e) => {
                e.preventDefault();
                window.history.pushState({}, '', `/artifacts/${artifact.id}`);
                window.dispatchEvent(new PopStateEvent('popstate'));
              }}
            >
              {artifact.title || '查看成果'} →
            </a>
          </Space>
        }
      />
    );
  }

  return (
    <Alert
      type="info"
      showIcon
      message={
        <Space wrap>
          <span>已识别到最终选题方案，可整理为研究项目成果。</span>
          <Button
            type="primary"
            size="small"
            icon={<CheckOutlined />}
            loading={creating}
            onClick={createCard}
          >
            {data.title || '整理为选题卡片'}
          </Button>
        </Space>
      }
    />
  );
}

function FrameworkCardOffer({
  data,
}: {
  data: AttachmentFrameworkCardOffer['data'];
}) {
  const { message: toast } = AntdApp.useApp();
  const [creating, setCreating] = useState(false);
  const [artifact, setArtifact] = useState<{
    id: string;
    title: string;
    artifact_type: string;
  } | null>(null);

  const createCard = async () => {
    if (creating || artifact) return;
    setCreating(true);
    try {
      const created = await api.createFrameworkCard({
        project_id: data.project_id,
        session_id: data.session_id,
      });
      setArtifact({
        id: created.id,
        title: created.title,
        artifact_type: created.artifact_type,
      });
      toast.success('已整理为框架卡片');
    } catch (err) {
      toast.error((err as Error).message || '整理框架卡片失败');
    } finally {
      setCreating(false);
    }
  };

  if (artifact) {
    return (
      <Alert
        type="success"
        showIcon
        message={
          <Space>
            <span>已生成成果</span>
            <Tag color="green">框架卡片</Tag>
            <a
              href={`/artifacts/${artifact.id}`}
              onClick={(e) => {
                e.preventDefault();
                window.history.pushState({}, '', `/artifacts/${artifact.id}`);
                window.dispatchEvent(new PopStateEvent('popstate'));
              }}
            >
              {artifact.title || '查看成果'} →
            </a>
          </Space>
        }
      />
    );
  }

  return (
    <Alert
      type="info"
      showIcon
      message={
        <Space wrap>
          <span>已识别到最终方案，可整理为研究项目成果。</span>
          <Button
            type="primary"
            size="small"
            icon={<CheckOutlined />}
            loading={creating}
            onClick={createCard}
          >
            {data.title || '整理为框架卡片'}
          </Button>
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
  const libraryPaperOptions = libraryPapers.map((paper) => {
    const label = `${paper.title} (${paper.arxiv_id})`;
    return {
      value: paper.id,
      title: label,
      label: (
        <Space direction="vertical" size={0} style={{ maxWidth: 340 }}>
          <Typography.Text ellipsis style={{ maxWidth: 340 }}>
            {paper.title}
          </Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {paper.arxiv_id}
          </Typography.Text>
        </Space>
      ),
    };
  });
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
            style={{ width: 360, maxWidth: 'min(360px, calc(100vw - 120px))' }}
            popupMatchSelectWidth={360}
            optionLabelProp="title"
            showSearch
            filterOption={(keyword, option) =>
              String((option as { title?: string } | undefined)?.title ?? '')
                .toLowerCase()
                .includes(keyword.toLowerCase())
            }
            onChange={onGuidedPaperChange}
            options={libraryPaperOptions}
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
            ? '围绕右侧论文提问，或说“开始精读”，导师会用追问引导你回到原文证据…'
            : '描述你当前的研究问题或想探索的主题…'
        }
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
      title: '选题导师',
      icon: <ExperimentOutlined style={{ fontSize: 22, color: '#2b82f6' }} />,
      text: '请根据我的情况帮我选题',
      tag: '选题',
      color: 'geekblue',
    },
    {
      title: '框架搭建',
      icon: <BulbOutlined style={{ fontSize: 22, color: '#fa8c16' }} />,
      text: '帮我搭建论文框架',
      tag: '框架',
      color: 'orange',
    },
    {
      title: '文献查找',
      icon: <SearchOutlined style={{ fontSize: 22, color: '#722ed1' }} />,
      text: '帮我检索[启发式算法]相关论文',
      tag: '文献发现',
      color: 'purple',
    },
    {
      title: '论文精读',
      icon: <ReadOutlined style={{ fontSize: 22, color: '#52c41a' }} />,
      text: '帮我精读这篇论文',
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
            开始你的研究之旅
          </Typography.Title>
          <Typography.Text type="secondary">
            从以下功能开始，或直接描述你的研究主题。
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


export default ChatPage;
