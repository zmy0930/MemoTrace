import type {
  AskResponse,
  BatchUploadResponse,
  CardInfo,
  HealthReviewResponse,
  KnowledgeGraphInfo,
  ModelSettings,
  PreferenceCandidate,
  QASessionInfo,
  StagingItemInfo,
  SystemLogInfo,
  UploadResponse,
  UserProfile,
  WikiPageInfo,
  WikiProposalInfo
} from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function healthCheck() {
  return request<{ status: string }>("/health");
}

export async function uploadDocument(file: File, settings?: ModelSettings) {
  const form = new FormData();
  form.append("file", file);
  return request<UploadResponse>("/api/documents/upload", {
    method: "POST",
    headers: modelHeaders(settings),
    body: form
  });
}

export async function uploadDocuments(files: File[], settings?: ModelSettings) {
  const form = new FormData();
  files.forEach((file) => form.append("files", file));
  return request<BatchUploadResponse>("/api/documents/upload/batch", {
    method: "POST",
    headers: modelHeaders(settings),
    body: form
  });
}

export async function listCards() {
  return request<CardInfo[]>("/api/wiki/cards");
}

export async function getWikiIndex() {
  return request<WikiPageInfo>("/api/wiki/index");
}

export async function getWikiLog() {
  return request<WikiPageInfo>("/api/wiki/log");
}

export async function getKnowledgeGraph() {
  return request<KnowledgeGraphInfo>("/api/wiki/graph");
}

export async function listWikiProposals() {
  return request<WikiProposalInfo[]>("/api/wiki/proposals");
}

export async function acceptWikiProposal(proposalId: string, settings?: ModelSettings) {
  return request<{ status: string }>(`/api/wiki/proposals/${proposalId}/accept`, {
    method: "POST",
    headers: modelHeaders(settings)
  });
}

export async function rejectWikiProposal(proposalId: string) {
  return request<{ status: string }>(`/api/wiki/proposals/${proposalId}/reject`, { method: "POST" });
}

export async function deleteCard(cardId: string) {
  return request<{ status: string }>(`/api/wiki/cards/${cardId}`, { method: "DELETE" });
}

export async function askQuestion(question: string, topK = 5, settings?: ModelSettings) {
  try {
    return await request<AskResponse>("/api/qa/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...modelHeaders(settings) },
      body: JSON.stringify({ question, top_k: topK })
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "提问失败";
    return {
      answer: `提问失败：${message}\n\n请确认 FastAPI 后端已启动，并检查模型配置里的 API Key、Base URL 和模型名称。`,
      claims: [],
      graph_mermaid: "",
      evidence: []
    };
  }
}

export async function listQASessions() {
  return request<QASessionInfo[]>("/api/qa/sessions");
}

export async function reviewHealth(settings?: ModelSettings) {
  return request<HealthReviewResponse>("/api/health/review", {
    headers: modelHeaders(settings)
  });
}

export async function runWebCompletion(query: string, limit = 3) {
  return request<StagingItemInfo[]>("/api/completion/web", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, limit })
  });
}

export async function listStaging() {
  return request<StagingItemInfo[]>("/api/completion/staging");
}

export async function mergeStaging(stagingId: string) {
  return request<CardInfo>(`/api/completion/staging/${stagingId}/merge`, { method: "POST" });
}

export async function listSystemLogs() {
  return request<SystemLogInfo[]>("/api/logs/system");
}

export async function getProfile() {
  return request<UserProfile>("/api/preferences/profile");
}

export async function saveFeedback(payload: {
  question: string;
  answer_summary: string;
  answer_type: string;
  user_feedback: string;
  user_action: string;
  accepted: boolean;
}) {
  return request<{ status: string }>("/api/preferences/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export async function distillPreferences() {
  return request<PreferenceCandidate[]>("/api/preferences/distill", { method: "POST" });
}

export async function listCandidates() {
  return request<PreferenceCandidate[]>("/api/preferences/candidates");
}

export async function acceptCandidate(candidateId: string) {
  return request<{ status: string }>(`/api/preferences/candidates/${candidateId}/accept`, { method: "POST" });
}

export async function rejectCandidate(candidateId: string) {
  return request<{ status: string }>(`/api/preferences/candidates/${candidateId}/reject`, { method: "POST" });
}

export async function generateContent(kind: "note" | "report" | "ppt" | "mindmap") {
  return request<{ kind: string; content: string }>(`/api/generate/${kind}`);
}

function modelHeaders(settings?: ModelSettings): Record<string, string> {
  if (!settings) return {};
  const headers: Record<string, string> = {};
  if (settings.apiKey.trim()) headers["X-LLM-Api-Key"] = settings.apiKey.trim();
  if (settings.baseUrl.trim()) headers["X-LLM-Base-Url"] = settings.baseUrl.trim();
  if (settings.textModel.trim()) headers["X-LLM-Text-Model"] = settings.textModel.trim();
  if (settings.visionModel.trim()) headers["X-LLM-Vision-Model"] = settings.visionModel.trim();
  if (settings.embeddingModel.trim()) headers["X-LLM-Embedding-Model"] = settings.embeddingModel.trim();
  return headers;
}
