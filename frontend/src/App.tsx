import { useState, useEffect } from 'react'

/**
 * App 根组件
 * 
 * 当前是项目初始化阶段，先做一个简单的健康检查页面
 * 后续板块会逐步替换成完整的聊天界面
 */
function App() {
  const [health, setHealth] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // 调用后端健康检查接口
    fetch('/api/')
      .then(res => res.json())
      .then(data => {
        setHealth(data)
        setLoading(false)
      })
      .catch(err => {
        console.error('连接后端失败:', err)
        setLoading(false)
      })
  }, [])

  return (
    <div style={{ 
      maxWidth: '800px', 
      margin: '50px auto', 
      padding: '20px',
      fontFamily: 'system-ui, sans-serif'
    }}>
      <h1>🏢 企业智能数据分析多智能体平台</h1>
      <p>Enterprise Multi-Agent Data Analysis Platform</p>

      <hr style={{ margin: '20px 0' }} />

      <h2>🔌 后端连接状态</h2>
      {loading ? (
        <p>正在连接后端服务...</p>
      ) : health ? (
        <div style={{ 
          background: '#f0f9ff', 
          padding: '15px', 
          borderRadius: '8px',
          border: '1px solid #bae6fd'
        }}>
          <p><strong>状态:</strong> ✅ {health.status}</p>
          <p><strong>服务:</strong> {health.service}</p>
          <p><strong>版本:</strong> {health.version}</p>
          <p><strong>环境:</strong> {health.environment}</p>
        </div>
      ) : (
        <div style={{ 
          background: '#fef2f2', 
          padding: '15px', 
          borderRadius: '8px',
          border: '1px solid #fecaca',
          color: '#dc2626'
        }}>
          <p>❌ 无法连接到后端服务</p>
          <p>请确保后端已启动: <code>uvicorn app.main:app --reload</code></p>
        </div>
      )}

      <hr style={{ margin: '20px 0' }} />

      <h2>📋 项目进度</h2>
      <ul>
        <li>✅ 板块一：项目架构设计与环境搭建</li>
        <li>⏳ 板块二：核心状态机 State 设计</li>
        <li>⏳ 板块三：Supervisor 调度 Agent</li>
        <li>⏳ 板块四：Data Agent + MCP 数据库工具</li>
        <li>⏳ 板块五：Analysis Agent + Python 计算工具</li>
        <li>⏳ 板块六：Viz Agent + 图表生成</li>
        <li>⏳ 板块七：Report Agent + RAG 报告生成</li>
        <li>⏳ 板块八：Review Agent + Harness 评估</li>
        <li>⏳ 板块九：LangGraph 图编排与链路打通</li>
        <li>⏳ 板块十：FastAPI 网关 + JWT 鉴权</li>
        <li>⏳ 板块十一：前端 React + Vite + WebSocket</li>
        <li>⏳ 板块十二：Redis 缓存 + MySQL 持久化</li>
        <li>⏳ 板块十三：项目部署与简历包装</li>
      </ul>
    </div>
  )
}

export default App
