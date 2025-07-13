import requests
import re
import json
import os
from dotenv import load_dotenv
from pydantic import BaseModel
from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import textwrap
import html

load_dotenv()

app = FastAPI(
    title="Universal Newsletter Scraper API v9.3",
    description="Now includes prompt templates, metadata, summarization, and batch mode.",
    version="9.3.0",
)

class URLBatchRequest(BaseModel):
    urls: List[str]
    summarize: bool = False

@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/docs")

def summarize_text_with_huggingface(text: str) -> str:
    api_url = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
    headers = {
        "Authorization": f"Bearer {os.getenv('HF_API_KEY')}",
        "Content-Type": "application/json"
    }
    chunks = textwrap.wrap(text, width=3000, break_long_words=False, break_on_hyphens=False)
    summaries = []
    for chunk in chunks:
        try:
            response = requests.post(api_url, headers=headers, json={"inputs": chunk}, timeout=30)
            response.raise_for_status()
            result = response.json()
            summary = result[0].get("summary_text", "")
            if summary:
                summaries.append(summary)
        except Exception as e:
            summaries.append(f"[Chunk summarization failed: {e}]")
    return "\n\n".join(summaries)

def compute_stats(text: str) -> dict:
    word_count = len(text.split())
    paragraph_count = text.count('\n\n')
    reading_time_minutes = max(1, round(word_count / 200))
    return {
        "word_count": word_count,
        "paragraph_count": paragraph_count,
        "reading_time_minutes": reading_time_minutes
    }

def extract_extra_metadata(soup: BeautifulSoup) -> dict:
    canonical = None
    tags = []
    category = None
    tag_meta = soup.find("meta", attrs={"name": "keywords"})
    if tag_meta and tag_meta.get("content"):
        tags = [tag.strip() for tag in tag_meta["content"].split(",") if tag.strip()]
    canonical_tag = soup.find("link", rel="canonical")
    if canonical_tag and canonical_tag.get("href"):
        canonical = canonical_tag["href"]
    else:
        og_url = soup.find("meta", property="og:url")
        if og_url and og_url.get("content"):
            canonical = og_url["content"]
    category_meta = soup.find("meta", attrs={"name": "category"})
    if category_meta and category_meta.get("content"):
        category = category_meta["content"]
    elif tags:
        category = tags[0]
    return {
        "canonical_url": canonical,
        "tags": tags,
        "newsletter_category": category
    }

def generate_prompt_templates(data: dict) -> dict:
    title = data.get("article_title", "Untitled")
    full_text = html.unescape(data.get("full_text", "")[:10000])
    return {
        "summarization": f"Summarize the following newsletter titled '{title}':\n\n{full_text}",
        "tweet_thread": f"Write a 5–7 tweet thread summarizing the newsletter '{title}':\n\n{full_text}",
        "reply_comment": f"Write a friendly, thoughtful comment to leave on this newsletter:\n\n{full_text}",
        "idea_extraction": f"Extract 5 content/post ideas from this newsletter:\n\n{full_text}",
        "quotes": f"Extract 5 impactful or shareable quotes from the newsletter titled '{title}':\n\n{full_text}"
    }
    
def _scrape_substack_article(soup: BeautifulSoup) -> dict:
    try:
        author, publication, publication_date = "Author not found", "Publication not found", None
        script_tag = soup.find('script', {'type': 'application/ld+json'})
        if script_tag:
            try:
                json_data = json.loads(script_tag.string)
                if '@graph' in json_data:
                    for item in json_data['@graph']:
                        if item.get('@type') == 'NewsArticle':
                            author = item.get('author', {}).get('name', author)
                            publication = item.get('publisher', {}).get('name', publication)
                            publication_date = item.get('datePublished', publication_date)
                            if publication_date:
                                publication_date = publication_date.split('T')[0]
                            break
            except Exception:
                pass

        if author == "Author not found":
            meta_author = soup.find("meta", attrs={"name": "author"})
            if meta_author and meta_author.get("content"):
                author = meta_author["content"].strip()

        if publication == "Publication not found":
            og_site = soup.find("meta", attrs={"property": "og:site_name"})
            if og_site and og_site.get("content"):
                publication = og_site["content"].strip()

        if not publication_date:
            pub_date_tag = soup.find("meta", attrs={"property": "article:published_time"})
            if pub_date_tag and pub_date_tag.get("content"):
                publication_date = pub_date_tag["content"].split("T")[0]

        byline = soup.select_one('div.pencraft-card-meta-row a.pencraft-card-meta-row-owner-name')
        if byline:
            author = byline.get_text(strip=True)
        pub = soup.select_one('div.pencraft-card-meta-row a.pencraft-card-meta-row-publication-name')
        if pub:
            publication = pub.get_text(strip=True)
        date_container = soup.select_one('div[aria-label="Post UFI"] div.color-pub-secondary-text-hGQ02T')
        if date_container:
            publication_date = date_container.get_text(strip=True)

        title = soup.select_one('h1.post-title')
        subtitle = soup.select_one('h3.subtitle')
        title = title.get_text(strip=True) if title else "Title not found"
        subtitle = subtitle.get_text(strip=True) if subtitle else None

        content_body = soup.select_one('div.body.markup')
        if not content_body:
            raise ValueError("Main content body not found.")

        for selector in [
            'div.subscription-widget-wrap', 'div.captioned-image-container',
            'div.community-chat', 'p.button-wrapper', 'div.pullquote', 'hr',
            '.instagram', '.like-button-container', '.post-ufi-comment-button'
        ]:
            for el in content_body.select(selector):
                el.decompose()

        text_blocks = [el.get_text(strip=True).replace('\n', ' ') for el in content_body.select('p, h3, li') if el.get_text(strip=True)]
        full_text = '\n\n'.join(text_blocks)

        data = {
            "publication_name": publication,
            "article_title": title,
            "article_subtitle": subtitle,
            "author": author,
            "publication_date": publication_date,
            "full_text": full_text,
            **compute_stats(full_text),
            **extract_extra_metadata(soup)
        }
        data["prompt_templates"] = generate_prompt_templates(data)
        return data

    except Exception as e:
        raise ValueError(f"Failed to parse Beehiiv article. Error: {e}")

def _scrape_beehiiv_article(soup: BeautifulSoup) -> dict:
    try:
        title, author, publication, publication_date, subtitle = "Title not found", "Author not found", "beehiiv", None, None
        script_tag = soup.find('script', {'type': 'application/ld+json'})
        if script_tag:
            json_data = json.loads(script_tag.string)
            title = json_data.get('headline', title)
            if json_data.get('author') and isinstance(json_data['author'], list):
                author = json_data['author'][0].get('name', author)
            publication = json_data.get('publisher', {}).get('name', publication)
            publication_date = json_data.get('datePublished', publication_date)
            if publication_date:
                publication_date = publication_date.split('T')[0]

        title_element = soup.select_one('h1')
        if title_element:
            title = title_element.get_text(strip=True)
        author_element = soup.select_one('a[href*="/authors/"]')
        if author_element:
            author = author_element.get_text(strip=True)

        content_body = soup.select_one('div.prose')
        if not content_body:
            raise ValueError("Main content body (`div.prose`) not found.")
                
        text_blocks = [el.get_text(strip=True).replace('\n', ' ') for el in content_body.select('p, h1, h2, h3, li') if el.get_text(strip=True)]
        full_text = '\n\n'.join(text_blocks)

        data = {
            "publication_name": publication,
            "article_title": title,
            "article_subtitle": subtitle,
            "author": author,
            "publication_date": publication_date,
            "full_text": full_text,
            **compute_stats(full_text),
            **extract_extra_metadata(soup)
        }
        data["prompt_templates"] = generate_prompt_templates(data)
        return data

    except Exception as e:
        raise ValueError(f"Failed to parse Beehiiv article. Error: {e}")

@app.get("/v1/article-content")
async def get_article_content(url: str, summarize: bool = False):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        domain = urlparse(url).netloc
        if "substack.com" in domain:
            data = _scrape_substack_article(soup)
        elif "beehiiv.com" in domain:
            data = _scrape_beehiiv_article(soup)
        else:
            raise HTTPException(status_code=400, detail="Unsupported platform.")
        if summarize:
            summary = summarize_text_with_huggingface(data["full_text"])
            data["summary"] = summary
        data["prompt_templates"] = generate_prompt_templates(data)
        return {"success": True, "article_url": url, **data}
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch the URL: {e}")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

@app.post("/v1/article-batch")
async def batch_article_scrape(payload: URLBatchRequest):
    headers = {'User-Agent': 'Mozilla/5.0'}
    results = []
    for url in payload.urls:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            domain = urlparse(url).netloc
            if "substack.com" in domain:
                data = _scrape_substack_article(soup)
            elif "beehiiv.com" in domain:
                data = _scrape_beehiiv_article(soup)
            else:
                raise ValueError("Unsupported platform.")
            if payload.summarize:
                summary = summarize_text_with_huggingface(data["full_text"])
                data["summary"] = summary
            data["prompt_templates"] = generate_prompt_templates(data)
            results.append({"article_url": url, **data})
        except Exception as e:
            results.append({"article_url": url, "error": str(e)})
    return {"success": True, "results": results}

from fastapi.responses import HTMLResponse

@app.get("/docs-html", response_class=HTMLResponse, include_in_schema=False)
async def custom_docs_html():
    html_content = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <meta name="description" content="Universal Newsletter Scraper API — extract clean content, metadata, summaries, and prompts from Substack and Beehiiv articles." />
        <meta name="keywords" content="newsletter API, substack API, beehiiv API, summarizer API, article scraper API, content extraction" />
        <meta name="author" content="349Z" />
        <title>Universal Newsletter Scraper API Docs</title>
        <style>
            body { font-family: sans-serif; max-width: 800px; margin: auto; padding: 2rem; line-height: 1.6; }
            code { background: #f4f4f4; padding: 0.2rem 0.4rem; border-radius: 4px; }
            pre { background: #f4f4f4; padding: 1rem; border-radius: 6px; overflow-x: auto; }
            h1, h2 { margin-top: 2rem; }
            .note { background: #eaf8e5; padding: 1rem; border-left: 4px solid #4caf50; margin: 1rem 0; }
        </style>
    </head>
    <body>
        <h1>📄 Universal Newsletter Scraper API</h1>
        <p>This API lets you extract clean content, metadata, summaries, and GPT-ready prompts from newsletters hosted on <strong>Substack</strong> and <strong>Beehiiv</strong> (as of now).</p>

        <h2>🔗 Base URL</h2>
        <pre>https://newsletter-scraper-api.vercel.app/docs</pre>

        <h2>📍 Endpoints</h2>

        <h3>1. <code>GET /v1/article-content</code></h3>
        <p>Scrapes a single article and returns metadata, content, and optional summary + prompts.</p>
        <h4>Query Parameters:</h4>
        <ul>
            <li><code>url</code> (required)</li>
            <li><code>summarize</code> (optional, default: false)</li>
        </ul>

        <h3>2. <code>POST /v1/article-batch</code></h3>
        <p>Scrapes multiple article URLs at once. JSON body:</p>
        <pre>{
    "urls": [
        "https://example.substack.com/p/article-1",
        "https://another.beehiiv.com/p/article-2"
    ],
    "summarize": true
}</pre>

        <div class="note">
            Summary uses <code>facebook/bart-large-cnn</code> via Hugging Face.
        </div>

        <h2>💡 Prompt Templates</h2>
        <ul>
            <li>Summarization</li>
            <li>Tweet thread</li>
            <li>Comment</li>
            <li>Content ideas</li>
            <li>Quotes</li>
        </ul>

        <h2>📊 Metadata Included</h2>
        <ul>
            <li>Canonical URL</li>
            <li>Tags and Category</li>
            <li>Word Count</li>
            <li>Read Time</li>
            <li>Paragraph Count</li>
        </ul>

        <h2>🔗 GitHub / Contact</h2>
        <p>GitHub: <a href="https://github.com/Afterknight/newsletter-scraper-api">github.com/newsletter-scraper-api</a></p>
        <p>Email: shanimam97@gmail.com</p>
        <p>Made by 359Z ❤️</p>
    </body>
    </html>
    '''
    return HTMLResponse(content=html_content)
