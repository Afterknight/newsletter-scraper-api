# 📬 Newsletter Scraper API

A fast, production-ready API that scrapes full content and metadata from public **Substack** and **Beehiiv** newsletter articles. Returns clean, structured JSON that’s perfect for AI tools, summarizers, dashboards, and searchable databases.

---

## 🔥 What This API Does

Send a single GET request with a public newsletter article URL, and get back:

- ✅ Title  
- ✅ Subtitle (if available)  
- ✅ Author  
- ✅ Publication name  
- ✅ Publish date  
- ✅ Full clean text (ready for AI or display)
---
## ✅ Supported Platforms

- `substack.com`  
- `beehiiv.com`

More platforms will be added later (Ghost, Medium, etc.).

---

## 📥 Getting Started

**Endpoint:**  
GET /v1/article-content


**Query Parameters:**

| Name | Type   | Required | Description                          |
|------|--------|----------|--------------------------------------|
| url  | string | Yes      | Full public article URL to scrape    |

**Example Request:**
GET /v1/article-content?url=https://annanewton.substack.com/p/how-to-be-organised-in-2025


**Example Response:**
```json
{
  "success": true,
  "article_url": "https://annanewton.substack.com/p/how-to-be-organised-in-2025",
  "publication_name": "The Wardrobe Edit",
  "article_title": "How To Be Organised in 2025",
  "article_subtitle": "29 ideas to make you feel like you have your s**t together...",
  "author": "Anna Newton",
  "publication_date": "Dec 28, 2024",
  "full_text": "Creating content online for 15 years means I’ve experienced many eras -the ombre..."
}
```
This has many potential uses, creativity depends on the user.

# 🧠 NEW: Batch Scraping (POST)
Need to scrape multiple articles in one call?

Endpoint:
POST /v1/article-batch

Request Body:

    {
      "urls": [
        "https://annanewton.substack.com/p/how-to-be-organised-in-2025",
        "https://mymorning.somesite.com/p/ai-wars"
      ]
    }


Response:

    {
      "success": true,
      "results": [
        {
          "article_url": "...",
          "publication_name": "...",
          "article_title": "...",
          ...
        },
        {
          "article_url": "...",
          "error": "Unsupported platform"
        }
      ]
    }

Send up to 10 URLs per request. Each result is returned individually. Invalid links are handled gracefully with an error field.

# 💡 Real-World Use Cases

**1.  For AI Builders & Researchers**
- Feed articles into GPT or RAG systems
- Build domain-specific LLM datasets
- Summarize newsletter content at scale

**2. For Content & Media Products**

- Power newsletter digests or aggregators
- Create audio versions with TTS
- Monitor topics, trends, and top writers 
 
**3. For Power Users & Analysts**

- Create searchable archives
- Track newsletter content across niches
- Analyze publishing frequency or sentiment 

# ❌ Limitations

- Does not support paywalled/private content
- Only works with Substack and Beehiiv for now
- Returns plain text only (no images/media)

# 🛠 Status

- Live & stable on Vercel
- JSON outputs are optimized for parsing or AI pipelines
- Built with FastAPI, BeautifulSoup, and fallback scraping logic

# 📬 Contact
Need more platforms supported?
Want a personal paid tier or private deployment?

Reach out: shanimam97@gmail.com (Please use **"Custom Newsletter Scraper Request"** as the subject)

Alternatively, you may also ask questions, report bugs, and request help in the [discussions](https://rapidapi.com/Afterknight/api/universal-newsletter-scraper/discussions) section.

**Thank You 💙** for using my API. Consider a paid plan to support me and have a greater amount of monthly requests.



