import csv, os, re, time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (NoSuchElementException, TimeoutException,
                                        ElementClickInterceptedException)
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.action_chains import ActionChains
import json
### ─────────────────────────  הגדרות בסיס  ─────────────────────────
EMAIL     = os.environ["NEVO_EMAIL"]
PASSWORD  = os.environ["NEVO_PASSWORD"]
FROM_DATE = "01/01/2013"
PAUSE     = 1        # שניות לעצירה קבועה בין פעולות
EXISTING_CSV = r"C:\Users\user\OneDrive\טל\projects\justice-tal\bias_weapon\data\new_verdicts.csv"
FOLDER_OUTPUT = "all_verdicts"
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                          options=chrome_options)
wait   = WebDriverWait(driver, 2)

# ──────────────── פונקציות עזר ────────────────
def total_pages():
    txt = driver.find_element(By.TAG_NAME, "h1").text
    cases = int(txt.split()[1].replace(',', ''))
    return (cases + 49) // 50

def extract_judges(result_div):
    judges = []
    prosecutors = []
    defendants = []
    laws_clauses = {}
    
    # ========== ניסיון ראשון: השיטה הישנה - מדף התוצאות ==========
    print("   → Trying to extract from search results page...")
    try:
        # Try to find and click "צדדים וב"כ" link in search results
        parties_links = result_div.find_elements(By.XPATH, ".//a[contains(text(),'צדדים וב\"כ')]")
        if parties_links:
            driver.execute_script("arguments[0].click();", parties_links[0])
            time.sleep(PAUSE)
            
            try:
                # חיפוש הקונטיינר המדויק של צדדים וב"כ
                participants_container = WebDriverWait(result_div, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "participantsList")))
                
                # עכשיו נחפש רק בתוך הקונטיינר הזה
                judges = [li.text.strip() for li in participants_container.find_elements(
                          By.XPATH, ".//span[contains(text(),'שופטים')]/following-sibling::ul/li")]
                prosecutors = [li.text.strip() for li in participants_container.find_elements(
                          By.XPATH, ".//span[contains(text(),'תובעים')]/following-sibling::ul/li")]
                defendants = [li.text.strip() for li in participants_container.find_elements(
                          By.XPATH, ".//span[contains(text(),'משיבים')]/following-sibling::ul/li")]
                
                # גם נאשמים
                defendants.extend([li.text.strip() for li in participants_container.find_elements(
                          By.XPATH, ".//span[contains(text(),'נאשמים')]/following-sibling::ul/li")])
                
                # סנן רשומות ריקות
                judges = [j for j in judges if j]
                prosecutors = [p for p in prosecutors if p]
                defendants = [d for d in defendants if d]
                
                print(f"   ✓ Found {len(judges)} judges, {len(prosecutors)} prosecutors, {len(defendants)} defendants")
            except (TimeoutException, NoSuchElementException) as e:
                print(f"   ⚠️ Participants container not found or empty")
        else:
            print("   ⚠️ 'צדדים וב\"כ' link not found")

                
    except Exception as e:
        print(f"   ⚠️ Search results method failed: {e}")
    
    if len(judges) == 0 or len(prosecutors) == 0 or len(defendants) == 0:
        judges = []
        prosecutors = []
        defendants = []
        
        # ========== שופט - מה-body ==========
        try:
            # מחפש span עם class="title" שמכיל "שופטים:"
            # השופט הוא הטקסט שאחרי ה-span
            body_div = result_div.find_element(By.CLASS_NAME, "body")
            
            # שיטה 1: XPath - לקחת את הטקסט אחרי span שופטים
            judge_span = body_div.find_element(By.XPATH, ".//span[@class='title' and contains(text(),'שופטים')]")
            
            # הטקסט של השופט הוא ה-nextSibling (text node)
            judge_name = driver.execute_script("""
                var span = arguments[0];
                var nextText = span.nextSibling;
                return nextText ? nextText.textContent.trim() : '';
            """, judge_span)
            
            if judge_name:
                judges.append(judge_name)
                print(f"   ✓ Judge: {judge_name}")
                
        except Exception as e:
            print(f"   ⚠️ Judge extraction failed: {e}")
        
        # ========== תובע מה-HEADER ==========
        try:
            header = result_div.find_element(By.CLASS_NAME, "header")
            h5 = header.find_element(By.TAG_NAME, "h5")
            
            b_elements = h5.find_elements(By.TAG_NAME, "b")
            if len(b_elements) >= 1:
                prosecutor = b_elements[0].get_attribute("title") or b_elements[0].text.strip()
                prosecutors.append(prosecutor)
                print(f"   ✓ Prosecutor: {prosecutor}")
                
        except Exception as e:
            print(f"   ⚠️ Prosecutor extraction failed: {e}")
        
        # ========== נאשם מה-veridctAnishaInfo ==========
# ========== נאשם מה-veridctAnishaInfo ==========
        try:
            anisha_div = result_div.find_element(By.CLASS_NAME, "veridctAnishaInfo")
            
            # מחפש את ה-span עם "הנאשם:" ולוקח את הטקסט שאחריו
            defendant_span = anisha_div.find_element(
                By.XPATH, ".//span[@class='title' and contains(text(),'הנאשם')]"
            )
            
            # הטקסט של הנאשם הוא ה-nextSibling (text node) - בדיוק כמו השופט
            defendant_text = driver.execute_script("""
                var span = arguments[0];
                var nextText = span.nextSibling;
                return nextText ? nextText.textContent.trim() : '';
            """, defendant_span)
            
            if defendant_text:
                # לקחת רק את השם (לפני הפסיק)
                if "," in defendant_text:
                    defendant_name = defendant_text.split(",")[0].strip()
                else:
                    defendant_name = defendant_text.strip()
                
                defendants.append(defendant_name)
                print(f"   ✓ Defendant: {defendant_name}")
            
        except NoSuchElementException:
            # fallback - מה-header
            try:
                b_elements = result_div.find_elements(By.CSS_SELECTOR, ".header h5 b")
                if len(b_elements) >= 2:
                    defendant = b_elements[1].get_attribute("title") or b_elements[1].text.strip()
                    defendants.append(defendant)
                    print(f"   ✓ Defendant (from header): {defendant}")
            except:
                pass
        except Exception as e:
            print(f"   ⚠️ Defendant extraction failed: {e}")

            
    return judges, prosecutors, defendants

# ──────────────── איסוף מידע ────────────────
def extract_case_data(result_div,real):
    """
    מחלצת את כל המידע מתיק בודד (result_div)
    """
    try:
        # שלוף את כל הפרטים הבסיסיים
        try:
            parties_text = result_div.find_element(By.TAG_NAME, "h5").text
        except NoSuchElementException:
            parties_text = ""
        
        try:
            date = result_div.find_element(By.CSS_SELECTOR,
                                          ".resultProperties span:nth-child(3)").text
        except NoSuchElementException:
            date = ""
        
        try:
            court = result_div.find_element(By.CSS_SELECTOR,
                                           ".resultProperties span:nth-child(2)").text
        except NoSuchElementException:
            court = ""
        
        try:
            pages = result_div.find_element(By.CSS_SELECTOR,
                                           ".resultProperties span:nth-child(4)").text
        except NoSuchElementException:
            pages = ""
        
        # Case Number - מנסה למצוא בכמה מקומות
        case_number = ""
        try:
            h5_text = result_div.find_element(By.TAG_NAME, "h5").text
            match = re.search(r'\b\d{5}-\d{2}-\d{2}\b', h5_text)
            if match:
                case_number = match.group(0)
        except NoSuchElementException:
            pass
        
        location_match = re.search(r"\(([^)]+)\)", parties_text)
        location = location_match.group(1) if location_match else ""
        
        # Document Link
        try:
            doc_element = result_div.find_element(By.XPATH, ".//a[contains(@title, 'הורדת Word') and contains(@class, 'docLink')]")
            doc_link = doc_element.get_attribute('href')
            part = doc_link.split("/")[-1]
        except NoSuchElementException:
            doc_element = result_div.find_element(
                By.XPATH, ".//a[contains(@title, 'הורדת PDF') and contains(@class, 'pdfLink')]")
            doc_link = doc_element.get_attribute('href')
            part = doc_link.split("/")[-1]
        if part[:-4] != real:
            return {
            "Case Number": None,
            "Date": None,
            "Court": None,
            "Pages": None,
            "Location": None,
            "Parties": None,
            "Mini Ratz": None,
            "Judges": None,
            "Prosecutors":None,
            "Defendants": None,
            "Laws/Clauses": None,
            "Document Link": None,
            }
            print(f"   ⚠️ Document part '{part}' does not match expected '{real}'")
        # Mini Ratz
        try:
            mini_div = result_div.find_element(By.CSS_SELECTOR, ".miniRatz")
            more = mini_div.find_elements(By.CSS_SELECTOR, "a.moreLink")
            if more:
                driver.execute_script("arguments[0].click();", more[0])
                time.sleep(0.5)
            mini_ratz = mini_div.text.strip()
        except NoSuchElementException:
            mini_ratz = ""
        
        # שלוף שופטים, תובעים, נאשמים וחוקים
        judges, prosecutors, defendants = extract_judges(result_div)
        
        # המר laws_clauses ל-JSON string
        law_txt = ""
        
        return {
            "Case Number": case_number,
            "Date": date,
            "Court": court,
            "Pages": pages,
            "Location": location,
            "Parties": parties_text,
            "Mini Ratz": mini_ratz,
            "Judges": ", ".join(judges),
            "Prosecutors": ", ".join(prosecutors),
            "Defendants": ", ".join(defendants),
            "Laws/Clauses": law_txt,
            "Document Link": doc_link,
        }
    except Exception as e:
        print(f"   ❌ Error extracting case data: {e}")
        import traceback
        traceback.print_exc()
        return None

import requests
import os

# Create output folder if it doesn't exist
os.makedirs(FOLDER_OUTPUT, exist_ok=True)

def download_verdict(result_div, case_id):
    """Download verdict file - prefers docx, falls back to pdf"""
    
    # Try docx first
    try:
        doc_element = result_div.find_element(
            By.XPATH, ".//a[contains(@title, 'הורדת Word') and contains(@class, 'docLink')]")
        doc_link = doc_element.get_attribute('href')
        extension = ".docx"
        print(f"   ✓ Found Word document")
    except NoSuchElementException:
        # Fall back to PDF
        try:
            doc_element = result_div.find_element(
                By.XPATH, ".//a[contains(@title, 'הורדת PDF') and contains(@class, 'pdfLink')]")
            doc_link = doc_element.get_attribute('href')
            extension = ".pdf"
            print(f"   ✓ Found PDF document")
        except NoSuchElementException:
            print(f"   ❌ No document link found")
            return None
    
    # Download the file
    try:
        # Get cookies from selenium session
        cookies = {c['name']: c['value'] for c in driver.get_cookies()}
        
        response = requests.get(doc_link, cookies=cookies, stream=True)
        response.raise_for_status()
        
        # Save file
        filename = f"{case_id}{extension}"
        filepath = os.path.join(FOLDER_OUTPUT, filename)
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"   ✓ Downloaded: {filename}")
        return filepath
        
    except Exception as e:
        print(f"   ❌ Download failed: {e}")
        return None
### ─────────────────────────  כניסה לחשבון  ─────────────────────────
driver.get("https://www.nevo.co.il/PsikaSearch.aspx")
wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "לחץ/י כאן"))).click()
wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_UserName")))\
    .send_keys(EMAIL)
wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_Password")))\
    .send_keys(PASSWORD)
wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_LoginButton"))).click()
driver.get("https://www.nevo.co.il/PsikaSearch.aspx")
time.sleep(PAUSE)

### ─────────────────────────  קריאת מספרי תיקים מקובץ CSV  ─────────────────────────
one_defendant = pd.read_csv("missing_files.csv")
case_numbers = one_defendant['verdict'].tolist()
reals = one_defendant['original_verdict'].tolist()
print(f"Found {len(case_numbers)} case numbers to search")

### ─────────────────────────  חיפוש לפי מספר תיק  ─────────────────────────
all_records = []
print(f"\n1. Reading CSV: {EXISTING_CSV}")
if os.path.exists(EXISTING_CSV):
    df = pd.read_csv(EXISTING_CSV, encoding='utf-8-sig')
    print(f"   ✓ Found existing CSV with {len(df)} rows")
else:
    # אם אין קובץ, צור DataFrame ריק עם העמודות הנכונות
    df = pd.DataFrame(columns=[
        "Case Number", "Date", "Court", "Pages", "Location", "Parties",
        "Mini Ratz", "Judges", "Prosecutors", "Defendants", "Laws/Clauses",
        "Document Link"
    ])
    print(f"   ⚠️ CSV not found, creating new one")
for i, row in enumerate(case_numbers):
    if i == 0:
        continue
    case_number = case_numbers[i]
    real = reals[i]
    print(f"\n========== Searching case {i+1}/{len(case_numbers)}: {case_number} ==========")

    # Navigate back to search page for each new search
    driver.get("https://www.nevo.co.il/PsikaSearch.aspx")
    time.sleep(PAUSE)
    # Set search to גזר דין
    wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_SearchData1Control1_PSAKDIN"))).click()
    wait.until(EC.element_to_be_clickable((By.XPATH, "//option[@value='גזר-דין']"))).click()
    
    # Enter case number in the procedure number field
    case_number_field = wait.until(EC.element_to_be_clickable(
        (By.ID, "ContentPlaceHolder1_ShowPlaceControl1_OneShowPlace1_ProcNumFix")))
    case_number_field.clear()
    case_number_field.send_keys(str(case_number))
    
    # Click search
    wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_btnSearchDown"))).click()
    print("✓ Started search")
    time.sleep(PAUSE)

    # Check if results found
    try:
        # Wait for results to load
        container = driver.find_element(By.ID, "searchResultsMain")
        results = container.find_elements(
            By.XPATH, ".//div[starts-with(@id,'searchItem_') and @role='article']")
        for i, result_div in enumerate(results):
            print(f"--- Extracting result {i+1}/{len(results)} ---")
            # Extract data from results
            # records = extract_case_data(result_div,real)
            # if records:
            #     # הוסף את השורה החדשה
            #     df = pd.concat([df, pd.DataFrame([records])], ignore_index=True)
            #     df.to_csv(EXISTING_CSV, index=False, encoding='utf-8-sig')
            #     print(f"   ✅ Successfully added new case")
            # else:
            #     print(f"   ❌ Failed to extract data")
            downloaded_path = download_verdict(result_div, case_number)

            time.sleep(PAUSE)
            
    except TimeoutException:
        print(f"   ❌ Timeout or no results for case {case_number}")
        continue

### ─────────────────────────  הצגת 50 תוצאות לעמוד  ─────────────────────────
# (This will be done per search if needed)


# ──────────────── שמירה ────────────────
# pd.DataFrame(all_records).to_csv("case_search_results.csv",
#                               index=False, encoding="utf-8-sig")
print(f"\n✅ Saved {len(all_records)} cases to case_search_results.csv")
driver.quit()