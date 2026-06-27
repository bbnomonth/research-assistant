import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Collapse,
  Descriptions,
  Empty,
  Input,
  List,
  Progress,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  Upload,
  App as AntdApp,
  Modal,
} from 'antd';
import {
  BookOutlined,
  CloudUploadOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  FilePdfOutlined,
  FileSearchOutlined,
  ReloadOutlined,
  RobotOutlined,
  StarFilled,
} from '@ant-design/icons';
import { api } from '@/api/client';
import { useAppStore } from '@/store/app';
import type { Paper, PaperChunk, TaskRecord } from '@/types/api';
import {
  parseAuthors,
  parseCategories,
  parsePurposeLabels,
  shortAuthors,
  isUploaded,
} from '@/utils/paper';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { getTaskControls } from '@/utils/task';

const { Search } = Input;
const { Panel } = Collapse;

const TASK_POLL_INTERVAL = 2000;
const TASK_POLL_MAX = 60;

export function PapersPage() {
  const { message: toast, modal } = AntdApp.useApp();
  const { activeProjectId, projects } = useAppStore();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [taskMap, setTaskMap] = useState<Record<string, TaskRecord>>({});
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [compareRunning, setCompareRunning] = useState(false);
  const [highlightedPaperId, setHighlightedPaperId] = useState<string | null>(null);
  const pollTimers = useRef<Record<string, number>>({});
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedPaperId = searchParams.get('paper');

  useEffect(() => {
    if (!activeProjectId) {
      setPapers([]);
      setCompareIds([]);
      return;
    }
    void loadPapers(activeProjectId);
  }, [activeProjectId]);

  useEffect(() => {
    if (!requestedPaperId || loading) return;
    const paper = papers.find((item) => item.id === requestedPaperId);
    if (!paper) {
      if (papers.length > 0) {
        toast.warning('来源论文不存在或已被移出论文库');
        setSearchParams({}, { replace: true });
      }
      return;
    }
    setHighlightedPaperId(requestedPaperId);
    window.setTimeout(() => {
      document
        .getElementById(`paper-${requestedPaperId}`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 80);
    window.setTimeout(() => {
      setHighlightedPaperId((current) =>
        current === requestedPaperId ? null : current,
      );
    }, 2400);
    setSearchParams({}, { replace: true });
  }, [loading, papers, requestedPaperId, setSearchParams, toast]);

  const loadPapers = async (projectId: string) => {
    setLoading(true);
    try {
      const res = await api.listProjectPapers(projectId);
      setPapers(res.papers);
      // Drop compare IDs that no longer exist
      setCompareIds((prev) =>
        prev.filter((id) => res.papers.some((p) => p.id === id)),
      );
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const pollTask = (paperId: string, taskId: string) => {
    if (pollTimers.current[taskId]) {
      clearInterval(pollTimers.current[taskId]);
    }
    let count = 0;
    const timer = window.setInterval(async () => {
      count++;
      try {
        const task = await api.getTask(taskId);
        setTaskMap((prev) => ({ ...prev, [taskId]: task }));
        if (
          task.status === 'completed' ||
          task.status === 'failed' ||
          task.status === 'cancelled'
        ) {
          clearInterval(timer);
          delete pollTimers.current[taskId];
          if (task.status === 'completed' && activeProjectId) {
            void loadPapers(activeProjectId);
          }
        }
        if (count >= TASK_POLL_MAX) {
          clearInterval(timer);
          delete pollTimers.current[taskId];
        }
      } catch {
        clearInterval(timer);
        delete pollTimers.current[taskId];
      }
    }, TASK_POLL_INTERVAL);
    pollTimers.current[taskId] = timer;
  };

  const handleUpload = async (file: File) => {
    if (!activeProjectId) {
      toast.error('请先选择一个项目');
      return false;
    }
    setUploading(true);
    try {
      const res = await api.uploadPdf(file, activeProjectId);
      setPapers((prev) => [
        ...prev,
        {
          id: res.paper_id,
          project_id: activeProjectId,
          arxiv_id: `upload:${file.name}`,
          title: file.name,
          authors_json: '[]',
          abstract: '',
          published: '',
          categories_json: '[]',
          entry_url: '',
          pdf_url: '',
          recommendation_reason: '',
          purpose_labels_json: '[]',
          favorited: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as Paper,
      ]);
      setTaskMap((prev) => ({ ...prev, [res.task.id]: res.task }));
      pollTask(res.paper_id, res.task.id);
      toast.success('PDF 上传成功，正在后台解析…');
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setUploading(false);
    }
    return false;
  };

  const handleImportArxiv = async (paper: Paper) => {
    try {
      const res = await api.importArxivPdf(paper.id);
      setTaskMap((prev) => ({ ...prev, [res.task.id]: res.task }));
      pollTask(paper.id, res.task.id);
      toast.success('论文 PDF 导入任务已创建，正在后台下载和解析…');
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const hasActivePaperTask = (paperId: string) =>
    Object.values(taskMap).some(
      (task) =>
        task.paper_id === paperId &&
        (task.status === 'pending' || task.status === 'processing'),
    );

  const handlePdfAction = async (paper: Paper) => {
    const importable = !isUploaded(paper) && paper.pdf_url.startsWith('http');
    if (importable && !hasActivePaperTask(paper.id)) {
      await handleImportArxiv(paper);
    }
    window.open(api.paperPdfUrl(paper.id), '_blank', 'noopener,noreferrer');
  };

  const handleQuickAnalysis = async (paper: Paper) => {
    try {
      const res = await api.quickAnalysis(paper.id);
      toast.success('快速分析完成！');
      modal.confirm({
        title: '分析完成',
        content: (
          <Space direction="vertical">
            <Typography.Text>成果标题：{res.title}</Typography.Text>
            <Typography.Text type="secondary">
              证据页：{res.evidence_pages.join(', ') || '无'}
            </Typography.Text>
          </Space>
        ),
        okText: '查看成果',
        cancelText: '关闭',
        onOk: () => navigate(`/artifacts/${res.artifact_id}`),
      });
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const handleFavoriteToggle = async (paper: Paper, favorited: boolean) => {
    if (!activeProjectId) return;
    try {
      const res = await api.favoritePaper({
        project_id: activeProjectId,
        arxiv_id: paper.arxiv_id,
        favorited,
      });
      if (!res.ok) {
        toast.error(res.message || '更新收藏状态失败');
        return;
      }
      if (!favorited && !isUploaded(paper)) {
        setPapers((prev) => prev.filter((item) => item.id !== paper.id));
        setCompareIds((prev) => prev.filter((id) => id !== paper.id));
      } else {
        setPapers((prev) =>
          prev.map((item) =>
            item.id === paper.id ? { ...item, favorited } : item,
          ),
        );
      }
      toast.success(favorited ? '已加入论文库' : '已移出论文库');
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const handleCancelTask = async (task: TaskRecord) => {
    try {
      const updated = await api.cancelTask(task.id);
      setTaskMap((prev) => ({ ...prev, [updated.id]: updated }));
      const timer = pollTimers.current[task.id];
      if (timer) {
        clearInterval(timer);
        delete pollTimers.current[task.id];
      }
      toast.success('任务已取消');
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const handleRetryTask = async (task: TaskRecord) => {
    try {
      const updated = await api.retryTask(task.id);
      setTaskMap((prev) => ({ ...prev, [updated.id]: updated }));
      if (updated.paper_id) {
        pollTask(updated.paper_id, updated.id);
      }
      toast.success('任务已重新提交');
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const toggleCompare = (id: string) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) return prev.filter((p) => p !== id);
      if (prev.length >= 3) {
        toast.warning('最多只能选择 3 篇论文进行对比');
        return prev;
      }
      return [...prev, id];
    });
  };

  const runCompare = async () => {
    if (compareIds.length < 2) {
      toast.warning('请至少选择 2 篇论文');
      return;
    }
    setCompareRunning(true);
    try {
      const res = await api.comparePapers({ paper_ids: compareIds });
      toast.success('对比完成');
      modal.confirm({
        title: '对比结果',
        content: (
          <Typography.Text>成果标题：{res.title}</Typography.Text>
        ),
        okText: '查看成果',
        cancelText: '关闭',
        onOk: () => navigate(`/artifacts/${res.artifact_id}`),
      });
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setCompareRunning(false);
    }
  };

  const activeTasks = Object.values(taskMap).filter(
    (t) => t.status === 'pending' || t.status === 'processing',
  );

  useEffect(() => {
    return () => {
      Object.values(pollTimers.current).forEach(clearInterval);
    };
  }, []);

  if (!activeProjectId) {
    return (
      <Card>
        <Empty description="请先在侧边栏选择一个研究项目，然后再上传论文。" />
      </Card>
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      {activeTasks.length > 0 && (
        <Alert
          type="info"
          showIcon
          message={
            <Space>
              <Badge status="processing" />
              <span>后台正在处理 {activeTasks.length} 个任务…</span>
            </Space>
          }
          description={
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              {activeTasks.map((t) => (
                <Progress
                  key={t.id}
                  percent={t.progress}
                  size="small"
                  status={t.status === 'failed' ? 'exception' : 'active'}
                  showInfo
                />
              ))}
            </Space>
          }
        />
      )}
      <Card
        title={
          <Space>
            <CloudUploadOutlined />
            <span>论文库</span>
          </Space>
        }
        extra={
          <Space size={12}>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {papers.length} 篇
            </Typography.Text>
            <Button
              type="primary"
              icon={<ExperimentOutlined />}
              loading={compareRunning}
              disabled={compareIds.length < 2}
              onClick={runCompare}
            >
              对比所选 {compareIds.length > 0 ? `(${compareIds.length}/3)` : ''}
            </Button>
          </Space>
        }
      >
        <Upload.Dragger
          accept=".pdf"
          multiple={false}
          showUploadList={false}
          beforeUpload={handleUpload}
          disabled={uploading}
          style={{
            background: '#fafbff',
            border: '1px dashed #adc6ff',
            marginBottom: 16,
          }}
        >
          {uploading ? (
            <Space direction="vertical" align="center">
              <Spin />
              <Typography.Text type="secondary">
                上传并解析中…
              </Typography.Text>
            </Space>
          ) : (
            <Space direction="vertical" align="center" size={6}>
              <CloudUploadOutlined style={{ fontSize: 36, color: '#2f54eb' }} />
              <Typography.Text style={{ fontSize: 14 }}>
                点击或拖拽 PDF 文件到此区域上传
              </Typography.Text>
            </Space>
          )}
        </Upload.Dragger>

        {loading ? (
          <div style={{ textAlign: 'center', padding: 24 }}>
            <Spin />
          </div>
        ) : papers.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="还没有论文"
          />
        ) : (
          <List
            dataSource={papers}
            rowKey={(item) => item.id}
            renderItem={(paper) => (
              <PaperItem
                key={paper.id}
                paper={paper}
                taskMap={taskMap}
                highlighted={highlightedPaperId === paper.id}
                selected={compareIds.includes(paper.id)}
                onToggleCompare={() => toggleCompare(paper.id)}
                onPdfAction={() => void handlePdfAction(paper)}
                onQuickAnalyze={() => handleQuickAnalysis(paper)}
                onFavoriteToggle={(favorited) =>
                  void handleFavoriteToggle(paper, favorited)
                }
                onCancelTask={handleCancelTask}
                onRetryTask={handleRetryTask}
              />
            )}
          />
        )}
      </Card>
    </Space>
  );
}

function PaperItem({
  paper,
  taskMap,
  highlighted,
  selected,
  onToggleCompare,
  onPdfAction,
  onQuickAnalyze,
  onFavoriteToggle,
  onCancelTask,
  onRetryTask,
}: {
  paper: Paper;
  taskMap: Record<string, TaskRecord>;
  highlighted: boolean;
  selected: boolean;
  onToggleCompare: () => void;
  onPdfAction: () => void;
  onQuickAnalyze: () => void;
  onFavoriteToggle: (favorited: boolean) => void;
  onCancelTask: (task: TaskRecord) => void;
  onRetryTask: (task: TaskRecord) => void;
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<PaperChunk[]>([]);
  const [searching, setSearching] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const { message: toast } = AntdApp.useApp();

  const paperTaskId = Object.keys(taskMap)
    .reverse()
    .find((key) => taskMap[key].paper_id === paper.id);
  const task = paperTaskId ? taskMap[paperTaskId] : undefined;
  const taskControls = task ? getTaskControls(task.status) : null;
  const isImportable = !isUploaded(paper) && paper.pdf_url.startsWith('http');

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await api.searchEvidence(paper.id, searchQuery.trim());
      setSearchResults(res.results);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSearching(false);
    }
  };

  return (
    <List.Item
      id={`paper-${paper.id}`}
      style={{
        flexDirection: 'column',
        alignItems: 'stretch',
        padding: '14px 0',
        border: highlighted ? '1px solid #91caff' : '1px solid transparent',
        borderBottom: '1px solid #f0f2f5',
        borderRadius: highlighted ? 8 : 0,
        background: highlighted ? '#e6f4ff' : undefined,
      }}
    >
      <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
        <div style={{ flex: 1 }}>
          <Space style={{ marginBottom: 4 }} wrap>
            <Checkbox
              checked={selected}
              onChange={onToggleCompare}
              disabled={!selected && task?.status === 'processing'}
            />
            <Typography.Text strong style={{ fontSize: 15 }}>
              {paper.title}
            </Typography.Text>
          </Space>
          <div style={{ marginTop: 4 }}>
            <Space size={4} wrap>
              {isUploaded(paper) && <Tag color="blue">本地 PDF</Tag>}
              {!isUploaded(paper) && paper.favorited && (
                <Tag color="gold" icon={<StarFilled />}>
                  已收藏
                </Tag>
              )}
              {!isUploaded(paper) && (
                <Tag color="green">{paper.published.slice(0, 10)}</Tag>
              )}
              {parseCategories(paper)
                .slice(0, 3)
                .map((cat) => (
                  <Tag key={cat}>{cat}</Tag>
                ))}
            </Space>
          </div>
          <Descriptions
            size="small"
            column={2}
            style={{ marginTop: 4 }}
            labelStyle={{ width: 100 }}
          >
            <Descriptions.Item label="作者">
              {shortAuthors(parseAuthors(paper))}
            </Descriptions.Item>
          </Descriptions>
          {paper.recommendation_reason && (
            <Typography.Paragraph
              type="secondary"
              style={{ fontSize: 12, marginBottom: 4 }}
            >
              推荐理由：{paper.recommendation_reason}
            </Typography.Paragraph>
          )}
          {parsePurposeLabels(paper).length > 0 && (
            <Space size={4} wrap style={{ marginTop: 4 }}>
              {parsePurposeLabels(paper).map((label) => (
                <Tag key={label} color="geekblue">
                  {label}
                </Tag>
              ))}
            </Space>
          )}
          {task && (
            <div style={{ marginTop: 8 }}>
              <Space size={8}>
                <Badge
                  status={
                    task.status === 'completed'
                      ? 'success'
                      : task.status === 'failed'
                        ? 'error'
                        : task.status === 'cancelled'
                          ? 'default'
                          : 'processing'
                  }
                />
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  {TASK_STATUS_LABEL[task.status] ?? task.status}
                </Typography.Text>
                {task.status === 'processing' && task.progress > 0 && (
                  <Progress
                    percent={task.progress}
                    size="small"
                    style={{ width: 120 }}
                  />
                )}
              </Space>
              {task.error_message && (
                <Alert
                  type="error"
                  message={task.error_message}
                  style={{ marginTop: 4 }}
                />
              )}
              {taskControls && (
                <Space size={8} style={{ marginTop: 8 }}>
                  {taskControls.canCancel && (
                    <Button
                      size="small"
                      danger
                      onClick={() => onCancelTask(task)}
                    >
                      取消任务
                    </Button>
                  )}
                  {taskControls.canRetry && (
                    <Button
                      size="small"
                      icon={<ReloadOutlined />}
                      onClick={() => onRetryTask(task)}
                    >
                      重试任务
                    </Button>
                  )}
                </Space>
              )}
            </div>
          )}
        </div>
        <Space wrap style={{ marginLeft: 16 }}>
          <Tooltip title={isImportable ? '导入 PDF 到论文库并打开' : '打开 PDF'}>
            <Button
              size="small"
              icon={isImportable ? <DownloadOutlined /> : <FilePdfOutlined />}
              onClick={onPdfAction}
            >
              PDF
            </Button>
          </Tooltip>
          <Button size="small" icon={<RobotOutlined />} onClick={onQuickAnalyze}>
            快速分析
          </Button>
          {!isUploaded(paper) && (
            <Button
              size="small"
              danger
              onClick={() => onFavoriteToggle(false)}
            >
              移出论文库
            </Button>
          )}
        </Space>
      </Space>

      <Collapse
        ghost
        style={{ width: '100%', marginTop: 8 }}
        activeKey={evidenceOpen ? ['evidence'] : []}
        onChange={(keys) =>
          setEvidenceOpen((keys as string[]).includes('evidence'))
        }
        items={[
          {
            key: 'evidence',
            label: (
              <Space>
                <FileSearchOutlined />
                <span>证据检索</span>
              </Space>
            ),
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Search
                  placeholder="输入关键词检索论文原文证据"
                  enterButton="检索"
                  loading={searching}
                  onSearch={handleSearch}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {searchResults.length > 0 && (
                  <List
                    size="small"
                    dataSource={searchResults}
                    rowKey={(item) => item.chunk_id}
                    header={
                      <Typography.Text strong>检索结果（按页码排序）</Typography.Text>
                    }
                    renderItem={(chunk) => (
                      <List.Item
                        style={{ flexDirection: 'column', alignItems: 'stretch', padding: '8px 0' }}
                      >
                        <div className="evidence-card">
                          <div className="meta">
                            <Tag color={chunk.is_ocr ? 'orange' : 'blue'}>
                              第 {chunk.page_number} 页
                            </Tag>
                            {chunk.is_ocr && <Tag color="orange">OCR</Tag>}
                            {chunk.section && <Tag>{chunk.section}</Tag>}
                          </div>
                          <div
                            style={{
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              display: '-webkit-box',
                              WebkitLineClamp: 4,
                              WebkitBoxOrient: 'vertical',
                            }}
                          >
                            {chunk.text}
                          </div>
                        </div>
                      </List.Item>
                    )}
                  />
                )}
                {searchResults.length === 0 && searchQuery && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    未找到匹配结果，尝试其他关键词。
                  </Typography.Text>
                )}
              </Space>
            ),
          },
        ]}
      />
    </List.Item>
  );
}

const TASK_STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
};
