import os
import requests
import json
from datetime import datetime
from openai import OpenAI

# === 1. 配置区域 ===
# 从 GitHub Secrets 获取密钥
WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_KEY")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

def fetch_readhub_news():
    """
    第一步：搬运工
    抓取 ReadHub 数据，增加了【浏览器伪装】防止被拦截
    """
    print("🚀 正在从 ReadHub 进货...")
    api_url = "https://api.readhub.cn/topic?lastCursor=&pageSize=25"
    
    # 关键修改：加上伪装头，假装自己是 Chrome 浏览器
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(api_url, headers=headers, timeout=15)
        print(f"📡 ReadHub 响应状态码: {response.status_code}") # 调试用：200表示成功
        
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            print(f"❌ 抓取被拦截，状态码: {response.status_code}")
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

    # 准备喂给 AI 的素材，只保留必要信息以节省 Token
    raw_data = []
    for item in news_list:
        raw_data.append({
            "id": item.get('id'),
            "title": item.get('title'),
            "summary": item.get('summary', '')[:200], # 限制长度
            "url": f"https://readhub.cn/topic/{item.get('id')}"
        })

    # AI 的人设与指令
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
        result = json.loads(content)
        
        # 兼容处理各种 JSON 结构
        if isinstance(result, dict):
            for key in result:
                if isinstance(result[key], list):
                    return result[key]
        return result if isinstance(result, list) else []

    except Exception as e:
        print(f"❌ AI 处理失败: {e}")
        return []

def send_wecom(news_list):
    """
    第三步：快递员
    发送最终简报到企业微信
    """
    if not WEBHOOK_URL:
        print("❌ 错误：Webhook 未配置")
        return

    if not news_list:
        print("⚠️ AI 觉得今天没有什么值得看的新闻，跳过推送。")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    
    # 构建 Markdown 消息
    content_lines = [f"### 🧠 AI 数据产品内参 ({today})"]
    
    for idx, news in enumerate(news_list, 1):
        content_lines.append(f"**{idx}. [{news['title']}]({news['url']})**")
        content_lines.append(f"><font color='comment'>💡 {news['comment']}</font>")
        content_lines.append("") # 空一行增加阅读舒适度

    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": "\n".join(content_lines)
        }
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=data)
        print(f"✅ 推送完成！服务器响应: {resp.text}")
    except Exception as e:
        print(f"❌ 推送出错: {e}")

if __name__ == "__main__":
    # 1. 抓取
    raw_news = fetch_readhub_news()
    if raw_news:
        print(f"📦 成功抓取到 {len(raw_news)} 条原始新闻")
        
        # 2. AI 思考
        ai_news = process_news_with_ai(raw_news)
        if ai_news:
            print(f"💎 AI 筛选出 {len(ai_news)} 条精华")
            # 3. 推送
            send_wecom(ai_news)
        else:
            print("⚠️ AI 没筛选出合适的内容。")
    else:
        print("⚠️ 没有抓取到任何数据，请检查网络或源站状态。")
