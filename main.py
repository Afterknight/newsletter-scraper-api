# main.py (v8.0 - The Definitive Dual-Engine Version)

import requests
import re
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# --- App Definition ---
app = FastAPI(
    title="Universal Newsletter Scraper API v8",
    description="A production-grade API with a multi-layered fallback system for both Substack and Beehiiv.",
    version="8.0.0",
)

# --- CORRECTED ROOT REDIRECT ENDPOINT ---
@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/docs")


# --- DEFINITIVE SUBSTACK SCRAPER (Unchanged from v7) ---
def _scrape_substack_article(soup: BeautifulSoup) -> dict:
    try:
        author, publication, publication_date = "Author not found", "Publication not found", None
        script_tag = soup.find('script', {'type': 'application/ld+json'})
        if script_tag:
            json_data = json.loads(script_tag.string)
            if '@graph' in json_data:
                for item in json_data['@graph']:
                    if item.get('@type') == 'NewsArticle':
                        author = item.get('author', {}).get('name', author)
                        publication = item.get('publisher', {}).get('name', publication)
                        publication_date = item.get('datePublished', publication_date).split('T')[0] if item.get('datePublished') else None
                        break
        if author == "Author not found":
            byline_container = soup.select_one('div.pencraft-card-meta-row')
            if byline_container:
                author_element = byline_container.select_one('a.pencraft-card-meta-row-owner-name')
                if author_element: author = author_element.get_text(strip=True)
        if publication == "Publication not found":
             byline_container = soup.select_one('div.pencraft-card-meta-row')
             if byline_container:
                publication_element = byline_container.select_one('a.pencraft-card-meta-row-publication-name')
                if publication_element: publication = publication_element.get_text(strip=True)
        if not publication_date:
            date_container = soup.select_one('div[aria-label="Post UFI"]')
            if date_container:
                date_element = date_container.select_one('div.pencraft.pc-reset.color-pub-secondary-text-hGQ02T')
                if date_element: publication_date = date_element.get_text(strip=True)

        title_element = soup.select_one('h1.post-title')
        title = title_element.get_text(strip=True) if title_element else "Title not found"
        subtitle_element = soup.select_one('h3.subtitle')
        subtitle = subtitle_element.get_text(strip=True) if subtitle_element else None
        
        content_body = soup.select_one('div.body.markup')
        if not content_body: raise ValueError("Main content body not found.")
        
        clutter_selectors = [
            'div.subscription-widget-wrap', 'div.captioned-image-container',
            'div.community-chat', 'p.button-wrapper', 'div.pullquote', 'hr',
            '.instagram', '.like-button-container', '.post-ufi-comment-button'
        ]
        for selector in clutter_selectors:
            for element in content_body.select(selector):
                element.decompose()
        
        text_blocks = [el.get_text(strip=True).replace('\n', ' ') for el in content_body.select('p, h3, li') if el.get_text(strip=True)]
        polished_text = '\n\n'.join(text_blocks)

        return {
            "publication_name": publication, "article_title": title,
            "article_subtitle": subtitle, "author": author,
            "publication_date": publication_date, "full_text": polished_text
        }
    except Exception as e:
        raise ValueError(f"Failed to parse Substack article. Error: {e}")

# --- NEW AND IMPROVED BEEHIIV SCRAPER ---

def _scrape_beehiiv_article(soup: BeautifulSoup) -> dict:
    """
    Scrapes a Beehiiv article using the same robust, fallback-driven approach.
    """
    try:
        # Initialize defaults
        title, author, publication, publication_date, subtitle = "Title not found", "Author not found", "beehiiv", None, None

        # Plan A: Parse the clean JSON-LD data
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

        # Plan B: Fallback to HTML scraping if JSON-LD fails or is incomplete
        if title == "Title not found":
            title_element = soup.select_one('h1')
            if title_element: title = title_element.get_text(strip=True)
        if author == "Author not found":
            author_element = soup.select_one('a[href*="/authors/"]')
            if author_element: author = author_element.get_text(strip=True)

        # Content extraction with iterative cleaning
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
        raise ValueError(f"Failed to parse Beehiiv article. The website layout may be different. Error: {e}")


# --- MAIN API ENDPOINT (Dispatcher) ---
@app.get("/v1/article-content")
async def get_article_content(url: str):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
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

        return {"success": True, "article_url": url, **data}

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch the URL: {e}")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")