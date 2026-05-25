有，Python 里做“网页正文核心内容抽取”的库主要分几类。我的建议是：**优先用 Trafilatura；简单场景可用 readability-lxml；新闻文章类可看 newspaper4k；复杂现代网页要配合 Playwright 先渲染再抽取。**

## 1. 首选：Trafilatura

**Trafilatura** 是目前 Python 生态里比较强的正文抽取库，目标就是从网页中提取 main text、metadata、comments 等内容，适合忽略 header、sidebar、footer、广告、推荐阅读等噪声。官方文档也明确说它用于 web crawling、downloads、scraping、main text extraction，并支持多种输出格式。([trafilatura.readthedocs.io][1])

安装：

```bash
pip install trafilatura
```

基本用法：

```python
import trafilatura

url = "https://example.com/article"
downloaded = trafilatura.fetch_url(url)

text = trafilatura.extract(
    downloaded,
    include_comments=False,
    include_tables=False,
    favor_precision=True
)

print(text)
```

如果想保留标题、作者、日期等结构化信息，可以用：

```python
import trafilatura

url = "https://example.com/article"
html = trafilatura.fetch_url(url)

result = trafilatura.bare_extraction(
    html,
    url=url,
    include_comments=False,
    favor_precision=True
)

print(result["title"])
print(result["author"])
print(result["date"])
print(result["text"])
```

Trafilatura 的 `bare_extraction` 可以直接返回 Python 变量，包括 metadata、正文和 comments；它也提供 `favor_precision` / `favor_recall` 这类参数控制“宁可少抽但准确”还是“尽量多抽”。([GitHub][2]) ([trafilatura.readthedocs.io][3])

**推荐使用场景：**

适合博客、新闻、文档页、长文章、资讯页、知识库页面、很多半结构化 HTML 页面。

---

## 2. 轻量备选：readability-lxml

`readability-lxml` 是 Python 版 Readability 算法，目标是从 HTML 文档中抽取 main body 和 title。([PyPI][4])

安装：

```bash
pip install readability-lxml lxml_html_clean
```

示例：

```python
import requests
from readability import Document
from bs4 import BeautifulSoup

url = "https://example.com/article"
html = requests.get(url, timeout=10).text

doc = Document(html)

title = doc.short_title()
content_html = doc.summary()

soup = BeautifulSoup(content_html, "html.parser")
text = soup.get_text("\n", strip=True)

print(title)
print(text)
```

**优点：**

简单、轻量、速度快。

**缺点：**

对于现代复杂页面、广告块很多的页面、正文分散的页面，效果通常不如 Trafilatura 稳。

---

## 3. 新闻文章类：newspaper4k / newspaper3k

`newspaper3k` 是老牌新闻文章抽取库，可以抽取 title、authors、publish_date、text、top_image 等。官方文档给出的典型用法就是下载文章后 `parse()`，也支持 `fulltext(html)`。([newspaper.readthedocs.io][5])

不过现在更建议关注 **newspaper4k**，它是 newspaper3k 的延续版本，PyPI 上说明它是 newspaper3k 的 continuation。([PyPI][6])

安装：

```bash
pip install newspaper4k
```

示例：

```python
from newspaper import Article

url = "https://example.com/news/article"

article = Article(url)
article.download()
article.parse()

print(article.title)
print(article.authors)
print(article.publish_date)
print(article.text)
```

**推荐使用场景：**

新闻站、媒体站、文章站。

**不太推荐用于：**

论坛、商品页、复杂 SPA、文档站、内容混排页面。

---

## 4. 现代网页重点问题：先渲染，再抽取

很多现代网页不是服务端直接返回完整正文，而是：

```text
requests 拿到 HTML
↓
里面只有空壳 div
↓
正文由 JavaScript 再请求接口渲染
```

这种情况下，Trafilatura / Readability / Newspaper 直接喂 `requests.get(url).text` 可能抽不到正文。

这时要先用 **Playwright** 或 Selenium 渲染页面，再把渲染后的 HTML 交给 Trafilatura。

安装：

```bash
pip install playwright trafilatura
playwright install chromium
```

示例：

```python
from playwright.sync_api import sync_playwright
import trafilatura

def fetch_rendered_html(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()
        return html

url = "https://example.com/article"

html = fetch_rendered_html(url)

text = trafilatura.extract(
    html,
    url=url,
    include_comments=False,
    include_tables=False,
    favor_precision=True
)

print(text)
```

这套组合是我比较推荐的工程方案：

```text
普通静态网页：
requests / trafilatura.fetch_url
        ↓
trafilatura.extract

现代 JS 网页：
Playwright 渲染
        ↓
page.content()
        ↓
trafilatura.extract
```

---

## 5. 一个实用封装版本

可以封装成“先静态抽取，失败再浏览器渲染”的策略：

```python
import requests
import trafilatura
from playwright.sync_api import sync_playwright


def extract_main_content_static(url: str) -> str | None:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        )
    }

    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    return trafilatura.extract(
        resp.text,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True
    )


def fetch_rendered_html(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        html = page.content()
        browser.close()
        return html


def extract_main_content(url: str) -> str | None:
    text = extract_main_content_static(url)

    if text and len(text) > 300:
        return text

    html = fetch_rendered_html(url)

    return trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True
    )


if __name__ == "__main__":
    url = "https://example.com/article"
    content = extract_main_content(url)
    print(content)
```

---

## 6. 几个库的取舍建议

| 库                  |  推荐程度 | 适合场景             | 特点                     |
| ------------------ | ----: | ---------------- | ---------------------- |
| `trafilatura`      |     高 | 通用正文抽取           | 准确率较好，适合工程化            |
| `readability-lxml` |     中 | 简单文章页            | 轻量，速度快                 |
| `newspaper4k`      |     中 | 新闻媒体文章           | title、author、date 等支持好 |
| `BeautifulSoup`    |    辅助 | 自定义规则            | 本身不负责判断正文区域            |
| `Playwright`       | 辅助但重要 | JS 动态页面          | 负责渲染，不负责正文判断           |
| `jusText`          |    可选 | 去 boilerplate 文本 | 老牌正文/噪声分离库             |

---

## 7. 我的推荐结论

如果您要做一个比较通用的网页正文抽取模块，我会这样设计：

```text
URL
 ↓
requests 静态抓取
 ↓
trafilatura 抽正文
 ↓
如果正文过短 / 为空 / 明显失败
 ↓
Playwright 渲染
 ↓
trafilatura 再抽一次
 ↓
输出 title、text、date、author、url、raw_html_hash
```

核心依赖可以先定为：

```bash
pip install trafilatura playwright beautifulsoup4 requests
playwright install chromium
```

其中：

**Trafilatura 负责判断哪里是正文；Playwright 负责让现代网页先完整渲染出来。**

这比自己用 BeautifulSoup 写一堆 `header/sidebar/footer/nav/aside` 删除规则稳得多。

[1]: https://trafilatura.readthedocs.io/?utm_source=chatgpt.com "A Python package & command-line tool to gather text on the ..."
[2]: https://github.com/adbar/trafilatura/blob/master/docs/usage-python.rst?utm_source=chatgpt.com "trafilatura/docs/usage-python.rst at master"
[3]: https://trafilatura.readthedocs.io/en/latest/corefunctions.html?utm_source=chatgpt.com "Core functions — Trafilatura 2.0.0 documentation"
[4]: https://pypi.org/project/readability-lxml/?utm_source=chatgpt.com "readability-lxml"
[5]: https://newspaper.readthedocs.io/?utm_source=chatgpt.com "Newspaper3k: Article scraping & curation — newspaper 0.0.2 ..."
[6]: https://pypi.org/project/newspaper4k/?utm_source=chatgpt.com "newspaper4k"
