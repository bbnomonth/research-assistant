import ReactMarkdown from 'react-markdown';
import rehypeKatex from 'rehype-katex';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import type { Components } from 'react-markdown';
import { Typography } from 'antd';
import { useMemo } from 'react';
import 'katex/dist/katex.min.css';

export interface MarkdownRendererProps {
  content: string;
  compact?: boolean;
}

const baseComponents: Components = {
  h1: ({ children }) => (
    <Typography.Title level={2} style={{ marginTop: 16, marginBottom: 12 }}>
      {children}
    </Typography.Title>
  ),
  h2: ({ children }) => (
    <Typography.Title level={3} style={{ marginTop: 14, marginBottom: 10 }}>
      {children}
    </Typography.Title>
  ),
  h3: ({ children }) => (
    <Typography.Title level={4} style={{ marginTop: 12, marginBottom: 8 }}>
      {children}
    </Typography.Title>
  ),
  h4: ({ children }) => (
    <Typography.Title level={5} style={{ marginTop: 10, marginBottom: 6 }}>
      {children}
    </Typography.Title>
  ),
  p: ({ children }) => (
    <Typography.Paragraph style={{ marginBottom: 10, lineHeight: 1.75 }}>
      {children}
    </Typography.Paragraph>
  ),
  ul: ({ children }) => (
    <ul style={{ paddingLeft: 22, marginBottom: 10 }}>{children}</ul>
  ),
  ol: ({ children }) => (
    <ol style={{ paddingLeft: 22, marginBottom: 10 }}>{children}</ol>
  ),
  li: ({ children }) => (
    <li style={{ marginBottom: 4, lineHeight: 1.7 }}>{children}</li>
  ),
  a: ({ href, children }) => (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: '#2f54eb' }}>
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote
      style={{
        margin: '8px 0',
        padding: '6px 12px',
        borderLeft: '3px solid #91caff',
        background: '#f0f5ff',
        color: '#444',
      }}
    >
      {children}
    </blockquote>
  ),
  code: ({ className, children, ...rest }) => {
    const isInline = !(rest as { node?: { position?: unknown } }).node;
    if (isInline) {
      return (
        <code
          style={{
            background: '#f5f7fb',
            padding: '1px 6px',
            borderRadius: 4,
            fontFamily: 'JetBrains Mono, Consolas, monospace',
            fontSize: '0.9em',
          }}
        >
          {children}
        </code>
      );
    }
    return (
      <code
        className={className}
        style={{
          fontFamily: 'JetBrains Mono, Consolas, monospace',
          fontSize: 13,
        }}
      >
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre
      style={{
        background: '#f5f7fb',
        padding: 12,
        borderRadius: 6,
        overflowX: 'auto',
        fontSize: 13,
        lineHeight: 1.6,
        margin: '8px 0',
      }}
    >
      {children}
    </pre>
  ),
  hr: () => <hr style={{ border: 0, borderTop: '1px solid #e6ebf5', margin: '16px 0' }} />,
  table: ({ children }) => (
    <div style={{ overflowX: 'auto', marginBottom: 12 }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: 14,
        }}
      >
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead style={{ background: '#fafbff' }}>{children}</thead>
  ),
  th: ({ children }) => (
    <th
      style={{
        padding: '8px 12px',
        borderBottom: '1px solid #e6ebf5',
        textAlign: 'left',
        fontWeight: 600,
      }}
    >
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td
      style={{
        padding: '8px 12px',
        borderBottom: '1px solid #f0f2f5',
        verticalAlign: 'top',
      }}
    >
      {children}
    </td>
  ),
  strong: ({ children }) => <strong style={{ fontWeight: 600 }}>{children}</strong>,
  em: ({ children }) => <em style={{ fontStyle: 'italic', color: '#444' }}>{children}</em>,
};

const compactComponents: Components = {
  ...baseComponents,
  p: ({ children }) => (
    <Typography.Paragraph style={{ marginBottom: 8, lineHeight: 1.7 }}>
      {children}
    </Typography.Paragraph>
  ),
  h1: ({ children }) => (
    <Typography.Title level={4} style={{ marginTop: 10, marginBottom: 6 }}>
      {children}
    </Typography.Title>
  ),
  h2: ({ children }) => (
    <Typography.Title level={5} style={{ marginTop: 8, marginBottom: 4 }}>
      {children}
    </Typography.Title>
  ),
  h3: ({ children }) => (
    <Typography.Text strong style={{ display: 'block', marginTop: 8 }}>
      {children}
    </Typography.Text>
  ),
};

function normalizeMathExpression(expression: string): string {
  return expression
    .trim()
    .replace(/^([_^])/, '{}$1')
    .replace(/(?<!\\)\\[ \t]*\n/g, '\n');
}

function normalizeDollarMath(input: string): string {
  let output = '';
  let index = 0;

  while (index < input.length) {
    const start = input.indexOf('$', index);
    if (start === -1) {
      output += input.slice(index);
      break;
    }

    output += input.slice(index, start);

    if (input[start + 1] === '$') {
      const end = input.indexOf('$$', start + 2);
      if (end === -1) {
        output += input.slice(start);
        break;
      }
      const expression = normalizeMathExpression(input.slice(start + 2, end));
      output += `\n\n$$\n${expression}\n$$\n\n`;
      index = end + 2;
      continue;
    }

    const end = input.indexOf('$', start + 1);
    const expression = input.slice(start + 1, end === -1 ? input.length : end);
    const likelyMath = /\\[A-Za-z]+|[_^{}=]/.test(expression);
    const shouldPromoteToBlock =
      likelyMath && (expression.includes('\n') || expression.length > 120);

    if (end === -1) {
      output += likelyMath
        ? `\n\n$$\n${normalizeMathExpression(expression)}\n$$\n\n`
        : input.slice(start);
      break;
    }

    if (shouldPromoteToBlock) {
      output += `\n\n$$\n${normalizeMathExpression(expression)}\n$$\n\n`;
    } else {
      output += `$${normalizeMathExpression(expression)}$`;
    }
    index = end + 1;
  }

  return output;
}

function normalizeMathMarkdown(input: string): string {
  const normalizedDelimiters = input
    .replace(/\\\[([\s\S]*?)\\\]/g, (_, expression: string) => {
      return `\n\n$$\n${normalizeMathExpression(expression)}\n$$\n\n`;
    })
    .replace(/\\\(([\s\S]*?)\\\)/g, (_, expression: string) => {
      return `$${normalizeMathExpression(expression)}$`;
    })
    .replace(
      /(?<!\$)([A-Za-z][A-Za-z0-9_{}\\()[\].,\s+\-*/=<>|^]*\\[A-Za-z]+[A-Za-z0-9_{}\\()[\].,\s+\-*/=<>|^]*)\$/g,
      (_, expression: string) => `$${normalizeMathExpression(expression)}$`,
    );
  return normalizeDollarMath(normalizedDelimiters);
}

export function MarkdownRenderer({ content, compact = false }: MarkdownRendererProps) {
  const safeContent = useMemo(() => normalizeMathMarkdown(content || ''), [content]);
  const components = compact ? compactComponents : baseComponents;

  return (
    <div
      className="markdown-body"
      style={{
        fontSize: compact ? 14 : 15,
        lineHeight: 1.7,
        color: '#222',
        wordBreak: 'break-word',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={components}
      >
        {safeContent}
      </ReactMarkdown>
    </div>
  );
}
