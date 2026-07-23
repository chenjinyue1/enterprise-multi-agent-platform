"""
# 月度运营报告模板

## 一、本月核心数据速览

| 指标 | 本月数值 | 上月数值 | 环比变化 |
|------|---------|---------|---------|
| GMV | {{gmv}}万 | {{last_gmv}}万 | {{gmv_change}}% |
| 订单量 | {{orders}}单 | {{last_orders}}单 | {{orders_change}}% |
| 客单价 | {{aov}}元 | {{last_aov}}元 | {{aov_change}}% |
| 转化率 | {{conversion}}% | {{last_conversion}}% | {{conversion_change}} |
| DAU | {{dau}} | {{last_dau}} | {{dau_change}}% |

## 二、流量分析

{{traffic_analysis}}

![流量来源占比](chart://traffic_pie)

## 三、用户行为分析

{{user_behavior}}

![用户行为漏斗](chart://user_funnel)

## 四、商品分析

{{product_analysis}}

![热销商品TOP10](chart://top_products)

## 五、问题与改进措施

{{issues_and_improvements}}

---

**报告生成时间**：{{generated_at}}
**数据口径**：全渠道（APP+小程序+Web）
"""

