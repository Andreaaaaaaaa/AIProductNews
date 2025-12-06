import os
import requests
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from openai import OpenAI

# === 1. 配置区域 ===
# ⚠️ 调试开关：True = 只打印不发送；False = 正式发送
DRY_RUN = True 

WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_KEY")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")

# 初始化 DeepSeek
client = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

# === RSS 抓取器 ===
def fetch_rss_data(rss_url):
    # 打印一下当前的 URL，确保它是纯净的
    print(f"🔄 正在连接优设网: {rss_url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    items = []
    try:
        response = requests.get(rss_url, headers=headers, timeout=15)
        if response.status_code == 200:
            try:
                root = ET.fromstring(response.content)
                nodes = root.findall('.//item')
                
                # 调试模式下只处理前 3 条
                limit = 3 if DRY_RUN else 15
                print(f"🧪 调试模式：处理前 {limit} 条" if DRY_RUN else f"🚀 正式模式：处理前 {limit} 条")

                for item in nodes[:limit]: 
                    title = item.find('title').text if item.find('title') is not None else "无标题"
                    link = item.find('link').text if item.find('link') is not None else ""
                    
                    desc = ""
                    desc_node = item.find('description')
                    if desc_node is not None and desc_node.text:
                        desc = re.sub(r'<[^>]+>', '', desc_node.text)
                    
                    if link and title:
                        items.append({
                            "title": title,
                            "original_summary": desc[:500],
                            "url": link
                        })
                
                print(f"✅ 成功获取 {len(items)} 条资讯")
                return items
            except Exception as e:
                print(f"❌ XML 解析失败: {e}")
        else:
            print(f"❌ 请求失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 网络错误 (可能是 URL 格式不对): {e}")
    
    return items

def process_news_with_ai(news_list):
    if not news_list: return []
        
    print(f"🧠 AI 正在提炼 {len(news_list)} 条资讯的重点...")
    
    # 构造 Prompt 素材
    input_data = [{"title": n["title"], "summary": n["original_summary"], "url": n["url"]} for n in news_list]
    raw_text = json.dumps(input_data, ensure_ascii=False)
    
    system_prompt = """
    你是一位【极简主义资讯编辑】。
    你的任务是重写新闻摘要。

    【处理要求】：
    1. **标题**：优化标题，使其更具吸引力。
    2. **摘要**：
       - 完全重写原文。
       - **极短**：严格控制在 30-50 字以内。
       - **直击重点**：直接说核心干货。
       - **严禁废话**：不要出现“本文介绍了”、“文章提到”等字眼。

    【输出格式】：
    必须返回 JSON 对象，且**必须保留原始 URL**：
    {
        "news": [
            {
                "title": "新标题",
                "summary": "极简摘要内容",
                "url": "原始URL(绝对不能改)"
            }
        ]
    }
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请处理：{raw_text}"}
            ],
            response_format={ "type": "json_object" }, 
            temperature=0.3
        )
        content = response.choices[0].message.content
        if content.startswith("```"): content = re.sub(r"^```json\s*|\s*```$", "", content, flags=re.MULTILINE)
        result = json.loads(content)
        
        if isinstance(result, dict) and "news" in result:
            return result["news"]
            
        return []
        
    except Exception as e:
        print(f"❌ AI 处理失败: {e}")
        return []

def send_wecom(news_list):
    if not news_list: return

    today = datetime.now().strftime("%m月%d日")
    content_lines = [f"### 🎨 优设灵感早报 ({today})"]
    
    for idx, news in enumerate(news_list, 1):
        title = news.get('title', '无标题')
        url = news.get('url', '#')
        summary = news.get('summary', '暂无介绍')
        
        content_lines.append(f"**{idx}. [{title}]({url})**")
        content_lines.append(f"> {summary}")
        content_lines.append("") 

    final_content = "\n".join(content_lines)

    # === 拦截逻辑 ===
    if DRY_RUN:
        print("\n" + "="*30)
        print("📢 [模拟发送] 看起来不错！正式内容如下：")
        print("="*30)
        print(final_content)
        print("="*30 + "\n")
        print("✅ 验证通过！未发送到企业微信。")
        return
    # ================

    if not WEBHOOK_URL: return
    
    data = {"msgtype": "markdown", "markdown": {"content": final_content}}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("✅ 推送成功")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    # 修正点：这里必须是纯净的字符串，不能有 [] 或 ()
    target_url = "[https://www.uisdc.com/news/feed](https://www.uisdc.com/news/feed)"
    
    raw_news = fetch_rss_data(target_url)
    
    if not raw_news:
        print("❌ 抓取失败")
    else:
        final_news = process_news_with_ai(raw_news)
        if final_news:
            send_wecom(final_news)
        else:
            print("⚠️ AI 未筛选出结果")
