import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Modal,
  Result,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  App as AntdApp,
} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { api } from '@/api/client';
import { useAppStore } from '@/store/app';
import type { DiagnosticResult, PrivacySettings } from '@/types/api';

const BACKEND_ENV = import.meta.env.VITE_BACKEND_URL ?? 'http://127.0.0.1:8000';
const DEFAULT_PRIVACY: PrivacySettings = {
  pii_scrub: false,
  local_only: false,
  data_ttl_days: 0,
};

const PRIVACY_HELP = [
  {
    title: '本地模式 (PRIVACY_LOCAL_ONLY)',
    description:
      '禁用远程模型调用；只使用论文检索、PDF 上传解析与本地证据检索等离线功能。',
  },
  {
    title: 'PII 脱敏 (PRIVACY_PII_SCRUB)',
    description:
      '在 PDF 文本提取与 OCR 之前自动替换明显的邮箱、手机号、身份证号等敏感信息。',
  },
  {
    title: '数据保留 (PRIVACY_DATA_TTL_DAYS)',
    description:
      '启动时自动清理超过 N 天的消息与会话；设为 0 表示永久保留。',
  },
];

export function SettingsPage() {
  const { message: toast, modal } = AntdApp.useApp();
  const { settings, setSettings } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [diagnostics, setDiagnostics] = useState<{
    storage?: DiagnosticResult;
    ocr?: DiagnosticResult;
    model?: DiagnosticResult;
  }>({});
  const [diagnosing, setDiagnosing] = useState(false);
  const [wiping, setWiping] = useState(false);
  const privacy = settings?.privacy ?? DEFAULT_PRIVACY;

  useEffect(() => {
    void loadSettings();
  }, []);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const res = await api.getRuntimeSettings();
      setSettings(res);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const runDiagnostics = async () => {
    setDiagnosing(true);
    setDiagnostics({});
    try {
      const [storage, ocr, model] = await Promise.allSettled([
        api.checkStorage(),
        api.checkOcr(),
        api.checkModel(),
      ]);
      setDiagnostics({
        storage: storage.status === 'fulfilled' ? storage.value : undefined,
        ocr: ocr.status === 'fulfilled' ? ocr.value : undefined,
        model: model.status === 'fulfilled' ? model.value : undefined,
      });
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setDiagnosing(false);
    }
  };

  const handleWipe = () => {
    modal.confirm({
      title: '清除全部本地数据？',
      icon: <DeleteOutlined />,
      okText: '确认清除',
      okButtonProps: { danger: true },
      cancelText: '取消',
      content: (
        <Space direction="vertical" size={4}>
          <Typography.Text>
            此次操作将永久删除所有上传的 PDF、对话消息、研究项目与论文缓存。
          </Typography.Text>
          <Typography.Text type="secondary">
            仅保留后端配置文件 (backend/.env)；下次启动会以全新状态运行。
          </Typography.Text>
        </Space>
      ),
      onOk: async () => {
        setWiping(true);
        try {
          const result = await api.wipeData();
          toast.success(
            `已清除 ${result.removed_uploads} 个文件、${result.removed_messages} 条消息、${result.removed_projects} 个项目。`,
          );
          void loadSettings();
        } catch (err) {
          toast.error((err as Error).message);
        } finally {
          setWiping(false);
        }
      },
    });
  };

  const copyEnvTemplate = () => {
    const template = `DASHSCOPE_API_KEY=replace-with-your-api-key
QWEN_BASE_URL=${settings?.qwen_base_url ?? 'https://dashscope.aliyuncs.com/compatible-mode/v1'}
QWEN_MODEL=${settings?.qwen_model ?? 'qwen3.7-plus'}

DATABASE_PATH=data/app.sqlite3
UPLOAD_DIR=data/uploads

TESSERACT_EXECUTABLE=
OCR_LANGUAGE=chi_sim+eng

PRIVACY_PII_SCRUB=0
PRIVACY_LOCAL_ONLY=0
PRIVACY_DATA_TTL_DAYS=0`;
    void navigator.clipboard.writeText(template).then(() => {
      toast.success('.env 模板已复制到剪贴板');
    });
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <Space direction="vertical" align="center">
          <Spin />
          <Typography.Text type="secondary">加载设置…</Typography.Text>
        </Space>
      </div>
    );
  }

  if (!settings) {
    return (
      <Result
        status="error"
        title="无法加载设置"
        subTitle="请确认后端服务已启动。"
      />
    );
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>当前运行配置</span>
          </Space>
        }
        extra={
          <Button icon={<ReloadOutlined />} onClick={loadSettings}>
            刷新
          </Button>
        }
      >
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="模型">
            <Tag color={settings.model_configured ? 'green' : 'red'}>
              {settings.model_configured
                ? `已配置（${settings.qwen_model}）`
                : '未配置'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="模型接口地址">
            <code>{settings.qwen_base_url}</code>
          </Descriptions.Item>
          <Descriptions.Item label="OCR">
            <Tag color={settings.ocr_configured ? 'green' : 'red'}>
              {settings.ocr_configured ? '已配置' : '未配置'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="OCR 语言">
            {settings.ocr_language}
          </Descriptions.Item>
          <Descriptions.Item label="PDF 大小限制">
            {(settings.pdf_max_bytes / 1024 / 1024).toFixed(1)} MB
          </Descriptions.Item>
          <Descriptions.Item label="PDF 页数限制">
            {settings.pdf_max_pages} 页
          </Descriptions.Item>
          <Descriptions.Item label="后端地址" span={2}>
            <code>{BACKEND_ENV}</code>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="配置诊断">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
            点击「运行诊断」可验证存储、OCR 和模型连通性。诊断接口不会回显模型输出、完整异常或本地 .env 内容。
          </Typography.Paragraph>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            loading={diagnosing}
            onClick={runDiagnostics}
          >
            运行诊断
          </Button>
          <DiagnosticRow label="存储目录" result={diagnostics.storage} />
          <DiagnosticRow label="OCR 服务" result={diagnostics.ocr} />
          <DiagnosticRow label="模型连通性" result={diagnostics.model} />
        </Space>
      </Card>

      <Card
        title={
          <Space>
            <SafetyCertificateOutlined />
            <span>隐私保护</span>
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
            以下开关来自 <code>backend/.env</code>，需要重启后端才能生效。
          </Typography.Paragraph>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="本地模式 (PRIVACY_LOCAL_ONLY)">
              <Tag color={privacy.local_only ? 'red' : 'green'}>
                {privacy.local_only ? '已启用 · 远程模型被禁用' : '未启用'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="PII 脱敏 (PRIVACY_PII_SCRUB)">
              <Tag color={privacy.pii_scrub ? 'green' : 'default'}>
                {privacy.pii_scrub ? '已启用 · 上传前自动清洗' : '未启用'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="数据保留天数 (PRIVACY_DATA_TTL_DAYS)">
              {privacy.data_ttl_days > 0
                ? `${privacy.data_ttl_days} 天后自动清理`
                : '永久保留'}
            </Descriptions.Item>
          </Descriptions>
          <Space wrap size={8}>
            {PRIVACY_HELP.map((item) => (
              <Card
                size="small"
                key={item.title}
                style={{ minWidth: 240, flex: 1, background: '#fafbff' }}
              >
                <Typography.Text strong>{item.title}</Typography.Text>
                <div style={{ color: '#666', fontSize: 12, marginTop: 4 }}>
                  {item.description}
                </div>
              </Card>
            ))}
          </Space>
          <Alert
            type="warning"
            showIcon
            message="清除全部本地数据"
            description="将删除所有上传 PDF、消息记录、对话会话和项目；仅保留 .env 中的 API Key 和配置。"
          />
          <Button
            danger
            icon={<DeleteOutlined />}
            loading={wiping}
            onClick={handleWipe}
          >
            立即清除全部本地数据
          </Button>
        </Space>
      </Card>

      <Card title="本地配置说明">
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="配置方法"
            description={
              <p style={{ margin: 0 }}>
                打开项目目录中的 <code>backend/.env</code> 文件，填入你的阿里云百炼 API Key。
                如果文件不存在，复制 <code>backend/.env.example</code> 作为模板。
              </p>
            }
          />
          <Button onClick={copyEnvTemplate}>复制 .env 配置模板</Button>
          <Descriptions column={1} size="small" bordered>
            <Descriptions.Item label="DASHSCOPE_API_KEY">
              阿里云百炼 API Key（必填）
            </Descriptions.Item>
            <Descriptions.Item label="QWEN_MODEL">
              模型名称，默认为 <code>qwen3.7-plus</code>
            </Descriptions.Item>
            <Descriptions.Item label="QWEN_BASE_URL">
              百炼接口地址，默认为{' '}
              <code>https://dashscope.aliyuncs.com/compatible-mode/v1</code>
            </Descriptions.Item>
            <Descriptions.Item label="TESSERACT_EXECUTABLE">
              Tesseract 可执行文件路径（可选，留空则不使用 OCR）
            </Descriptions.Item>
            <Descriptions.Item label="OCR_LANGUAGE">
              OCR 语言，默认为 <code>chi_sim+eng</code>
            </Descriptions.Item>
            <Descriptions.Item label="DATABASE_PATH">
              数据库文件路径（默认：<code>data/app.sqlite3</code>）
            </Descriptions.Item>
            <Descriptions.Item label="UPLOAD_DIR">
              上传文件目录（默认：<code>data/uploads</code>）
            </Descriptions.Item>
            <Descriptions.Item label="PRIVACY_PII_SCRUB">
              是否对 PDF/OCR 文本做 PII 脱敏（<code>1</code> 启用，<code>0</code> 关闭）
            </Descriptions.Item>
            <Descriptions.Item label="PRIVACY_LOCAL_ONLY">
              是否禁用远程模型（<code>1</code> 仅本地功能）
            </Descriptions.Item>
            <Descriptions.Item label="PRIVACY_DATA_TTL_DAYS">
              自动清理天数（默认 <code>0</code> 永久保留）
            </Descriptions.Item>
          </Descriptions>
          <Alert
            type="warning"
            showIcon
            message="安全提醒"
            description={
              <span>
                <code>backend/.env</code> 已加入 Git 忽略规则，请勿将真实 API Key
                提交到版本控制、聊天记录或截图。
              </span>
            }
          />
          <Alert
            type="info"
            showIcon
            message="重启服务"
            description="修改 .env 后需要重启后端服务使配置生效。"
          />
        </Space>
      </Card>

      <Card title="启动说明">
        <Space direction="vertical" size={8} style={{ width: '100%' }}>
          <Typography.Paragraph>
            <strong>启动后端</strong>（在项目根目录运行）：
          </Typography.Paragraph>
          <pre
            style={{
              background: '#f5f7fb',
              padding: 12,
              borderRadius: 6,
              fontSize: 12,
              overflow: 'auto',
            }}
          >
            {`& 'E:\\anaconda927\\envs\\py39232\\python.exe' -m uvicorn research_agent.main:app --app-dir backend/src --host 127.0.0.1 --port 8000 --reload`}
          </pre>
          <Typography.Paragraph>
            <strong>启动前端</strong>（在项目根目录运行）：
          </Typography.Paragraph>
          <pre
            style={{
              background: '#f5f7fb',
              padding: 12,
              borderRadius: 6,
              fontSize: 12,
              overflow: 'auto',
            }}
          >
            {`cd frontend\nnpm install\nnpm run dev`}
          </pre>
          <Typography.Paragraph type="secondary" style={{ margin: 0 }}>
            访问前端：<code>http://127.0.0.1:5173</code>
            &nbsp;&nbsp;API 文档：<code>http://127.0.0.1:8000/docs</code>
            &nbsp;&nbsp;Windows 一键启动：<code>dev-start.bat</code>
          </Typography.Paragraph>
        </Space>
      </Card>

      <Card title="快速统计">
        <Space size={32} wrap>
          <Statistic title="最大 PDF 大小" value={`${(settings.pdf_max_bytes / 1024 / 1024).toFixed(1)} MB`} />
          <Statistic title="最大解析页数" value={`${settings.pdf_max_pages} 页`} />
          <Statistic title="OCR 语言" value={settings.ocr_language} />
        </Space>
      </Card>
    </Space>
  );
}

function DiagnosticRow({ label, result }: { label: string; result?: DiagnosticResult }) {
  if (!result) {
    return (
      <Space>
        <Tag>·</Tag>
        <Typography.Text>{label}：未检测</Typography.Text>
      </Space>
    );
  }
  return (
    <Alert
      type={result.available ? 'success' : 'error'}
      showIcon
      icon={
        result.available ? (
          <CheckCircleOutlined />
        ) : (
          <CloseCircleOutlined />
        )
      }
      message={label}
      description={result.message}
    />
  );
}
