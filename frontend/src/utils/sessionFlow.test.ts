import { describe, expect, it } from 'vitest';
import {
  removeLiveMessageDuplicates,
  resolveChatTarget,
  resolveRenderSessionId,
} from './sessionFlow';


describe('chat session flow', () => {
  it('allows the backend to create the first project and session', () => {
    expect(resolveChatTarget(null, null, [])).toEqual({
      projectId: null,
      sessionId: null,
    });
  });

  it('creates a new session without sending the local render id', () => {
    expect(
      resolveChatTarget(
        'project-1',
        null,
        [{ id: 'project-1' }],
      ),
    ).toEqual({
      projectId: 'project-1',
      sessionId: null,
    });
  });

  it('keeps a local render key until backend metadata arrives', () => {
    expect(resolveRenderSessionId(null, 'local-1')).toBe('local-1');
    expect(resolveRenderSessionId('session-1', 'local-1')).toBe('session-1');
  });

  it('removes only persisted copies of completed live turns', () => {
    const messages = [
      { role: 'user', content: 'same' },
      { role: 'assistant', content: 'old answer' },
      { role: 'user', content: 'same' },
      { role: 'assistant', content: 'new answer' },
    ];
    const turns = [
      { role: 'user', content: 'same' },
      { role: 'assistant', content: 'new answer', pending: false },
    ];

    expect(removeLiveMessageDuplicates(messages, turns)).toEqual([
      { role: 'user', content: 'same' },
      { role: 'assistant', content: 'old answer' },
    ]);
  });
});
