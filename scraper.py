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
import requests
from dotenv import load_dotenv
import os

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import urllib3
# Disable the specific InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# Constants
OUTPUT_FILE = "hackathons.json"
SEARCH_QUERY = "upcoming hackathons"
MAX_RESULTS = 50
DELAY = 0.2  # Seconds between requests
EXCLUDED_SITES = ["devpost", "devfolio", "unstop", "hackerrank","hackerearth"]
CUSTOM_SEARCH_URL = 'https://www.googleapis.com/customsearch/v1'
CUSTOM_SEARCH_API_KEY = os.getenv('GOOGLE_API_KEY')
CUSTOM_SEARCH_ID = os.getenv('SEARCH_ENGINE_ID')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
# EXCLUDED_SITES = []

# Configure logging and API
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

class WebScraper:
    def __init__(self):
        self.options = webdriver.ChromeOptions()
        # self.options.add_argument('--headless')
        # self.service = Service(chromedrier_path)

    def google_search(self, max_results = MAX_RESULTS):
        """URLs from multiple Google search results pages."""
        driver = webdriver.Chrome(options=self.options)
        '''driver.get("https://accounts.google.com/ServiceLogin?hl=en&passive=true&continue=https://www.google.com/&ec=GAZAmgQ")
         
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "identifierId"))
        )
        # Interact with the element (e.g., enter text)
        email_field.send_keys("selenium.webscraper.temp@gmail.com")
        email_field.send_keys(Keys.RETURN)
        
        try:
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "Passwd"))
            )
            password_field.send_keys("temp@1234",Keys.ENTER)
        except Exception as e:
            print(f"Error: {e}")

        time.sleep(10) 

        driver.implicitly_wait(100)'''
        links = []
        page_number = 0
        results_per_page = 10  # Google search returns 10 results per page by default
        
        try:
            while len(links) < max_results:
                # Build the URL for the current page of results
                start_param = page_number * results_per_page
                search_url = f"https://www.google.com/search?q={SEARCH_QUERY}&start={start_param}"
                logger.info(f"Scraping page {page_number + 1}: {search_url}")
                
                #driver.get(search_url)
                #time.sleep(2)  # Delay to mimic human behavior

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
                #quit()
                results = results.json()['items']
                
                # Find all search result links
                #results = driver.find_elements(By.TAG_NAME, "a")
                for result in results:
                    href = result["link"]
                    # Filter out None, non-http links, and excluded sites
                    if href and href.startswith('http') and not 'google' in href:
                        if not any(excluded in href for excluded in EXCLUDED_SITES):
                            links.append(href)
                        else:
                            logger.info(f"Excluded URL: {href}")
                    if len(links) >= max_results:
                        break
                
                page_number += 1  # Go to the next page
                
            logger.info(f"Found {len(links)} valid URLs")
        
        except Exception as e:
            logger.error(f"Search error: {e}")
        finally:
            driver.quit()
        
        return links[:max_results]  # Ensure we don't return more than MAX_RESULTS
        

    def scrape_page(self,url):
            """Scrape webpage content using Selenium and BeautifulSoup to extract both text and links."""
            driver = webdriver.Chrome(options=self.options)
            content = {"text": None, "links": [], "image_links" : []}
            
            try:
                driver.get(url)
                time.sleep(2)  # Wait for dynamic content to load
                page_source = driver.page_source
                
                soup = BeautifulSoup(page_source, 'html.parser')
                
                # Extract text content
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                content["text"] = ' '.join(line for line in lines if line)
                
                # Extract image src links
                image_srcs = [img['src'] for img in soup.find_all('img') if 'src' in img.attrs]
                content["image_links"] = image_srcs

                # Extract all links that start with http
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    if href and (href.startswith('http://') or href.startswith('https://')):
                        description = a_tag.get_text(strip=True)  # Extract text between <a> and </a> tags
                        content["links"].append({"url": href, "description": description})
                
            except Exception as e:
                logger.error(f"Scraping error for {url}: {e}")
            finally:
                driver.quit()
            
            return content


    def parse_date_range(self,date_str):
        """
        Parse a date string that might be a range and return the end date in DD-MM-YYYY format.
        """
        # try:
            # Remove any whitespace and convert to lowercase
        date_str = date_str.strip().lower()
        
        # Check if it's a date range
        if " to " in date_str:
            # Split on "to" and take the second part (end date)
            end_date_str = date_str.split(" to ")[1].strip()
        else:
            # Single date case
            end_date_str = date_str
            
        # Parse the date string
        # end_date = datetime.strptime(end_date_str, '%d-%m-%Y')
        return end_date_str
            
        # except Exception as e:
        #     logging.warning(f"Date parsing error: {e} for date string: {date_str}")
        #     return None
    
    def classify_content(self,content: str, url: str) -> Optional[List[Dict]]:
        """
        Classify content and extract hackathon details with improved date handling.
        """
        today_date = datetime.now()
    
        prompt = f"""
        Determine whether the following content describes a hackathon event. 
        If it does, extract the relevant details and return them in the specified JSON format. 
        If the content does not describe a hackathon, return a JSON response indicating "is_hackathon": false.
        
        Task Requirements:
        Event Classification:
        - Identify whether the content describes a hackathon.
        - If it is a hackathon, extract the following details in a JSON array format:
            "is_hackathon": Always set this to true for hackathons.
            "name": The official name of the hackathon.
            "date": The end date of the event in "DD-MM-YYYY" format (if it's a date range, return the full range as "DD-MM-YYYY to DD-MM-YYYY").
            "link": The URL associated with the event (if available).
            "description": A brief description of the event, including its theme, objectives, or any other important details.
            "type": remote or onsite
            "category": AI,Web3,Software Development
            "prize pool": list prizes(can be cash prize or intrnship offer of job offer etc.)
            "image sources": return a list of urls keep same as image_links DO NOT CHANGE.
        
        Important guidelines:
        1. Keep the date in its original format - DO NOT try to parse or modify date ranges
        2. Only include events that are upcoming (i.e., events happening after {today_date.strftime('%d-%m-%Y')})
        3. Ensure that the event is a hackathon. Do not classify other types of events
        4. If any of the details are unclear, mark them as null
        5. If the image_links in the json file provided is not null return it WITHOUT CHANGING.
        6. Return the response in this exact format:
        [
            {{
                "is_hackathon": true,
                "name": "Example Hackathon",
                "date": "01-02-2025 to 02-02-2025",
                "link": "http://example.com",
                "description": "an innovation-driven hackathon where artificial intelligence meets creativity! This event brings together developers, data scientists, AI enthusiasts, and problem-solvers to build groundbreaking AI-powered solutions. Whether you're an AI expert or just starting your journey, HackAIthon provides the perfect platform to collaborate, learn, and push the boundaries of AI technology. ",
                "type": Remote,
                "category":AI,
                "prize pool": $10000,
                "image sources": ["https://image-source1.png","https://image-source2.png"]
            }}
        ]
    
        Content to Classify:
        {content}
        """
        
        try:
            # Call the model to classify the content
            response = model.generate_content(prompt)
            text = response.text.strip()
            
            # Clean JSON from markdown if present
            if '```' in text:
                text = text.split('```')[1]
                if text.startswith('json'):
                    text = text[4:]
            
            # Parse the response as JSON
            try:
                hackathons = json.loads(text)
                if not isinstance(hackathons, list):
                    hackathons = [hackathons]
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON response: {e}. Response: {text}")
                return None
            
            # Filter out only the upcoming hackathons
            upcoming_hackathons = []
            for hackathon in hackathons:
                if isinstance(hackathon, dict) and hackathon.get("is_hackathon") and hackathon.get("date"):
                    # try:
                    # For date ranges, parse_date_range will handle extracting the end date
                    end_date_str = self.parse_date_range(hackathon["date"])
                    if not end_date_str:
                        logger.warning(f"Skipping hackathon due to invalid date format: {hackathon.get('name', 'Unknown')}")
                        continue
                        
                    # end_date = datetime.strptime(end_date_str, '%d-%m-%Y')
                    
                    # Compare with today's date
                    # if end_date >= today_date:
                        # Keep the original date string but also store the parsed end date
                        # hackathon["original_date"] = hackathon["date"]
                        # hackathon["parsed_end_date"] = end_date_str
                    upcoming_hackathons.append(hackathon)
                    # else:
                    #     logger.info(f"Skipping past hackathon: {hackathon.get('name', 'Unknown')}")
                            
                    # except ValueError as e:
                    #     logger.warning(f"Date validation error for {hackathon.get('name', 'Unknown')}: {e}")
                    #     continue
            
            return upcoming_hackathons
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return None


    def save_hackathons(self,hackathons: List[Dict]):
        """Save hackathons to JSON file."""
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(hackathons, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(hackathons)} hackathons to {OUTPUT_FILE}")
        except Exception as e:
            logger.error(f"Save error: {e}")


    def search_additional_info(self, name: str) -> Dict[str, Optional[str]]:
        """Use an LLM to search and extract additional details about a hackathon by name."""
        search_query = f"{name} details"
        logger.info(f"Searching additional details for: {name}")
    
        '''driver = webdriver.Chrome(options=self.options)
        driver.get("https://accounts.google.com/ServiceLogin?hl=en&passive=true&continue=https://www.google.com/&ec=GAZAmgQ")
         
        email_field = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "identifierId"))
        )
        # Interact with the element (e.g., enter text)
        email_field.send_keys("selenium.webscraper.temp@gmail.com")
        email_field.send_keys(Keys.RETURN)
        
        try:
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "Passwd"))
            )
            password_field.send_keys("temp@1234",Keys.ENTER)
        except Exception as e:
            print(f"Error: {e}")'''

        additional_info = {
            "link": None,
            "description": None,
            "type": None,
            "category": None,
            "prize pool": None
        }
        
        try:
            '''# Step 1: Perform Google search
            driver.get("https://www.google.com")
            search_box = driver.find_element(By.NAME, "q")
            search_box.send_keys(search_query + Keys.RETURN)
            time.sleep(1)
            
            # Step 2: Collect and scrape content from the first few search result links
            results = driver.find_elements(By.TAG_NAME, "a")'''
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
            #quit()
            results = results.json()['items']
            
            for result in results[:3]:  # Check the top 3 websites
                href = result['link']
                if href and href.startswith('http') and not 'google' in href:
                    logger.info(f"Scraping {href} for details...")
                    page_content = self.scrape_page(href)
                    if page_content:
                        candidate_contents.append((href, page_content))
                        if not additional_info["link"]:
                            additional_info["link"] = href  # Save the first valid URL
            
            # Step 3: Use LLM to analyze content and extract details
            if candidate_contents:
                # Prepare the content for the LLM
                prompt = f"""
                Extract hackathon details from the provided content. Use the following JSON structure:
                - "link": The URL of the event (if available).
                - "description": A brief description of the event.
                - "type": "remote" or "onsite" (if unclear, return null).
                - "category": "AI", "Web3", or "Software Development" (if unclear, return null).
                - "prize pool": A list of prizes (e.g., cash prizes, internships, job offers; if unclear, return null).
                
                Content:
                {json.dumps(candidate_contents[:2])}  # Send only the first two contents for LLM evaluation
                """
                try:
                    response = model.generate_content(prompt)
                    text = response.text.strip()
                    
                    # Clean JSON from markdown if present
                    if '```' in text:
                        text = text.split('```')[1]
                        if text.startswith('json'):
                            text = text[4:]
                    
                    # Parse the response as JSON
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


def main():
        # chromedriver_path = r'/home/prajjwalbajpai/Downloads/chromedriver-linux64/chromedriver'
        scraper = WebScraper()
        hackathons = []

        # Step 1: Get URLs from Google
        logger.info("Searching for hackathons...")
        urls = scraper.google_search()

        if not urls:
            logger.error("No URLs found")
            return

        # Step 2: Scrape and classify pages
        logger.info("Processing pages...")
        for url in urls:
            content = scraper.scrape_page(url)
            if content:
                result = scraper.classify_content(content, url)
                if result:
                    hackathons.extend(result)  # Extend because classify_content returns a list
            time.sleep(DELAY)

        # Step 3: Identify incomplete records
        incomplete_hackathons = [h for h in hackathons if not h.get("link") or not h.get("description")]

        for hackathon in incomplete_hackathons:
            additional_info = scraper.search_additional_info(hackathon["name"])
            hackathon.update({
                "link": hackathon.get("link") or additional_info["link"],
                "description": hackathon.get("description") or additional_info["description"],
                "type": hackathon.get("type") or additional_info["type"],
                "category": hackathon.get("category") or additional_info["category"],
                "prize pool": hackathon.get("prize pool") or additional_info["prize pool"]
            })

        # Step 4: Save results
    
        if hackathons:
            scraper.save_hackathons(hackathons)
        else:
            logger.warning("No hackathons found")

main()

