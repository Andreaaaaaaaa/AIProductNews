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

# === 工具函数：通用 RSS 解析器 (增强版) ===
def fetch_rss_data(source_name, rss_url):
    """
    通用的 RSS 抓取函数
    """
    print(f"🔄 [{source_name}] 正在连接...")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    items = []
    try:
        response = requests.get(rss_url, headers=headers, timeout=15)
        if response.status_code == 200:
            # 兼容处理：有些 RSS 编码可能是乱码，使用 content 让 ET 自动处理
            try:
                root = ET.fromstring(response.content)
                
                # 暴力查找所有的 item 标签（不管它藏在多深的层级里）
                # 这种写法能同时搞定 RSS 2.0, RSS 1.0 (Solidot) 和部分 Atom
                nodes = root.findall('.//item') 
                if not nodes:
                    # 如果找不到 item，尝试找 Atom 格式的 entry
                    nodes = root.findall('.//{http://www.w3.org/2005/Atom}entry')

                for item in nodes[:8]: # 限制数量，防止 Token 溢出
                    # === 标题抓取 ===
                    title = "无标题"
                    title_node = item.find('title')
                    if title_node is None:
                        # 尝试带命名空间的 XML 查找
                        title_node = item.find('{http://purl.org/rss/1.0/}title')
                    if title_node is not None:
                        title = title_node.text

                    # === 链接抓取 ===
                    link = ""
                    link_node = item.find('link')
                    if link_node is None:
                        link_node = item.find('{http://purl.org/rss/1.0/}link')
                    
                    if link_node is not None:
                        link = link_node.text
                        # 兼容 Atom: <link href="..." />
                        if not link and link_node.attrib.get('href'):
                            link = link_node.attrib.get('href')

                    # === 描述抓取 ===
                    desc = ""
                    desc_node = item.find('description')
                    if desc_node is None:
                        desc_node = item.find('{http://purl.org/rss/1.0/}description')
                    
                    if desc_node is not None and desc_node.text:
                        desc = desc_node.text
                    
                    # 清洗 HTML 标签
                    desc = re.sub(r'<[^>]+>', '', desc)
                    
                    if link:
                        items.append({
                            "source": source_name,
                            "title": title,
                            "summary": desc[:200],
                            "url": link
                        })
                print(f"✅ [{source_name}] 获取到 {len(items)} 条")
            except Exception as e:
                print(f"❌ [{source_name}] XML 解析失败: {e}")
        else:
            print(f"❌ [{source_name}] 请求失败: {response.status_code}")
    except Exception as e:
        print(f"❌ [{source_name}] 网络错误: {e}")
    
    return items

def fetch_readhub():
    """
    ReadHub 专用抓取
    """
    print(f"🔄 [ReadHub] 正在连接...")
    url = "https://api.readhub.cn/topic?pageSize=10"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://readhub.cn",
        "Referer": "https://readhub.cn/"
    }
    items = []
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            for d in data:
                items.append({
                    "source": "ReadHub",
                    "title": d.get('title'),
                    "summary": d.get('summary', '')[:200],
                    "url": f"https://readhub.cn/topic/{d.get('id')}"
                })
            print(f"✅ [ReadHub] 获取到 {len(items)} 条")
        else:
            print(f"❌ [ReadHub] 状态码: {resp.status_code}")
    except Exception as e:
        print(f"❌ [ReadHub] 失败: {e}")
    return items

def get_all_news():
    """
    聚合所有数据源
    """
    all_news = []
    all_news.extend(fetch_readhub())
    all_news.extend(fetch_rss_data("36Kr", "https://36kr.com/feed"))
    all_news.extend(fetch_rss_data("Solidot", "https://www.solidot.org/index.rss"))
    all_news.extend(fetch_rss_data("InfoQ", "https://www.infoq.cn/feed"))
    return all_news

def process_news_with_ai(news_list):
    """
    AI 筛选与点评
    """
    if len(news_list) > 40:
        print(f"✂️ 新闻太多({len(news_list)}条)，截取前 40 条喂给 AI...")
        news_list = news_list[:40]

    print(f"🧠 AI (产品专家 & 体验设计师) 正在阅读 {len(news_list)} 条新闻...")
    
    raw_text = json.dumps(news_list, ensure_ascii=False)
    
    # === 修复点：明确要求 JSON 对象格式 ===
    system_prompt = """
    你是一位拥有双重视角的专家：既是【资深数据产品专家】，又是【数据产品体验设计师】。
    你的任务是为同行业者筛选出 4-6 条最有价值的资讯，不需要输出硬件相关的讯息。
    
    【筛选优先级】：
    1. 核心关注：AI Agent 交互范式、数据可视化创新、BI 工具的新体验设计。
    2. 核心关注：数据架构变革、大模型落地（RAG/向量库）的技术突破和大模型版本发布相关的信息。
    3. 重要关注：主流科技大厂（OpenAI/Google/Figma等）对数据产品的设计调整。
    
    【输出铁律】：
    1. 标题：简练、专业。
    2. 点评（Comment）：
       - 必须结合“商业价值”或“用户体验”进行深度洞察。
       - 严禁出现“作为设计师”、“笔者认为”等身份指代词。
       - 直接输出观点。
    3. **格式要求**：必须返回一个包含 `news` 字段的 JSON 对象。

    JSON 示例：
    {
        "news": [
            {
                "title": "重写后的标题",
                "source": "来源",
                "comment": "直接的犀利点评",
                "url": "链接"
            }
        ]
    }
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请筛选并分析：{raw_text}"}
            ],
            response_format={ "type": "json_object" }, 
            temperature=0.3
        )
        content = response.choices[0].message.content
        
        # 清洗
        if content.startswith("```"):
            content = re.sub(r"^```json\s*|\s*```$", "", content, flags=re.MULTILINE)
            
        result = json.loads(content)
        
        # === 修复点：兼容解析逻辑 ===
        # 现在的 Prompt 会返回 {"news": [...]}, 所以我们优先取 result["news"]
        if isinstance(result, dict):
            if "news" in result and isinstance(result["news"], list):
                return result["news"]
            # 兜底：如果 AI 还是自作聪明只返回了 list 的 dict 包装
            for k, v in result.items():
                if isinstance(v, list): return v
        
        return []
        
    except Exception as e:
        print(f"❌ AI 思考失败: {e}")
        # 调试打印，方便看 AI 到底回了什么
        print(f"AI 原始内容: {content[:200] if 'content' in locals() else '空'}")
        return []

def send_wecom(news_list):
    if not WEBHOOK_URL: return
    if not news_list: return

    today = datetime.now().strftime("%Y-%m-%d")
    content_lines = [f"### 🚀 AI 数据产品日报 ({today})"]
    
    for idx, news in enumerate(news_list, 1):
        title = news.get('title', '无标题')
        url = news.get('url', '#')
        comment = news.get('comment', '无点评')
        src = news.get('source', '精选')
        
        content_lines.append(f"**{idx}. {title}**")
        content_lines.append(f"_{src}_  [查看原文]({url})")
        content_lines.append(f"> 💡 {comment}") 
        content_lines.append("")

    data = {"msgtype": "markdown", "markdown": {"content": "\n".join(content_lines)}}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("✅ 推送成功")
    except Exception as e:
        print(f"❌ 推送失败: {e}")

if __name__ == "__main__":
    all_data = get_all_news()
    
    if not all_data:
        print("❌ 所有源都抓取失败，请检查网络。")
    else:
        print(f"📦 总共获取到 {len(all_data)} 条候选新闻")
        final_news = process_news_with_ai(all_data)
        if final_news:
            send_wecom(final_news)
        else:
            print("⚠️ AI 觉得今天没什么值得看的新闻。")
