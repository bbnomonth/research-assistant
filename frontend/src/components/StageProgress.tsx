import { useEffect, useRef } from 'react';
import { Tag, Typography } from 'antd';

export interface StreamingStages {
  queryGeneration?: string;
  paperSearch?: string;
  recommendation?: string;
  persistence?: string;
  evidenceCollection?: string;
  readingGuidance?: string;
}

export function StageProgress({ stages }: { stages: StreamingStages }) {
  const items: { key: keyof StreamingStages; label: string }[] = [
    { key: 'queryGeneration', label: '生成检索式' },
    { key: 'paperSearch', label: '检索论文库' },
    { key: 'recommendation', label: '生成推荐卡片' },
    { key: 'persistence', label: '保存到研究项目' },
    { key: 'evidenceCollection', label: '收集项目文献证据' },
    { key: 'readingGuidance', label: '生成阅读反馈' },
  ];

  const seen = items.some((i) => stages[i.key]);
  if (!seen) return null;

  return (
    <div
      style={{
        background: '#fafbff',
        border: '1px dashed #adc6ff',
        padding: 12,
        borderRadius: 6,
        marginTop: 8,
      }}
    >
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        工作阶段
      </Typography.Text>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
        {items
          .filter((i) => stages[i.key])
          .map((i) => (
            <Tag color="processing" key={i.key}>
              {stages[i.key]} · {i.label}
            </Tag>
          ))}
      </div>
    </div>
  );
}

export function useAutoScroll<T extends HTMLElement>(deps: unknown[]) {
  const ref = useRef<T | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, deps);
  return ref;
}
