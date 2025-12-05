import os
import requests
import json
import re
from datetime import datetime
from openai import OpenAI

# === 1. 配置区域 ===
WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_KEY")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="[https://api.deepseek.com](https://api.deepseek.com)"
)

def fetch_readhub_news():
    """
    第一步：搬运工
    抓取 ReadHub 数据，增加了【全套浏览器伪装】防止被拦截
    """
    print("🚀 正在从 ReadHub 进货...")
    # 去掉了 lastCursor 参数，直接请求最新数据
    api_url = "[https://api.readhub.cn/topic?pageSize=20](https://api.readhub.cn/topic?pageSize=20)"
    
    # 关键修改：补全了 Referer 和 Origin，这对很多 API 是必须的
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "[https://readhub.cn](https://readhub.cn)",
        "Referer": "[https://readhub.cn/](https://readhub.cn/)",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
    }
    
    try:
        # 使用 Session 对象可以稍微模拟更好一点的网络环境
        session = requests.Session()
        response = session.get(api_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            try:
                data = response.json()
                items = data.get('data', [])
                if not items:
                    print(f"⚠️ 警告：状态码 200，但数据列表为空。")
                    print(f"🕵️ 服务器返回原始内容片段: {response.text[:200]}")
                return items
            except json.JSONDecodeError:
                print(f"❌ 解析 JSON 失败，返回可能不是 JSON: {response.text[:100]}")
                return []
        else:
            print(f"❌ 抓取被拦截，状态码: {response.status_code}")
            print(f"❌ 错误详情: {response.text[:100]}")
    except Exception as e:
        print(f"❌ 网络请求出错: {e}")
    return []

def process_news_with_ai(news_list):
    """
    第二步：智能大脑
    让 DeepSeek 挑选并重写新闻
    """
    print(f"🧠 AI 正在阅读 {len(news_list)} 条新闻并进行思考...")
    
    if not news_list:
        return []

    # 准备素材
    raw_data = []
    for item in news_list:
        raw_data.append({
            "id": item.get('id'),
            "title": item.get('title'),
            "summary": item.get('summary', '')[:200],
            "url": f"[https://readhub.cn/topic/](https://readhub.cn/topic/){item.get('id')}"
        })

    system_prompt = """
    你是一位眼光毒辣的【资深数据产品专家】。
    你的任务是从给定的新闻列表中，筛选出 3-5 条对“数据产品经理”最有价值的新闻。
    
    筛选标准：
    1. 关注 AI 落地、BI 工具变革、大模型企业服务、数据分析新趋势。
    2. 坚决过滤掉娱乐八卦、无关的社会新闻、纯粹的硬件发布。

    处理要求：
    1. 【标题】：重写标题，要简练且专业，直击痛点。
    2. 【点评】：不要写摘要！要写“洞察”。用一句话告诉产品经理：这条新闻背后的商业逻辑是什么？或者对我们做产品有什么启发？风格要犀利、专业。
    3. 严格返回 JSON 格式列表：[{"title": "...", "comment": "...", "url": "..."}]
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"今日新闻列表数据：{json.dumps(raw_data, ensure_ascii=False)}"}
            ],
            response_format={ "type": "json_object" }, 
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        
        # === 增加清洗逻辑：防止 AI 返回 Markdown 代码块 ===
        if content.startswith("```"):
            content = re.sub(r"^```json\s*|\s*```$", "", content, flags=re.MULTILINE)
        
        result = json.loads(content)
        
        if isinstance(result, dict):
            for key in result:
                if isinstance(result[key], list):
                    return result[key]
        return result if isinstance(result, list) else []

    except Exception as e:
        print(f"❌ AI 处理失败: {e}")
        # 如果出错，打印一下 AI 返回了什么，方便调试
        print(f"AI 返回的原始内容: {content if 'content' in locals() else '无内容'}")
        return []

def send_wecom(news_list):
    """
    第三步：快递员
    发送最终简报到企业微信
    """
    if not WEBHOOK_URL:
        print("❌ 错误：Webhook 未配置")
        return

    if not
