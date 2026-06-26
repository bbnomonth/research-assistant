import { describe, expect, it } from 'vitest';
import { getTaskControls } from './task';


describe('task controls', () => {
  it('allows cancelling active tasks', () => {
    expect(getTaskControls('pending')).toEqual({
      canCancel: true,
      canRetry: false,
    });
    expect(getTaskControls('processing')).toEqual({
      canCancel: true,
      canRetry: false,
    });
  });

  it('allows retrying terminal recoverable tasks', () => {
    for (const status of ['failed', 'cancelled', 'interrupted'] as const) {
      expect(getTaskControls(status)).toEqual({
        canCancel: false,
        canRetry: true,
      });
    }
  });
});
