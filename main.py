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

load_dotenv()

app = FastAPI(
    title="Universal Newsletter Scraper API v9",
    description="Now supports summarization and batch mode for Substack and Beehiiv.",
    version="9.0.0",
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

        return {
            "publication_name": publication,
            "article_title": title,
            "article_subtitle": subtitle,
            "author": author,
            "publication_date": publication_date,
            "full_text": full_text
        }

    except Exception as e:
        raise ValueError(f"Failed to parse Substack article. Error: {e}")

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
        polished_text = '\n\n'.join(text_blocks)
        
        return {
            "publication_name": publication, "article_title": title,
            "article_subtitle": subtitle, "author": author, "publication_date": publication_date,
            "full_text": polished_text
        }
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

            results.append({"article_url": url, **data})

        except Exception as e:
            results.append({"article_url": url, "error": str(e)})

    return {"success": True, "results": results}
