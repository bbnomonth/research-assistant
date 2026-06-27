import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Space,
  Spin,
  Tag,
  Typography,
  App as AntdApp,
} from 'antd';
import {
  ArrowLeftOutlined,
  FilePdfOutlined,
  SendOutlined,
  StopOutlined,
  UserOutlined,
  RobotOutlined,
} from '@ant-design/icons';
import { api, streamChat, type ChatStreamHandle } from '@/api/client';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { useAppStore, type ChatTurn } from '@/store/app';
import type { Paper, StreamEvent } from '@/types/api';

const { TextArea } = Input;

interface ReadingTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  error?: string;
  attachments?: ReadingAttachment[];
}

type ReadingDisplayTurn = ReadingTurn | ChatTurn;

interface ReadingAttachment {
  type: 'guided_reading_card_offer';
  data: { project_id: string; session_id: string; paper_id?: string; title?: string };
}

function createId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function parseAuthors(value: string): string[] {
  try {
    const parsed = JSON.parse(value || '[]');
    return Array.isArray(parsed) ? parsed.map((item) => String(item)) : [];
  } catch {
    return [];
  }
}

export function PaperReadingPage() {
  const { paperId } = useParams<{ paperId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const pageSessionId = searchParams.get('session');
  const turnsBySession = useAppStore((state) => state.turnsBySession);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(pageSessionId);
  const [input, setInput] = useState('请带我精读这篇论文。');
  const [turns, setTurns] = useState<ReadingTurn[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [pdfLoaded, setPdfLoaded] = useState(false);
  const [pdfReloadKey, setPdfReloadKey] = useState(0);
  const streamRef = useRef<ChatStreamHandle | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const authors = useMemo(
    () => (paper ? parseAuthors(paper.authors_json).join(', ') : ''),
    [paper],
  );
  const sessionTurns = pageSessionId ? turnsBySession[pageSessionId] ?? [] : [];
  const displayTurns: ReadingDisplayTurn[] = [...sessionTurns, ...turns];

  useEffect(() => {
    if (pageSessionId) setSessionId(pageSessionId);
  }, [pageSessionId]);

  useEffect(() => {
    let alive = true;
    if (!paperId) {
      setLoadError('缺少论文 ID');
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .getPaper(paperId)
      .then((item) => {
        if (!alive) return;
        setPaper(item);
        setLoadError(null);
      })
      .catch((err) => {
        if (!alive) return;
        setLoadError((err as Error).message || '论文加载失败');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
      streamRef.current?.close();
    };
  }, [paperId]);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: 'smooth',
    });
  }, [displayTurns]);

  useEffect(() => {
    setPdfLoaded(false);
    setPdfReloadKey((current) => current + 1);
  }, [paper?.id]);

  const patchAssistant = (id: string, patch: Partial<ReadingTurn>) => {
    setTurns((current) =>
      current.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn)),
    );
  };

  const appendAssistantAttachment = (id: string, attachment: ReadingAttachment) => {
    setTurns((current) =>
      current.map((turn) =>
        turn.id === id
          ? { ...turn, attachments: [...(turn.attachments ?? []), attachment] }
          : turn,
      ),
    );
  };

  const appendAssistantToken = (id: string, token: string) => {
    setTurns((current) =>
      current.map((turn) =>
        turn.id === id ? { ...turn, content: `${turn.content}${token}` } : turn,
      ),
    );
  };

  const handleEvent = (event: StreamEvent, assistantId: string) => {
    if (event.event === 'metadata') {
      const nextSessionId = event.data.session_id as string | undefined;
      if (nextSessionId) setSessionId(nextSessionId);
      return;
    }
    if (event.event === 'token') {
      appendAssistantToken(assistantId, (event.data.content as string) ?? '');
      return;
    }
    if (event.event === 'done') {
      const finalContent = event.data.content as string | undefined;
      patchAssistant(
        assistantId,
        finalContent ? { content: finalContent, pending: false } : { pending: false },
      );
      return;
    }
    if (event.event === 'guided_reading_card_offer') {
      appendAssistantAttachment(assistantId, {
        type: 'guided_reading_card_offer',
        data: event.data as ReadingAttachment['data'],
      });
      return;
    }
    if (event.event === 'error') {
      patchAssistant(assistantId, {
        pending: false,
        error: (event.data.message as string) ?? '精读对话出现错误',
      });
    }
  };

  const send = () => {
    const content = input.trim();
    if (!content || !paper || streaming) return;

    const userTurn: ReadingTurn = {
      id: createId('user'),
      role: 'user',
      content,
    };
    const assistantId = createId('assistant');
    const assistantTurn: ReadingTurn = {
      id: assistantId,
      role: 'assistant',
      content: '',
      pending: true,
    };

    setTurns((current) => [...current, userTurn, assistantTurn]);
    setInput('');
    setStreaming(true);
    streamRef.current = streamChat(
      {
        content,
        project_id: paper.project_id,
        session_id: sessionId,
        paper_id: paper.id,
        mode_override: 'paper_reading',
      },
      {
        onEvent: (event) => handleEvent(event, assistantId),
        onError: (message) => {
          patchAssistant(assistantId, { pending: false, error: message });
        },
        onClose: () => {
          patchAssistant(assistantId, { pending: false });
          setStreaming(false);
          streamRef.current = null;
        },
      },
    );
  };

  const stop = () => {
    streamRef.current?.close();
    streamRef.current = null;
    setStreaming(false);
  };

  if (loading) {
    return (
      <Card>
        <Spin /> <Typography.Text style={{ marginLeft: 8 }}>正在加载论文...</Typography.Text>
      </Card>
    );
  }

  if (loadError || !paper) {
    return (
      <Card>
        <Alert
          type="error"
          showIcon
          message="论文加载失败"
          description={loadError}
          action={
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/chat')}>
              返回主工作台
            </Button>
          }
        />
      </Card>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Card styles={{ body: { padding: '12px 16px' } }}>
        <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space align="start">
            <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/chat')}>
              返回主工作台
            </Button>
            <Space direction="vertical" size={2}>
              <Typography.Text strong>{paper.title}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {authors || paper.arxiv_id}
              </Typography.Text>
            </Space>
          </Space>
          <Tag color="green">论文精读</Tag>
        </Space>
      </Card>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(320px, 1fr) minmax(620px, 2fr)',
          gap: 12,
          minHeight: 'calc(100vh - 160px)',
        }}
      >
        <Card
          title="精读对话"
          styles={{
            body: {
              height: 'calc(100vh - 238px)',
              display: 'flex',
              flexDirection: 'column',
              padding: 0,
            },
          }}
        >
          <div
            ref={scrollRef}
            style={{
              flex: 1,
              overflow: 'auto',
              padding: 16,
              background: '#fbfcff',
            }}
          >
            {displayTurns.length === 0 ? (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={null}
              />
            ) : (
              <Space direction="vertical" size={14} style={{ width: '100%' }}>
                {displayTurns.map((turn) => (
                  <div
                    key={turn.id}
                    style={{
                      display: 'flex',
                      justifyContent:
                        turn.role === 'user' ? 'flex-end' : 'flex-start',
                      gap: 8,
                    }}
                  >
                    {turn.role === 'assistant' && (
                      <RobotOutlined style={{ marginTop: 8, color: '#52c41a' }} />
                    )}
                    <div
                      style={{
                        maxWidth: '88%',
                        borderRadius: 8,
                        padding: '10px 12px',
                        background: turn.role === 'user' ? '#2f54eb' : '#fff',
                        color: turn.role === 'user' ? '#fff' : undefined,
                        border:
                          turn.role === 'assistant'
                            ? '1px solid #e5e8ef'
                            : '1px solid #2f54eb',
                      }}
                    >
                      {turn.role === 'assistant' ? (
                        <>
                          {turn.error ? (
                            <Alert type="error" showIcon message={turn.error} />
                          ) : (
                            <>
                              <MarkdownRenderer
                                content={turn.content || (turn.pending ? '正在生成...' : '')}
                                compact
                              />
                              {((turn as { attachments?: Array<{ type: string; data: unknown }> })
                                .attachments ?? [])
                                .filter((attachment) => attachment.type === 'guided_reading_card_offer')
                                .map((attachment, index) => (
                                  <div key={`${attachment.type}-${index}`} style={{ marginTop: 8 }}>
                                    <GuidedReadingCardOffer
                                      data={attachment.data as ReadingAttachment['data']}
                                    />
                                  </div>
                                ))}
                            </>
                          )}
                        </>
                      ) : (
                        <Typography.Text style={{ color: '#fff' }}>
                          {turn.content}
                        </Typography.Text>
                      )}
                    </div>
                    {turn.role === 'user' && (
                      <UserOutlined style={{ marginTop: 8, color: '#2f54eb' }} />
                    )}
                  </div>
                ))}
              </Space>
            )}
          </div>
          <div style={{ padding: 12, borderTop: '1px solid #f0f0f0' }}>
            <TextArea
              value={input}
              onChange={(event) => setInput(event.target.value.slice(0, 4000))}
              autoSize={{ minRows: 3, maxRows: 6 }}
              placeholder="询问关于这篇论文的任何问题..."
              disabled={streaming}
              onPressEnter={(event) => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
              {streaming ? (
                <Button danger icon={<StopOutlined />} onClick={stop}>
                  停止生成
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  disabled={!input.trim()}
                  onClick={send}
                >
                  发送
                </Button>
              )}
            </div>
          </div>
        </Card>

        <Card
          title={
            <Space>
              <FilePdfOutlined />
              <span>论文原文</span>
            </Space>
          }
          extra={
            <Button
              onClick={() => {
                setPdfLoaded(false);
                setPdfReloadKey((current) => current + 1);
              }}
            >
              重新加载
            </Button>
          }
          styles={{
            body: {
              padding: 0,
              height: 'calc(100vh - 238px)',
              overflow: 'hidden',
              background: '#f5f7fb',
              position: 'relative',
            },
          }}
        >
          {!pdfLoaded && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                zIndex: 1,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'column',
                gap: 8,
                background: '#f8fafc',
              }}
            >
              <Spin />
              <Typography.Text type="secondary">正在加载论文原文...</Typography.Text>
            </div>
          )}
          <iframe
            key={pdfReloadKey}
            title={paper.title}
            src={api.paperPdfUrl(paper.id)}
            onLoad={() => setPdfLoaded(true)}
            style={{ width: '100%', height: '100%', border: 0, background: '#fff' }}
          />
        </Card>
      </div>
    </div>
  );
}

function GuidedReadingCardOffer({
  data,
}: {
  data: { project_id: string; session_id: string; paper_id?: string; title?: string };
}) {
  const { message: toast } = AntdApp.useApp();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [artifact, setArtifact] = useState<{ id: string; title: string } | null>(null);

  const createCard = async () => {
    if (creating || artifact) return;
    setCreating(true);
    try {
      const created = await api.createGuidedReadingCard({
        project_id: data.project_id,
        session_id: data.session_id,
      });
      setArtifact({ id: created.id, title: created.title });
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
          <Space wrap>
            <span>已生成成果</span>
            <Tag color="green">精读卡片</Tag>
            <Button size="small" onClick={() => navigate(`/artifacts/${artifact.id}`)}>
              {artifact.title || '查看成果'}
            </Button>
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
