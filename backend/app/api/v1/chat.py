
# 11. 编写后端API路由（聊天+报告）
"""
聊天API路由
处理用户任务提交、状态查询、WebSocket连接

企业级API设计原则：
-------------------
1. RESTful：资源导向，状态码规范
2. 异步化：Agent任务耗时较长，提交后立即返回task_id
3. 幂等性：同一task_id多次查询返回相同结果
4. 限流：防止恶意请求耗尽系统资源
"""

from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import asyncio
from datetime import datetime

from ...graph.builder import run_analysis_task
from ...services.redis_service import RedisService
from ...core.security import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])

# 存储活跃WebSocket连接（生产环境应使用Redis Pub/Sub）
active_connections: dict[str, WebSocket] = {}


# ============================================
# 请求/响应模型
# ============================================
class SubmitTaskRequest(BaseModel):
    query: str

class TaskResponse(BaseModel):
    task_id: str
    status: str
    message: str
    report: Optional[dict] = None
    review_result: Optional[dict] = None
    error: Optional[str] = None


# ============================================
# 提交任务（HTTP）
# ============================================
@router.post("/submit", response_model=TaskResponse)
async def submit_task(
    request: SubmitTaskRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    """
    提交分析任务
    
    流程：
    1. 接收用户Query
    2. 生成task_id
    3. 后台启动Agent任务
    4. 立即返回task_id（异步模式）
    
    为什么用后台任务？
    -----------------
    Agent执行可能需要30-120秒，HTTP请求不能等这么久。
    后台任务模式：提交后立即返回，用户通过WebSocket或轮询获取结果。
    """
    import uuid
    task_id = str(uuid.uuid4())
    
    # 后台执行Agent任务
    background_tasks.add_task(
        execute_agent_task,
        task_id=task_id,
        query=request.query,
        user_id=current_user.get("id", "anonymous")
    )
    
    return TaskResponse(
        task_id=task_id,
        status="pending",
        message="任务已提交，正在处理中..."
    )


# ============================================
# 查询任务状态（HTTP轮询备用）
# ============================================
@router.get("/status/{task_id}", response_model=TaskResponse)
async def get_task_status(
    task_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    查询任务状态
    
    用于：
    - WebSocket不可用的降级方案
    - 页面刷新后恢复状态
    """
    # 从Redis查询任务状态
    redis = RedisService()
    task_data = await redis.get(f"task:{task_id}")
    
    if not task_data:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    
    return TaskResponse(**json.loads(task_data))


# ============================================
# WebSocket：实时推送
# ============================================
@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket):
    """
    WebSocket连接
    
    为什么用WebSocket？
    -------------------
    Agent执行是长流程，用户需要实时看到进度：
    - "Data Agent正在查询..."
    - "Analysis Agent分析完成"
    - "Report Agent生成中..."
    
    WebSocket让服务器能主动推送消息到客户端，
    比HTTP轮询更高效、更实时。
    
    消息协议：
    ---------
    客户端 → 服务器: {"type": "subscribe", "task_id": "xxx"}
    服务器 → 客户端: {"type": "agent_progress", "payload": {...}}
    服务器 → 客户端: {"type": "task_completed", "payload": {...}}
    客户端 → 服务器: {"type": "ping"}
    服务器 → 客户端: {"type": "pong"}
    """
    await websocket.accept()
    
    client_id = f"ws_{id(websocket)}"
    active_connections[client_id] = websocket
    
    try:
        while True:
            # 接收客户端消息
            data = await websocket.receive_text()
            message = json.loads(data)
            
            msg_type = message.get("type")
            
            if msg_type == "subscribe":
                # 订阅任务进度
                task_id = message.get("task_id")
                # 将WebSocket关联到task_id（用于推送）
                await websocket.send_json({
                    "type": "subscribed",
                    "task_id": task_id
                })
                
            elif msg_type == "ping":
                # 心跳响应
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
                
    except WebSocketDisconnect:
        print(f"WebSocket断开: {client_id}")
    except Exception as e:
        print(f"WebSocket错误: {e}")
    finally:
        active_connections.pop(client_id, None)


# ============================================
# 后台任务：执行Agent流程
# ============================================
async def execute_agent_task(task_id: str, query: str, user_id: str):
    """
    后台执行Agent任务
    
    这是真正的业务逻辑执行函数，在后台线程中运行。
    """
    try:
        # 更新状态：运行中
        await _update_task_status(task_id, "running", progress=0)
        
        # 执行Agent图
        result = run_analysis_task(
            user_query=query,
            thread_id=task_id
        )
        
        # 提取结果
        report = result.get("report")
        review = result.get("review_result")
        
        # 更新状态：完成
        await _update_task_status(
            task_id,
            "completed",
            progress=100,
            report=report.to_dict() if report else None,
            review_result=review.to_dict() if review else None
        )
        
        # 推送给订阅的客户端
        await _broadcast_to_task(task_id, {
            "type": "task_completed",
            "payload": {
                "task_id": task_id,
                "status": "completed",
                "report": report.to_dict() if report else None,
                "review_result": review.to_dict() if review else None
            }
        })
        
    except Exception as e:
        # 更新状态：失败
        await _update_task_status(task_id, "failed", error=str(e))
        await _broadcast_to_task(task_id, {
            "type": "error",
            "payload": {"task_id": task_id, "message": str(e)}
        })


async def _update_task_status(
    task_id: str,
    status: str,
    progress: int = 0,
    report: Optional[dict] = None,
    review_result: Optional[dict] = None,
    error: Optional[str] = None
):
    """更新任务状态到Redis"""
    redis = RedisService()
    data = {
        "task_id": task_id,
        "status": status,
        "progress": progress,
        "report": report,
        "review_result": review_result,
        "error": error,
        "updated_at": datetime.now().isoformat()
    }
    await redis.set(f"task:{task_id}", json.dumps(data), expire=3600)  # 1小时过期


async def _broadcast_to_task(task_id: str, message: dict):
    """向订阅了该任务的所有客户端推送消息"""
    # 简化版：实际应通过Redis Pub/Sub实现分布式推送
    for ws in active_connections.values():
        try:
            await ws.send_json(message)
        except Exception:
            pass


print("✅ backend/app/api/v1/chat.py 编写完成")
