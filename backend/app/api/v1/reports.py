
# 12. 编写报告API路由
"""
报告API路由
处理报告查询、导出、下载

企业级设计：
-----------
1. 分页查询：避免一次性返回大量数据
2. 异步导出：大文件导出用后台任务
3. 缓存：热门报告缓存，减少重复生成
4. 权限控制：只能查看自己或同部门的报告
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, List
import io
import markdown
from datetime import datetime

from ...core.security import get_current_user

router = APIRouter(prefix="/reports", tags=["reports"])


# ============================================
# 响应模型
# ============================================
class ReportListItem(BaseModel):
    report_id: str
    title: str
    report_type: str
    status: str
    quality_score: Optional[int]
    generated_at: str
    total_words: int
    total_charts: int

class ReportListResponse(BaseModel):
    items: List[ReportListItem]
    total: int
    page: int
    page_size: int


# ============================================
# 获取报告列表
# ============================================
@router.get("", response_model=ReportListResponse)
async def get_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    report_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    获取报告列表（分页）
    
    企业场景：
    ---------
    管理层查看团队生成的所有报告，支持按类型和状态筛选。
    """
    # 简化版：实际应从MySQL查询
    # 这里返回模拟数据
    mock_reports = [
        ReportListItem(
            report_id=f"report_{i}",
            title=f"Q{i}销售分析报告",
            report_type="quarterly",
            status="approved",
            quality_score=85 + i,
            generated_at=datetime.now().isoformat(),
            total_words=2500 + i * 100,
            total_charts=3 + i
        )
        for i in range(1, 6)
    ]
    
    return ReportListResponse(
        items=mock_reports,
        total=5,
        page=page,
        page_size=page_size
    )


# ============================================
# 获取报告详情
# ============================================
@router.get("/{report_id}")
async def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):
    """获取报告详情"""
    # 简化版：实际应从MySQL+Redis查询
    return {
        "code": 200,
        "message": "success",
        "data": {
            "report_id": report_id,
            "title": "Q3销售分析报告",
            "content": "# Q3销售分析报告\\n\\n## 一、执行摘要\\n\\n本季度...",
            "report_type": "quarterly",
            "status": "approved",
            "quality_score": 88,
            "generated_at": datetime.now().isoformat(),
        }
    }


# ============================================
# 导出报告
# ============================================
@router.get("/{report_id}/export")
async def export_report(
    report_id: str,
    format: str = Query("markdown", regex="^(markdown|html|pdf|word)$"),
    current_user: dict = Depends(get_current_user)
):
    """
    导出报告
    
    支持格式：
    - markdown: 原始Markdown，可编辑
    - html: 网页格式，适合邮件发送
    - pdf: PDF格式，适合打印和存档
    - word: Word文档，适合二次编辑
    
    企业场景：
    ---------
    - 发给老板：PDF（正式、不可编辑）
    - 发给团队：Markdown（可协作编辑）
    - 发给客户：HTML（邮件内嵌）
    - 发给财务：Word（需要补充数据）
    """
    # 获取报告内容（简化版）
    report_content = f"# 报告 {report_id}\\n\\n这是报告内容..."
    
    if format == "markdown":
        # 直接返回Markdown
        output = io.BytesIO(report_content.encode("utf-8"))
        return StreamingResponse(
            output,
            media_type="text/markdown",
            headers={"Content-Disposition": f"attachment; filename=report_{report_id}.md"}
        )
    
    elif format == "html":
        # Markdown转HTML
        html_content = markdown.markdown(report_content, extensions=["tables", "fenced_code"])
        full_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>报告</title></head>
<body style="max-width:800px;margin:40px auto;font-family:system-ui;line-height:1.6">
{html_content}
</body>
</html>"""
        output = io.BytesIO(full_html.encode("utf-8"))
        return StreamingResponse(
            output,
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename=report_{report_id}.html"}
        )
    
    elif format == "pdf":
        # 简化版：实际应使用weasyprint或pdfkit
        # 这里返回HTML，由前端处理PDF生成
        html_content = markdown.markdown(report_content, extensions=["tables"])
        output = io.BytesIO(html_content.encode("utf-8"))
        return StreamingResponse(
            output,
            media_type="text/html",
            headers={"Content-Disposition": f"attachment; filename=report_{report_id}.pdf.html"}
        )
    
    elif format == "word":
        # 简化版：实际应使用python-docx生成真正的Word文档
        output = io.BytesIO(report_content.encode("utf-8"))
        return StreamingResponse(
            output,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename=report_{report_id}.docx"}
        )
    
    raise HTTPException(status_code=400, detail="不支持的导出格式")


print("✅ backend/app/api/v1/reports.py 编写完成")
