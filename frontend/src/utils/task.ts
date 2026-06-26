import type { TaskRecord } from '@/types/api';


export function getTaskControls(status: TaskRecord['status']) {
  return {
    canCancel: status === 'pending' || status === 'processing',
    canRetry:
      status === 'failed' ||
      status === 'cancelled' ||
      status === 'interrupted',
  };
}
