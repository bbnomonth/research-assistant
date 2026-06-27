import { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Layout,
  Menu,
  Select,
  Space,
  Tag,
  Typography,
  Button,
  Empty,
  Input,
  Modal,
  Popconfirm,
  Spin,
  App as AntApp,
} from 'antd';
import {
  MessageOutlined,
  BookOutlined,
  FileTextOutlined,
  SettingOutlined,
  ReloadOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { api } from '@/api/client';
import { useAppStore } from '@/store/app';
import type { Project } from '@/types/api';

const { Sider, Header, Content } = Layout;

const ROUTE_TITLES: Record<string, string> = {
  chat: '对话工作台',
  papers: '论文库',
  artifacts: '研究项目成果',
  settings: '系统设置与诊断',
};

const HEALTH_POLL_INTERVAL_MS = 15_000;

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { message: antMessage } = AntApp.useApp();
  const {
    projects,
    setProjects,
    upsertProject,
    removeProject,
    activeProjectId,
    setActiveProjectId,
    settings,
    setSettings,
  } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [editingProject, setEditingProject] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [projectProfile, setProjectProfile] = useState('{}');
  const [savingProject, setSavingProject] = useState(false);
  const [creatingProject, setCreatingProject] = useState(false);
  const previousHealthRef = useRef<boolean | null>(null);

  const refreshAll = async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const [health, projectsRes, settingsRes] = await Promise.all([
        api.health(),
        api.listProjects(),
        api.getRuntimeSettings(),
      ]);
      setHealthOk(health.status === 'ok');
      setProjects(projectsRes.projects);
      setSettings(settingsRes);
      if (silent) {
        antMessage.success({ content: '已刷新后端状态', duration: 1.5 });
      }
    } catch (err) {
      setHealthOk(false);
      console.error(err);
      if (!silent) {
        antMessage.error('刷新失败：' + (err as Error).message);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  };

  useEffect(() => {
    void refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeProjectId && projects.length > 0) {
      setActiveProjectId(projects[0].id);
    }
  }, [activeProjectId, projects, setActiveProjectId]);

  useEffect(() => {
    const previous = previousHealthRef.current;
    if (healthOk === false && previous !== false) {
      antMessage.warning('后端连接已断开，正在尝试重连…');
    } else if (healthOk === true && previous === false) {
      antMessage.success('后端已恢复连接');
    }
    previousHealthRef.current = healthOk;
  }, [healthOk, antMessage]);

  useEffect(() => {
    const handle = window.setInterval(() => {
      void (async () => {
        try {
          const health = await api.health();
          setHealthOk(health.status === 'ok');
        } catch {
          setHealthOk(false);
        }
      })();
    }, HEALTH_POLL_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, []);

  const activeProject: Project | undefined = projects.find(
    (p) => p.id === activeProjectId,
  );

  const handleSelectProject = (id: string) => {
    setActiveProjectId(id);
    if (location.pathname !== '/chat') {
      navigate('/chat');
    }
  };

  const createProjectAndEnterChat = async () => {
    if (creatingProject) return;
    setCreatingProject(true);
    try {
      const project = await api.createProject({});
      upsertProject(project);
      setActiveProjectId(project.id);
      navigate('/chat');
      antMessage.success('已创建新项目');
    } catch (err) {
      antMessage.error((err as Error).message || '创建项目失败');
    } finally {
      setCreatingProject(false);
    }
  };

  const openProjectEditor = () => {
    if (!activeProject) return;
    setProjectName(activeProject.name);
    setProjectProfile(JSON.stringify(activeProject.profile ?? {}, null, 2));
    setEditingProject(true);
  };

  const saveProject = async () => {
    if (!activeProject) return;
    const name = projectName.trim();
    if (!name) {
      antMessage.error('项目名称不能为空');
      return;
    }
    let profile: Record<string, unknown>;
    try {
      profile = JSON.parse(projectProfile || '{}') as Record<string, unknown>;
    } catch {
      antMessage.error('项目档案必须是有效 JSON');
      return;
    }
    setSavingProject(true);
    try {
      const updated = await api.updateProject(activeProject.id, {
        name,
        profile,
      });
      upsertProject(updated);
      setEditingProject(false);
      antMessage.success('项目已更新');
    } catch (err) {
      antMessage.error((err as Error).message);
    } finally {
      setSavingProject(false);
    }
  };

  const deleteActiveProject = async () => {
    if (!activeProject) return;
    try {
      await api.deleteProject(activeProject.id);
      removeProject(activeProject.id);
      antMessage.success('项目已删除');
      navigate('/chat');
    } catch (err) {
      antMessage.error((err as Error).message);
    }
  };

  const menuKey = location.pathname.split('/').filter(Boolean)[0] ?? 'chat';

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={280} theme="light" style={{ borderRight: '1px solid #e6ebf5' }}>
        <div style={{ padding: '16px 16px 8px' }}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            研究能力训练助手
          </Typography.Title>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            论文阅读 · 文献发现 · 选题指导 · 框架搭建
          </Typography.Text>
        </div>
        <div style={{ padding: '0 16px 12px' }}>
          <Space.Compact style={{ width: '100%' }}>
            <Select
              value={activeProjectId ?? undefined}
              onChange={handleSelectProject}
              placeholder="选择研究项目"
              style={{ width: '100%' }}
              options={projects.map((p) => ({ value: p.id, label: p.name }))}
              notFoundContent={
                <span style={{ fontSize: 12, color: '#999' }}>暂无项目</span>
              }
            />
            <Button
              icon={<ReloadOutlined />}
              onClick={() => void refreshAll(true)}
              title="刷新项目列表"
            />
            <Button
              icon={<EditOutlined />}
              onClick={openProjectEditor}
              disabled={!activeProject}
              title="编辑当前项目"
            />
            <Popconfirm
              title="删除当前项目？"
              description="项目下的会话、论文库和成果卡片会一并删除。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={() => void deleteActiveProject()}
              disabled={!activeProject}
            >
              <Button
                danger
                icon={<DeleteOutlined />}
                disabled={!activeProject}
                title="删除当前项目"
              />
            </Popconfirm>
          </Space.Compact>
          <Typography.Paragraph
            type="secondary"
            style={{ fontSize: 12, marginTop: 8, marginBottom: 0 }}
          >
            创建新项目后自动进入对话工作台。
          </Typography.Paragraph>
          <Button
            block
            type="dashed"
            icon={<PlusOutlined />}
            loading={creatingProject}
            style={{ marginTop: 8 }}
            onClick={() => void createProjectAndEnterChat()}
          >
            创建新项目
          </Button>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[menuKey]}
          onClick={({ key }) => navigate(`/${key}`)}
          style={{ borderInlineEnd: 'none' }}
          items={[
            { key: 'chat', icon: <MessageOutlined />, label: '对话工作台' },
            { key: 'papers', icon: <BookOutlined />, label: '论文库' },
            { key: 'artifacts', icon: <FileTextOutlined />, label: '研究项目成果' },
            { key: 'settings', icon: <SettingOutlined />, label: '系统设置与诊断' },
          ]}
        />
        <div style={{ position: 'absolute', bottom: 12, left: 16, right: 16 }}>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            <Space size={4} wrap>
              <Tag
                color={
                  healthOk === true ? 'green' : healthOk === false ? 'red' : 'default'
                }
                style={{ margin: 0 }}
              >
                <span style={{ marginRight: 4 }}>
                  {healthOk === null ? '○' : healthOk ? '●' : '●'}
                </span>
                {healthOk === null
                  ? '检测中'
                  : healthOk
                    ? '后端在线'
                    : '后端离线'}
              </Tag>
              {settings && (
                <Tag
                  color={settings.model_configured ? 'blue' : 'orange'}
                  style={{ margin: 0 }}
                >
                  {settings.model_configured ? '模型已配置' : '模型未配置'}
                </Tag>
              )}
              {settings && (
                <Tag
                  color={settings.ocr_configured ? 'cyan' : 'default'}
                  style={{ margin: 0 }}
                >
                  {settings.ocr_configured ? 'OCR 已配置' : 'OCR 未配置'}
                </Tag>
              )}
            </Space>
            {activeProject && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                当前项目：{activeProject.name}
              </Typography.Text>
            )}
          </Space>
        </div>
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            paddingInline: 24,
            borderBottom: '1px solid #e6ebf5',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            {ROUTE_TITLES[menuKey] ?? '研究能力训练助手'}
          </Typography.Title>
          {activeProject && (
            <Tag color="processing" style={{ marginLeft: 12 }}>
              {activeProject.name}
            </Tag>
          )}
        </Header>
        <Content style={{ padding: 24, background: '#f5f7fb' }}>
          {settings?.privacy?.local_only && (
            <Alert
              type="warning"
              showIcon
              style={{ marginBottom: 16 }}
              message="本地隐私模式已启用"
              description="远程模型调用已被禁用，仅支持论文检索、PDF 解析与本地证据检索。如需恢复对话能力，请在 backend/.env 中关闭 PRIVACY_LOCAL_ONLY 后重启后端。"
            />
          )}
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
              <Space direction="vertical" align="center">
                <Spin />
                <Typography.Text type="secondary">
                  正在加载后端状态…
                </Typography.Text>
              </Space>
            </div>
          ) : healthOk === false ? (
            <Empty
              description={
                <div>
                  <Typography.Text strong>无法连接后端服务</Typography.Text>
                  <div style={{ color: '#999', marginTop: 6 }}>
                    请确认后端服务已启动，默认地址 http://127.0.0.1:8000
                  </div>
                  <Button
                    type="primary"
                    style={{ marginTop: 16 }}
                    onClick={() => void refreshAll()}
                  >
                    重新连接
                  </Button>
                </div>
              }
            />
          ) : (
            <Outlet />
          )}
        </Content>
      </Layout>
      <Modal
        title="编辑研究项目"
        open={editingProject}
        confirmLoading={savingProject}
        okText="保存"
        cancelText="取消"
        onOk={() => void saveProject()}
        onCancel={() => setEditingProject(false)}
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <div>
            <Typography.Text strong>项目名称</Typography.Text>
            <Input
              value={projectName}
              maxLength={200}
              onChange={(event) => setProjectName(event.target.value)}
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Typography.Text strong>结构化项目档案</Typography.Text>
            <Input.TextArea
              value={projectProfile}
              onChange={(event) => setProjectProfile(event.target.value)}
              autoSize={{ minRows: 6, maxRows: 14 }}
              style={{ marginTop: 4, fontFamily: 'monospace' }}
            />
          </div>
        </Space>
      </Modal>
    </Layout>
  );
}
