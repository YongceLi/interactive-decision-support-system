export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  quick_replies?: string[] | null;
  suggested_followups?: string[];
}

export interface ChatRequest {
  message: string;
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  vehicles: Record<string, unknown>[];
  filters: Record<string, unknown>;
  preferences: Record<string, unknown>;
  session_id: string;
}
