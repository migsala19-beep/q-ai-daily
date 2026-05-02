#!/usr/bin/env python3
"""
Q虾 AI 日报生成器
每日早晨 8:00 自动运行，收集并生成 AI 资讯报告
"""
import json
import os
import re
import smtplib
import subprocess
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

REPORTS_DIR = os.path.expanduser("~/qxia-reports/reports")
DATA_FILE = os.path.expanduser("~/qxia-reports/data/reports.json")
BASE_URL = "https://348afb4850b528.lhr.life"

# 邮件配置（需要填写）
SMTP_HOST = os.environ.get("QXIA_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("QXIA_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("QXIA_SMTP_USER", "")
SMTP_PASS = os.environ.get("QXIA_SMTP_PASS", "")
MAIL_TO = os.environ.get("QXIA_MAIL_TO", "")

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)


def fetch(url, timeout=60):
    try:
        r = requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        return r.text if r.status_code == 200 else ""
    except Exception as e:
        print(f"[ERR] fetch {url}: {e}")
        return ""


def get_github_trending():
    html = fetch("https://github.com/trending?spoken_language_code=en")
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for article in soup.find_all("article", class_="Box-row")[:8]:
        h2 = article.find("h2")
        if not h2:
            continue
        a = h2.find("a")
        if not a:
            continue
        repo = a.get_text(strip=True).replace("\n", "").replace(" ", "")
        desc = article.find("p", class_="col-9")
        desc = desc.get_text(strip=True) if desc else ""
        items.append({"repo": repo, "desc": desc, "url": f"https://github.com/{repo}"})
    return items


def get_arxiv_papers():
    # arXiv cs.AI RSS
    xml = fetch("https://rss.arxiv.org/rss/cs.AI")
    if not xml:
        return []
    papers = []
    try:
        soup = BeautifulSoup(xml, "xml")
        for item in soup.find_all("item")[:6]:
            title = item.find("title")
            title = title.get_text(strip=True) if title else ""
            link = item.find("link")
            link = link.get_text(strip=True) if link else ""
            desc = item.find("description")
            desc = desc.get_text(strip=True) if desc else ""
            # 去掉 arxiv 的摘要前置说明
            desc = re.sub(r"Abstract:\s*", "", desc)[:300]
            papers.append({"title": title, "url": link, "desc": desc})
    except Exception as e:
        print(f"[ERR] arxiv parse: {e}")
    return papers


def get_hf_papers():
    # HuggingFace daily papers 页面
    html = fetch("https://huggingface.co/papers")
    if not html:
        return []
    papers = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"/papers/"))[:6]:
            href = a.get("href", "")
            if not href.startswith("/papers/"):
                continue
            title = a.get_text(strip=True)
            if not title or any(p["title"] == title for p in papers):
                continue
            papers.append({"title": title, "url": f"https://huggingface.co{href}"})
    except Exception as e:
        print(f"[ERR] hf parse: {e}")
    return papers


def get_blog_posts():
    blogs = []
    # OpenAI
    html = fetch("https://openai.com/news/")
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True)[:4]:
            if "/news/" in a["href"] and a.get_text(strip=True):
                blogs.append({"source": "OpenAI", "title": a.get_text(strip=True), "url": urljoin("https://openai.com", a["href"])})
    # Anthropic
    html = fetch("https://www.anthropic.com/news")
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True)[:4]:
            if "/news/" in a["href"] and a.get_text(strip=True):
                blogs.append({"source": "Anthropic", "title": a.get_text(strip=True), "url": urljoin("https://www.anthropic.com", a["href"])})
    # DeepMind
    html = fetch("https://deepmind.google/discover/blog/")
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True)[:4]:
            if "/discover/blog/" in a["href"] and a.get_text(strip=True):
                blogs.append({"source": "DeepMind", "title": a.get_text(strip=True), "url": urljoin("https://deepmind.google", a["href"])})
    return blogs[:12]
BASE_URL = "https://domiai.com.cn"

def call_kimi_api(prompt: str) -> str:
    """调用 Kimi API 生成文本分析"""
    api_key = os.environ.get("KIMI_API_KEY", "")
    if not api_key:
        return ""
    try:
        r = requests.post(
            "https://api.moonshot.cn/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "moonshot-v1-8k",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2048
            },
            timeout=120
        )
        data = r.json()
        if r.status_code != 200:
            print(f"[ERR] Kimi API HTTP {r.status_code}: {data}")
            return ""
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[ERR] Kimi API call: {e}")
        return ""

def call_local_summary(raw_data: dict) -> str:
    """无 API Key 时，从原始数据生成简单汇总"""
    parts = []
    
    gh = raw_data.get("github", [])
    if gh:
        repos = [f"{x['repo']}（{x['desc'][:40]}）" for x in gh[:3] if x.get('repo')]
        parts.append(f"【GitHub 热门】{'; '.join(repos)}")
    
    arxiv = raw_data.get("arxiv", [])
    if arxiv:
        titles = [x['title'][:50] for x in arxiv[:3] if x.get('title')]
        parts.append(f"【arXiv 论文】{'; '.join(titles)}")
    
    hf = raw_data.get("hf", [])
    if hf:
        titles = [x['title'][:50] for x in hf[:3] if x.get('title')]
        parts.append(f"【HuggingFace】{'; '.join(titles)}")
    
    blogs = raw_data.get("blogs", [])
    if blogs:
        titles = [f"{x['source']}:{x['title'][:40]}" for x in blogs[:3] if x.get('title')]
        parts.append(f"【大厂动态】{'; '.join(titles)}")
    
    raw_summary = "\n\n".join(parts) if parts else "暂无原始数据"
    
    return f"""### 执行摘要
今日 AI 资讯摘要：
{raw_summary.replace(chr(10), '<br>')}

### 深度研究报告
基于上述来源，以下内容值得关注：
<br>1. GitHub Trending 反映了开发者对 {gh[0]['repo'].split('/')[1] if gh else 'AI 工具'} 等方向的关注
<br>2. arXiv 最新论文探索了 {arxiv[0]['title'][:30] if arxiv else 'AI 技术'} 等课题
<br>3. 大厂博客动态显示 {blogs[0]['source'] if blogs else '业界'}在持续推进相关产品和研究
<br><br>【提示】配置 Kimi API Key 后，此处将由 AI 自动生成深度分析。

### 实践启发
<br>1. 关注 GitHub 热门项目，了解开源社区最新工具和框架
<br>2. 浏览 arXiv 论文摘要，把握学术前沿动向
<br>3. 阅读大厂博客，了解产品化应用和商业落地情况
<br>4. 尝试将有趣的工具/框架应用到自己的项目中
<br>5. 持续关注 Q虾 AI 日报，获取每日精选资讯"""


def git_push():
    """将报告站推送到 GitHub Pages"""
    repo_dir = os.path.expanduser("~/qxia-reports")
    try:
        subprocess.run(["git", "-C", repo_dir, "add", "."], check=True, capture_output=True)
        subprocess.run(["git", "-C", repo_dir, "commit", "-m", f"update report {datetime.now().strftime('%Y-%m-%d %H:%M')}"], capture_output=True)
        result = subprocess.run(["git", "-C", repo_dir, "push", "origin", "main"], capture_output=True, text=True)
        if result.returncode == 0:
            print("[GitHub] 已推送到 https://github.com/migsala19-beep/ai-daily")
        else:
            print(f"[WARN] GitHub push 失败: {result.stderr.strip()}")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] Git commit 失败: {e}")


def send_email(date_str: str, report_url: str, summary_text: str):
    """发送邮件通知"""
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASS, MAIL_TO]):
        print("[EMAIL] 未配置邮箱，跳过发送")
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Q虾 AI 日报 | {date_str}"
        msg["From"] = SMTP_USER
        msg["To"] = MAIL_TO

        body = f"""
        <html>
        <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:600px;margin:0 auto;padding:20px">
        <h2 style="color:#00d4aa">🔔 Q虾 AI 日报 — {date_str}</h2>
        <p>{summary_text[:300]}...</p>
        <p>
          <a href="{report_url}" style="display:inline-block;background:#00d4aa;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none">
            查看完整报告
          </a>
        </p>
        <p style="color:#888;font-size:12px">
          此邮件由运行于 Mac mini 上的 Q虾 AI 助手自动发送<br>
          固定网址：{BASE_URL}
        </p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, "html", "utf-8"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, MAIL_TO, msg.as_string())
        print(f"[EMAIL] 已发送到 {MAIL_TO}")
    except Exception as e:
        print(f"[ERR] 邮件发送失败: {e}")


def generate_analysis(raw_data: dict) -> str:
    # 先尝试调用 Kimi API，无 Key 时自动回退到本地汇总
    prompt = f"""你是 AI 行业研究员。以下是今日收集到的原始 AI 资讯：

[GitHub Trending]
{json.dumps(raw_data.get('github', []), ensure_ascii=False, indent=2)[:2000]}

[arXiv 论文]
{json.dumps(raw_data.get('arxiv', []), ensure_ascii=False, indent=2)[:2000]}

[HuggingFace Papers]
{json.dumps(raw_data.get('hf', []), ensure_ascii=False, indent=2)[:1500]}

[大厂博客]
{json.dumps(raw_data.get('blogs', []), ensure_ascii=False, indent=2)[:1500]}

请严格按照下面格式输出（不要说任何多余的话，只输出下面三部分内容，每部分用 ### 分隔）：

### 执行摘要
用 3-5 条幻灯片要点，每条 20 字以内，概括今日最重要的 AI 动态。

### 深度研究报告
结合上述来源，分析 1-2 个值得关注的趋势或技术方向，每点配合具体案例/论文/项目进行说明。约 300 字。

### 实践启发
基于今日资讯，给出 3-5 个可落地的实践 idea 或行动建议，每条带一句简短理由。
"""
    analysis = call_kimi_api(prompt)
    if not analysis:
        print("[INFO] 未配置 Kimi API Key，使用本地汇总模式")
        analysis = call_local_summary(raw_data)
    return analysis


def build_html(date_str: str, raw_data: dict, analysis_text: str) -> str:
    # 解析 Hermes 返回的文本
    parts = analysis_text.split("###")
    summary = "暂无摘要"
    research = "暂无研究报告"
    insights = "暂无实践启发"
    for part in parts[1:]:
        lines = part.strip().split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        if "摘要" in title:
            summary = body.replace("\n", "<br>")
        elif "研究" in title:
            research = body.replace("\n", "<br>")
        elif "启发" in title or "实践" in title:
            insights = body.replace("\n", "<br>")

    gh_items = "".join([f'<li><a href="{x["url"]}">{x["repo"]}</a> — {x["desc"]}</li>' for x in raw_data.get("github", [])])
    arxiv_items = "".join([f'<li><a href="{x["url"]}">{x["title"]}</a> — {x["desc"]}</li>' for x in raw_data.get("arxiv", [])])
    hf_items = "".join([f'<li><a href="{x["url"]}">{x["title"]}</a></li>' for x in raw_data.get("hf", [])])
    blog_items = "".join([f'<li>[{x["source"]}] <a href="{x["url"]}">{x["title"]}</a></li>' for x in raw_data.get("blogs", [])])

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 日报 | {date_str}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#0a0a12;color:#e8e8e8;line-height:1.7}}
h1{{color:#00d4aa;border-bottom:2px solid #00d4aa;padding-bottom:10px}}
h2{{color:#00d4aa;margin-top:32px;font-size:1.3em}}
.card{{background:#12121e;border-radius:14px;padding:20px;margin:16px 0;box-shadow:0 4px 12px rgba(0,212,170,0.08)}}
a{{color:#4ecdc4;text-decoration:none}}
a:hover{{text-decoration:underline}}
ul{{padding-left:20px}}
li{{margin:8px 0}}
.back{{display:inline-block;margin-bottom:20px;color:#888}}
.tag{{display:inline-block;background:#00d4aa20;color:#00d4aa;padding:2px 10px;border-radius:20px;font-size:12px;margin-right:6px}}
.empty{{color:#666}}
</style>
</head>
<body>
<a class="back" href="../index.html">← 返回首页</a>
<h1>🔔 AI 日报 — {date_str}</h1>
<div style="margin-bottom:20px">
  <span class="tag">执行摘要</span>
  <span class="tag">深度研究</span>
  <span class="tag">实践启发</span>
</div>

<div class="card">
  <h2>📊 执行摘要</h2>
  <div>{summary}</div>
</div>

<div class="card">
  <h2>🔬 深度研究报告</h2>
  <div>{research}</div>
</div>

<div class="card">
  <h2>💡 实践启发</h2>
  <div>{insights}</div>
</div>

<div class="card">
  <h2>🗣️ 原始资讯</h2>
  <h3>GitHub Trending</h3>
  <ul>{gh_items or '<li class="empty">暂无数据</li>'}</ul>
  <h3>arXiv 论文</h3>
  <ul>{arxiv_items or '<li class="empty">暂无数据</li>'}</ul>
  <h3>HuggingFace Papers</h3>
  <ul>{hf_items or '<li class="empty">暂无数据</li>'}</ul>
  <h3>大厂博客</h3>
  <ul>{blog_items or '<li class="empty">暂无数据</li>'}</ul>
</div>

<footer style="text-align:center;color:#555;margin-top:40px">
  生成于 {datetime.now().strftime("%Y-%m-%d %H:%M")} | Q虾 AI 助手
</footer>
</body>
</html>'''
    return html


def update_index(reports_meta: list):
    items = ""
    for r in sorted(reports_meta, key=lambda x: x["date"], reverse=True):
        items += f'<div class="card"><a href="reports/{r["date"]}.html"><h3>{r["date"]}</h3></a><p>{r["summary"][:120]}...</p></div>\n'

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Q虾 AI 报告中心</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#0a0a12;color:#e8e8e8}}
h1{{color:#00d4aa;border-bottom:2px solid #00d4aa;padding-bottom:10px}}
.card{{background:#12121e;border-radius:14px;padding:18px;margin:14px 0;transition:transform .1s}}
.card:hover{{transform:translateX(6px)}}
.card a{{color:#00d4aa;text-decoration:none}}
.card p{{color:#aaa;margin:6px 0 0}}
.empty{{text-align:center;color:#666;padding:40px}}
.tag{{display:inline-block;background:#00d4aa20;color:#00d4aa;padding:3px 12px;border-radius:20px;font-size:12px;margin-right:6px}}
</style>
</head>
<body>
<h1>🐠 Q虾 AI 报告中心</h1>
<p style="color:#888">每日早晨 8:00 自动更新最新 AI 资讯 | 历史报告永久归档</p>
<div style="margin:10px 0">
  <span class="tag">执行摘要</span>
  <span class="tag">深度研究</span>
  <span class="tag">实践启发</span>
  <span class="tag">永久归档</span>
</div>
<div id="reports">
{items or '<div class="empty">暂无报告，请等待每日 8:00 自动生成。</div>'}
</div>
<footer style="text-align:center;color:#444;margin-top:40px">
  Q虾 AI 助手 · 运行于 Mac mini
</footer>
</body>
</html>'''
    with open(os.path.expanduser("~/qxia-reports/index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"[开始] 生成 {today} 的报告...")

    raw = {
        "github": get_github_trending(),
        "arxiv": get_arxiv_papers(),
        "hf": get_hf_papers(),
        "blogs": get_blog_posts(),
    }

    print(f"[收集完成] GH={len(raw['github'])} arXiv={len(raw['arxiv'])} HF={len(raw['hf'])} Blogs={len(raw['blogs'])}")

    print("[分析] 调用 Hermes 生成摘要、研究报告、实践启发...")
    analysis = generate_analysis(raw)

    html = build_html(today, raw, analysis)
    report_path = os.path.join(REPORTS_DIR, f"{today}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[存档] {report_path}")

    # 更新索引
    meta = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            meta = json.load(f)
    # 去重
    meta = [m for m in meta if m["date"] != today]
    meta.append({"date": today, "summary": analysis[:200]})
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    update_index(meta)
    print("[完成] 报告站已更新")

    # 推送到 GitHub Pages
    git_push()

    # 发送邮件通知
    report_url = f"{BASE_URL}/reports/{today}.html"
    send_email(today, report_url, analysis)


if __name__ == "__main__":
    main()
