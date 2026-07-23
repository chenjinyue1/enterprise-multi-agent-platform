
# 8. 创建示例报告模板
"""
# 季度销售分析报告模板

## 一、执行摘要

本季度销售总体表现{{summary}}。核心指标如下：
- 总销售额：{{total_sales}}万元
- 同比增长：{{yoy_growth}}%
- 环比增长：{{mom_growth}}%
- 达成率：{{achievement_rate}}%

## 二、各品类销售分析

{{category_analysis}}

### 2.1 品类排名

| 排名 | 品类 | 销售额(万元) | 占比 | 同比 |
|------|------|-------------|------|------|
{{category_table}}

## 三、区域销售分布

{{region_analysis}}

### 3.1 区域热力图

![区域销售热力图](chart://region_heatmap)

## 四、时间趋势分析

{{trend_analysis}}

### 4.1 月度趋势

![月度销售趋势](chart://monthly_trend)

## 五、关键发现与建议

### 5.1 核心发现
{{key_findings}}

### 5.2 行动建议
{{action_items}}

## 六、下季度展望

{{outlook}}

---

**报告生成时间**：{{generated_at}}
**数据来源**：企业数据仓库（MySQL）
**数据周期**：{{data_period}}
"""


