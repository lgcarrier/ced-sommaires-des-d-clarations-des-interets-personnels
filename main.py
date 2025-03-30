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
from tqdm import tqdm
import dotenv
from pathlib import Path

# Load environment variables from .env file
dotenv.load_dotenv()

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

def get_json_template():
    """
    Returns a JSON template for financial declarations that the AI model should try to fill.
    
    Returns:
        dict: A template JSON structure
    """
    return {
        "member": "",
        "income": [
            {
                "source": "",
                "type": "",
                "amount": ""
            }
        ],
        "assets": [
            {
                "type": "",
                "value": ""
            }
        ],
        "liabilities": [
            {
                "type": "",
                "amount": ""
            }
        ],
        "other_interests": [
            {
                "type": "",
                "description": "",
                "value": ""
            }
        ],
        "family_interests": [
            {
                "member": "",
                "interests": [
                    {
                        "name": "",
                        "description": ""
                    }
                ]
            }
        ]
    }

def get_json_extraction_prompt():
    """
    Returns a detailed prompt for extracting financial information in JSON format.
    
    Returns:
        str: A detailed prompt for the AI model
    """
    template = json.dumps(get_json_template(), ensure_ascii=False, indent=2)
    
    return (
        "Analyser ce document PDF qui contient la déclaration des intérêts personnels d'un membre "
        "de l'Assemblée nationale du Québec. Extraire toutes les informations pertinentes concernant "
        "les revenus, actifs, passifs, et autres intérêts du membre et de sa famille (conjoint, enfants). "
        "Formater la réponse en JSON selon le modèle suivant:\n\n"
        f"```json\n{template}\n```\n\n"
        "Assurez-vous de remplir tous les champs pertinents. Si une information n'est pas disponible, "
        "laissez le champ vide ou indiquez \"Non spécifié\". Pour les montants, si la valeur exacte "
        "n'est pas indiquée mais qu'il y a un seuil (par exemple >= 10 000$), veuillez l'indiquer "
        "dans le format approprié."
    )

def analysis_files_exist(pdf_path, require_both=False):
    """
    Check if analysis files already exist for a given PDF file.
    
    Args:
        pdf_path (str): Path to the PDF file
        require_both (bool): If True, both text and JSON analysis files must exist
        
    Returns:
        bool: True if analysis files exist, False otherwise
    """
    txt_path = pdf_path.replace('.pdf', '_analysis.txt')
    json_path = pdf_path.replace('.pdf', '_analysis.json')
    
    if require_both:
        return os.path.exists(txt_path) and os.path.exists(json_path)
    else:
        return os.path.exists(txt_path) or os.path.exists(json_path)

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Download and analyze PDFs from CED-QC website')
    
    # Download options
    download_group = parser.add_argument_group('Download options')
    download_group.add_argument('--latest-only', action='store_true', 
                        help='Download only the latest document for each person')
    download_group.add_argument('--skip-existing', action='store_true',
                        help='Skip downloading files that already exist')
    
    # Analysis options
    analysis_group = parser.add_argument_group('Analysis options')
    analysis_group.add_argument('--analyze', action='store_true',
                         help='Analyze PDFs after downloading')
    analysis_group.add_argument('--analyze-only', action='store_true',
                         help='Skip downloading and only analyze existing PDFs')
    analysis_group.add_argument('--prompt', type=str, 
                         default=get_json_extraction_prompt(),
                         help='Custom prompt to use for PDF analysis')
    analysis_group.add_argument('--person', type=str,
                         help='Analyze PDFs for a specific person (provide folder name)')
    analysis_group.add_argument('--compare-all-person-pdfs', action='store_true',
                         help='Compare all PDFs of each person together')
    analysis_group.add_argument('--output-file', type=str, default="pdf_analysis_results.json",
                         help='Output file for analysis results')
    analysis_group.add_argument('--no-text-files', action='store_true',
                         help='Do not save analysis results as text files next to PDFs')
    analysis_group.add_argument('--skip-analyzed', action='store_true',
                         help='Skip analyzing PDFs that already have analysis files')
    
    args = parser.parse_args()

    # Determine whether to save text files (default is True)
    save_text_files = not args.no_text_files

    # If analyze-only is set, skip the download process
    if not args.analyze_only:
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

        # Count total PDFs to download
        total_pdfs = 0
        for person_li in person_lis:
            sub_ul = person_li.find('ul')
            if sub_ul:
                pdf_links = sub_ul.find_all('a')
                if args.latest_only:
                    total_pdfs += min(1, len(pdf_links))
                else:
                    total_pdfs += len(pdf_links)
        
        logger.info(f"Found {total_pdfs} total PDFs to process")
        
        # Create main progress bar for persons
        person_pbar = tqdm(total=len(person_lis), desc="Processing persons", position=0)
        
        # Create overall PDF progress bar
        pdf_total_pbar = tqdm(total=total_pdfs, desc="Total PDFs", position=1)
        
        # Counter for processed PDFs
        processed_pdfs = 0

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
                    person_pbar.update(1)
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
                    person_pbar.update(1)
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
                
                # Add progress bar for PDFs per person
                pdf_person_pbar = tqdm(total=len(pdf_links), desc=f"{original_name}'s PDFs", position=2, leave=False)
                
                for link in pdf_links:
                    href = link.get('href')
                    if not href:
                        logger.warning(f"No href found in link for {original_name}")
                        pdf_person_pbar.update(1)
                        pdf_total_pbar.update(1)
                        processed_pdfs += 1
                        continue

                    # Extract document ID and year
                    doc_id = link.get('data-id-document', 'unknown')
                    text = link.get_text(strip=True)
                    year_match = re.search(r'\d{4}(?:-\d{4})?', text)
                    year = year_match.group(0) if year_match else 'unknown'

                    # Construct filename
                    filename = f"document_{doc_id}_{year}.pdf"
                    file_path = os.path.join(person_dir, filename)
                    
                    # Update PDF progress bar description
                    pdf_person_pbar.set_description(f"Downloading {filename}")

                    # Check if file should be downloaded
                    if filename in existing_files and args.skip_existing:
                        logger.info(f"Skipping already documented file {filename} for {original_name}")
                        downloaded_files.append(filename)
                        pdf_person_pbar.update(1)
                        pdf_total_pbar.update(1)
                        processed_pdfs += 1
                        continue

                    # Download the PDF
                    if download_pdf(href, file_path, args.skip_existing):
                        downloaded_files.append(filename)
                        logger.info(f"Downloaded {filename} for {original_name}")
                    
                    # Update progress bars
                    pdf_person_pbar.update(1)
                    pdf_total_pbar.update(1)
                    processed_pdfs += 1
                    
                    # Be polite to the server
                    time.sleep(random.uniform(1, 3))
                
                # Close PDF per person progress bar
                pdf_person_pbar.close()

                # Create or update JSON file with the person's information
                json_data = {
                    "name": original_name,
                    "documents": downloaded_files
                }
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=4)
                logger.info(f"Created/Updated JSON file for {original_name}")

                # Update the person progress bar
                person_pbar.update(1)
                
            except Exception as e:
                logger.error(f"Error processing person '{original_name}': {e}", exc_info=True)
                # Still update progress bars in case of error
                person_pbar.update(1)
                
        # Close progress bars
        person_pbar.close()
        pdf_total_pbar.close()
        
        logger.info(f"CED-QC PDF download process completed. Processed {processed_pdfs} PDFs across {len(person_lis)} persons.")

    # PDF Analysis Section
    if args.analyze or args.analyze_only:
        logger.info("Starting PDF analysis process")
        
        # Check if a specific person was specified
        if args.person:
            logger.info(f"Analyzing PDFs for person: {args.person}")
            
            if args.compare_all_person_pdfs:
                # Compare all PDFs for this person
                person_dir = os.path.join(OUTPUT_DIR, args.person)
                if os.path.exists(person_dir) and os.path.isdir(person_dir):
                    pdf_files = [f for f in os.listdir(person_dir) if f.endswith('.pdf')]
                    
                    # Check if combined analysis already exists
                    skip_combined_analysis = False
                    if args.skip_analyzed:
                        combined_analysis_path = os.path.join(person_dir, f"{args.person}_combined_analysis.txt")
                        combined_analysis_json_path = os.path.join(person_dir, f"{args.person}_combined_analysis.json")
                        if os.path.exists(combined_analysis_path) or os.path.exists(combined_analysis_json_path):
                            logger.info(f"Skipping combined analysis for {args.person} as it already exists")
                            skip_combined_analysis = True
                    
                    if not skip_combined_analysis and pdf_files:
                        pdf_paths = [os.path.join(person_dir, pdf) for pdf in pdf_files]
                        result = analyze_multiple_pdfs_together(pdf_paths, args.prompt, save_text_files)
                        results = {args.person: {"combined_analysis": result}}
                        save_analysis_results(results, args.output_file)
                    elif pdf_files and skip_combined_analysis:
                        logger.info(f"Combined analysis for {args.person} already exists. Skipping.")
                    else:
                        logger.warning(f"No PDF files found for person: {args.person}")
                else:
                    logger.error(f"Person directory not found: {person_dir}")
            else:
                # Analyze each PDF separately
                results = analyze_pdfs_by_person(args.person, OUTPUT_DIR, args.prompt, save_text_files, args.skip_analyzed)
                if results:
                    save_analysis_results({args.person: results}, args.output_file)
        else:
            # Analyze all persons
            logger.info("Analyzing PDFs for all persons")
            results = analyze_pdfs_for_all_persons(OUTPUT_DIR, args.prompt, save_text_files, args.skip_analyzed)
            save_analysis_results(results, args.output_file)
            
        logger.info("PDF analysis process completed")

def analyze_pdf_with_gemini(pdf_path, prompt="Summarize this document"):
    """
    Analyze a single PDF file using Google's Gemini AI model.
    
    Args:
        pdf_path (str): Path to the PDF file
        prompt (str): Prompt to send to Gemini along with the PDF
        
    Returns:
        str: The analysis result text
    """
    try:
        from google import genai
        from google.genai import types
        import pathlib
        
        # Check for API key
        if not os.environ.get("GOOGLE_API_KEY"):
            error_msg = "GOOGLE_API_KEY environment variable not found. Please set it and try again."
            logger.error(error_msg)
            return error_msg
        
        logger.info(f"Analyzing PDF: {pdf_path}")
        client = genai.Client()
        
        # Prepare the PDF file
        filepath = pathlib.Path(pdf_path)
        
        if not filepath.exists():
            error_msg = f"PDF file not found: {pdf_path}"
            logger.error(error_msg)
            return error_msg
        
        # Create a progress bar for the analysis
        filename = os.path.basename(pdf_path)
        analysis_steps = ['Loading PDF', 'Sending to Gemini', 'Processing with AI', 'Receiving response']
        step_pbar = tqdm(analysis_steps, desc=f"Analyzing {filename}", position=2, leave=False)
        
        # Read the PDF content (first step)
        step_pbar.set_description(f"Loading {filename}")
        pdf_data = filepath.read_bytes()
        step_pbar.update(1)
        
        # Prepare the request (second step)
        step_pbar.set_description(f"Preparing request")
        contents = [
            types.Part.from_bytes(
                data=pdf_data,
                mime_type='application/pdf',
            ),
            prompt
        ]
        step_pbar.update(1)
        
        # Generate content with the model (third step)
        try:
            step_pbar.set_description(f"Analyzing with Gemini")
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=contents
            )
            step_pbar.update(1)
            
            # Process response (fourth step)
            step_pbar.set_description(f"Processing response")
            result = response.text
            step_pbar.update(1)
            
            # Complete
            step_pbar.set_description(f"Analysis complete")
            step_pbar.close()
            
            logger.info(f"Successfully analyzed PDF: {pdf_path}")
            return result
        except Exception as e:
            step_pbar.set_description(f"Analysis failed")
            step_pbar.close()
            
            error_msg = f"Error generating content with Gemini: {str(e)}"
            logger.error(error_msg)
            return error_msg
    except ImportError as e:
        error_msg = f"Missing required package: {str(e)}. Please install google-genai package."
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        logger.error(f"Error analyzing PDF {pdf_path}: {e}", exc_info=True)
        return f"Analysis failed: {str(e)}"

def extract_json_from_text(text):
    """
    Extract JSON from text content. This tries to find content between ```json and ``` tags,
    or any valid JSON object in the text.
    
    Args:
        text (str): Text that may contain JSON
        
    Returns:
        dict or None: Extracted JSON as dict if found, otherwise None
    """
    try:
        # First try to find JSON between ```json and ``` tags
        json_pattern = r'```json\s*([\s\S]*?)\s*```'
        json_matches = re.findall(json_pattern, text)
        
        if json_matches:
            return json.loads(json_matches[0])
        
        # If that fails, try to extract anything that looks like a JSON object
        json_obj_pattern = r'{\s*"[^"]+"\s*:[\s\S]*}'
        obj_matches = re.findall(json_obj_pattern, text)
        
        if obj_matches:
            return json.loads(obj_matches[0])
        
        # If we couldn't extract JSON, attempt to use the response to fill the template
        template = get_json_template()
        
        # Try to extract member name
        name_pattern = r'"?[Mm]ember"?\s*:\s*"([^"]+)"'
        name_match = re.search(name_pattern, text)
        if name_match:
            template["member"] = name_match.group(1)
        
        # As a basic fallback, set full_text in the template
        template["full_text"] = text
        
        return template
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON from text")
        template = get_json_template()
        template["full_text"] = text
        return template

def save_analysis_files(analysis_text, pdf_path, save_text=True, save_json=True):
    """
    Save analysis results as text and JSON files next to the PDF file.
    
    Args:
        analysis_text (str): The analysis text to save
        pdf_path (str): Path to the PDF file
        save_text (bool): Whether to save as text file
        save_json (bool): Whether to save as JSON file
        
    Returns:
        tuple: Paths to the saved text and JSON files (None if not saved)
    """
    txt_path = None
    json_path = None
    
    # Save as text file if requested
    if save_text:
        txt_path = pdf_path.replace('.pdf', '_analysis.txt')
        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(analysis_text)
            logger.info(f"Saved analysis text to {txt_path}")
        except Exception as e:
            logger.error(f"Error saving analysis text to {txt_path}: {e}")
            txt_path = None
    
    # Save as JSON file if requested
    if save_json:
        json_path = pdf_path.replace('.pdf', '_analysis.json')
        try:
            # Try to extract JSON from the text
            json_data = extract_json_from_text(analysis_text)
            
            # Make sure we have a valid JSON object
            if json_data is None:
                json_data = {"full_analysis": analysis_text}
                logger.warning(f"Couldn't extract structured JSON from analysis, saving full text in JSON format")
            
            # Check if this is already our template with no populated data
            if json_data.get("member", "") == "" and not json_data.get("full_text"):
                # If it's an empty template, include the full text
                json_data["full_text"] = analysis_text
                
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
            logger.info(f"Saved analysis JSON to {json_path}")
        except Exception as e:
            logger.error(f"Error saving analysis JSON to {json_path}: {e}")
            json_path = None
    
    return txt_path, json_path

def save_analysis_results(results, output_file):
    """
    Save analysis results to a JSON file.
    
    Args:
        results (dict): Analysis results to save
        output_file (str): Path to the output file
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    logger.info(f"Analysis results saved to {output_file}")

def analyze_pdfs_for_person(person_dir, prompt="Summarize this document", save_text_files=True, skip_analyzed=False):
    """
    Analyze all PDF files for a single person.
    
    Args:
        person_dir (str): Path to the person's directory
        prompt (str): Prompt to send to Gemini along with the PDFs
        save_text_files (bool): Whether to save analysis results as text files
        skip_analyzed (bool): Whether to skip PDFs that already have analysis files
        
    Returns:
        dict: Dictionary mapping filenames to analysis results
    """
    results = {}
    pdf_files = [f for f in os.listdir(person_dir) if f.endswith('.pdf')]
    
    if not pdf_files:
        logger.warning(f"No PDF files found in {person_dir}")
        return results
    
    logger.info(f"Found {len(pdf_files)} PDF files in {person_dir}")
    
    # Filter out already analyzed PDFs if skip_analyzed is True
    if skip_analyzed:
        filtered_pdf_files = []
        for pdf_file in pdf_files:
            pdf_path = os.path.join(person_dir, pdf_file)
            if not analysis_files_exist(pdf_path):
                filtered_pdf_files.append(pdf_file)
            else:
                logger.info(f"Skipping analyzed PDF: {pdf_file}")
        
        pdf_files = filtered_pdf_files
        if not pdf_files:
            logger.info(f"All PDFs in {person_dir} have already been analyzed. Skipping.")
            return results
    
    # Create a progress bar for analyzing PDFs
    person_name = os.path.basename(person_dir)
    pdf_analysis_pbar = tqdm(pdf_files, desc=f"Analyzing PDFs for {person_name}", position=0, leave=True)
    
    for pdf_file in pdf_analysis_pbar:
        pdf_path = os.path.join(person_dir, pdf_file)
        pdf_analysis_pbar.set_description(f"Analyzing {pdf_file}")
        analysis_result = analyze_pdf_with_gemini(pdf_path, prompt)
        results[pdf_file] = analysis_result
        
        # Save analysis as text file if requested
        if save_text_files and not analysis_result.startswith("Error") and not analysis_result.startswith("Analysis failed"):
            save_analysis_files(analysis_result, pdf_path, save_text_files, True)
        
    return results

def analyze_pdfs_for_all_persons(output_dir, prompt="Summarize this document", save_text_files=True, skip_analyzed=False):
    """
    Analyze PDFs for all persons in the output directory.
    
    Args:
        output_dir (str): Path to the output directory containing person directories
        prompt (str): Prompt to send to Gemini along with the PDFs
        save_text_files (bool): Whether to save analysis results as text files
        skip_analyzed (bool): Whether to skip analyzing PDFs that already have analysis files
        
    Returns:
        dict: Dictionary mapping person names to their analysis results
    """
    results = {}
    person_dirs = [d for d in os.listdir(output_dir) if os.path.isdir(os.path.join(output_dir, d))]
    
    logger.info(f"Found {len(person_dirs)} person directories in {output_dir}")
    
    # Create a progress bar for all persons
    persons_pbar = tqdm(person_dirs, desc="Analyzing persons", position=0, leave=True)
    
    for person_dir_name in persons_pbar:
        person_dir = os.path.join(output_dir, person_dir_name)
        persons_pbar.set_description(f"Person: {person_dir_name}")
        
        person_results = analyze_pdfs_for_person(person_dir, prompt, save_text_files, skip_analyzed)
        if person_results:
            results[person_dir_name] = person_results
    
    # Close the persons progress bar
    persons_pbar.close()
    
    return results

def analyze_pdfs_by_person(person_name, output_dir=OUTPUT_DIR, prompt="Summarize this document", save_text_files=True, skip_analyzed=False):
    """
    Analyze PDFs for a specific person by name.
    
    Args:
        person_name (str): The name of the person (directory name)
        output_dir (str): Path to the output directory containing person directories
        prompt (str): Prompt to send to Gemini along with the PDFs
        save_text_files (bool): Whether to save analysis results as text files
        skip_analyzed (bool): Whether to skip analyzing PDFs that already have analysis files
        
    Returns:
        dict: Dictionary mapping filenames to analysis results, or None if person not found
    """
    person_dir = os.path.join(output_dir, person_name)
    
    if not os.path.exists(person_dir) or not os.path.isdir(person_dir):
        logger.error(f"Person directory not found: {person_dir}")
        return None
    
    return analyze_pdfs_for_person(person_dir, prompt, save_text_files, skip_analyzed)

def analyze_multiple_pdfs_together(pdf_paths, prompt="Compare these documents and highlight the main differences", save_text_file=True):
    """
    Analyze multiple PDFs together in a single prompt to compare them.
    
    Args:
        pdf_paths (list): List of paths to PDF files
        prompt (str): Prompt to send to Gemini along with the PDFs
        save_text_file (bool): Whether to save analysis results as a text file
        
    Returns:
        str: The analysis result text
    """
    try:
        from google import genai
        from google.genai import types
        import pathlib
        
        # Check for API key
        if not os.environ.get("GOOGLE_API_KEY"):
            error_msg = "GOOGLE_API_KEY environment variable not found. Please set it and try again."
            logger.error(error_msg)
            return error_msg
        
        if not pdf_paths or len(pdf_paths) == 0:
            error_msg = "No PDF paths provided for analysis."
            logger.error(error_msg)
            return error_msg
        
        logger.info(f"Analyzing {len(pdf_paths)} PDFs together")
        client = genai.Client()
        
        # Create a progress bar for preparing the PDFs
        prep_pbar = tqdm(pdf_paths, desc="Preparing PDFs for batch analysis", position=0, leave=True)
        
        # Prepare content parts with all PDFs
        contents = []
        for pdf_path in prep_pbar:
            filepath = pathlib.Path(pdf_path)
            filename = os.path.basename(pdf_path)
            prep_pbar.set_description(f"Loading {filename}")
            
            if not filepath.exists():
                error_msg = f"PDF file not found: {pdf_path}"
                logger.error(error_msg)
                return error_msg
                
            contents.append(
                types.Part.from_bytes(
                    data=filepath.read_bytes(),
                    mime_type='application/pdf',
                )
            )
        
        # Close the progress bar
        prep_pbar.close()
        
        # Add the prompt as the last part
        contents.append(prompt)
        
        # Show a progress bar for the analysis phase
        analysis_pbar = tqdm(total=1, desc="Analyzing batch of PDFs with Gemini", position=0, leave=True)
        
        # Generate content with the model
        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=contents
            )
            
            # Update progress bar
            analysis_pbar.update(1)
            analysis_pbar.set_description("Analysis complete!")
            analysis_pbar.close()
            
            logger.info(f"Successfully analyzed {len(pdf_paths)} PDFs together")
            result_text = response.text
            
            # Save analysis as text and JSON files if requested
            if save_text_file and pdf_paths:
                # Use the parent directory of the first PDF for the combined analysis file
                base_dir = os.path.dirname(pdf_paths[0])
                # Use the name of the directory as part of the filename
                dir_name = os.path.basename(base_dir)
                
                # Create a combined filename for the analysis
                combined_file_path = os.path.join(base_dir, f"{dir_name}_combined_analysis.pdf")
                
                # Save both text and JSON files
                save_analysis_files(result_text, combined_file_path, True, True)
            
            return result_text
        except Exception as e:
            # Update progress bar on error
            analysis_pbar.set_description("Analysis failed!")
            analysis_pbar.close()
            
            error_msg = f"Error generating content with Gemini: {str(e)}"
            logger.error(error_msg)
            return error_msg
    except ImportError as e:
        error_msg = f"Missing required package: {str(e)}. Please install google-genai package."
        logger.error(error_msg)
        return error_msg
    except Exception as e:
        logger.error(f"Error analyzing multiple PDFs: {e}", exc_info=True)
        return f"Analysis failed: {str(e)}"

if __name__ == "__main__":
    main()