export interface ColumnMetadata {
  name: string;
  type: string;
  is_pk?: boolean;
  is_pii?: boolean;
  foreign_table?: string;
  foreign_column?: string;
}

export interface TableMetadata {
  table_name: string;
  columns: ColumnMetadata[];
  description: string;
  foreign_keys?: {
    column: string;
    foreign_table: string;
    foreign_column: string;
  }[];
}

export interface ChartSpec {
  type: 'line' | 'bar' | 'pie' | 'doughnut' | 'scatter' | 'table';
  data?: {
    labels: string[];
    datasets: {
      label: string;
      data: (number | null)[] | { x: number; y: number }[];
      backgroundColor?: string | string[];
      borderColor?: string | string[];
      borderWidth?: number;
      fill?: boolean;
    }[];
  };
  options?: any;
}

export interface DiagramSpec {
  mermaid?: string;
  diagram_type?: 'er' | 'process' | 'decision';
  process_mode?: 'state_transitions' | 'ordered_steps' | 'agent_pipeline' | 'not_applicable';
  decision_mode?: 'rule_hierarchy' | 'learned_classification' | 'not_applicable';
  decision_target?: string | null;
}

export interface ToolCall {
  tool: string;
  status: string;
  duration_ms?: number;
  attempts?: number;
}

export interface ChatMessage {
  id: string;
  timestamp: string;
  sender: 'user' | 'agent';
  prompt: string;
  tenant_id: string;
  phase?: 'planning' | 'executing' | 'reflecting' | 'summarizing' | 'complete' | 'error';
  statusMessage?: string;
  sqlQuery?: string;
  strategy?: string;
  explainCost?: number;
  rawResults?: Record<string, any>[];
  summary?: string;
  chartSpec?: ChartSpec;
  chartSpecs?: ChartSpec[];
  diagramSpec?: DiagramSpec[];
  toolCalls?: ToolCall[];
  errorMessage?: string;
  retryCount?: number;
  isStreaming?: boolean;
  cachedHit?: boolean;
  thoughtDurationSec?: number;
}

export interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  tenant_id: string;
  messages: ChatMessage[];
}

export interface Tenant {
  id: string;
  name: string;
  tier: string;
  recordCount: number;
  color?: string;
}
