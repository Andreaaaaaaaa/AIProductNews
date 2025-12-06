import os
import requests
import json
import re
import time
from datetime import datetime
from openai import OpenAI
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# === 1. 配置区域 ===
# ⚠️ 调试模式：True = 只打印不发送；False = 正式发送
# 验证通过后，记得改成 False
DRY_RUN = True

WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_KEY")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")

if DEEPSEEK_KEY:
    client = OpenAI(
        api_key=DEEPSEEK_KEY,
        base_url="https://api.deepseek.com"
    )
else:
    client = None
    print("⚠️ Warning: DEEPSEEK_API_KEY not set. AI processing will skipped or fail.")

# === 2. 网页爬虫 (Selenium Version) ===
def fetch_uisdc_news_html():
    target_url = "https://www.uisdc.com/news"
    
    # Configure Headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1920,1080")
    # Mimic a real user agent to avoid being blocked
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        print(f"🔄 Launching Browser for {target_url}...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(target_url)
        
        # Wait for the Dubao items to load (dynamic content)
        # We wait up to 15 seconds for .dubao-item to appear
        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CLASS_NAME, "dubao-item"))
            )
            print("✅ Dynamic content loaded.")
        except Exception:
            print("⚠️ Timeout waiting for .dubao-item. Page might have changed or loaded slowly.")

        # Get the page source after JS execution
        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Target Dubao items
        news_items = soup.select('.dubao-item')
        
        if not news_items:
            print("⚠️ Still did not find .dubao-item after JS wait.")
            return []

        # User request: Limit to top 20 items
        news_items = news_items[:20]
        print(f"✅ Found {len(news_items)} items. Processing...")

        valid_news = []
        
        for item in news_items:
            # Title: .dubao-title
            title_tag = item.select_one('.dubao-title')
            if title_tag:
                num_tag = title_tag.select_one('.num')
                if num_tag:
                    num_tag.decompose()
                title = title_tag.get_text(strip=True)
            else:
                title = ""
            
            # Content: .dubao-content
            content_tag = item.select_one('.dubao-content')
            summary = content_tag.get_text(strip=True) if content_tag else ""
            
            # --- FILTERING LOGIC ---
            # Strictly exclude "优设"
            if "优设" in title or "优设" in summary:
                print(f"🚫 Filtered (contains 优设): {title}")
                continue
                
            # Basic validation
            if title:
                # User requested NO LINKS. We store only Title and Summary.
                # We do NOT scrape the URL anymore as it's not needed for output.
                valid_news.append({
                    "title": title,
                    "summary": summary
                })
            
        return valid_news

    except Exception as e:
        print(f"❌ Browser/Scraping Error: {e}")
        return []
    finally:
        if driver:
            driver.quit()

# === 3. AI 润色 ===
def process_news_with_ai(news_list):
    if not news_list or not client:
        return news_list 
        
    formatted_input = ""
    for idx, item in enumerate(news_list):
        formatted_input += f"{idx+1}. Title: {item['title']} | Summary: {item['summary']}\n"

    print("🤖 Sending to AI for polishing...")
    
    try:
        completion = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的内容聚合编辑。请分析输入的新闻列表，只保留跟 AI、产品、设计趋势强相关的内容。请返回一个 JSON 对象，包含字段 'news'，值是一个列表。列表中的每个元素包含 'title' (原标题) 和 'summary' (基于内容生成的吸引人的简短推荐语，50字以内)。⚠️ 重要：绝对不要包含任何带有 '优设' 字样的内容。由于用户要求不包含链接，请不要返回 url 字段。"
                },
                {
                    "role": "user",
                    "content": f"请处理以下新闻列表:\n{formatted_input}"
                }
            ],
            max_tokens=2048,
            temperature=0.7,
            stream=False,
            response_format={"type": "json_object"}
        )
        
        result_content = completion.choices[0].message.content
        result = json.loads(result_content)
        
        final_list = []
        if isinstance(result, dict) and 'news' in result and isinstance(result['news'], list):
            for item in result['news']:
                t = item.get('title', '')
                s = item.get('summary', '')
                if "优设" not in t and "优设" not in s:
                    final_list.append(item)
                    
        return final_list

    except Exception as e:
        print(f"❌ AI 处理失败: {e}")
        return news_list

# === 4. 推送逻辑 (NO LINKS) ===
def send_wecom(news_list):
    if not news_list:
        print("📭 无内容可发送")
        return

    today = datetime.now().strftime("%m月%d日")
    content_lines = [f"### 🚀 AI & Design News ({today})"] 
    
    for idx, news in enumerate(news_list, 1):
        title = news.get('title', '无标题')
        summary = news.get('summary', '')
        
        # User requested: "把链接过滤掉，微信看不到任何图片链接"
        # Output format: **1. Title** \n > Summary
        content_lines.append(f"**{idx}. {title}**")
        if summary:
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

    if not WEBHOOK_URL:
        print("⚠️ No Webhook URL set")
        return
        
    data = {"msgtype": "markdown", "markdown": {"content": final_content}}
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("✅ 推送成功")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    # 1. 爬取 (Selenium)
    raw_news = fetch_uisdc_news_html()
    
    if not raw_news:
        print("❌ 没抓到任何新闻 (or all filtered)")
    else:
        # 2. AI 润色
        final_news = process_news_with_ai(raw_news)
        
        # 3. 发送
        if final_news:
            # User request: Final push should only be 5 items
            final_news = final_news[:5]
            send_wecom(final_news)
        else:
            print("⚠️ 最终列表为空")
