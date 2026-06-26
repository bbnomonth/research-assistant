import { beforeEach, describe, expect, it } from 'vitest';
import { useAppStore } from './app';


describe('app store session migration', () => {
  beforeEach(() => {
    useAppStore.getState().reset();
  });

  it('moves pending turns to the backend session without duplication', () => {
    useAppStore.getState().appendTurn('local-1', {
      id: 'user-1',
      role: 'user',
      content: 'hello',
    });
    useAppStore.getState().appendTurn('local-1', {
      id: 'assistant-1',
      role: 'assistant',
      content: '',
      pending: true,
    });

    useAppStore.getState().moveTurns(
      'local-1',
      'session-1',
      'project-1',
    );

    const state = useAppStore.getState();
    expect(state.turnsBySession['local-1']).toBeUndefined();
    expect(state.turnsBySession['session-1']).toHaveLength(2);
    expect(state.turnsBySession['session-1'][0]).toMatchObject({
      projectId: 'project-1',
      sessionId: 'session-1',
    });
  });
});
