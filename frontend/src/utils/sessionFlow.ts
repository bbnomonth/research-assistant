interface ProjectRef {
  id: string;
}

export interface ChatTarget {
  projectId: string | null;
  sessionId: string | null;
}


export function resolveChatTarget(
  activeProjectId: string | null,
  activeSessionId: string | null,
  projects: ProjectRef[],
): ChatTarget {
  if (activeProjectId) {
    return {
      projectId: activeProjectId,
      sessionId: activeSessionId,
    };
  }
  return {
    projectId: projects[0]?.id ?? null,
    sessionId: null,
  };
}


export function resolveRenderSessionId(
  backendSessionId: string | null,
  localSessionId: string,
): string {
  return backendSessionId ?? localSessionId;
}


interface MessageLike {
  role: string;
  content: string;
}

interface TurnLike extends MessageLike {
  pending?: boolean;
}


export function removeLiveMessageDuplicates<T extends MessageLike>(
  messages: T[],
  turns: TurnLike[],
): T[] {
  const remaining = new Map<string, number>();
  for (const turn of turns) {
    if (turn.pending || !turn.content) continue;
    const key = `${turn.role}\u0000${turn.content}`;
    remaining.set(key, (remaining.get(key) ?? 0) + 1);
  }

  const kept: T[] = [];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    const key = `${message.role}\u0000${message.content}`;
    const count = remaining.get(key) ?? 0;
    if (count > 0) {
      remaining.set(key, count - 1);
      continue;
    }
    kept.push(message);
  }
  kept.reverse();
  return kept;
}
