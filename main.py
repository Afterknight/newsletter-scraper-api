# main.py 

import requests
import re
import json
from fastapi import FastAPI, HTTPException
from bs4 import BeautifulSoup
from urllib.parse import urlparse

# --- App Definition ---
app = FastAPI(
    title="Universal Newsletter Scraper API v1 (multiple upgrades)",
    description="A production-grade API with a multi-layered fallback system for maximum reliability and pristine text output.",
    version="1.0.0",
)


def _scrape_substack_article(soup: BeautifulSoup) -> dict:
    """
    Scrapes a Substack article using a hybrid, fallback-driven approach.
    1. Attempts to get metadata from the reliable JSON-LD script.
    2. If it fails, falls back to specific HTML selectors.
    3. Performs two-stage text sanitization for perfectly clean output.
    """
    try:
        # --- Metadata Extraction ---
        # Initialize with default "not found" values
        author, publication, publication_date = "Author not found", "Publication not found", None

        # Plan A: Try to parse the clean JSON-LD data first
        script_tag = soup.find('script', {'type': 'application/ld+json'})
        if script_tag:
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
        
        # Plan B: If JSON-LD fails, fall back to HTML scraping for metadata
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

        # Extract visual titles from HTML (this is generally reliable)
        title_element = soup.select_one('h1.post-title')
        title = title_element.get_text(strip=True) if title_element else "Title not found"
        subtitle_element = soup.select_one('h3.subtitle')
        subtitle = subtitle_element.get_text(strip=True) if subtitle_element else None
        
        # --- Content Extraction and Two-Stage Sanitization ---
        content_body = soup.select_one('div.body.markup')
        if not content_body:
            raise ValueError("Main content body (`div.body.markup`) could not be found.")

        clutter_selectors = [
            'div.subscription-widget-wrap', 'div.captioned-image-container',
            'div.community-chat', 'p.button-wrapper', 'div.pullquote', 'hr',
            '.instagram', '.like-button-container', '.post-ufi-comment-button'
        ]
        for selector in clutter_selectors:
            for element in content_body.select(selector):
                element.decompose()

        text_blocks = []
        for element in content_body.select('p, h3, li'):
            # Stage 1: Get text and immediately sanitize it by replacing single newlines with spaces
            clean_text = element.get_text(strip=True).replace('\n', ' ')
            if clean_text:
                text_blocks.append(clean_text)
        
        # Stage 2: Join the pre-cleaned blocks to form the final, pristine text
        polished_text = '\n\n'.join(text_blocks)

        return {
            "publication_name": publication, "article_title": title,
            "article_subtitle": subtitle, "author": author,
            "publication_date": publication_date, "full_text": polished_text
        }
    except Exception as e:
        raise ValueError(f"A critical error occurred during parsing. The website layout may be fundamentally different. Error: {e}")

# ... [The Beehiiv scraper] ...
def _scrape_beehiiv_article(soup: BeautifulSoup) -> dict:
    try:
        title = soup.select_one('h1').get_text(strip=True)
        subtitle = None
        author = soup.select_one('a.text-center.text-sm.font-semibold').get_text(strip=True)
        publication = urlparse(soup.select_one("link[rel='canonical']")['href']).netloc.split('.')[0]
        date_element = soup.select_one('time[datetime]')
        publication_date = date_element['datetime'].split('T')[0] if date_element else None
        
        content_body = soup.select_one('div.prose')
        if not content_body: raise ValueError("Main content body (`div.prose`) not found.")
            
        text_blocks = [el.get_text(strip=True).replace('\n', ' ') for el in content_body.select('p, h1, h2, h3, li') if el.get_text(strip=True)]
        polished_text = '\n\n'.join(text_blocks)
        
        return {
            "publication_name": publication.capitalize(), "article_title": title,
            "article_subtitle": subtitle, "author": author, "publication_date": publication_date,
            "full_text": polished_text
        }
    except Exception as e:
        raise ValueError(f"Failed to parse Beehiiv article. Error: {e}")


# --- MAIN API ENDPOINT ---
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

@app.get("/")
def read_root():
    return {"message": "Newsletter Scraper API v1 is running. See /docs for usage."}