// 6. 编写ReportViewer组件

/**
 * ReportViewer 组件
 * 
 * 报告预览与导出组件。
 * 
 * 功能：
 * -----
 * 1. Markdown渲染：将报告内容渲染为美观的HTML
 * 2. 图表嵌入：解析chart://引用，用ECharts渲染图表
 * 3. 多格式导出：支持Markdown/HTML/PDF/Word
 * 4. 审核结果展示：显示Review Agent的审核评分
 * 
 * 企业级要求：
 * -----------
 * - 打印友好：CSS媒体查询优化打印样式
 * - 响应式：适配不同屏幕尺寸
 * - 无障碍：图表添加alt文本
 */

import React, { useState, useCallback } from "react";
import type { ReportSpec, ReviewResult, ChartSpec } from "../types";
import { reportApi } from "../services/api";

interface ReportViewerProps {
  report: ReportSpec;
  reviewResult?: ReviewResult;
  onClose: () => void;
}

const ReportViewer: React.FC<ReportViewerProps> = ({ report, reviewResult, onClose }) => {
  const [activeTab, setActiveTab] = useState<"preview" | "review">("preview");
  const [isExporting, setIsExporting] = useState(false);

  // ============================================
  // 导出报告
  // ============================================
  const handleExport = useCallback(
    async (format: "markdown" | "html" | "pdf" | "word") => {
      setIsExporting(true);
      try {
        const blob = await reportApi.exportReport(report.report_id, format);
        const extensionMap: Record<string, string> = {
          markdown: "md",
          html: "html",
          pdf: "pdf",
          word: "docx",
        };
        const filename = `${report.title}.${extensionMap[format]}`;
        reportApi.downloadReport(blob, filename);
      } catch (error: any) {
        alert(`导出失败: ${error.message}`);
      } finally {
        setIsExporting(false);
      }
    },
    [report]
  );

  // ============================================
  // 渲染Markdown内容（简化版）
  // 
  // 实际项目中应使用react-markdown库
  // 这里为了演示，用简单的正则替换
  // ============================================
  const renderMarkdown = (content: string) => {
    // 处理标题
    let html = content
      .replace(/^### (.*$)/gim, "<h3 class=\\"text-lg font-bold text-gray-900 mt-6 mb-3\\">$1</h3>")
      .replace(/^## (.*$)/gim, "<h2 class=\\"text-xl font-bold text-gray-900 mt-8 mb-4 border-b pb-2\\">$1</h2>")
      .replace(/^# (.*$)/gim, "<h1 class=\\"text-2xl font-bold text-gray-900 mt-8 mb-4\\">$1</h1>");

    // 处理加粗
    html = html.replace(/\\*\\*(.*?)\\*\\*/g, "<strong class=\\"text-gray-900\\">$1</strong>");

    // 处理斜体
    html = html.replace(/\\*(.*?)\\*/g, "<em>$1</em>");

    // 处理图表引用（简化版）
    html = html.replace(
      /!\\[(.*?)\\]\\(chart:\\/\\/([a-zA-Z0-9_-]+)\\)/g,
      `<div class="my-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
        <p class="text-sm text-gray-500 mb-2">📊 图表: $1</p>
        <div class="h-64 flex items-center justify-center bg-white rounded border border-dashed border-gray-300">
          <span class="text-gray-400">[图表 $2 渲染区域]</span>
        </div>
      </div>`
    );

    // 处理表格（简化版）
    const tableRegex = /\\|(.+)\\|\\n\\|[-\\s|]+\\|\\n((?:\\|.+\\|\\n?)+)/g;
    html = html.replace(tableRegex, (match, header, rows) => {
      const headers = header.split("|").map((h: string) => h.trim()).filter(Boolean);
      const rowData = rows
        .trim()
        .split("\\n")
        .map((row: string) =>
          row.split("|").map((cell: string) => cell.trim()).filter(Boolean)
        )
        .filter((row: string[]) => row.length > 0);

      return `
        <table class="min-w-full border-collapse border border-gray-300 my-4">
          <thead class="bg-gray-50">
            <tr>
              ${headers.map((h: string) => `<th class="border border-gray-300 px-4 py-2 text-left text-sm font-semibold text-gray-700">${h}</th>`).join("")}
            </tr>
          </thead>
          <tbody>
            ${rowData
              .map(
                (row: string[]) => `
              <tr class="hover:bg-gray-50">
                ${row.map((cell: string) => `<td class="border border-gray-300 px-4 py-2 text-sm text-gray-700">${cell}</td>`).join("")}
              </tr>
            `
              )
              .join("")}
          </tbody>
        </table>
      `;
    });

    // 处理引用块
    html = html.replace(
      /^> (.*$)/gim,
      "<blockquote class=\\"border-l-4 border-blue-500 pl-4 py-2 my-4 bg-blue-50 text-gray-700\\">$1</blockquote>"
    );

    // 处理分隔线
    html = html.replace(/^---$/gim, "<hr class=\\"my-6 border-gray-200\\" />");

    // 处理段落（必须在最后）
    html = html
      .split("\\n\\n")
      .map((block) => {
        if (block.trim().startsWith("<") || block.trim() === "") return block;
        return `<p class="text-gray-700 leading-relaxed mb-4">${block}</p>`;
      })
      .join("\\n");

    return html;
  };

  // ============================================
  // 渲染审核结果
  // ============================================
  const renderReviewResult = () => {
    if (!reviewResult) {
      return (
        <div className="p-8 text-center text-gray-500">
          <p>暂无审核结果</p>
        </div>
      );
    }

    const gradeColors: Record<string, string> = {
      A: "bg-green-100 text-green-800",
      B: "bg-blue-100 text-blue-800",
      C: "bg-yellow-100 text-yellow-800",
      D: "bg-orange-100 text-orange-800",
      F: "bg-red-100 text-red-800",
    };

    return (
      <div className="p-6">
        {/* 综合评分 */}
        <div className="flex items-center gap-4 mb-6">
          <div className={`text-3xl font-bold px-4 py-2 rounded-lg ${gradeColors[reviewResult.overall_grade] || "bg-gray-100"}`}>
            {reviewResult.overall_grade}
          </div>
          <div>
            <p className="text-2xl font-bold text-gray-900">{reviewResult.overall_score}分</p>
            <p className="text-sm text-gray-500">
              {reviewResult.status === "approved"
                ? "✅ 审核通过"
                : reviewResult.status === "needs_revision"
                ? "⚠️ 建议修改"
                : "❌ 审核未通过"}
            </p>
          </div>
        </div>

        {/* 各维度评分 */}
        <h4 className="font-semibold text-gray-900 mb-3">各维度评分</h4>
        <div className="space-y-3 mb-6">
          {Object.entries(reviewResult.dimension_scores).map(([name, score]) => (
            <div key={name}>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-600">{name}</span>
                <span className="font-medium">{score.score}分</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className={`h-2 rounded-full ${
                    score.score >= 80
                      ? "bg-green-500"
                      : score.score >= 60
                      ? "bg-yellow-500"
                      : "bg-red-500"
                  }`}
                  style={{ width: `${score.score}%` }}
                />
              </div>
            </div>
          ))}
        </div>

        {/* 发现的问题 */}
        {reviewResult.issues.length > 0 && (
          <>
            <h4 className="font-semibold text-gray-900 mb-3">发现的问题</h4>
            <div className="space-y-2 mb-6">
              {reviewResult.issues.map((issue, index) => (
                <div
                  key={index}
                  className={`p-3 rounded-lg border ${
                    issue.severity === "critical"
                      ? "bg-red-50 border-red-200"
                      : issue.severity === "high"
                      ? "bg-orange-50 border-orange-200"
                      : "bg-yellow-50 border-yellow-200"
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${
                        issue.severity === "critical"
                          ? "bg-red-100 text-red-700"
                          : issue.severity === "high"
                          ? "bg-orange-100 text-orange-700"
                          : "bg-yellow-100 text-yellow-700"
                      }`}
                    >
                      {issue.severity}
                    </span>
                    <span className="text-xs text-gray-500">{issue.category}</span>
                  </div>
                  <p className="text-sm text-gray-700">{issue.description}</p>
                  {issue.suggestion && (
                    <p className="text-xs text-gray-500 mt-1">建议: {issue.suggestion}</p>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        {/* 优点 */}
        {reviewResult.strengths.length > 0 && (
          <>
            <h4 className="font-semibold text-gray-900 mb-3">优点</h4>
            <ul className="list-disc list-inside space-y-1">
              {reviewResult.strengths.map((strength, index) => (
                <li key={index} className="text-sm text-gray-700">{strength}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-5xl max-h-[90vh] flex flex-col m-4">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div>
            <h2 className="text-lg font-bold text-gray-900">{report.title}</h2>
            <p className="text-sm text-gray-500">
              {report.report_type === "quarterly"
                ? "季度报告"
                : report.report_type === "monthly"
                ? "月度报告"
                : report.report_type === "annual"
                ? "年度报告"
                : "专项分析"}
              {" | "}
              {report.total_words}字 | {report.total_charts}个图表
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Tab切换 */}
            <div className="flex bg-gray-100 rounded-lg p-1 mr-4">
              <button
                onClick={() => setActiveTab("preview")}
                className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                  activeTab === "preview"
                    ? "bg-white text-gray-900 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                报告预览
              </button>
              {reviewResult && (
                <button
                  onClick={() => setActiveTab("review")}
                  className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                    activeTab === "review"
                      ? "bg-white text-gray-900 shadow-sm"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  审核结果
                </button>
              )}
            </div>

            {/* 导出按钮 */}
            <div className="flex gap-1">
              {(["markdown", "html", "pdf"] as const).map((format) => (
                <button
                  key={format}
                  onClick={() => handleExport(format)}
                  disabled={isExporting}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
                >
                  {isExporting ? "导出中..." : format.toUpperCase()}
                </button>
              ))}
            </div>

            {/* 关闭按钮 */}
            <button
              onClick={onClose}
              className="ml-2 p-2 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <svg className="w-5 h-5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* 内容区域 */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === "preview" ? (
            <div className="max-w-4xl mx-auto p-8">
              {/* 报告元信息 */}
              <div className="mb-8 p-4 bg-gray-50 rounded-lg text-sm text-gray-600">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <span className="text-gray-400">生成时间:</span>{" "}
                    {new Date(report.generated_at).toLocaleString()}
                  </div>
                  <div>
                    <span className="text-gray-400">数据来源:</span> {report.data_source}
                  </div>
                  <div>
                    <span className="text-gray-400">目标受众:</span>{" "}
                    {report.audience === "executive"
                      ? "高管"
                      : report.audience === "external"
                      ? "外部"
                      : "内部"}
                  </div>
                  <div>
                    <span className="text-gray-400">质量评分:</span>{" "}
                    {report.quality_score ? `${report.quality_score}分` : "未评分"}
                  </div>
                </div>
              </div>

              {/* 报告正文 */}
              <div
                className="prose prose-lg max-w-none"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(report.content) }}
              />
            </div>
          ) : (
            renderReviewResult()
          )}
        </div>
      </div>
    </div>
  );
};

export default ReportViewer;

