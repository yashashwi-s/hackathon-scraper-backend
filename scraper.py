import time
import json
import logging
from typing import List, Dict, Optional
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
import google.generativeai as genai
from datetime import datetime
import re
from dotenv import load_dotenv
import os
import urllib3
from pymongo import MongoClient

# Disable the specific InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# Constants
OUTPUT_FILE = "hackathons.json"
SEARCH_QUERY = "upcoming hackathons"
MAX_RESULTS = 50
DELAY = 0.2  # Seconds between requests
EXCLUDED_SITES = ["devpost", "devfolio", "unstop", "hackerrank", "hackerearth"]
CUSTOM_SEARCH_URL = 'https://www.googleapis.com/customsearch/v1'
CUSTOM_SEARCH_API_KEY = os.getenv('GOOGLE_API_KEY')
CUSTOM_SEARCH_ID = os.getenv('SEARCH_ENGINE_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Configure logging and API
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

class WebScraper:
    def __init__(self):
        self.options = webdriver.ChromeOptions()
        self.options.add_argument('--headless')
        # self.service = Service(chromedrier_path)

    def google_search(self, max_results = MAX_RESULTS):
        """URLs from multiple Google search results pages."""
        driver = webdriver.Chrome(options=self.options)
        links = []
        page_number = 0
        results_per_page = 10  # Google search returns 10 results per page by default
        
        try:
            while len(links) < max_results:
                start_param = page_number * results_per_page
                search_url = f"https://www.google.com/search?q={SEARCH_QUERY}&start={start_param}"
                logger.info(f"Scraping page {page_number + 1}: {search_url}")
                
                params = {
                    'q': SEARCH_QUERY,
                    'key': CUSTOM_SEARCH_API_KEY,
                    'cx': CUSTOM_SEARCH_ID,
                    'cr': 'countryIN',
                    'start': start_param,
                }

                print(CUSTOM_SEARCH_URL)
                results = requests.get(CUSTOM_SEARCH_URL, params=params)
                for item in results.json()['items']:
                    print(item['title'])
                results = results.json()['items']
                
                for result in results:
                    href = result["link"]
                    if href and href.startswith('http') and not 'google' in href:
                        if not any(excluded in href for excluded in EXCLUDED_SITES):
                            links.append(href)
                        else:
                            logger.info(f"Excluded URL: {href}")
                    if len(links) >= max_results:
                        break
                
                page_number += 1
                
            logger.info(f"Found {len(links)} valid URLs")
        
        except Exception as e:
            logger.error(f"Search error: {e}")
        finally:
            driver.quit()
        
        return links[:max_results]
        
    def scrape_page(self, url):
        """Scrape webpage content using Selenium and BeautifulSoup to extract both text and links."""
        driver = webdriver.Chrome(options=self.options)
        content = {"text": None, "links": [], "image_links" : []}
        
        try:
            driver.get(url)
            time.sleep(2)
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            content["text"] = ' '.join(line for line in lines if line)
            image_srcs = [img['src'] for img in soup.find_all('img') if 'src' in img.attrs]
            content["image_links"] = image_srcs

            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if href and (href.startswith('http://') or href.startswith('https://')):
                    description = a_tag.get_text(strip=True)
                    content["links"].append({"url": href, "description": description})
                
        except Exception as e:
            logger.error(f"Scraping error for {url}: {e}")
        finally:
            driver.quit()
            
        return content

    def parse_date_range(self, date_str):
        date_str = date_str.strip().lower()
        if " to " in date_str:
            end_date_str = date_str.split(" to ")[1].strip()
        else:
            end_date_str = date_str
        return end_date_str
    
    def classify_content(self, content: str, url: str) -> Optional[List[Dict]]:
        today_date = datetime.now()
    
        prompt = f"""
        Determine whether the following content describes a hackathon event. 
        If it does, extract the relevant details and return them in the specified JSON format. 
        If the content does not describe a hackathon, return a JSON response indicating "is_hackathon": false.
        
        Task Requirements:
        - "is_hackathon": true for hackathons.
        - "name": The official name.
        - "date": End date in "DD-MM-YYYY" format or full range.
        - "link": URL associated.
        - "description": A brief description.
        - "type": remote or onsite.
        - "category": AI,Web3,Software Development.
        - "prize pool": list prizes.
        - "image sources": list of URLs (same as image_links).
        
        Only include upcoming events (after {today_date.strftime('%d-%m-%Y')}). 
        
        Content to Classify:
        {content}
        """
        
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            if '```' in text:
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
            try:
                hackathons = json.loads(text)
                if not isinstance(hackathons, list):
                    hackathons = [hackathons]
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON response: {e}. Response: {text}")
                return None
            
            upcoming_hackathons = []
            for hackathon in hackathons:
                if isinstance(hackathon, dict) and hackathon.get("is_hackathon") and hackathon.get("date"):
                    end_date_str = self.parse_date_range(hackathon["date"])
                    if not end_date_str:
                        logger.warning(f"Skipping hackathon due to invalid date format: {hackathon.get('name', 'Unknown')}")
                        continue
                    upcoming_hackathons.append(hackathon)
            return upcoming_hackathons
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return None

    def save_hackathons(self, hackathons: List[Dict]):
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(hackathons, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(hackathons)} hackathons to {OUTPUT_FILE}")
        except Exception as e:
            logger.error(f"Save error: {e}")

    def search_additional_info(self, name: str) -> Dict[str, Optional[str]]:
        search_query = f"{name} details"
        logger.info(f"Searching additional details for: {name}")
    
        additional_info = {
            "link": None,
            "description": None,
            "type": None,
            "category": None,
            "prize pool": None
        }
        
        try:
            candidate_contents = []
            params = {
                'q': search_query,
                'key': CUSTOM_SEARCH_API_KEY,
                'cx': CUSTOM_SEARCH_ID,
                'cr': 'countryIN',
                'start': 1,
            }
            results = requests.get(CUSTOM_SEARCH_URL, params=params)
            for item in results.json()['items']:
                print(item['title'])
            results = results.json()['items']
            
            for result in results[:3]:
                href = result['link']
                if href and href.startswith('http') and not 'google' in href:
                    logger.info(f"Scraping {href} for details...")
                    page_content = self.scrape_page(href)
                    if page_content:
                        candidate_contents.append((href, page_content))
                        if not additional_info["link"]:
                            additional_info["link"] = href
            if candidate_contents:
                prompt = f"""
                Extract hackathon details from the provided content using this JSON structure:
                - "link": The event URL.
                - "description": A brief event description.
                - "type": "remote" or "onsite".
                - "category": "AI", "Web3", or "Software Development".
                - "prize pool": list prizes.
                
                Content:
                {json.dumps(candidate_contents[:2])}
                """
                try:
                    response = model.generate_content(prompt)
                    text = response.text.strip()
                    if '```' in text:
                        text = text.split('```')[1]
                        if text.startswith('json'):
                            text = text[4:]
                    additional_details = json.loads(text)
                    if isinstance(additional_details, dict):
                        additional_info.update({
                            "link": additional_details.get("link") or additional_info["link"],
                            "description": additional_details.get("description") or additional_info["description"],
                            "type": additional_details.get("type"),
                            "category": additional_details.get("category"),
                            "prize pool": additional_details.get("prize pool")
                        })
                except Exception as e:
                    logger.error(f"LLM processing error for {name}: {e}")
        except Exception as e:
            logger.error(f"Error searching additional info for {name}: {e}")
    
        return additional_info

def save_hackathons_to_mongo(hackathons: List[Dict]):
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client["hackathonDB"]
    if "hackathons" in db.list_collection_names():
        db.drop_collection("hackathons")
    collection = db["hackathons"]
    
    formatted_hackathons = []
    for h in hackathons:
        formatted_h = {
            "is_hackathon": h.get("is_hackathon", True),
            "name": h.get("name"),
            "date": h.get("date"),
            "link": h.get("link"),
            "description": h.get("description"),
            "type": h.get("type"),
            # Ensure category is stored as a list
            "category": h.get("category") if isinstance(h.get("category"), list) else [h.get("category")] if h.get("category") else [],
            "prize pool": h.get("prize_pool", []),
            "image sources": h.get("image_sources", [])
        }
        formatted_hackathons.append(formatted_h)
    
    if formatted_hackathons:
        result = collection.insert_many(formatted_hackathons)
        print("Inserted document IDs:", result.inserted_ids)
    else:
        print("No hackathons to insert.")

def main():
    scraper = WebScraper()
    hackathons = []

    logger.info("Searching for hackathons...")
    urls = scraper.google_search()

    if not urls:
        logger.error("No URLs found")
        return

    logger.info("Processing pages...")
    for url in urls:
        content = scraper.scrape_page(url)
        if content:
            result = scraper.classify_content(content, url)
            if result:
                hackathons.extend(result)
        time.sleep(DELAY)

    incomplete_hackathons = [h for h in hackathons if not h.get("link") or not h.get("description")]
    for hackathon in incomplete_hackathons:
        additional_info = scraper.search_additional_info(hackathon["name"])
        hackathon.update({
            "link": hackathon.get("link") or additional_info["link"],
            "description": hackathon.get("description") or additional_info["description"],
            "type": hackathon.get("type") or additional_info["type"],
            "category": hackathon.get("category") or additional_info["category"],
            "prize pool": hackathon.get("prize_pool") or additional_info["prize pool"]
        })
    print(hackathons)
    if hackathons:
        scraper.save_hackathons(hackathons)
        save_hackathons_to_mongo(hackathons)
    else:
        logger.warning("No hackathons found")

main()
