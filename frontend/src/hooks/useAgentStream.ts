import { useState, useRef, useCallback } from 'react';
import { ChatMessage } from '../types';

export function useAgentStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentMessage, setCurrentMessage] = useState<ChatMessage | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const clearHistory = useCallback(() => {
    setMessages([]);
    setCurrentMessage(null);
  }, []);

  const cancelStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsStreaming(false);
    if (currentMessage) {
      setMessages((prev) => [
        ...prev,
        { ...currentMessage, isStreaming: false, statusMessage: 'Query stream cancelled by user.' },
      ]);
      setCurrentMessage(null);
    }
  }, [currentMessage]);

  const sendPrompt = useCallback(
    async (prompt: string, tenantId: string) => {
      if (!prompt.trim() || isStreaming) return;

      const userMsgId = `user-${Date.now()}`;
      const agentMsgId = `agent-${Date.now()}`;
      const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

      const userMsg: ChatMessage = {
        id: userMsgId,
        timestamp: nowStr,
        sender: 'user',
        prompt,
        tenant_id: tenantId,
      };

      setMessages((prev) => [...prev, userMsg]);

      let workingAgentMsg: ChatMessage = {
        id: agentMsgId,
        timestamp: nowStr,
        sender: 'agent',
        prompt,
        tenant_id: tenantId,
        phase: 'planning',
        statusMessage: 'Analyzing natural language prompt and retrieving schema catalog via pgvector...',
        isStreaming: true,
      };

      setCurrentMessage(workingAgentMsg);
      setIsStreaming(true);

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const response = await fetch('/api/v1/agent/stream', {
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
                  statusMessage: `Self-Correction Triggered: ${data.error}. Re-prompting LLM with AST diagnostics...`,
                };
                setCurrentMessage({ ...workingAgentMsg });
                break;

              case 'final_response':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  summary: data.summary || '',
                  chartSpec: data.chart_spec,
                };
                setCurrentMessage({ ...workingAgentMsg });
                break;

              case 'error':
                workingAgentMsg = {
                  ...workingAgentMsg,
                  phase: 'error',
                  errorMessage: data.message || 'Unknown execution error.',
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
        const finalized = { ...workingAgentMsg, isStreaming: false };
        setCurrentMessage(null);
        setMessages((prev) => [...prev, finalized]);
      }
    },
    [isStreaming]
  );

  return {
    messages,
    currentMessage,
    isStreaming,
    sendPrompt,
    cancelStream,
    clearHistory,
  };
}
