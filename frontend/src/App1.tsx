

// 7. 编写前端App.tsx

/**
 * App.tsx
 * 
 * 应用入口组件。
 * 
 * 路由结构：
 * ---------
 * /          → 聊天界面（核心功能）
 * /login     → 登录页
 * /dashboard → 管理面板（查看历史报告、系统状态）
 * 
 * 企业级路由要求：
 * ---------------
 * - 路由守卫：未登录用户重定向到登录页
 * - 懒加载：代码分割，减少首屏加载时间
 * - 错误边界：组件崩溃不导致整个应用白屏
 */

import React, { Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

// 懒加载页面（代码分割）
const ChatPage = lazy(() => import("./pages/ChatPage"));
const LoginPage = lazy(() => import("./pages/LoginPage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));

// 加载中占位
const PageLoader: React.FC = () => (
  <div className="min-h-screen flex items-center justify-center">
    <div className="flex flex-col items-center gap-4">
      <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin" />
      <p className="text-gray-500">加载中...</p>
    </div>
  </div>
);

// 路由守卫：检查登录状态
const PrivateRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const token = localStorage.getItem("access_token");
  return token ? <>{children}</> : <Navigate to="/login" replace />;
};

const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <ChatPage />
              </PrivateRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <PrivateRoute>
                <DashboardPage />
              </PrivateRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
};

export default App;
