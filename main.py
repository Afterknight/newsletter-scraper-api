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


def _scrape_substack_article(soup: BeautifulSoup) -> dict:
    try:
        author, publication, publication_date = "Author not found", "Publication not found", None

        # --- PRIMARY: JSON-LD block ---
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
                pass  # silently skip malformed JSON

        # --- SECONDARY: HTML META TAGS ---
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

        # --- THIRD: DOM Elements as fallback ---
        if author == "Author not found":
            byline = soup.select_one('div.pencraft-card-meta-row a.pencraft-card-meta-row-owner-name')
            if byline:
                author = byline.get_text(strip=True)

        if publication == "Publication not found":
            pub = soup.select_one('div.pencraft-card-meta-row a.pencraft-card-meta-row-publication-name')
            if pub:
                publication = pub.get_text(strip=True)

        if not publication_date:
            date_container = soup.select_one('div[aria-label="Post UFI"] div.color-pub-secondary-text-hGQ02T')
            if date_container:
                publication_date = date_container.get_text(strip=True)

        # --- Title and subtitle ---
        title = soup.select_one('h1.post-title')
        subtitle = soup.select_one('h3.subtitle')
        title = title.get_text(strip=True) if title else "Title not found"
        subtitle = subtitle.get_text(strip=True) if subtitle else None

        # --- Content parsing ---
        content_body = soup.select_one('div.body.markup')
        if not content_body:
            raise ValueError("Main content body not found.")

        # Clean up clutter
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