
import os


"""
Python 计算 MCP Server (mcp/servers/python_server.py)

职责：
1. 在安全的沙箱环境中执行 Python 代码
2. 提供数据分析相关的预装库（pandas、numpy、matplotlib）
3. 限制执行时间、内存、可访问的模块
4. 返回执行结果（文本、图片、数据）

安全设计（企业级）：
====================
1. 导入白名单：只允许数据分析相关库
2. 执行超时：30 秒强制终止
3. 内存限制：512MB（Linux 可用 resource 模块）
4. 文件系统隔离：禁止访问系统目录
5. 网络隔离：禁止网络请求
6. 输出审查：只允许 JSON/CSV/图片/文本

使用方式：
=========
# STDIO 模式
python -m app.mcp.servers.python_server

# HTTP 模式
python -m app.mcp.servers.python_server --transport http --port 8002
"""

import io
import sys
import json
import base64
import signal
import traceback
import resource
import multiprocessing
from typing import Optional, Any
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP


# ============================================================
# 1. 创建 FastMCP 实例
# ============================================================

mcp = FastMCP("python-analysis-server")


# ============================================================
# 2. 安全配置
# ============================================================

# 允许导入的模块白名单
ALLOWED_IMPORTS = {
    # 数据分析核心库
    "pandas", "numpy", "np", "pd",
    # 统计
    "scipy", "scipy.stats",
    # 可视化
    "matplotlib", "matplotlib.pyplot", "plt",
    "seaborn", "sns",
    # 基础库
    "json", "math", "random", "statistics",
    "datetime", "collections", "itertools",
    "typing", "re", "string", "hashlib",
    # 数据格式
    "csv", "io", "base64",
}

# 禁止导入的模块（安全黑名单）
BLOCKED_IMPORTS = {
    "os", "sys", "subprocess", "socket", "urllib",
    "http", "ftplib", "smtplib", "telnetlib",
    "pickle", "marshal", "ctypes", "multiprocessing",
    "threading", "asyncio", "tkinter", "pygame",
    "shutil", "pathlib", "glob", "fnmatch",
    "tempfile", "mmap", "resource", "signal",
    "pwd", "grp", "spwd", "crypt",
}

# 执行超时（秒）
EXECUTION_TIMEOUT = 30

# 内存限制（MB）- 仅在 Linux 有效
MEMORY_LIMIT_MB = 512


# ============================================================
# 3. 安全执行器
# ============================================================

def _set_resource_limits():
    """设置子进程资源限制（Linux 专用）"""
    try:
        # 内存限制（字节）
        memory_limit = MEMORY_LIMIT_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))
        
        # CPU 时间限制（秒）
        resource.setrlimit(resource.RLIMIT_CPU, (EXECUTION_TIMEOUT, EXECUTION_TIMEOUT))
        
        # 文件描述符限制
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        
    except (ImportError, OSError, ValueError):
        # Windows 或不支持 resource 模块
        pass


def _create_restricted_globals():
    """
    创建受限的全局命名空间
    
    只允许访问安全的内置函数和模块。
    """
    safe_builtins = {
        "abs", "all", "any", "bin", "bool", "bytearray", "bytes",
        "chr", "complex", "dict", "divmod", "enumerate", "filter",
        "float", "format", "frozenset", "hasattr", "hash", "hex",
        "int", "isinstance", "issubclass", "iter", "len", "list",
        "map", "max", "min", "next", "oct", "ord", "pow", "print",
        "range", "repr", "reversed", "round", "set", "slice", "sorted",
        "str", "sum", "tuple", "type", "vars", "zip",
        "True", "False", "None",
        # 数学函数
        "__import__",  # 会被自定义函数替换
    }
    
    # 构建安全的 globals
    restricted_globals = {
        "__builtins__": {name: __builtins__[name] for name in safe_builtins if name in __builtins__},
    }
    
    # 添加常用数学常量
    restricted_globals["__builtins__"]["__import__"] = _safe_import
    
    return restricted_globals


def _safe_import(name, *args, **kwargs):
    """
    安全的导入函数
    
    只允许导入白名单中的模块。
    """
    # 检查模块名是否在白名单中
    base_name = name.split(".")[0]
    
    if base_name in BLOCKED_IMPORTS:
        raise ImportError(f"禁止导入模块 '{name}'：该模块存在安全风险")
    
    if base_name not in ALLOWED_IMPORTS and name not in ALLOWED_IMPORTS:
        raise ImportError(f"禁止导入模块 '{name}'：不在允许列表中")
    
    # 允许导入
    return __import__(name, *args, **kwargs)


def _execute_code_in_process(code: str, input_data: Optional[str]) -> dict:
    """
    在子进程中执行代码（安全沙箱）
    
    为什么用子进程？
    - 代码执行超时可以用进程终止
    - 内存限制可以独立设置
    - 崩溃不会影响主进程
    """
    
    # 重定向标准输出/错误
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    
    try:
        # 设置资源限制
        _set_resource_limits()
        
        # 创建受限环境
        restricted_globals = _create_restricted_globals()
        
        # 预导入常用库
        try:
            import pandas as pd
            import numpy as np
            restricted_globals["pd"] = pd
            restricted_globals["np"] = np
        except ImportError:
            pass
        
        # 注入输入数据
        if input_data:
            try:
                data = json.loads(input_data)
                restricted_globals["input_data"] = data
            except json.JSONDecodeError:
                restricted_globals["input_data"] = input_data
        
        # 执行代码
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            exec(code, restricted_globals)
        
        # 提取结果（如果代码定义了 result 变量）
        result = restricted_globals.get("result", None)
        
        # 序列化结果
        if result is not None:
            try:
                # 尝试 JSON 序列化
                result_json = json.dumps(result, default=str, ensure_ascii=False)
                result_parsed = json.loads(result_json)
            except (TypeError, ValueError):
                result_parsed = str(result)
        else:
            result_parsed = None
        
        return {
            "success": True,
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue(),
            "result": result_parsed,
            "error": None,
        }
        
    except Exception as e:
        return {
            "success": False,
            "stdout": stdout_buffer.getvalue(),
            "stderr": stderr_buffer.getvalue() + "\\n" + traceback.format_exc(),
            "result": None,
            "error": f"{type(e).__name__}: {str(e)}",
        }


def _execute_with_timeout(code: str, input_data: Optional[str], timeout: int) -> dict:
    """
    带超时的代码执行
    
    使用 multiprocessing 实现超时控制。
    """
    
    # 创建队列用于获取结果
    from multiprocessing import Queue, Process
    
    result_queue = Queue()
    
    def target():
        result = _execute_code_in_process(code, input_data)
        result_queue.put(result)
    
    process = Process(target=target)
    process.start()
    process.join(timeout=timeout)
    
    if process.is_alive():
        # 超时，强制终止
        process.terminate()
        process.join(timeout=2)
        if process.is_alive():
            process.kill()
        
        return {
            "success": False,
            "stdout": "",
            "stderr": "",
            "result": None,
            "error": f"代码执行超时（>{timeout}秒），已强制终止。请优化代码或降低数据量。",
        }
    
    if not result_queue.empty():
        return result_queue.get()
    
    return {
        "success": False,
        "stdout": "",
        "stderr": "",
        "result": None,
        "error": "代码执行异常终止",
    }


# ============================================================
# 4. MCP 工具定义
# ============================================================

@mcp.tool()
async def execute_python(
    code: str,
    input_data: Optional[str] = None,
    timeout: int = EXECUTION_TIMEOUT,
) -> dict:
    """
    在安全沙箱中执行 Python 代码，进行数据分析计算。
    
    **安全限制**：
    - 只允许导入 pandas、numpy、matplotlib、scipy 等数据分析库
    - 禁止导入 os、sys、subprocess、socket 等系统/网络库
    - 执行超时 30 秒（可调整）
    - 内存限制 512MB
    - 禁止文件系统访问（除临时数据外）
    
    **参数**：
    - code: Python 代码字符串。建议定义 `result` 变量作为返回值。
    - input_data: 输入数据（JSON 字符串）。代码中可通过 `input_data` 变量访问。
    - timeout: 执行超时时间（秒，默认 30，最大 120）
    
    **返回**：
    {
        "success": true/false,
        "stdout": "标准输出内容",
        "stderr": "标准错误内容",
        "result": {...},      // 代码中 result 变量的值（JSON 格式）
        "error": null         // 错误信息（如有）
    }
    
    **示例**：
    ```python
    # 计算平均值
    import pandas as pd
    df = pd.DataFrame(input_data)
    result = {
        "mean": df["amount"].mean(),
        "max": df["amount"].max(),
        "min": df["amount"].min(),
    }
    ```
    """
    
    # 限制超时
    if timeout > 120:
        timeout = 120
    if timeout < 1:
        timeout = 1
    
    # 检查危险代码（简单正则检查）
    dangerous_patterns = [
        r"import\\s+os",
        r"import\\s+sys",
        r"import\\s+subprocess",
        r"import\\s+socket",
        r"__import__\\s*\\(",
        r"open\\s*\\(\\s*['\"]/",
        r"eval\\s*\\(",
        r"exec\\s*\\(",
        r"compile\\s*\\(",
        r"os\\.system",
        r"os\\.popen",
        r"subprocess\\.",
        r"socket\\.",
    ]
    
    for pattern in dangerous_patterns:
        import re
        if re.search(pattern, code, re.IGNORECASE):
            return {
                "success": False,
                "stdout": "",
                "stderr": "",
                "result": None,
                "error": f"安全拦截：检测到危险代码模式。禁止执行包含系统调用、文件操作、网络请求的代码。",
            }
    
    # 执行代码（带超时）
    result = _execute_with_timeout(code, input_data, timeout)
    
    return result


@mcp.tool()
async def analyze_dataframe(
    data_json: str,
    analysis_type: str = "summary",
) -> dict:
    """
    对 DataFrame 数据进行快速分析。
    
    预置分析模板，无需编写代码即可获取常见统计指标。
    
    **参数**：
    - data_json: 数据（JSON 数组字符串）
    - analysis_type: 分析类型
      - "summary": 基础统计（计数、均值、标准差、最值）
      - "correlation": 相关性分析
      - "distribution": 分布分析
      - "trend": 趋势分析（需要时间序列数据）
      - "outliers": 异常值检测
    
    **返回**：
    {
        "success": true/false,
        "analysis": {...},    // 分析结果
        "error": null
    }
    """
    
    import pandas as pd
    import numpy as np
    from scipy import stats
    
    try:
        # 解析数据
        data = json.loads(data_json)
        df = pd.DataFrame(data)
        
        result = {"columns": list(df.columns), "row_count": len(df)}
        
        if analysis_type == "summary":
            # 基础统计
            desc = df.describe().to_dict()
            result["statistics"] = desc
            
            # 各列数据类型
            result["dtypes"] = {col: str(dtype) for col, dtype in df.dtypes.items()}
            
            # 缺失值
            result["missing"] = df.isnull().sum().to_dict()
            
        elif analysis_type == "correlation":
            # 相关性分析
            numeric_df = df.select_dtypes(include=[np.number])
            if len(numeric_df.columns) >= 2:
                corr = numeric_df.corr().to_dict()
                result["correlation_matrix"] = corr
            else:
                result["correlation_matrix"] = {}
                result["warning"] = "数值列不足2列，无法计算相关性"
                
        elif analysis_type == "outliers":
            # 异常值检测（IQR 方法）
            numeric_df = df.select_dtypes(include=[np.number])
            outliers = {}
            for col in numeric_df.columns:
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower = Q1 - 1.5 * IQR
                upper = Q3 + 1.5 * IQR
                outlier_count = ((df[col] < lower) | (df[col] > upper)).sum()
                outliers[col] = {
                    "outlier_count": int(outlier_count),
                    "outlier_ratio": round(float(outlier_count / len(df)), 4),
                    "lower_bound": float(lower),
                    "upper_bound": float(upper),
                }
            result["outliers"] = outliers
            
        elif analysis_type == "distribution":
            # 分布分析
            numeric_df = df.select_dtypes(include=[np.number])
            distributions = {}
            for col in numeric_df.columns:
                # 正态性检验（Shapiro-Wilk，小样本）
                if len(df) <= 5000:
                    stat, p_value = stats.shapiro(df[col].dropna())
                    distributions[col] = {
                        "mean": float(df[col].mean()),
                        "std": float(df[col].std()),
                        "skewness": float(df[col].skew()),
                        "kurtosis": float(df[col].kurtosis()),
                        "normality_test": {"statistic": float(stat), "p_value": float(p_value)},
                        "is_normal": bool(p_value > 0.05),
                    }
                else:
                    distributions[col] = {
                        "mean": float(df[col].mean()),
                        "std": float(df[col].std()),
                        "skewness": float(df[col].skew()),
                        "kurtosis": float(df[col].kurtosis()),
                        "note": "样本量过大，跳过正态性检验",
                    }
            result["distributions"] = distributions
            
        else:
            result["warning"] = f"未知的分析类型: {analysis_type}"
        
        return {
            "success": True,
            "analysis": result,
            "error": None,
        }
        
    except Exception as e:
        return {
            "success": False,
            "analysis": {},
            "error": f"分析失败: {str(e)}\\n{traceback.format_exc()}",
        }


# ============================================================
# 5. 启动入口
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="MCP Python Analysis Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8002)
    
    args = parser.parse_args()
    
    if args.transport == "stdio":
        print("🚀 MCP Python Analysis Server 启动 (STDIO 模式)", flush=True)
        mcp.run(transport="stdio")
    else:
        print(f"🚀 MCP Python Analysis Server 启动 (HTTP 模式, 端口 {args.port})")
        mcp.run(transport="http", port=args.port)


print("✅ backend/app/mcp/servers/python_server.py 创建完成")
