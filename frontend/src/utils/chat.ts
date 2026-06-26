import type { ChatMode, StreamEvent } from '@/types/api';
import { CHAT_MODE_LABEL, CHAT_MODE_COLOR } from '@/types/api';

export function describeMode(mode: ChatMode | string | undefined): {
  label: string;
  color: string;
} {
  const key = (mode ?? 'general_qa') as ChatMode;
  return {
    label: CHAT_MODE_LABEL[key] ?? key,
    color: CHAT_MODE_COLOR[key] ?? 'default',
  };
}

export function isChatMode(value: unknown): value is ChatMode {
  return (
    typeof value === 'string' &&
    ['other', 'literature_discovery', 'paper_reading', 'topic_guidance', 'framework_building'].includes(
      value,
    )
  );
}

export type ChatEvent = StreamEvent;
