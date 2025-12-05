import os
import requests
import json
from datetime import datetime
from openai import OpenAI

# === 配置区域 ===
# 1. 获取密钥 (必须在 GitHub Secrets 中配置)
WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_KEY")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")

# 2. 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

def fetch_readhub_news():
    """1. 搬运工：抓取 ReadHub 原始数据"""
    print("正在从 ReadHub 进货...")
    api_url = "https://api.readhub.cn/topic?lastCursor=&pageSize=25" # 多抓点，给 AI 更多选择空间
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            return response.json().get('data', [])
    except Exception as e:
        print(f"ReadHub 抓取失败: {e}")
    return []

def process_news_with_ai(news_list):
    """2. 核心大脑：让 DeepSeek 挑选并重写新闻"""
    print("AI 正在阅读并思考...")
    
    if not news_list:
        return []

    # 准备喂给 AI 的素材，只保留必要信息以节省 Token
    raw_data = []
    for item in news_list:
        raw_data.append({
            "id": item.get('id'),
            "title": item.get('title'),
            "summary": item.get('summary', '')[:200], # 限制长度
            "url": f"https://readhub.cn/topic/{item.get('id')}"
        })

    # AI 的人设与指令 (Prompt Engineering)
    system_prompt = """
    你是一位眼光毒辣的【资深数据产品专家和产品体验设计师】。
    你的任务是从给定的新闻列表中，筛选出 3-5 条对“数据产品经理”“数据产品体验设计师”最有价值的新闻。
    
    筛选标准：
    1. 关注 AI 落地、BI 工具变革、大模型企业服务、数据分析新趋势、数据产品交互变革、AI Agent。
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
            response_format={ "type": "json_object" }, # 强制 JSON 格式，防止 AI 乱说话
            temperature=0.3 # 保持理性
        )
        
        content = response.choices[0].message.content
        # 有时候 AI 可能会包一层 key，做一下防御性解析
        result = json.loads(content)
        
        # 兼容处理：如果 AI 返回的是 {"news": [...]} 格式
        if isinstance(result, dict):
            for key in result:
                if isinstance(result[key], list):
                    return result[key]
        return result if isinstance(result, list) else []

    except Exception as e:
        print(f"AI 处理失败: {e}")
        return []

def send_wecom(news_list):
    """3. 快递员：发送最终简报"""
    if not WEBHOOK_URL:
        print("错误：Webhook 未配置")
        return

    if not news_list:
        print("AI 觉得今天没有什么值得看的新闻。")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    
    # 这里的文案风格也可以改
    content_lines = [f"### 🧠 AI 数据产品内参 ({today})"]
    
    for idx, news in enumerate(news_list, 1):
        content_lines.append(f"**{idx}. [{news['title']}]({news['url']})**")
        # 引用部分变成了 AI 的“毒舌点评”
        content_lines.append(f"><font color='comment'>💡 {news['comment']}</font>")
        content_lines.append("") # 空一行，呼吸感

    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": "\n".join(content_lines)
        }
    }

    requests.post(WEBHOOK_URL, json=data)
    print("推送完成！")

if __name__ == "__main__":
    # 1. 抓取
    raw_news = fetch_readhub_news()
    print(f"抓取到 {len(raw_news)} 条原始新闻")
    
    # 2. AI 思考
    if raw_news:
        ai_news = process_news_with_ai(raw_news)
        print(f"AI 筛选出 {len(ai_news)} 条精华")
        
        # 3. 推送
        send_wecom(ai_news)
