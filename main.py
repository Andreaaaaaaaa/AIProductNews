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

# 初始化 DeepSeek
client = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

# === RSS 抓取器 ===
def fetch_rss_data(rss_url):
    print(f"🔄 正在连接优设网 (UISDC)...")
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
                
                for item in nodes[:15]: 
                    title = item.find('title').text if item.find('title') is not None else "无标题"
                    link = item.find('link').text if item.find('link') is not None else ""
                    
                    desc = ""
                    desc_node = item.find('description')
                    if desc_node is not None and desc_node.text:
                        desc = re.sub(r'<[^>]+>', '', desc_node.text) # 去除 HTML 标签
                    
                    if link and title:
                        items.append({
                            "title": title,
                            "original_summary": desc[:500], # 把原文描述传给 AI 参考
                            "url": link
                        })
                
                print(f"✅ 成功获取 {len(items)} 条优设资讯")
                return items
            except Exception as e:
                print(f"❌ XML 解析失败: {e}")
        else:
            print(f"❌ 请求失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 网络错误: {e}")
    
    return items

def process_news_with_ai(news_list):
    """
    AI 筛选与摘要重写
    """
    if not news_list: return []
        
    print(f"🧠 AI 正在提炼 {len(news_list)} 条资讯的重点...")
    
    # 构造 Prompt 素材
    # 只传必要的字段给 AI，节省 Token
    input_data = [{"title": n["title"], "summary": n["original_summary"]} for n in news_list]
    raw_text = json.dumps(input_data, ensure_ascii=False)
    
    # === 核心修改：让 AI 做“极简摘要” ===
    system_prompt = """
    你是一位【极简主义资讯编辑】。
    你的任务是从优设网的资讯中，筛选出 4-6 条最有价值的内容（关注 AI 设计、交互趋势、效率工具）。

    【处理要求】：
    1. **标题**：优化标题，使其更具吸引力且清晰。
    2. **摘要（summary）**：
       - **完全重写**原文描述。
       - **要求极短**：控制在 30-50 字以内。
       - **直击重点**：直接说这个工具能干什么，或者这篇文章讲了什么核心技巧。
       - **拒绝废话**：不要写“这篇文章介绍了...”、“本文通过...”。直接上干货。

    【输出格式】：
    返回包含 `news` 字段的 JSON 对象。
    示例：
    {
        "news": [
            {
                "title": "Figma 新版自动布局实战技巧",
                "summary": "新增的换行功能解决了多行卡片排版的痛点，配合绝对定位可实现更复杂的响应式布局。",
                "url": "（这里不用填，代码会自动匹配）"
            }
        ]
    }
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请处理以下资讯：{raw_text}"}
            ],
            response_format={ "type": "json_object" }, 
            temperature=0.3
        )
        content = response.choices[0].message.content
        
        if content.startswith("```"):
            content = re.sub(r"^```json\s*|\s*```$", "", content, flags=re.MULTILINE)
            
        result = json.loads(content)
        ai_items = []
        
        if isinstance(result, dict):
            if "news" in result and isinstance(result["news"], list):
                ai_items = result["news"]
            else:
                for k, v in result.items():
                    if isinstance(v, list): ai_items = v; break
        
        # === 关键步骤：把 AI 返回的结果和原始 URL 拼回去 ===
        # 因为 AI 有时会把 URL 弄丢或者编造，所以我们用“标题匹配”或者“顺序匹配”的方式把 URL 找回来
        # 这里采用简单的“原文标题匹配法”来找回 URL（如果 AI 改了标题，可能匹配不上，所以我们用更稳妥的索引匹配）
        
        # 修正策略：让 AI 只需要返回 title 和 summary，我们根据顺序或模糊匹配找回 URL 比较麻烦。
        # 最简单的办法：Prompt 里不传 URL，但实际上很难一一对应。
        # 更好的办法：直接在 Python 里处理。
        
        # 重新整理逻辑：AI 返回的列表其实是基于输入的子集。
        # 为了 URL 不丢，我们得稍微改一下 Prompt 让 AI 必须把原始标题（或部分特征）带回来方便我们匹配，
        # 或者更简单粗暴 —— 我们信任 AI 按顺序筛选？不，筛选会导致顺序打乱。
        
        # 终极方案：把 URL 喂给 AI，让它原样吐出来。
        # 重新构造 input_data 包含 url
        input_data_with_url = [{"title": n["title"], "summary": n["original_summary"], "url": n["url"]} for n in news_list]
        raw_text_full = json.dumps(input_data_with_url, ensure_ascii=False)
        
        # 重新请求（Prompt 稍微调整一下，要求保留 URL）
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt + "\n\n【重要】：输出的 JSON 中必须包含原始的 `url` 字段，绝对不能改动 URL！"},
                {"role": "user", "content": f"请处理：{raw_text_full}"}
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
    if not WEBHOOK_URL: return
    if not news_list: return

    today = datetime.now().strftime("%m月%d日")
    
    content_lines = [f"### 🎨 优设灵感早报 ({today})"]
    
    for idx, news in enumerate(news_list, 1):
        title = news.get('title', '无标题')
        url = news.get('url', '#')
        summary = news.get('summary', '暂无介绍') # 这里已经是 AI 重写过的短描述了
        
        # 格式调整：
        # 1. 标题 (链接)
        # > 简短描述
        content_lines.append(f"**{idx}. [{title}]({url})**")
        content_lines.append(f"> {summary}")  # 纯净的引用块，没有 emoji，没有“点评”字样
        content_lines.append("") 

    data = {"msgtype": "markdown", "markdown": {"content": "\n".join(content_lines)}}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("✅ 推送成功")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    raw_news = fetch_rss_data("https://www.uisdc.com/news/feed")
    
    if not raw_news:
        print("❌ 抓取失败")
    else:
        final_news = process_news_with_ai(raw_news)
        if final_news:
            send_wecom(final_news)
        else:
            print("⚠️ AI 未筛选出结果")
