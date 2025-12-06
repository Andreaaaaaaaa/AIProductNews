import os
import requests
import json
import re
from datetime import datetime
from openai import OpenAI
# 引入新朋友：BeautifulSoup (专门用来解析网页 HTML)
from bs4 import BeautifulSoup 

# === 1. 配置区域 ===
# ⚠️ 调试模式：True = 只打印不发送；False = 正式发送
DRY_RUN = True 

WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_KEY")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")

client = OpenAI(
    api_key=DEEPSEEK_KEY,
    base_url="https://api.deepseek.com"
)

# === 2. 网页爬虫抓取器 (针对 HTML) ===
def fetch_uisdc_news_html():
    target_url = "https://www.uisdc.com/news"
    print(f"🔄 正在像浏览器一样访问: {target_url}")
    
    headers = {
        # 必须伪装成浏览器，否则优设可能会拦截
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.uisdc.com/",
        "Accept-Language": "zh-CN,zh;q=0.9"
    }
    
    items = []
    try:
        response = requests.get(target_url, headers=headers, timeout=15)
        response.encoding = 'utf-8' # 强制使用 utf-8 防止乱码
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # === 🕵️‍♂️ 页面结构定位 (核心逻辑) ===
            # 优设读报的结构通常是 .news-list 下的 .item 或者直接是 article 标签
            # 我们尝试查找页面上所有带有 "读报" 特征的列表，或者直接找文章标题
            
            # 策略1：查找 .news-item (最常见的设计类网站命名)
            # 策略2：查找 h2 或 h3 标签中包含链接的
            
            # 这里使用更稳健的查找：找到主要内容区域，然后提取标题
            # 假设优设的新闻标题在 h3 或 h2 标签里
            news_nodes = soup.find_all(['h3', 'h2'])
            
            count = 0
            for node in news_nodes:
                if count >= 8: break # 这里的“读报”可能很多，我们只取前8条最新的
                
                link_tag = node.find('a')
                if not link_tag: continue
                
                title = link_tag.get_text(strip=True)
                href = link_tag.get('href')
                
                # 过滤掉无效的、或者不是新闻的标题 (比如侧边栏广告)
                if len(title) < 5: continue 
                
                # 尝试抓取紧跟在标题后面的描述 (通常是 <p>)
                desc = ""
                parent = node.parent
                desc_node = parent.find('p')
                if desc_node:
                    desc = desc_node.get_text(strip=True)
                
                # 优设的链接有时是相对路径，处理一下
                if href and not href.startswith('http'):
                    href = f"https://www.uisdc.com{href}"
                    
                if title and href:
                    items.append({
                        "title": title,
                        "original_summary": desc[:200], # 截取前200字给AI
                        "url": href
                    })
                    count += 1
            
            print(f"✅ 成功从页面解析出 {len(items)} 条新闻")
            return items
        else:
            print(f"❌ 页面请求失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 爬虫发生错误: {e}")
    
    return items

# === 3. AI 处理逻辑 ===
def process_news_with_ai(news_list):
    if not news_list: return []
    
    print(f"🧠 AI 正在阅读并提炼 {len(news_list)} 条新闻...")
    
    input_data = [{"title": n["title"], "summary": n["original_summary"], "url": n["url"]} for n in news_list]
    raw_text = json.dumps(input_data, ensure_ascii=False)
    
    system_prompt = """
    你是一位【极简资讯编辑】。你的任务是重写优设读报的摘要。
    
    【处理要求】：
    1. **标题**：优化标题，使其更吸引设计师。
    2. **摘要**：
       - **完全重写**原文。
       - **极短**：控制在 30-40 字以内。
       - **直击重点**：直接说这个工具或新闻对设计师有什么用。
       - **保留 URL**：必须原样返回 URL。

    【输出格式】：
    {
        "news": [
            {
                "title": "新标题",
                "summary": "极简摘要",
                "url": "原始URL"
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
        
        if isinstance(result, dict):
            if "news" in result: return result["news"]
            for k, v in result.items():
                if isinstance(v, list): return v
        return []
    except Exception as e:
        print(f"❌ AI 处理失败: {e}")
        return []

# === 4. 推送逻辑 ===
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

    if DRY_RUN:
        print("\n" + "="*30)
        print("📢 [模拟发送] 最终效果如下：")
        print("="*30)
        print(final_content)
        print("="*30 + "\n")
        return

    if not WEBHOOK_URL: return
    data = {"msgtype": "markdown", "markdown": {"content": final_content}}
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("✅ 推送成功")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    # 1. 爬取 HTML
    raw_news = fetch_uisdc_news_html()
    
    if not raw_news:
        print("❌ 没抓到任何新闻，可能是优设网改版了 HTML 结构")
    else:
        # 2. AI 润色
        final_news = process_news_with_ai(raw_news)
        if final_news:
            send_wecom(final_news)
        else:
            print("⚠️ AI 未筛选出结果")
