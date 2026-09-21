// 与后端 DTO 对齐的类型定义（服务端按角色生成，前端不自行脱敏）

export type Role = 'guest' | 'student' | 'teacher' | 'admin'

export interface QueryPlan {
  cohort: string | null
  education: string | null
  college: string | null
  major: string | null
  city: string | null
  position_or_unit: string | null
  keywords: string[]
  page: number
  page_size: number
}

export interface MatchReason {
  field: string
  label: string
  weight: number
}

export interface Relaxation {
  field: string
  label: string
  removed_condition: string
  match_count: number
}

export interface RecordFields {
  cohort: string | null
  grade: string | null
  education: string | null
  college: string | null
  major: string | null
  city: string | null
  position_or_unit: string | null
}

export interface RecordSource {
  title: string
  published_at: string | null
  content_type: string
  url?: string
}

export interface EvidenceItem {
  field: string
  text: string
  method: string
  bbox?: number[] | null
  asset_id?: string
}

export interface RecordSummary {
  record_key: string
  notice_id: string
  display_name: string
  review_status: 'pending' | 'processed' | 'review_required' | 'failed'
  visibility: 'draft' | 'published' | 'withdrawn'
  confidence: number
  fields: RecordFields
  source?: RecordSource
  score?: number
  match_reasons?: MatchReason[]
  evidence_count?: number
}

export interface RecordDetail extends RecordSummary {
  evidence: EvidenceItem[]
  poster: { full_access: boolean; note: string }
  person?: Record<string, string | null>
  extractor_version?: string
}

export interface SearchResponse {
  query_plan: QueryPlan
  total: number
  page: number
  page_size: number
  results: RecordSummary[]
  relaxations: Relaxation[]
  empty_plan: boolean
  role: Role
}

export interface ParseResponse {
  query: string
  query_plan: QueryPlan
  source: string
  degraded: boolean
  notes: string[]
  role: Role
}

export interface Citation {
  index: number
  record_key: string
  field: string
  text: string
  source_url?: string | null
  review_status: string
}

export interface AnswerResponse {
  answer: string
  insufficient_evidence: boolean
  degraded: boolean
  degraded_reason: string | null
  citations: Citation[]
  records: RecordSummary[]
  query_plan: QueryPlan
  role: Role
}

export interface MeResponse {
  role: Role
  role_label: string
  capabilities: string[]
  authenticated: boolean
  dev_switch_enabled: boolean
  campus_original_asset_enabled: boolean
}

export interface StatsResponse {
  query_plan: QueryPlan
  role: Role
  total: number
  distributions: {
    education: Record<string, number>
    city: Record<string, number>
    cohort: Record<string, number>
  }
  with_field_evidence: number
  review_status_distribution?: Record<string, number>
}

export interface SavedSearch {
  saved_search_id: number
  query_plan: QueryPlan
  alert_frequency: 'off' | 'daily' | 'weekly'
  created_at: string
  updated_at: string
}

export interface PrivacySettings {
  history_enabled: boolean
  recommendation_enabled: boolean
  retention_days: number
  updated_at: string | null
}

export interface NotificationItem {
  notification_id: number
  saved_search_id: number
  notice_id: string
  title: string
  created_at: string
  read_at: string | null
}

export const FIELD_LABELS: Record<string, string> = {
  cohort: '届别',
  grade: '年级',
  education: '学历',
  college: '学院',
  major: '专业',
  city: '城市',
  position_or_unit: '岗位/单位',
  keywords: '关键词',
}

export const REVIEW_STATUS_LABELS: Record<string, string> = {
  pending: '待处理',
  processed: '已核验',
  review_required: '待复核',
  failed: '失败',
}
