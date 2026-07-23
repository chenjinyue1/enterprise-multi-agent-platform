// 1. 编写前端类型定义

/**
 * 前端类型定义
 * 
 * TypeScript类型系统是前端开发的安全网。
 * 它能在编译时捕获类型错误，避免运行时崩溃。
 * 企业级项目必须有严格的类型定义。
 */

// ============================================
// 消息类型
// ============================================
export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  // 消息关联的Agent执行状态
  agentStatus?: AgentExecutionStatus;
}

// ============================================
// Agent执行状态
// ============================================
export interface AgentExecutionStatus {
  currentAgent: string;           // 当前执行的Agent名称
  progress: number;               // 进度 0-100
  status: "idle" | "running" | "completed" | "error" | "reviewing";
  steps: AgentStep[];             // 执行步骤列表
  startTime: string;
  endTime?: string;
}

export interface AgentStep {
  agentName: string;
  status: "pending" | "running" | "completed" | "error";
  startTime?: string;
  endTime?: string;
  description: string;
}

// ============================================
// 报告类型
// ============================================
export interface ReportSpec {
  report_id: string;
  title: string;
  content: string;
  report_type: "quarterly" | "monthly" | "annual" | "ad_hoc";
  audience: "executive" | "external" | "internal";
  generated_at: string;
  data_source: string;
  total_charts: number;
  total_words: number;
  chart_ids: string[];
  quality_score?: number;
  status: "draft" | "generated" | "reviewed" | "approved" | "rejected";
  review_comment?: string;
}

// ============================================
// 图表类型
// ============================================
export interface ChartSpec {
  chart_id: string;
  title: string;
  chart_type: "bar" | "line" | "pie" | "scatter" | "table";
  description: string;
  echarts_config: Record<string, any>;
  data_summary: string;
}

// ============================================
// 审核结果类型
// ============================================
export interface ReviewResult {
  report_id: string;
  overall_grade: "A" | "B" | "C" | "D" | "F";
  overall_score: number;
  status: "approved" | "needs_revision" | "rejected";
  dimension_scores: Record<string, { score: number; comment: string }>;
  issues: ReviewIssue[];
  strengths: string[];
  final_verdict: string;
  reviewed_at: string;
}

export interface ReviewIssue {
  severity: "critical" | "high" | "medium" | "low";
  category: "data" | "logic" | "business" | "compliance" | "ux";
  description: string;
  location?: string;
  suggestion: string;
}

// ============================================
// API响应类型
// ============================================
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
  timestamp: string;
}

export interface TaskResponse {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  report?: ReportSpec;
  review_result?: ReviewResult;
  error?: string;
}



