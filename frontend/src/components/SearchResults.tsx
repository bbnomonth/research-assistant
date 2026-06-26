import {
  BulbOutlined,
  DownloadOutlined,
  ExperimentOutlined,
  FileSearchOutlined,
  LinkOutlined,
  RocketOutlined,
  StarOutlined,
  StarFilled,
} from '@ant-design/icons';
import { App as AntdApp, Button, Empty, Space, Tag, Tooltip, Typography } from 'antd';
import type { ReactNode } from 'react';
import { useState } from 'react';
import { api } from '@/api/client';

export interface SearchResultsProps {
  data: unknown;
  activeProjectId?: string | null;
}

interface PaperLike {
  title?: unknown;
  authors?: unknown[];
  categories?: unknown[];
  abstract?: unknown;
  entry_url?: unknown;
  pdf_url?: unknown;
  arxiv_id?: unknown;
  reason?: unknown;
  purpose_labels?: unknown[];
}

function getStr(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

function getArr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : [];
}

export function SearchResults({ data, activeProjectId }: SearchResultsProps) {
  const payload = data as { query?: unknown; candidates?: unknown[]; recommendations?: unknown[] };
  const candidates = getArr(payload.candidates);
  const recommendations = getArr(payload.recommendations);

  if (!candidates.length) {
    return (
      <Empty
        description="本次未检索到匹配的候选文献。"
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  const recommendedIds = new Set(
    recommendations.map((r) => {
      const rec = r as { paper?: PaperLike };
      return rec.paper?.arxiv_id;
    }),
  );

  return (
    <div>
      <Typography.Paragraph style={{ marginBottom: 8 }}>
        <Space size={6} wrap>
          <Tag color="purple">检索式</Tag>
          <code>{getStr(payload.query)}</code>
          <Tag icon={<FileSearchOutlined />} color="blue">
            候选 {candidates.length} 篇
          </Tag>
          <Tag icon={<RocketOutlined />} color="green">
            推荐 {recommendations.length} 篇
          </Tag>
        </Space>
      </Typography.Paragraph>
      <Typography.Title level={5} style={{ marginTop: 12 }}>
        <BulbOutlined /> 为你推荐的文献
      </Typography.Title>
      <Space direction="vertical" size={8} style={{ width: '100%' }}>
        {recommendations.map((r: unknown, idx: number) => {
          const rec = r as { paper?: PaperLike; reason?: unknown; purpose_labels?: unknown[] };
          const paper = rec.paper ?? {};
          return (
            <PaperCard
              key={idx}
              title={getStr(paper.title)}
              authors={getArr(paper.authors).join(', ')}
              categories={getArr(paper.categories).join(', ')}
              abstract={getStr(paper.abstract)}
              entryUrl={getStr(paper.entry_url)}
              pdfUrl={getStr(paper.pdf_url)}
              arxivId={getStr(paper.arxiv_id)}
              reason={getStr(rec.reason)}
              purposeLabels={getArr(rec.purpose_labels).map(getStr)}
              activeProjectId={activeProjectId}
            />
          );
        })}
      </Space>
      <Typography.Title level={5} style={{ marginTop: 16 }}>
        <ExperimentOutlined /> 其他候选
      </Typography.Title>
      <Space direction="vertical" size={6} style={{ width: '100%' }}>
        {candidates
          .filter((c: unknown) => {
            const paper = c as PaperLike;
            return !recommendedIds.has(paper.arxiv_id);
          })
          .map((c: unknown, idx: number) => {
            const paper = c as PaperLike;
            return (
              <PaperCard
                key={idx}
                title={getStr(paper.title)}
                authors={getArr(paper.authors).join(', ')}
                categories={getArr(paper.categories).join(', ')}
                abstract={getStr(paper.abstract)}
                entryUrl={getStr(paper.entry_url)}
                pdfUrl={getStr(paper.pdf_url)}
                arxivId={getStr(paper.arxiv_id)}
                activeProjectId={activeProjectId}
              />
            );
          })}
      </Space>
    </div>
  );
}

function PaperCard(props: {
  title: string;
  authors: string;
  categories: string;
  abstract: string;
  entryUrl: string;
  pdfUrl: string;
  arxivId: string;
  reason?: string;
  purposeLabels?: string[];
  activeProjectId?: string | null;
}): ReactNode {
  const { message } = AntdApp.useApp();
  const [favorited, setFavorited] = useState(false);
  const [favoriting, setFavoriting] = useState(false);

  const handleFavorite = async () => {
    if (!props.arxivId || !props.activeProjectId) {
      message.warning('请先选择研究项目');
      return;
    }
    setFavoriting(true);
    try {
      const next = !favorited;
      const res = await api.favoritePaper({
        project_id: props.activeProjectId,
        arxiv_id: props.arxivId,
        favorited: next,
      });
      if (!res.ok) {
        message.error(res.message || '收藏失败');
        return;
      }
      setFavorited(next);
      message.success(next ? '已加入论文库' : '已取消收藏');
    } catch (err) {
      message.error((err as Error).message);
    } finally {
      setFavoriting(false);
    }
  };

  return (
    <div
      style={{
        border: '1px solid #e6ebf5',
        borderRadius: 6,
        padding: 12,
        background: '#fff',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ flex: 1 }}>
          <Typography.Text strong>{props.title || '（无标题）'}</Typography.Text>
        </div>
        <Tooltip title={favorited ? '取消收藏' : '收藏后加入论文库'}>
          <Button
            type="text"
            size="small"
            icon={favorited ? <StarFilled style={{ color: '#faad14' }} /> : <StarOutlined />}
            loading={favoriting}
            onClick={handleFavorite}
            style={{ flexShrink: 0 }}
          />
        </Tooltip>
      </div>
      <div style={{ color: '#666', fontSize: 12, marginTop: 2 }}>
        {props.authors || '未知作者'}
        {props.categories ? ` · ${props.categories}` : ''}
      </div>
      {props.purposeLabels && props.purposeLabels.length > 0 && (
        <div style={{ marginTop: 6 }}>
          {props.purposeLabels.map((label: string) => (
            <Tag color="geekblue" key={label}>
              {label}
            </Tag>
          ))}
        </div>
      )}
      {props.reason && (
        <Typography.Paragraph style={{ marginTop: 8, marginBottom: 0 }}>
          {props.reason}
        </Typography.Paragraph>
      )}
      <Typography.Paragraph
        type="secondary"
        style={{ marginTop: 8, marginBottom: 6, fontSize: 12 }}
        ellipsis={{ rows: 3, expandable: true, symbol: '展开' }}
      >
        {props.abstract}
      </Typography.Paragraph>
      <Space size={6}>
        {props.entryUrl && (
          <Button
            size="small"
            icon={<LinkOutlined />}
            href={props.entryUrl}
            target="_blank"
            rel="noreferrer"
          >
            论文链接
          </Button>
        )}
        {props.pdfUrl && (
          <Button
            size="small"
            icon={<DownloadOutlined />}
            href={props.pdfUrl}
            target="_blank"
            rel="noreferrer"
          >
            PDF 下载
          </Button>
        )}
      </Space>
    </div>
  );
}
