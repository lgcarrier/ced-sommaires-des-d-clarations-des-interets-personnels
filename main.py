import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString
import random
import os
import re
import json
import time
import logging
from fake_useragent import UserAgent
import argparse

# Configure logging to output to both console and a file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('ced_qc_crawler.log')
    ]
)
logger = logging.getLogger(__name__)

# Create a separate debug log file for HTML dumps and detailed debugging
debug_logger = logging.getLogger('debug')
debug_logger.setLevel(logging.DEBUG)
debug_file_handler = logging.FileHandler('ced_qc_debug.log')
debug_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
debug_logger.addHandler(debug_file_handler)
debug_logger.propagate = False  # Prevent debug logs from appearing in the main log

# Initialize UserAgent for random browser mimicking
ua = UserAgent()

# URL of the page to crawl
PAGE_URL = "https://www.ced-qc.ca/fr/registres-publics/sommaires-des-declarations-des-interets-personnels/22-membres-du-conseil-executif-et-deputes"

# Output directory
OUTPUT_DIR = "output/sommaires-des-declarations-des-interets-personnels"

def get_random_headers():
    """Generate random headers with different User-Agent to mimic browsers."""
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Referer": "https://www.google.com/",
        "Connection": "keep-alive"
    }

def sanitize_name(name):
    """Sanitize a person's name to make it suitable for folder and file naming."""
    # Remove parentheses
    name = re.sub(r'[()]', '', name)
    # Replace multiple spaces with a single space
    name = re.sub(r'\s+', ' ', name)
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    return name

def download_pdf(url, filepath, skip_existing=False):
    """Download a PDF file from a URL and save it to the specified filepath."""
    # Check if file already exists and skip_existing flag is set
    if skip_existing and os.path.exists(filepath):
        logger.info(f"Skipping existing file: {filepath}")
        return True
        
    try:
        response = requests.get(url, headers=get_random_headers())
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        return False

def save_html_snippet(html_content, filename):
    """Save HTML content to a file for debugging purposes."""
    os.makedirs("debug", exist_ok=True)
    with open(f"debug/{filename}", 'w', encoding='utf-8') as f:
        f.write(html_content)
    debug_logger.debug(f"Saved HTML snippet to debug/{filename}")

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Download PDFs from CED-QC website')
    parser.add_argument('--latest-only', action='store_true', 
                        help='Download only the latest document for each person')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip downloading files that already exist')
    args = parser.parse_args()

    logger.info("Starting CED-QC PDF download process")

    # Fetch the webpage
    try:
        response = requests.get(PAGE_URL, headers=get_random_headers())
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch the page {PAGE_URL}: {e}")
        return

    # Save the full HTML for debugging
    save_html_snippet(response.text, "full_page.html")
    
    # Parse the HTML content
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Debug the structure to find the correct selectors
    debug_logger.debug("HTML Structure Analysis:")
    
    # Check for div.texte_contenuStructure
    texte_elements = soup.select("div.texte_contenuStructure")
    debug_logger.debug(f"Found {len(texte_elements)} div.texte_contenuStructure elements")
    
    # Find the letter category listings
    letter_categories = soup.select("div.texte_contenuStructure > div > ul > li")
    debug_logger.debug(f"Found {len(letter_categories)} letter category elements")
    
    # Find all person <li> elements - these are the second level of <li> elements
    person_lis = soup.select("div.texte_contenuStructure > div > ul > li > ul > li")
    logger.info(f"Found {len(person_lis)} persons to process")
    
    if len(person_lis) == 0:
        debug_logger.debug("No person elements found with the primary selector, trying fallbacks...")
        # Save the structure around where we expect to find the lists
        for i, texte_element in enumerate(texte_elements):
            save_html_snippet(str(texte_element), f"texte_element_{i}.html")
        
        # Try a more general selector as fallback
        person_lis = soup.select("ul > li > ul > li")
        debug_logger.debug(f"Fallback selector found {len(person_lis)} elements")

    for person_li in person_lis:
        try:
            # Debug the person element structure
            debug_logger.debug(f"Processing person element: {str(person_li)[:200]}...")
            # Extract the person's original name from direct children before the sub-<ul>
            name_parts = []
            for child in person_li.children:
                if child.name == 'ul':
                    break
                if isinstance(child, NavigableString):
                    text = child.strip()
                    if text:
                        name_parts.append(text)
                elif child.name in ['span', 'br']:
                    text = child.get_text(strip=True)
                    if text:
                        name_parts.append(text)
            original_name = ' '.join(name_parts).strip()

            if not original_name:
                logger.warning("Empty name found, skipping this entry")
                continue

            debug_logger.debug(f"Extracted name: {original_name}")

            # Sanitize the name for folder naming
            folder_name = sanitize_name(original_name)
            person_dir = os.path.join(OUTPUT_DIR, folder_name)
            os.makedirs(person_dir, exist_ok=True)

            # Find the sub-<ul> containing PDF links
            sub_ul = person_li.find('ul')
            if not sub_ul:
                logger.warning(f"No PDF links found for {original_name}")
                continue

            # Get all PDF <a> tags
            pdf_links = sub_ul.find_all('a')
            if args.latest_only:
                pdf_links = pdf_links[:1]  # Take only the first (latest) document

            downloaded_files = []
            existing_files = []
            
            # Check for existing JSON file to get previously downloaded files
            json_path = os.path.join(person_dir, f"{folder_name}.json")
            if args.skip_existing and os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        existing_files = existing_data.get("documents", [])
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse JSON file {json_path}")
            
            for link in pdf_links:
                href = link.get('href')
                if not href:
                    logger.warning(f"No href found in link for {original_name}")
                    continue

                # Extract document ID and year
                doc_id = link.get('data-id-document', 'unknown')
                text = link.get_text(strip=True)
                year_match = re.search(r'\d{4}(?:-\d{4})?', text)
                year = year_match.group(0) if year_match else 'unknown'

                # Construct filename
                filename = f"document_{doc_id}_{year}.pdf"
                file_path = os.path.join(person_dir, filename)

                # Check if file should be downloaded
                if filename in existing_files and args.skip_existing:
                    logger.info(f"Skipping already documented file {filename} for {original_name}")
                    downloaded_files.append(filename)
                    continue

                # Download the PDF
                if download_pdf(href, file_path, args.skip_existing):
                    downloaded_files.append(filename)
                    logger.info(f"Downloaded {filename} for {original_name}")
                
                # Be polite to the server
                time.sleep(random.uniform(1, 3))

            # Create or update JSON file with the person's information
            json_data = {
                "name": original_name,
                "documents": downloaded_files
            }
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
            logger.info(f"Created/Updated JSON file for {original_name}")

        except Exception as e:
            logger.error(f"Error processing person '{original_name}': {e}", exc_info=True)

    logger.info("CED-QC PDF download process completed")

if __name__ == "__main__":
    main()