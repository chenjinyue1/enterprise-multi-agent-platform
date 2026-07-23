// 5. 编写AgentStatus组件

/**
 * AgentStatus 组件
 * 
 * 实时显示多智能体系统的执行进度。
 * 
 * 设计思路：
 * ---------
 * 1. 步骤条：显示所有Agent的执行顺序和状态
 * 2. 进度条：显示整体完成百分比
 * 3. 状态标识：用颜色和图标区分运行中/完成/错误
 * 4. 耗时统计：显示每个Agent的执行时间
 * 
 * 企业价值：
 * ---------
 * - 透明化：用户能看到系统在"干什么"，减少焦虑
 * - 可追踪：出问题能快速定位到哪个Agent
 * - 可审计：执行轨迹记录用于事后分析
 */

import React from "react";
import type { AgentExecutionStatus } from "../types";

interface AgentStatusProps {
  status: AgentExecutionStatus | null;
  isLoading: boolean;
}

const AgentStatus: React.FC<AgentStatusProps> = ({ status, isLoading }) => {
  // Agent名称映射（中文显示）
  const agentNameMap: Record<string, string> = {
    supervisor: "任务调度",
    data_agent: "数据查询",
    analysis_agent: "统计分析",
    viz_agent: "图表生成",
    report_agent: "报告撰写",
    review_agent: "质量审核",
  };

  // 状态图标
  const StatusIcon: React.FC<{ stepStatus: string }> = ({ stepStatus }) => {
    switch (stepStatus) {
      case "completed":
        return (
          <svg className="w-5 h-5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
        );
      case "running":
        return (
          <svg className="w-5 h-5 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        );
      case "error":
        return (
          <svg className="w-5 h-5 text-red-500" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
              clipRule="evenodd"
            />
          </svg>
        );
      default:
        return (
          <svg className="w-5 h-5 text-gray-300" fill="currentColor" viewBox="0 0 20 20">
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
              clipRule="evenodd"
            />
          </svg>
        );
    }
  };

  // 如果没有状态，显示提示
  if (!status && !isLoading) {
    return (
      <div className="p-4">
        <h3 className="font-semibold text-gray-900 mb-2">执行状态</h3>
        <p className="text-sm text-gray-500">等待任务开始...</p>
      </div>
    );
  }

  // 计算进度
  const progress = status?.progress || 0;
  const completedSteps = status?.steps.filter((s) => s.status === "completed").length || 0;
  const totalSteps = status?.steps.length || 6;

  return (
    <div className="p-4">
      <h3 className="font-semibold text-gray-900 mb-4">执行状态</h3>

      {/* 整体进度条 */}
      {isLoading && (
        <div className="mb-4">
          <div className="flex justify-between text-sm mb-1">
            <span className="text-gray-600">总体进度</span>
            <span className="text-blue-600 font-medium">{progress}%</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-400 mt-1">
            {completedSteps}/{totalSteps} 步骤已完成
          </p>
        </div>
      )}

      {/* 当前执行Agent */}
      {status?.currentAgent && isLoading && (
        <div className="mb-4 p-3 bg-blue-50 rounded-lg border border-blue-100">
          <p className="text-sm text-blue-800">
            正在执行: <strong>{agentNameMap[status.currentAgent] || status.currentAgent}</strong>
          </p>
        </div>
      )}

      {/* 步骤列表 */}
      <div className="space-y-3">
        {(status?.steps || []).map((step, index) => (
          <div
            key={step.agentName}
            className={`flex items-start gap-3 p-2 rounded-lg transition-colors ${
              step.status === "running"
                ? "bg-blue-50 border border-blue-100"
                : step.status === "completed"
                ? "bg-green-50"
                : step.status === "error"
                ? "bg-red-50"
                : ""
            }`}
          >
            {/* 序号/图标 */}
            <div className="flex-shrink-0 mt-0.5">
              <StatusIcon stepStatus={step.status} />
            </div>

            {/* 内容 */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-gray-900">
                  {agentNameMap[step.agentName] || step.agentName}
                </span>
                {step.status === "running" && (
                  <span className="text-xs text-blue-600 animate-pulse">执行中...</span>
                )}
              </div>
              <p className="text-xs text-gray-500 mt-0.5">{step.description}</p>
              
              {/* 耗时显示 */}
              {step.startTime && (
                <p className="text-xs text-gray-400 mt-1">
                  {step.status === "completed" && step.endTime
                    ? `耗时: ${
                        Math.round(
                          (new Date(step.endTime).getTime() - new Date(step.startTime).getTime()) / 1000
                        )
                      }s`
                    : step.status === "running"
                    ? `开始于: ${new Date(step.startTime).toLocaleTimeString()}`
                    : ""}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* 总耗时 */}
      {status?.endTime && status.startTime && (
        <div className="mt-4 pt-4 border-t">
          <p className="text-sm text-gray-600">
            总耗时:{" "}
            <span className="font-medium">
              {Math.round(
                (new Date(status.endTime).getTime() - new Date(status.startTime).getTime()) / 1000
              )}
              s
            </span>
          </p>
        </div>
      )}
    </div>
  );
};

export default AgentStatus;

