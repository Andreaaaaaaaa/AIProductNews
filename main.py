import os
import requests
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from openai import OpenAI

# === 1. 配置区域 ===
WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_KEY")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")

# 初始化 DeepSeek 客户端
client = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

def fetch_readhub_news():
    """
    引擎 1：ReadHub API
    """
    print("🚀 [引擎1] 尝试连接 ReadHub...")
    api_url = "https://api.readhub.cn/topic?pageSize=20"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://readhub.cn",
        "Referer": "https://readhub.cn/"
    }
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if data:
                print(f"✅ ReadHub 成功获取 {len(data)} 条")
                return data
            else:
                print("⚠️ ReadHub 返回了空数据 (可能是 IP 被风控)")
        else:
            print(f"❌ ReadHub 请求失败: {response.status_code}")
    except Exception as e:
        print(f"❌ ReadHub 连接错误: {e}")
    return []

def fetch_36kr_rss():
    """
    引擎 2：36Kr RSS (备用方案，稳定性极高)
    """
    print("🔄 [引擎2] 启动备用电源：正在抓取 36Kr RSS...")
    rss_url = "https://36kr.com/feed"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(rss_url, headers=headers, timeout=15)
        if response.status_code == 200:
            # 解析 XML
            try:
                root = ET.fromstring(response.content)
                items = []
                # 36Kr 的 RSS 结构通常在 channel -> item 下
                for item in root.findall('./channel/item')[:20]: # 取前20条
                    title = item.find('title').text if item.find('title') is not None else "无标题"
                    link = item.find('link').text if item.find('link') is not None else ""
                    desc = item.find('description').text if item.find('description') is not None else ""
                    
                    # 构造和 ReadHub 一样的数据结构
                    items.append({
                        "id": link,
                        "title": title,
                        "summary": desc,
                        "url": link
                    })
                
                print(f"✅ 36Kr 成功获取 {len(items)} 条")
                return items
            except Exception as xml_e:
                print(f"❌ XML 解析失败: {xml_e}")
                return []
        else:
            print(f"❌ 36Kr 请求失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 36Kr 连接错误: {e}")
    return []

def process_news_with_ai(news_list):
    """
    第二步：智能大脑
    """
    print(f"🧠 AI 正在阅读 {len(news_list)} 条新闻并进行思考...")
    
    if not news_list:
        return []

    # 准备素材
    raw_data = []
    for item in news_list:
        raw_data.append({
            "title": item.get('title'),
            "summary": item.get('summary', '')[:150], # 进一步压缩摘要长度
            "url": item.get('url') or f"https://readhub.cn/topic/{item.get('id')}"
        })

    system_prompt = """
    你是一位【资深数据产品专家】。你的任务是从新闻列表中筛选出 3-5 条对“数据产品经理”最有价值的新闻。
    
    筛选标准：
    1. 优先选择：AI Agent、大模型应用、BI/数据分析工具更新、数字化转型案例。
    2. 严格排除：纯融资新闻、汽车发布会、无关的社会热点。

    输出要求：
    1. 重新撰写【标题】：简练、专业。
    2. 撰写【洞察】：一句话点评背后的产品逻辑或商业价值。
    3. 返回 JSON 列表：[{"title": "...", "comment": "...", "url": "..."}]
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"新闻数据：{json.dumps(raw_data, ensure_ascii=False)}"}
            ],
            response_format={ "type": "json_object" }, 
            temperature=0.3
        )
        
        content = response.choices[0].message.content
        
        # 清洗 Markdown 标记
        if content.startswith("```"):
            content = re.sub(r"^```json\s*|\s*```$", "", content, flags=re.MULTILINE)
        
        result = json.loads(content)
        
        # 兼容性处理
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
    第三步：推送
    """
    if not WEBHOOK_URL:
        print("❌ 错误：Webhook 未配置")
        return

    if not news_list:
        print("⚠️ AI 筛选后列表为空，跳过推送。")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    
    content_lines = [f"### 🤖 AI 数据产品日报 ({today})"]
    
    for idx, news in enumerate(news_list, 1):
        url = news.get('url', '#')
        title = news.get('title', '无标题')
        comment = news.get('comment', '暂无点评')
        
        content_lines.append(f"**{idx}. [{title}]({url})**")
        content_lines.append(f"><font color='info'>💡 {comment}</font>")
        content_lines.append("")

    data = {
        "msgtype": "markdown",
        "markdown": {
            "content": "\n".join(content_lines)
        }
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=data)
        print(f"✅ 推送完成！响应: {resp.text}")
    except Exception as e:
        print(f"❌ 推送出错: {e}")

if __name__ == "__main__":
    # === 主流程 ===
    
    # 1. 先试 ReadHub
    raw_news = fetch_readhub_news()
    
    # 2. 如果 ReadHub 挂了，试 36Kr
    if not raw_news:
        print("⚠️ ReadHub 数据为空，切换至 36Kr 源...")
        raw_news = fetch_36kr_rss()
        
    # 3. 如果有数据，交给 AI
    if raw_news:
        print(f"📦 最终获取到 {len(raw_news)} 条原始新闻")
        ai_news = process_news_with_ai(raw_news)
        
        if ai_news:
            print(f"💎 AI 筛选出 {len(ai_news)} 条精华，准备推送...")
            send_wecom(ai_news)
        else:
            print("⚠️ AI 认为今天的新闻都不太行，决定不打扰你。")
    else:
        print("❌ 所有数据源都挂了，请检查网络或 GitHub Actions 环境。")
