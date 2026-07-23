// 2. 编写前端API服务层

/**
 * API服务层
 * 
 * 为什么需要API服务层？
 * --------------------
 * 1. 统一封装axios实例，配置baseURL、超时、拦截器
 * 2. 集中管理所有API调用，避免散落在各个组件中
 * 3. 统一错误处理，前端只关心业务逻辑
 * 4. 便于Mock和测试（可以切换mock数据）
 */

import axios, { AxiosInstance, AxiosError } from "axios";
import type { ApiResponse, TaskResponse, ReportSpec } from "../types";

// ============================================
// Axios实例配置
// ============================================
const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
  timeout: 120000,  // Agent任务可能需要较长时间
  headers: {
    "Content-Type": "application/json",
  },
});

// 请求拦截器：添加JWT Token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器：统一错误处理
apiClient.interceptors.response.use(
  (response) => response.data,
  (error: AxiosError<ApiResponse<any>>) => {
    const message = error.response?.data?.message || error.message || "网络错误";
    console.error("API Error:", message);
    return Promise.reject(new Error(message));
  }
);

// ============================================
// 聊天/任务API
// ============================================
export const chatApi = {
  /**
   * 发送分析任务请求
   * 
   * 为什么用POST而不是WebSocket？
   * ---------------------------
   * 任务提交是"一次性"操作，用HTTP POST更自然。
   * 实时进度通过WebSocket推送，这是企业级最佳实践：
   * - HTTP: 请求-响应模式，适合提交任务
   * - WebSocket: 全双工通信，适合实时推送
   */
  async submitTask(query: string): Promise<ApiResponse<TaskResponse>> {
    return apiClient.post("/chat/submit", { query });
  },

  /**
   * 查询任务状态
   * 
   * 轮询备用方案：如果WebSocket不可用，前端可以轮询此接口
   */
  async getTaskStatus(taskId: string): Promise<ApiResponse<TaskResponse>> {
    return apiClient.get(`/chat/status/${taskId}`);
  },

  /**
   * 获取任务结果（报告）
   */
  async getTaskResult(taskId: string): Promise<ApiResponse<TaskResponse>> {
    return apiClient.get(`/chat/result/${taskId}`);
  },
};

// ============================================
// 报告API
// ============================================
export const reportApi = {
  /**
   * 获取报告列表
   */
  async getReports(page: number = 1, pageSize: number = 10): Promise<ApiResponse<{
    items: ReportSpec[];
    total: number;
  }>> {
    return apiClient.get("/reports", { params: { page, page_size: pageSize } });
  },

  /**
   * 获取报告详情
   */
  async getReport(reportId: string): Promise<ApiResponse<ReportSpec>> {
    return apiClient.get(`/reports/${reportId}`);
  },

  /**
   * 导出报告
   * 
   * 支持格式：
   * - markdown: 原始Markdown（可编辑）
   * - html: 网页格式（适合邮件发送）
   * - pdf: PDF格式（适合打印和存档）
   * - word: Word文档（适合二次编辑）
   */
  async exportReport(
    reportId: string,
    format: "markdown" | "html" | "pdf" | "word"
  ): Promise<Blob> {
    const response = await apiClient.get(`/reports/${reportId}/export`, {
      params: { format },
      responseType: "blob",
    });
    return response as unknown as Blob;
  },

  /**
   * 下载导出的报告
   */
  downloadReport(blob: Blob, filename: string) {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
};

// ============================================
// Agent监控API
// ============================================
export const agentApi = {
  /**
   * 获取Agent执行历史
   */
  async getExecutionHistory(taskId: string): Promise<ApiResponse<any>> {
    return apiClient.get(`/agent/history/${taskId}`);
  },

  /**
   * 获取系统状态（各Agent健康状态）
   */
  async getSystemStatus(): Promise<ApiResponse<{
    agents: Record<string, { status: string; last_heartbeat: string }>;
    queue_size: number;
    active_tasks: number;
  }>> {
    return apiClient.get("/agent/status");
  },
};

export default apiClient;

