import os
import requests
import json
from datetime import datetime

# 从 GitHub Secrets 中读取 Webhook 地址，更安全
WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_KEY")

# 关键词过滤：只有包含这些词的新闻才会被推送
KEYWORDS = ["AI", "大模型", "GPT", "Copilot", "数据", "DeepMind", "OpenAI", "分析", "趋势"]

def fetch_readhub_news():
    """抓取 ReadHub 热门话题"""
    print("正在抓取 ReadHub 数据...")
    api_url = "https://api.readhub.cn/topic?lastCursor=&pageSize=20"
    try:
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            return response.json().get('data', [])
    except Exception as e:
        print(f"抓取失败: {e}")
    return []

def filter_news(news_list):
    """筛选包含关键词的新闻"""
    target_news = []
    for item in news_list:
        title = item.get('title', '')
        summary = item.get('summary', '')
        # 只要标题或摘要里包含任一关键词
        if any(k.lower() in (title + summary).lower() for k in KEYWORDS):
            target_news.append({
                "title": title,
                "summary": summary[:80] + "...", # 摘要截取前80字
                "url": f"https://readhub.cn/topic/{item.get('id')}"
            })
    return target_news

def send_wecom(news_list):
    """发送消息到企业微信"""
    if not WEBHOOK_URL:
        print("错误：未找到 Webhook 地址，请检查 GitHub Secrets 配置！")
        return

    if not news_list:
        print("今日无相关关键词新闻，跳过推送。")
        return

    # 获取当前日期
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 构建 Markdown 消息
    content_lines = [f"### 🤖 AI & 数据产品日报 ({today})"]
    for idx, news in enumerate(news_list[:5], 1): # 限制最多发5条
        content_lines.append(f"**{idx}. [{news['title']}]({news['url']})**")
        content_lines.append(f"><font color='comment'>{news['summary']}</font>")
    
    # 底部加一个小尾巴
    content_lines.append(f"\n_来自 GitHub Actions 自动推送_") 

    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": "\n".join(content_lines)
        }
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=data)
        print(f"推送结果: {resp.text}")
    except Exception as e:
        print(f"推送出错: {e}")

if __name__ == "__main__":
    news = fetch_readhub_news()
    filtered_news = filter_news(news)
    print(f"抓取到 {len(news)} 条，筛选出 {len(filtered_news)} 条")
    send_wecom(filtered_news)
