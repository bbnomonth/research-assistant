import { useEffect, useState } from 'react';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Empty,
  List,
  Popconfirm,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  App as AntdApp,
} from 'antd';
import {
  FileTextOutlined,
  ReloadOutlined,
  ReadOutlined,
  CompassOutlined,
  BulbOutlined,
  DeleteOutlined,
  ExperimentOutlined,
  LinkOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import { useAppStore } from '@/store/app';
import type { ArtifactSourceLink, ArtifactSummary } from '@/types/api';

const ARTIFACT_TYPE_CONFIG: Record<
  string,
  { label: string; icon: React.ReactNode; color: string; bgColor: string }
> = {
  literature_card: {
    label: '文献卡片',
    icon: <ReadOutlined />,
    color: '#2f54eb',
    bgColor: '#e6f4ff',
  },
  paper_comparison: {
    label: '论文对比',
    icon: <CompassOutlined />,
    color: '#722ed1',
    bgColor: '#f9f0ff',
  },
  guided_reading_note: {
    label: '精读笔记',
    icon: <FileTextOutlined />,
    color: '#52c41a',
    bgColor: '#f6ffed',
  },
  topic_guidance_plan: {
    label: '选题方案',
    icon: <ExperimentOutlined />,
    color: '#2b82f6',
    bgColor: '#e6f4ff',
  },
  framework_card: {
    label: '框架卡片',
    icon: <BulbOutlined />,
    color: '#fa8c16',
    bgColor: '#fff7e6',
  },
};

function formatDate(iso: string): string {
  const date = new Date(iso);
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

export function ArtifactsPage() {
  const navigate = useNavigate();
  const { message: toast } = AntdApp.useApp();
  const { activeProjectId, projects, setActiveProjectId } = useAppStore();
  const [artifacts, setArtifacts] = useState<ArtifactSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const activeProject = projects.find((p) => p.id === activeProjectId);

  useEffect(() => {
    if (!activeProjectId) {
      setArtifacts([]);
      return;
    }
    void loadArtifacts(activeProjectId);
  }, [activeProjectId]);

  useEffect(() => {
    setSelectedIds(new Set());
  }, [activeProjectId]);

  const loadArtifacts = async (projectId: string) => {
    setLoading(true);
    try {
      const res = await api.listProjectArtifacts(projectId);
      setArtifacts(res.artifacts);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteOne = async (artifactId: string) => {
    try {
      await api.deleteArtifact(artifactId);
      setArtifacts((prev) => prev.filter((a) => a.id !== artifactId));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(artifactId);
        return next;
      });
      toast.success('成果已删除');
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const handleBatchDelete = async () => {
    const ids = Array.from(selectedIds);
    try {
      await Promise.all(ids.map((id) => api.deleteArtifact(id)));
      setArtifacts((prev) => prev.filter((a) => !selectedIds.has(a.id)));
      setSelectedIds(new Set());
      toast.success(`已删除 ${ids.length} 项成果`);
    } catch (err) {
      toast.error((err as Error).message);
    }
  };

  const toggleAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(artifacts.map((a) => a.id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const toggleOne = (artifactId: string, checked: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) {
        next.add(artifactId);
      } else {
        next.delete(artifactId);
      }
      return next;
    });
  };

  const handleOpenSource = async (source: ArtifactSourceLink) => {
    const projectId = source.project_id ?? activeProjectId;
    if (source.source_type === 'session') {
      try {
        await api.listSessionMessages(source.target_id);
        if (projectId) setActiveProjectId(projectId);
        navigate(
          `/chat?project=${encodeURIComponent(projectId ?? '')}&session=${encodeURIComponent(
            source.target_id,
          )}`,
        );
      } catch {
        toast.warning('来源对话不存在或已被删除');
      }
      return;
    }

    if (source.source_type === 'paper') {
      try {
        const paper = await api.getPaper(source.target_id);
        setActiveProjectId(paper.project_id);
        navigate(`/papers?paper=${encodeURIComponent(source.target_id)}`);
      } catch {
        toast.warning('来源论文不存在或已被移出论文库');
      }
      return;
    }

    toast.info('该成果没有可跳转的来源');
  };

  const allSelected = artifacts.length > 0 && selectedIds.size === artifacts.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < artifacts.length;

  if (!activeProjectId) {
    return (
      <Card>
        <Empty description="请先在侧边栏选择一个研究项目。" />
      </Card>
    );
  }

  return (
    <Card
      title={
        <Space>
          <span>项目成果</span>
          <Tag>{artifacts.length} 项</Tag>
          {activeProject && (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              {activeProject.name}
            </Typography.Text>
          )}
        </Space>
      }
      extra={
        <Space>
          {selectedIds.size > 0 && (
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>
              已选 {selectedIds.size} 项
            </Typography.Text>
          )}
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              if (activeProjectId) void loadArtifacts(activeProjectId);
            }}
          >
            刷新
          </Button>
        </Space>
      }
    >
      {loading ? (
        <div style={{ textAlign: 'center', padding: 24 }}>
          <Spin />
        </div>
      ) : artifacts.length === 0 ? (
        <Empty
          description="还没有任何研究成果。通过文献发现、快速分析、选题指导或框架搭建即可自动生成成果。"
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      ) : (
        <>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 12,
              padding: '8px 4px',
              borderRadius: 8,
              background: selectedIds.size > 0 ? '#fff7e6' : undefined,
              transition: 'background 160ms ease',
            }}
          >
            <Checkbox
              indeterminate={someSelected}
              checked={allSelected}
              onChange={(e) => toggleAll(e.target.checked)}
            />
            <span style={{ fontSize: 13, color: '#666' }}>
              {allSelected || someSelected
                ? `已选 ${selectedIds.size} / ${artifacts.length}`
                : '全选'}
            </span>
            <div style={{ flex: 1 }} />
            {selectedIds.size > 0 && (
              <Popconfirm
                title={`确定删除这 ${selectedIds.size} 项成果？`}
                description="成果删除后将无法恢复。"
                okText="删除"
                okButtonProps={{ danger: true }}
                cancelText="取消"
                onConfirm={handleBatchDelete}
              >
                <Button size="small" danger icon={<DeleteOutlined />}>
                  批量删除
                </Button>
              </Popconfirm>
            )}
          </div>
          <List
            dataSource={artifacts}
            rowKey={(item) => item.id}
            split={false}
            renderItem={(artifact) => {
              const config = ARTIFACT_TYPE_CONFIG[artifact.artifact_type] ?? {
                label: artifact.artifact_type,
                icon: <FileTextOutlined />,
                color: '#8c8c8c',
                bgColor: '#fafafa',
              };
              const checked = selectedIds.has(artifact.id);
              return (
                <List.Item
                  style={{
                    cursor: 'pointer',
                    padding: '16px 20px',
                    marginBottom: 8,
                    borderRadius: 10,
                    border: `1px solid ${checked ? '#91caff' : '#f0f2f5'}`,
                    background: checked ? '#f0f5ff' : '#fff',
                    boxShadow: checked ? '0 2px 8px rgba(47,84,235,0.08)' : 'none',
                    transition: 'all 160ms ease',
                  }}
                  onMouseEnter={(e) => {
                    if (!checked) {
                      e.currentTarget.style.borderColor = '#91caff';
                      e.currentTarget.style.boxShadow = '0 2px 8px rgba(47,84,235,0.08)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!checked) {
                      e.currentTarget.style.borderColor = '#f0f2f5';
                      e.currentTarget.style.boxShadow = 'none';
                    }
                  }}
                  onClick={() => navigate(`/artifacts/${artifact.id}`)}
                >
                  <Checkbox
                    checked={checked}
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => toggleOne(artifact.id, e.target.checked)}
                    style={{ marginRight: 12, flexShrink: 0 }}
                  />
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: 10,
                      background: config.bgColor,
                      color: config.color,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 20,
                      flexShrink: 0,
                      marginRight: 16,
                    }}
                  >
                    {config.icon}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Typography.Text
                      strong
                      style={{ fontSize: 15, display: 'block', marginBottom: 4 }}
                      ellipsis
                    >
                      {artifact.title || '（无标题成果）'}
                    </Typography.Text>
                    <Space size={8} wrap>
                      <Tag
                        color={config.color}
                        style={{ margin: 0, borderRadius: 4 }}
                      >
                        {config.label}
                      </Tag>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {formatDate(artifact.created_at)}
                      </Typography.Text>
                    </Space>
                  </div>
                  <Space size={4} onClick={(e) => e.stopPropagation()}>
                    {(artifact.source_links ?? []).map((source) => (
                      <Button
                        key={`${source.source_type}-${source.target_id}`}
                        type="text"
                        icon={<LinkOutlined />}
                        onClick={() => void handleOpenSource(source)}
                      >
                        {source.label}
                      </Button>
                    ))}
                    <Button
                      type="text"
                      icon={<ReadOutlined />}
                      onClick={() => navigate(`/artifacts/${artifact.id}`)}
                      style={{ flexShrink: 0 }}
                    >
                      查看
                    </Button>
                    <Popconfirm
                      title="删除该成果？"
                      description="成果删除后将无法恢复。"
                      okText="删除"
                      okButtonProps={{ danger: true }}
                      cancelText="取消"
                      onConfirm={() => handleDeleteOne(artifact.id)}
                    >
                      <Tooltip title="删除">
                        <Button
                          type="text"
                          danger
                          icon={<DeleteOutlined />}
                        />
                      </Tooltip>
                    </Popconfirm>
                  </Space>
                </List.Item>
              );
            }}
          />
        </>
      )}
    </Card>
  );
}
