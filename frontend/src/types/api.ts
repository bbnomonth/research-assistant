export type ChatMode =
  | 'other'
  | 'literature_discovery'
  | 'paper_reading'
  | 'topic_guidance'
  | 'framework_building';

export const CHAT_MODE_LABEL: Record<ChatMode, string> = {
  other: '自由问答',
  literature_discovery: '论文检索',
  paper_reading: '论文引导精读',
  topic_guidance: '选题导师',
  framework_building: '论文框架搭建',
};

export const CHAT_MODE_COLOR: Record<ChatMode, string> = {
  other: 'blue',
  literature_discovery: 'purple',
  paper_reading: 'green',
  topic_guidance: 'geekblue',
  framework_building: 'orange',
};

export interface Project {
  id: string;
  name: string;
  profile: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ProjectUpdateRequest {
  name?: string;
  profile?: Record<string, unknown>;
}

export interface SessionUpdateRequest {
  title?: string;
}

export interface Session {
  id: string;
  project_id: string;
  title: string;
  summary: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  mode: string | null;
  sequence: number;
  created_at: string;
}

export interface Paper {
  id: string;
  project_id: string;
  arxiv_id: string;
  title: string;
  authors_json: string;
  abstract: string;
  published: string;
  categories_json: string;
  entry_url: string;
  pdf_url: string;
  recommendation_reason: string;
  purpose_labels_json: string;
  favorited: boolean;
  created_at: string;
  updated_at: string;
}

export interface PaperChunk {
  chunk_id: string;
  page_number: number;
  section: string;
  text: string;
  is_ocr: boolean;
}

export interface TaskRecord {
  id: string;
  status:
    | 'pending'
    | 'processing'
    | 'completed'
    | 'failed'
    | 'cancelled'
    | 'interrupted';
  progress: number;
  paper_id: string | null;
  error_message: string | null;
}

export interface UploadResponse {
  paper_id: string;
  task: TaskRecord;
}

export interface EvidenceSearchResponse {
  results: PaperChunk[];
}

export interface QuickAnalysisResponse {
  artifact_id: string;
  title: string;
  evidence_pages: number[];
}

export interface PaperComparisonRequest {
  paper_ids: string[];
}

export interface PaperComparisonResponse {
  artifact_id: string;
  title: string;
  evidence_pages: Record<string, number[]>;
}

export interface ArtifactSummary {
  id: string;
  project_id: string;
  artifact_type: string;
  title: string;
  created_at: string;
}

export interface Artifact {
  id: string;
  project_id: string;
  artifact_type: string;
  title: string;
  content: Record<string, unknown>;
  markdown: string;
  created_at: string;
}

export interface ArtifactUpdateRequest {
  title?: string;
  content?: Record<string, unknown>;
  markdown?: string;
}

export interface PrivacySettings {
  pii_scrub: boolean;
  local_only: boolean;
  data_ttl_days: number;
}

export interface RuntimeSettings {
  model_configured: boolean;
  qwen_model: string;
  qwen_base_url: string;
  ocr_configured: boolean;
  ocr_language: string;
  pdf_max_bytes: number;
  pdf_max_pages: number;
  privacy?: PrivacySettings;
}

export interface DiagnosticResult {
  available?: boolean;
  configured?: boolean;
  message: string;
}

export interface HealthResponse {
  status: string;
  database: string;
  model_configured: boolean;
  ocr_configured: boolean;
}

export interface ArxivPaper {
  arxiv_id: string;
  title: string;
  authors: string[];
  abstract: string;
  published: string;
  categories: string[];
  entry_url: string;
  pdf_url: string;
}

export interface RecommendedPaper {
  paper: ArxivPaper;
  reason: string;
  purpose_labels: string[];
}

export interface LiteratureDiscoveryResult {
  query: string;
  candidates: ArxivPaper[];
  recommendations: RecommendedPaper[];
}

export type StreamEventName =
  | 'mode'
  | 'metadata'
  | 'stage'
  | 'search_results'
  | 'evidence'
  | 'artifact'
  | 'token'
  | 'done'
  | 'error';

export interface StreamEvent {
  event: StreamEventName;
  data: Record<string, unknown>;
}
