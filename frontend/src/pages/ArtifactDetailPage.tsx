import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Divider,
  Empty,
  Input,
  Spin,
  Space,
  Tag,
  Typography,
  App as AntdApp,
  Tabs,
} from 'antd';
import {
  EditOutlined,
  SaveOutlined,
  DownloadOutlined,
  ArrowLeftOutlined,
} from '@ant-design/icons';
import { useNavigate, useParams } from 'react-router-dom';
import { api } from '@/api/client';
import type { Artifact } from '@/types/api';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';

const { TextArea } = Input;

const ARTIFACT_TYPE_CONFIG: Record<
  string,
  { label: string; color: string }
> = {
  literature_card: { label: '文献卡片', color: 'blue' },
  paper_comparison: { label: '论文对比', color: 'purple' },
  guided_reading_note: { label: '精读笔记', color: 'green' },
  topic_guidance_plan: { label: '选题方案', color: 'geekblue' },
  framework_card: { label: '框架卡片', color: 'orange' },
};

export function ArtifactDetailPage() {
  const navigate = useNavigate();
  const { artifactId } = useParams<{ artifactId: string }>();
  const { message: toast } = AntdApp.useApp();
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');
  const [markdownDraft, setMarkdownDraft] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!artifactId) return;
    void loadArtifact(artifactId);
  }, [artifactId]);

  const loadArtifact = async (id: string) => {
    setLoading(true);
    try {
      const res = await api.getArtifact(id);
      setArtifact(res);
      setTitleDraft(res.title);
      setMarkdownDraft(res.markdown);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!artifact) return;
    setSaving(true);
    try {
      const res = await api.updateArtifact(artifact.id, {
        title: titleDraft,
        markdown: markdownDraft,
      });
      setArtifact(res);
      setEditing(false);
      toast.success('保存成功');
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleExportMarkdown = () => {
    if (!artifact) return;
    const blob = new Blob([artifact.markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${artifact.title}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Space direction="vertical" align="center">
          <Spin />
          <Typography.Text type="secondary">加载成果…</Typography.Text>
        </Space>
      </div>
    );
  }

  if (!artifact) {
    return (
      <Card>
        <Empty description="成果不存在或加载失败。" />
      </Card>
    );
  }

  const config = ARTIFACT_TYPE_CONFIG[artifact.artifact_type] ?? {
    label: artifact.artifact_type,
    color: 'default',
  };
  const content = artifact.content as Record<string, unknown>;

  const tabItems = [
    {
      key: 'preview',
      label: '预览',
      children: (
        <div
          style={{
            background: '#fff',
            padding: '24px 28px',
            borderRadius: 6,
            border: '1px solid #e6ebf5',
            minHeight: 400,
          }}
        >
          {artifact.markdown.trim() ? (
            <MarkdownRenderer content={artifact.markdown} />
          ) : (
            <Typography.Paragraph type="secondary">该成果暂无内容。</Typography.Paragraph>
          )}
        </div>
      ),
    },
    {
      key: 'content',
      label: '原始数据',
      children: (
        <pre
          style={{
            background: '#f5f7fb',
            padding: 16,
            borderRadius: 6,
            overflow: 'auto',
            maxHeight: 500,
            fontSize: 12,
          }}
        >
          {JSON.stringify(content, null, 2)}
        </pre>
      ),
    },
  ];

  if (editing) {
    tabItems.unshift({
      key: 'edit',
      label: '编辑',
      children: (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Typography.Text strong>成果标题</Typography.Text>
            <Input
              value={titleDraft}
              onChange={(e) => setTitleDraft(e.target.value)}
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Typography.Text strong>Markdown 内容</Typography.Text>
            <TextArea
              value={markdownDraft}
              onChange={(e) => setMarkdownDraft(e.target.value)}
              autoSize={{ minRows: 20, maxRows: 40 }}
              style={{ marginTop: 4, fontFamily: 'monospace', fontSize: 13 }}
            />
          </div>
          <Space>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={handleSave}
            >
              保存
            </Button>
            <Button onClick={() => setEditing(false)}>取消</Button>
          </Space>
        </Space>
      ),
    });
  }

  return (
    <Card
      title={
        <Space>
          <Button
            type="text"
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/artifacts')}
          />
          <span>{artifact.title}</span>
          <Tag color={config.color}>{config.label}</Tag>
        </Space>
      }
      extra={
        <Space>
          {!editing && (
            <Button icon={<EditOutlined />} onClick={() => setEditing(true)}>
              编辑
            </Button>
          )}
          <Button icon={<DownloadOutlined />} onClick={handleExportMarkdown}>
            导出 Markdown
          </Button>
        </Space>
      }
    >
      <Descriptions size="small" column={2} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="类型">
          <Tag color={config.color}>{config.label}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label="创建时间">
          {new Date(artifact.created_at).toLocaleString('zh-CN')}
        </Descriptions.Item>
        <Descriptions.Item label="ID">{artifact.id}</Descriptions.Item>
        <Descriptions.Item label="所属项目">
          {artifact.project_id.slice(0, 8)}
        </Descriptions.Item>
      </Descriptions>
      <Divider style={{ margin: '12px 0' }} />
      <Tabs items={tabItems} />
    </Card>
  );
}
