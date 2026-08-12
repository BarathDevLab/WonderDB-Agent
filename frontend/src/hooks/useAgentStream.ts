import { useState, useRef, useCallback, useEffect } from 'react';
import { ChatMessage, ChatSession } from '../types';

const STORAGE_KEY = 'ai_db_agent_sessions_v1';
const API_BASE_URL = (process.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');

function getInitialSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed;
      }
    }
  } catch (e) {
    console.error('Failed to load chat sessions from localStorage', e);
  }
  return [];
}

export function useAgentStream(initialTenantId: string) {
  const [sessions, setSessions] = useState<ChatSession[]>(getInitialSessions);
  const [activeSessionId, setActiveSessionId] = useState<string>(() => {
    const saved = getInitialSessions();
    return saved.length > 0 ? saved[0].id : '';
  });
  const [currentMessage, setCurrentMessage] = useState<ChatMessage | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const streamStartTimeRef = useRef<number>(0);

  // Save to localStorage whenever sessions change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    } catch (e) {
      console.error('Failed to save sessions to localStorage', e);
    }
  }, [sessions]);

  const activeSession = sessions.find((s) => s.id === activeSessionId) || null;
  const messages = activeSession ? activeSession.messages : [];

  const createNewSession = useCallback((tenantId: string = initialTenantId) => {
    const newSession: ChatSession = {
      id: `session-${Date.now()}`,
      title: 'New Database Query',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      tenant_id: tenantId,
      messages: [],
    };
    setSessions((prev) => [newSession, ...prev]);
    setActiveSessionId(newSession.id);
    setCurrentMessage(null);
    return newSession.id;
  }, [initialTenantId]);

  const switchSession = useCallback((sessionId: string) => {
    if (isStreaming) return;
    setActiveSessionId(sessionId);
    setCurrentMessage(null);
  }, [isStreaming]);

  const deleteSession = useCallback((sessionId: string) => {
    setSessions((prev) => {
      const updated = prev.filter((s) => s.id !== sessionId);
      if (activeSessionId === sessionId) {
        setActiveSessionId(updated.length > 0 ? updated[0].id : '');
      }
      return updated;
    });
  }, [activeSessionId]);

  const renameSession = useCallback((sessionId: string, newTitle: string) => {
    if (!newTitle.trim()) return;
    setSessions((prev) =>
      prev.map((s) => (s.id === sessionId ? { ...s, title: newTitle.trim(), updatedAt: Date.now() } : s))
    );
  }, []);

  const clearCurrentHistory = useCallback(() => {
    if (activeSessionId) {
      setSessions((prev) =>
        prev.map((s) => (s.id === activeSessionId ? { ...s, messages: [], updatedAt: Date.now() } : s))
      );
    }
    setCurrentMessage(null);
  }, [activeSessionId]);

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    if (currentMessage && activeSessionId) {
      const elapsed = Math.max(0.5, (Date.now() - streamStartTimeRef.current) / 1000);
      const finalized: ChatMessage = {
        ...currentMessage,
        isStreaming: false,
        thoughtDurationSec: Number(elapsed.toFixed(1)),
        statusMessage: 'Query stream stopped by user.',
      };
      setSessions((prev) =>
        prev.map((s) =>
          s.id === activeSessionId ? { ...s, messages: [...s.messages, finalized], updatedAt: Date.now() } : s
        )
      );
      setCurrentMessage(null);
    }
  }, [currentMessage, activeSessionId]);

  const sendPrompt = useCallback(
    async (prompt: string, tenantId: string) => {
      if (!prompt.trim() || isStreaming) return;

      let targetSessionId = activeSessionId;

      // If no active session, create one
      if (!targetSessionId || !sessions.some((s) => s.id === targetSessionId)) {
        const title = prompt.length > 40 ? prompt.slice(0, 40) + '...' : prompt;
        const newSession: ChatSession = {
          id: `session-${Date.now()}`,
          title,
          createdAt: Date.now(),
          updatedAt: Date.now(),
          tenant_id: tenantId,
          messages: [],
        };
        setSessions((prev) => [newSession, ...prev]);
        setActiveSessionId(newSession.id);
        targetSessionId = newSession.id;
      } else {
        // Auto-title if it's currently default and has no messages
        const currentSess = sessions.find((s) => s.id === targetSessionId);
        if (currentSess && currentSess.messages.length === 0 && currentSess.title === 'New Database Query') {
          const title = prompt.length > 40 ? prompt.slice(0, 40) + '...' : prompt;
          setSessions((prev) =>
            prev.map((s) => (s.id === targetSessionId ? { ...s, title } : s))
          );
        }
      }

      const userMsgId = `user-${Date.now()}`;
      const agentMsgId = `agent-${Date.now()}`;
      const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      streamStartTimeRef.current = Date.now();

      const userMsg: ChatMessage = {
        id: userMsgId,
        timestamp: nowStr,
        sender: 'user',
        prompt,
        tenant_id: tenantId,
      };

      // Append user message immediately
      setSessions((prev) =>
        prev.map((s) =>
          s.id === targetSessionId
            ? { ...s, messages: [...s.messages, userMsg], tenant_id: tenantId, updatedAt: Date.now() }
            : s
        )
      );

      let workingAgentMsg: ChatMessage = {
        id: agentMsgId,
        timestamp: nowStr,
        sender: 'agent',
        prompt,
        tenant_id: tenantId,
        phase: 'planning',
        statusMessage: 'Searching schema catalog via pgvector dense embeddings...',
        isStreaming: true,
      };

      setCurrentMessage(workingAgentMsg);
      setIsStreaming(true);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/agent/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Accept: 'text/event-stream',
          },
          body: JSON.stringify({
            prompt,
            tenant_id: tenantId,
            user_id: 'console-operator',
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
        }

        if (!response.body) {
          throw new Error('ReadableStream not supported on this response.');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || '';

          for (const block of parts) {
            if (!block.trim()) continue;

            const lines = block.split('\n');
            let eventType = '';
            let rawData = '';

            for (const line of lines) {
              if (line.startsWith('event:')) {
                eventType = line.replace('event:', '').trim();
              } else if (line.startsWith('data:')) {
                rawData = line.replace('data:', '').trim();
              }
            }

            if (!eventType || !rawData) continue;

            let data: any;
            try {
              data = JSON.parse(rawData);
            } catch {
              data = rawData;
            }

            switch (eventType) {
              case 'status':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  phase: (data.phase || 'planning') as any,
                  statusMessage: data.message || '',
                };
                setCurrentMessage({ ...workingAgentMsg });
                break;

              case 'plan_ready':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  strategy: data.strategy || '',
                  sqlQuery: data.sql || '',
                  phase: 'executing',
                };
                setCurrentMessage({ ...workingAgentMsg });
                break;

              case 'execution_complete':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  rawResults: data.data || [],
                  explainCost: data.cost ?? 0,
                  phase: 'summarizing',
                };
                setCurrentMessage({ ...workingAgentMsg });
                break;

              case 'reflection_retry':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  phase: 'reflecting',
                  retryCount: data.retry ?? (workingAgentMsg.retryCount || 0) + 1,
                  statusMessage: `Self-Correction Triggered: ${data.error}. Re-prompting with AST diagnostics...`,
                };
                setCurrentMessage({ ...workingAgentMsg });
                break;

              case 'final_response':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  summary: data.summary || '',
                  chartSpec: data.chart_spec,
                  chartSpecs: data.chart_specs || (data.chart_spec ? [data.chart_spec] : []),
                  diagramSpec: data.diagram_spec,
                  toolCalls: data.tool_calls,
                };
                setCurrentMessage({ ...workingAgentMsg });
                break;

              case 'error':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  phase: 'error',
                  errorMessage: data.message || 'Execution error encountered.',
                };
                setCurrentMessage({ ...workingAgentMsg });
                break;

              case 'complete':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  phase: 'complete',
                  isStreaming: false,
                };
                break;
            }
          }
        }
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          workingAgentMsg = {
            ...workingAgentMsg,
            phase: 'error',
            errorMessage: err.message || 'Stream connection failed.',
            isStreaming: false,
          };
        }
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
        const elapsed = Math.max(0.5, (Date.now() - streamStartTimeRef.current) / 1000);
        const finalized: ChatMessage = {
          ...workingAgentMsg,
          isStreaming: false,
          thoughtDurationSec: Number(elapsed.toFixed(1)),
        };
        setCurrentMessage(null);
        setSessions((prev) =>
          prev.map((s) =>
            s.id === targetSessionId
              ? { ...s, messages: [...s.messages, finalized], updatedAt: Date.now() }
              : s
          )
        );
      }
    },
    [activeSessionId, isStreaming, sessions]
  );

  return {
    sessions,
    activeSessionId,
    activeSession,
    messages,
    currentMessage,
    isStreaming,
    sendPrompt,
    cancelStream,
    createNewSession,
    switchSession,
    deleteSession,
    renameSession,
    clearCurrentHistory,
  };
}
