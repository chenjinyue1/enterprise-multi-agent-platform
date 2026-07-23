// 4. 编写聊天窗口组件

/**
 * ChatWindow 组件
 * 
 * 这是用户与多智能体平台交互的主界面。
 * 
 * 设计思路：
 * ---------
 * 1. 左侧：聊天消息列表（用户提问 + AI回复）
 * 2. 右侧：Agent执行状态面板（实时显示各Agent进度）
 * 3. 底部：输入框（支持Markdown快捷输入）
 * 
 * 企业级UI要求：
 * -------------
 * - 响应式：支持桌面端和移动端
 * - 无障碍：支持键盘导航、屏幕阅读器
 * - 性能：虚拟滚动处理大量消息
 * - 状态持久：刷新页面后聊天记录不丢失
 */

import React, { useState, useRef, useEffect, useCallback } from "react";
import type { ChatMessage, AgentExecutionStatus, TaskResponse } from "../types";
import { chatApi } from "../services/api";
import { useWebSocket } from "../hooks/useWebSocket";
import AgentStatus from "./AgentStatus";
import ReportViewer from "./ReportViewer";

// 消息唯一ID生成器
const generateId = () => `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

const ChatWindow: React.FC = () => {
  // ============================================
  // 状态管理
  // ============================================
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: "👋 欢迎使用企业智能数据分析平台！\\n\\n我可以帮您：\\n• 查询数据库数据\\n• 进行统计分析\\n• 生成可视化图表\\n• 撰写专业报告\\n• 质量审核\\n\\n请直接输入您的需求，例如：\\n\"帮我分析Q3各品类销售数据，生成季度报告\"",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [currentTaskId, setCurrentTaskId] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentExecutionStatus | null>(null);
  const [currentReport, setCurrentReport] = useState<TaskResponse["report"] | null>(null);
  const [showReport, setShowReport] = useState(false);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // ============================================
  // WebSocket：实时接收Agent执行进度
  // ============================================
  const { status: wsStatus, sendMessage } = useWebSocket({
    url: `${import.meta.env.VITE_WS_URL || "ws://localhost:8000"}/ws/chat`,
    onMessage: (data) => {
      if (data.type === "agent_progress") {
        // 更新Agent执行状态
        setAgentStatus(data.payload);
        
        // 更新对应消息的agentStatus
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === currentTaskId
              ? { ...msg, agentStatus: data.payload }
              : msg
          )
        );
      }
      
      if (data.type === "task_completed") {
        // 任务完成，获取结果
        handleTaskCompleted(data.payload);
      }
      
      if (data.type === "error") {
        setIsLoading(false);
        addMessage("assistant", `❌ 执行出错: ${data.payload.message}`);
      }
    },
  });

  // ============================================
  // 自动滚动到底部
  // ============================================
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ============================================
  // 添加消息
  // ============================================
  const addMessage = useCallback((role: ChatMessage["role"], content: string) => {
    const newMessage: ChatMessage = {
      id: generateId(),
      role,
      content,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, newMessage]);
    return newMessage.id;
  }, []);

  // ============================================
  // 发送消息
  // ============================================
  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) return;

    const query = inputValue.trim();
    setInputValue("");
    setIsLoading(true);
    setShowReport(false);
    setCurrentReport(null);

    // 添加用户消息
    const userMsgId = addMessage("user", query);
    setCurrentTaskId(userMsgId);

    // 初始化Agent状态
    const initialStatus: AgentExecutionStatus = {
      currentAgent: "supervisor",
      progress: 0,
      status: "running",
      steps: [
        { agentName: "supervisor", status: "running", description: "分析需求并拆解任务" },
        { agentName: "data_agent", status: "pending", description: "查询数据库" },
        { agentName: "analysis_agent", status: "pending", description: "统计分析" },
        { agentName: "viz_agent", status: "pending", description: "生成图表" },
        { agentName: "report_agent", status: "pending", description: "撰写报告" },
        { agentName: "review_agent", status: "pending", description: "质量审核" },
      ],
      startTime: new Date().toISOString(),
    };
    setAgentStatus(initialStatus);

    try {
      // 提交任务
      const response = await chatApi.submitTask(query);
      
      if (response.code === 200) {
        const task = response.data;
        
        // 如果任务立即完成（缓存或简单任务）
        if (task.status === "completed" && task.report) {
          handleTaskCompleted(task);
        }
        // 否则等待WebSocket推送进度
      } else {
        addMessage("assistant", `❌ 任务提交失败: ${response.message}`);
        setIsLoading(false);
      }
    } catch (error: any) {
      addMessage("assistant", `❌ 网络错误: ${error.message}`);
      setIsLoading(false);
      setAgentStatus(null);
    }
  };

  // ============================================
  // 任务完成处理
  // ============================================
  const handleTaskCompleted = (task: TaskResponse) => {
    setIsLoading(false);
    setAgentStatus((prev) =>
      prev
        ? {
            ...prev,
            status: "completed",
            progress: 100,
            endTime: new Date().toISOString(),
          }
        : null
    );

    if (task.report) {
      setCurrentReport(task.report);
      
      // 生成完成消息
      let completionMsg = `✅ 报告生成完成！\\n\\n`;
      completionMsg += `📄 **${task.report.title}**\\n`;
      completionMsg += `📝 ${task.report.total_words}字 | 📊 ${task.report.total_charts}个图表\\n`;
      
      if (task.review_result) {
        completionMsg += `🔍 审核等级: **${task.review_result.overall_grade}** (${task.review_result.overall_score}分)\\n`;
        if (task.review_result.status === "approved") {
          completionMsg += `✅ 审核通过，可直接使用\\n`;
        } else if (task.review_result.status === "needs_revision") {
          completionMsg += `⚠️ 审核建议修改\\n`;
        }
      }
      
      completionMsg += `\\n💡 点击右侧"查看报告"按钮预览完整报告`;
      
      addMessage("assistant", completionMsg);
    }
  };

  // ============================================
  // 键盘事件：Enter发送，Shift+Enter换行
  // ============================================
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // ============================================
  // 渲染消息气泡
  // ============================================
  const renderMessage = (msg: ChatMessage) => {
    const isUser = msg.role === "user";
    
    return (
      <div
        key={msg.id}
        className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}
      >
        <div
          className={`max-w-[80%] rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-blue-600 text-white rounded-br-none"
              : "bg-gray-100 text-gray-800 rounded-bl-none"
          }`}
        >
          {/* 消息内容（支持Markdown渲染） */}
          <div className="prose prose-sm max-w-none">
            {msg.content.split("\\n").map((line, i) => (
              <p key={i} className="mb-1 last:mb-0">
                {line.startsWith("**") && line.endsWith("**") ? (
                  <strong>{line.slice(2, -2)}</strong>
                ) : line.startsWith("📄") || line.startsWith("📝") || 
                   line.startsWith("📊") || line.startsWith("🔍") ||
                   line.startsWith("✅") || line.startsWith("⚠️") ? (
                  <span className="flex items-center gap-1">{line}</span>
                ) : (
                  line
                )}
              </p>
            ))}
          </div>
          
          {/* 时间戳 */}
          <div
            className={`text-xs mt-1 ${
              isUser ? "text-blue-200" : "text-gray-400"
            }`}
          >
            {new Date(msg.timestamp).toLocaleTimeString()}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-screen bg-gray-50">
      {/* ============================================ */}
      {/* 左侧：聊天区域 */}
      {/* ============================================ */}
      <div className="flex-1 flex flex-col max-w-4xl mx-auto">
        {/* 头部 */}
        <header className="bg-white border-b px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              企业智能数据分析平台
            </h1>
            <p className="text-sm text-gray-500">
              AI驱动的数据分析与报告生成
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* WebSocket连接状态 */}
            <div
              className={`w-2 h-2 rounded-full ${
                wsStatus === "connected"
                  ? "bg-green-500"
                  : wsStatus === "connecting"
                  ? "bg-yellow-500 animate-pulse"
                  : "bg-red-500"
              }`}
            />
            <span className="text-xs text-gray-500">
              {wsStatus === "connected"
                ? "实时连接"
                : wsStatus === "connecting"
                ? "连接中..."
                : "已断开"}
            </span>
          </div>
        </header>

        {/* 消息列表 */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {messages.map(renderMessage)}
          <div ref={messagesEndRef} />
        </div>

        {/* 输入区域 */}
        <div className="bg-white border-t px-6 py-4">
          <div className="flex gap-2">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入您的数据分析需求，例如：帮我分析Q3销售数据..."
              className="flex-1 resize-none rounded-lg border border-gray-300 px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent min-h-[60px] max-h-[200px]"
              disabled={isLoading}
              rows={2}
            />
            <button
              onClick={handleSend}
              disabled={isLoading || !inputValue.trim()}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors self-end"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  处理中
                </span>
              ) : (
                "发送"
              )}
            </button>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            按 Enter 发送，Shift + Enter 换行
          </p>
        </div>
      </div>

      {/* ============================================ */}
      {/* 右侧：Agent状态面板 */}
      {/* ============================================ */}
      <div className="w-80 bg-white border-l flex flex-col">
        <AgentStatus status={agentStatus} isLoading={isLoading} />
        
        {/* 查看报告按钮 */}
        {currentReport && (
          <div className="p-4 border-t">
            <button
              onClick={() => setShowReport(!showReport)}
              className="w-full py-2 px-4 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
            >
              {showReport ? "隐藏报告" : "查看报告"}
            </button>
          </div>
        )}
      </div>

      {/* ============================================ */}
      {/* 报告预览弹窗 */}
      {/* ============================================ */}
      {showReport && currentReport && (
        <ReportViewer
          report={currentReport}
          onClose={() => setShowReport(false)}
        />
      )}
    </div>
  );
};

export default ChatWindow;
