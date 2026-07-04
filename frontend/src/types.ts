export interface CardInfo {
  card_id: string;
  title: string;
  summary: string;
  tags: string[];
  category: string;
  source_id: string;
  source_path: string;
  content: string;
  evidence: Record<string, unknown>[];
  created_at: string;
}

export interface WikiPageInfo {
  filename: string;
  content: string;
}

export interface KnowledgeGraphNode {
  id: string;
  label: string;
  type: string;
  data: Record<string, unknown>;
}

export interface KnowledgeGraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label: string;
  weight: number;
  data: Record<string, unknown>;
}

export interface KnowledgeGraphCommunity {
  id: string;
  label: string;
  card_ids: string[];
  card_titles: string[];
  size: number;
  span_count: number;
  tags: string[];
}

export interface KnowledgeGraphInfo {
  nodes: KnowledgeGraphNode[];
  edges: KnowledgeGraphEdge[];
  communities: KnowledgeGraphCommunity[];
  stats: Record<string, number>;
}

export interface WikiProposalInfo {
  proposal_id: string;
  proposal_type: string;
  title: string;
  rationale: string;
  proposed_content: string;
  target_card_id: string;
  status: string;
  created_at: string;
}

export interface UploadResponse {
  card: CardInfo;
  message: string;
}

export interface BatchUploadResponse {
  cards: CardInfo[];
  message: string;
}

export interface EvidenceResult {
  title: string;
  score: number;
  locator: string;
  source: string;
  snippet: string;
}

export interface AskResponse {
  answer: string;
  claims: Record<string, unknown>[];
  graph_mermaid: string;
  evidence: EvidenceResult[];
}

export interface QASessionInfo {
  session_id: string;
  question: string;
  answer: string;
  evidence: Record<string, unknown>[];
  graph_mermaid: string;
  created_at: string;
}

export interface ModelSettings {
  apiKey: string;
  baseUrl: string;
  textModel: string;
  visionModel: string;
  embeddingModel: string;
}

export interface HealthReviewResponse {
  report_markdown: string;
  issues: Array<{
    title: string;
    severity: string;
    issue_type: string;
    reason: string;
    suggestion: string;
  }>;
  completion_actions: Array<{
    issue_title: string;
    action_type: string;
    query_or_request: string;
    rationale: string;
  }>;
}

export interface StagingItemInfo {
  staging_id: string;
  title: string;
  url: string;
  summary: string;
  content: string;
  status: string;
  created_at: string;
}

export interface SystemLogInfo {
  log_id: string;
  action_type: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface PreferenceCandidate {
  candidate_id: string;
  field: string;
  old_value: string;
  new_value: string;
  evidence: string;
  confidence: number;
  status: string;
  created_at: string;
}

export interface UserProfile {
  language: string;
  answer_style: string;
  technical_level: string;
  length_preference: string;
  preferred_outputs: string[];
  domain_focus: string[];
  avoid: string[];
  citation_required: boolean;
  learned_preferences: Array<Record<string, unknown>>;
}
