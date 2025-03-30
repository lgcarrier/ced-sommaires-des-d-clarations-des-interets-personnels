# CED-QC PDF Downloader

This Python script downloads PDF documents from the "Commissaire à l'éthique et à la déontologie" (CED-QC) website, specifically from the "Registres publics / Sommaires des déclarations des intérêts personnels / Membres du Conseil exécutif et député(e)s" section. The script allows users to download either only the latest document or all available documents for each listed person. Downloaded PDFs are organized in a structured folder hierarchy, and a JSON file is generated for each person to catalog their documents.

## Features

- **Flexible Downloads**: Option to download only the latest document or all documents per person.
- **Organized Output**: PDFs are saved in individual folders with sanitized names for compatibility.
- **JSON Metadata**: Each person's folder includes a JSON file listing their name and downloaded documents.
- **PDF Analysis**: Analyze PDFs using Google's Gemini AI model with customizable prompts.
- **Multiple Analysis Modes**: Analyze PDFs one by one or compare multiple PDFs of the same person.
- **Logging**: Progress and errors are logged to both the console and a file for easy monitoring.
- **Polite Crawling**: Uses random User-Agents and delays to minimize server load.
- **Debug Mode**: Detailed HTML debug logs and HTML snippet saving for troubleshooting.
- **Skip Existing Files**: Supports skipping already downloaded files to avoid redundant downloads.
- **Progress Tracking**: Visual progress bars showing:
  - Overall person processing progress
  - Total PDF download progress across all persons
  - Individual person's PDF download progress

## Installation

Follow these steps to set up the project:

1. **Clone the Repository** (if applicable) or create a project directory.
2. **Create a Virtual Environment**:
   - Navigate to your project directory:
     ```bash
     cd path/to/your/project
     ```
   - Create a virtual environment (replace `env` with your preferred name):
     ```bash
     python -m venv .venv
     ```
   - Activate the virtual environment:
     - **Windows**:
       ```bash
       .venv\Scripts\activate
       ```
     - **macOS/Linux**:
       ```bash
       source .venv/bin/activate
       ```
3. **Install Dependencies**:
   - Install the dependencies from requirements.txt:
     ```bash
     pip install -r requirements.txt
     ```

## Usage

Run the script from the command line with these options:

### Download Options

- **Download all documents for each person**:
  ```bash
  python main.py
  ```
- **Download only the latest document for each person**:
  ```bash
  python main.py --latest-only
  ```
- **Skip downloading files that already exist**:
  ```bash
  python main.py --skip-existing
  ```
- **Combine options**:
  ```bash
  python main.py --latest-only --skip-existing
  ```

### PDF Analysis Options

- **Download and analyze PDFs**:
  ```bash
  python main.py --analyze
  ```
- **Only analyze existing PDFs (no download)**:
  ```bash
  python main.py --analyze-only
  ```
- **Analyze with a custom prompt**:
  ```bash
  python main.py --analyze-only --prompt "Extract key financial interests and summarize them"
  ```
- **Analyze PDFs for a specific person**:
  ```bash
  python main.py --analyze-only --person "Legault,_François_L'Assomption"
  ```
- **Compare all PDFs of a specific person together**:
  ```bash
  python main.py --analyze-only --person "Legault,_François_L'Assomption" --compare-all-person-pdfs
  ```
- **Specify a custom output file for analysis results**:
  ```bash
  python main.py --analyze-only --output-file "analysis_results.json"
  ```
- **Disable saving analysis as text files**:
  ```bash
  python main.py --analyze-only --no-text-files
  ```

### Example

To download only the latest PDF for each person:
```bash
python main.py --latest-only
```

To skip re-downloading existing files in subsequent runs:
```bash
python main.py --skip-existing
```

To download PDFs and then analyze them:
```bash
python main.py --latest-only --skip-existing --analyze
```

To analyze existing PDFs without downloading:
```bash
python main.py --analyze-only
```

The script logs its progress and any errors to both the console and file:
- General logs: `ced_qc_crawler.log`
- Detailed debug logs: `ced_qc_debug.log`

## Output Structure

Downloaded PDFs and JSON files are saved in the following directory structure:

```
output/
└── sommaires-des-declarations-des-interets-personnels/
    ├── Abou-Khalil,_Alice_Fabre/
    │   ├── document_2466_2022-2023.pdf
    │   ├── document_2466_2022-2023_analysis.txt
    │   └── Abou-Khalil,_Alice_Fabre.json
    ├── Arseneau,_Joël_îles-de-la-Madeleine/
    │   ├── document_2468_2022-2023.pdf
    │   ├── document_2468_2022-2023_analysis.txt
    │   └── Arseneau,_Joël_îles-de-la-Madeleine.json
    └── ...
```

Analysis results are saved in three formats:
1. Individual text files alongside each PDF (e.g., `document_2466_2022-2023_analysis.txt`)
2. Combined text file for comparative analyses (e.g., `Legault,_François_L'Assomption_combined_analysis.txt`)
3. JSON file with all results (default: `pdf_analysis_results.json`) with this structure:

```json
{
    "Legault,_François_L'Assomption": {
        "document_2466_2022-2023.pdf": "AI-generated analysis of the document contents..."
    },
    "Arseneau,_Joël_îles-de-la-Madeleine": {
        "document_2468_2022-2023.pdf": "AI-generated analysis of the document contents..."
    }
}
```

Or, when using the `--compare-all-person-pdfs` option:

```json
{
    "Legault,_François_L'Assomption": {
        "combined_analysis": "AI-generated comparative analysis of all the person's documents..."
    }
}
```

- **PDF Filenames**: Named using the document ID and year (e.g., `document_2466_2022-2023.pdf`).
- **JSON Files**: Each person's folder contains a JSON file with this structure:
  ```json
  {
      "name": "Arseneau, Joël (îles-de-la-Madeleine)",
      "documents": [
          "document_2468_2022-2023.pdf"
      ]
  }
  ```

## Debugging

The script includes advanced debugging capabilities:

- **HTML Dumps**: Full page HTML and specific elements are saved in the `debug/` directory.
- **Detailed Logging**: The `ced_qc_debug.log` file contains detailed information about HTML parsing and element selection.
- **Fallback Selectors**: The script attempts alternative CSS selectors if primary selectors fail to find elements.

## Logging and Error Handling

- **Main Logging**: The script uses Python's `logging` module to record info, warnings, and errors to both the console and `ced_qc_crawler.log`.
- **Debug Logging**: More detailed logs are written to `ced_qc_debug.log` without cluttering the main log.
- **Error Handling**: If a PDF download fails or a person's data cannot be parsed, the script logs the error and proceeds to the next person, ensuring uninterrupted operation.

## Project Structure

```
.
├── main.py                # The main script
├── requirements.txt       # Python dependencies
├── .gitignore             # Git ignore file
├── README.md              # This documentation
├── ced_qc_crawler.log     # General logging
├── ced_qc_debug.log       # Detailed debug logging
├── debug/                 # HTML snippets for debugging
│   ├── full_page.html
│   └── texte_element_0.html
└── output/                # Downloaded documents
    └── sommaires-des-declarations-des-interets-personnels/
        └── ...
```

## Dependencies

The script depends on the following Python packages:

- `requests`: For HTTP requests to download PDFs
- `beautifulsoup4`: For parsing HTML content
- `fake-useragent`: For generating random user agents
- `tqdm`: For progress bars
- `google-genai`: For analyzing PDFs using Google's Gemini AI model

You'll need to set up your Google Gemini API key as an environment variable:

```bash
export GOOGLE_API_KEY="your-api-key-here"
```

Or create a `.env` file with:

```
GOOGLE_API_KEY=your-api-key-here
```

## Enhancements and Contributions

### Potential Enhancements

- ✅ **Skip Existing Files**: Added `--skip-existing` flag to prevent re-downloading existing files.
- ✅ **Progress Bar**: Integrate `tqdm` for visual download progress tracking.
- ✅ **PDF Analysis**: Added PDF analysis using Google's Gemini AI model.
- **Metadata Expansion**: Enhance JSON files with additional metadata (e.g., extracted via an LLM).
- **Proxy Support**: Add support for using proxies to distribute requests.
- **Incremental Updates**: Add ability to check for and download only new documents since last run.

### Contributions

Contributions are encouraged! To contribute:
- Submit pull requests with improvements or fixes.
- Report bugs or suggest features via the issue tracker (if hosted on a platform like GitHub).

## License

This project is licensed under the MIT License. See the `LICENSE` file for details (if included).