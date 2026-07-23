// 3. 编写WebSocket Hook

/**
 * useWebSocket Hook
 * 
 * 为什么需要自定义Hook？
 * ----------------------
 * WebSocket连接管理涉及：
 * - 连接建立/断开/重连
 * - 心跳保活
 * - 消息订阅/取消订阅
 * - 错误处理
 * 
 * 把这些逻辑封装成Hook，组件只需要关心"收到什么消息"，
 * 不用关心"怎么维护连接"。
 * 
 * 企业级WebSocket最佳实践：
 * ------------------------
 * 1. 自动重连：网络波动后自动恢复连接
 * 2. 心跳机制：防止长时间无通信被服务器断开
 * 3. 消息队列：断线期间的消息缓存，恢复后补发
 * 4. 连接状态暴露：UI可以显示"连接中/已连接/已断开"
 */

import { useState, useEffect, useRef, useCallback } from "react";

export type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

export interface UseWebSocketOptions {
  url: string;
  onMessage?: (data: any) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
  reconnectInterval?: number;      // 重连间隔(ms)
  maxReconnectAttempts?: number;   // 最大重连次数
  heartbeatInterval?: number;      // 心跳间隔(ms)
}

export function useWebSocket(options: UseWebSocketOptions) {
  const {
    url,
    onMessage,
    onOpen,
    onClose,
    onError,
    reconnectInterval = 3000,
    maxReconnectAttempts = 5,
    heartbeatInterval = 30000,
  } = options;

  const [status, setStatus] = useState<WebSocketStatus>("connecting");
  const [lastMessage, setLastMessage] = useState<any>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * 发送消息
   * 
   * 封装发送逻辑，处理连接未就绪的情况
   */
  const sendMessage = useCallback((data: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const message = typeof data === "string" ? data : JSON.stringify(data);
      wsRef.current.send(message);
      return true;
    }
    console.warn("WebSocket未连接，消息发送失败:", data);
    return false;
  }, []);

  /**
   * 建立连接
   */
  const connect = useCallback(() => {
    // 清理旧连接
    if (wsRef.current) {
      wsRef.current.close();
    }

    setStatus("connecting");

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("✅ WebSocket连接成功");
        setStatus("connected");
        reconnectCountRef.current = 0;
        
        // 启动心跳
        if (heartbeatTimerRef.current) {
          clearInterval(heartbeatTimerRef.current);
        }
        heartbeatTimerRef.current = setInterval(() => {
          sendMessage({ type: "ping", timestamp: Date.now() });
        }, heartbeatInterval);

        onOpen?.();
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // 处理心跳响应
          if (data.type === "pong") return;
          
          setLastMessage(data);
          onMessage?.(data);
        } catch (e) {
          // 非JSON消息（如纯文本）
          setLastMessage(event.data);
          onMessage?.(event.data);
        }
      };

      ws.onclose = () => {
        console.log("🔌 WebSocket连接关闭");
        setStatus("disconnected");
        
        // 停止心跳
        if (heartbeatTimerRef.current) {
          clearInterval(heartbeatTimerRef.current);
          heartbeatTimerRef.current = null;
        }

        // 自动重连
        if (reconnectCountRef.current < maxReconnectAttempts) {
          reconnectCountRef.current++;
          console.log(`🔄 ${reconnectInterval}ms后尝试第${reconnectCountRef.current}次重连...`);
          reconnectTimerRef.current = setTimeout(connect, reconnectInterval);
        } else {
          console.error("❌ 达到最大重连次数，停止重连");
          setStatus("error");
        }

        onClose?.();
      };

      ws.onerror = (error) => {
        console.error("💥 WebSocket错误:", error);
        setStatus("error");
        onError?.(error);
      };

    } catch (error) {
      console.error("WebSocket连接失败:", error);
      setStatus("error");
    }
  }, [url, heartbeatInterval, maxReconnectAttempts, reconnectInterval, onOpen, onMessage, onClose, onError, sendMessage]);

  /**
   * 手动断开连接
   */
  const disconnect = useCallback(() => {
    reconnectCountRef.current = maxReconnectAttempts; // 阻止自动重连
    
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
    }
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus("disconnected");
  }, [maxReconnectAttempts]);

  // 组件挂载时自动连接，卸载时断开
  useEffect(() => {
    connect();
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    status,
    lastMessage,
    sendMessage,
    connect,
    disconnect,
    isConnected: status === "connected",
  };
}

export default useWebSocket;

