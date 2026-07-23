
# 在Python交互式环境中测试
from app.graph.builder import run_analysis_task

result = run_analysis_task("帮我分析本月销售数据，生成月度运营报告")
print(result["report"].content)
