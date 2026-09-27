import os
import csv, os, re, time
import pandas as pd
import json
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

### ─────────────────────────  הגדרות בסיס  ─────────────────────────
EMAIL     = os.environ["NEVO_EMAIL"]
PASSWORD  = os.environ["NEVO_PASSWORD"]
FROM_DATE = "01/01/2013"
PAUSE     = 1        # שניות לעצירה קבועה בין פעולות
EXISTING_CSV = r"C:\Users\user\OneDrive\טל\projects\justice-tal\bias\data\new_verdicts.csv"

chrome_options = Options()
chrome_options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                          options=chrome_options)
wait   = WebDriverWait(driver, 2)

### ─────────────────────────  כניסה לחשבון  ─────────────────────────
driver.get("https://www.nevo.co.il/PsikaSearch.aspx")
wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "לחץ/י כאן"))).click()
wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_UserName")))\
    .send_keys(EMAIL)
wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_Password")))\
    .send_keys(PASSWORD)
wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_LoginButton"))).click()
driver.get("https://www.nevo.co.il/PsikaSearch.aspx")

### ─────────────────────────  הגדרת סינון חיפוש  ─────────────────────────
wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_SearchData1Control1_PSAKDIN"))).click()
wait.until(EC.element_to_be_clickable((By.XPATH, "//option[@value='גזר-דין']"))).click()
law_box = wait.until(EC.element_to_be_clickable(
    (By.ID, "ContentPlaceHolder1_LawMentionsControl1_OneLawMention1_HLawMentionNameTextBox")))
law_box.send_keys("סמים")
ActionChains(driver).move_to_element(
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#autocompleteList li")))
).click().perform()
date_box = wait.until(EC.element_to_be_clickable(
    (By.ID, "ContentPlaceHolder1_SearchData1Control1_FromDate")))
date_box.clear()
date_box.send_keys(FROM_DATE)

# בחירת סוג הליך: ת"פ - תיק פלילי
process_dropdown = Select(wait.until(EC.element_to_be_clickable(
    (By.ID, "ContentPlaceHolder1_ShowPlaceControl1_OneShowPlace1_Process"))))
process_dropdown.select_by_value("תפ")
time.sleep(PAUSE)

# לחיצה על כפתור בחירת ערכאות
try:
    arkaa_wrapper = wait.until(EC.presence_of_element_located(
        (By.ID, "ContentPlaceHolder1_ShowPlaceControl1_OneShowPlace1_arkaaWrapper")))
    driver.execute_script("arguments[0].scrollIntoView(true);", arkaa_wrapper)
    time.sleep(0.5)
    
    arkaa_button = arkaa_wrapper.find_element(By.CLASS_NAME, "arkaaButton")
    driver.execute_script("arguments[0].click();", arkaa_button)
    print("✓ Clicked arkaaButton")
    time.sleep(PAUSE)
except Exception as e:
    print(f"⚠️ First attempt failed: {e}")
    try:
        driver.execute_script("arguments[0].click();", arkaa_wrapper)
        print("✓ Clicked arkaa_wrapper")
        time.sleep(PAUSE)
    except Exception as e2:
        print(f"⚠️ Second attempt failed: {e2}")
        try:
            ActionChains(driver).move_to_element(arkaa_wrapper).click().perform()
            print("✓ Clicked with ActionChains")
            time.sleep(PAUSE)
        except Exception as e3:
            print(f"❌ All click attempts failed: {e3}")
            raise

# המתנה לפתיחת החלון
try:
    popup = WebDriverWait(driver, 15).until(
        EC.visibility_of_element_located((By.ID, "arkaaPopup")))
    print("✓ Popup opened successfully")
    time.sleep(PAUSE)
except TimeoutException:
    print("❌ Popup did not open. Taking screenshot...")
    driver.save_screenshot("popup_error.png")
    try:
        popup_exists = driver.find_element(By.ID, "arkaaPopup")
        print(f"Popup exists but not visible. Display style: {popup_exists.get_attribute('style')}")
        driver.execute_script("document.getElementById('arkaaPopup').style.display = 'block';")
        driver.execute_script("document.getElementById('arkaaPopup').style.opacity = '1';")
        time.sleep(1)
    except NoSuchElementException:
        print("Popup element does not exist at all")
    raise

# בחירת בתי משפט: עליון, מחוזי, שלום
courts_to_select = [
    "ContentPlaceHolder1_ArkaaPopup1_PsikaCategory1_cblArkaa_0",  # עליון
    "ContentPlaceHolder1_ArkaaPopup1_PsikaCategory1_cblArkaa_1",  # מחוזי
    "ContentPlaceHolder1_ArkaaPopup1_PsikaCategory1_cblArkaa_2"   # שלום
]

for court_id in courts_to_select:
    try:
        checkbox = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, court_id)))
        if not checkbox.is_selected():
            driver.execute_script("arguments[0].click();", checkbox)
            print(f"✓ Selected {court_id}")
            time.sleep(0.3)
    except Exception as e:
        print(f"⚠️ Failed to select {court_id}: {e}")

# שמירה וסגירת החלון
save_button = wait.until(EC.element_to_be_clickable(
    (By.ID, "ContentPlaceHolder1_ArkaaPopup1_btnSave")))
driver.execute_script("arguments[0].click();", save_button)
print("✓ Clicked save button")
time.sleep(PAUSE)

# המשך החיפוש
wait.until(EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_btnSearchDown"))).click()
print("✓ Started search")

### ─────────────────────────  הצגת 50 תוצאות לעמוד  ─────────────────────────
wait.until(EC.element_to_be_clickable((By.ID, "pageSizeDropDown"))).click()
wait.until(EC.element_to_be_clickable(
    (By.XPATH, "//select[@id='pageSizeDropDown']/option[@value='50']"))).click()

# ──────────────── פונקציות עזר ────────────────
def total_pages():
    txt = driver.find_element(By.TAG_NAME, "h1").text
    cases = int(txt.split()[1].replace(',', ''))
    return (cases + 49) // 50


### ─────────────────────────  פונקציה לחילוץ נתונים  ─────────────────────────

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
        
        # Try to extract laws from search results
        sources_tabs = result_div.find_elements(By.XPATH, ".//a[contains(text(),'מקורות שאוזכרו')]")
        if sources_tabs:
            try:
                driver.execute_script("arguments[0].click();", sources_tabs[0])
                time.sleep(PAUSE)
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "mentionTabsContents")))
            except (ElementClickInterceptedException, TimeoutException, NoSuchElementException):
                pass

        # "חקיקה" - לחיצה על הטאב
        law_tabs = result_div.find_elements(By.XPATH, ".//a[contains(text(),'חקיקה')]")
        if law_tabs:
            try:
                driver.execute_script("arguments[0].click();", law_tabs[0])
                time.sleep(PAUSE)
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "mentionTabsContents")))
                container = result_div.find_element(By.CLASS_NAME, "mentionTabsContents")
                blocks = container.find_elements(By.CSS_SELECTOR,
                                                 ".mentionTabItem[style*='display: block'] > *")
                current_law = None
                for el in blocks:
                    cls = el.get_attribute("class")
                    if "law" in cls:
                        # חוק חדש
                        try:
                            law_link = el.find_element(By.CSS_SELECTOR, "a.link")
                            current_law = law_link.text.strip()
                            if current_law and current_law not in laws_clauses:
                                laws_clauses[current_law] = []
                        except NoSuchElementException:
                            pass
                    elif "clause" in cls and current_law:
                        # סעיף - נשלוף רק את ה-span (מספר הסעיף)
                        try:
                            clause_span = el.find_element(By.CSS_SELECTOR, "a.link span")
                            clause_text = clause_span.text.strip()
                            if clause_text:
                                laws_clauses[current_law].append(clause_text)
                        except NoSuchElementException:
                            pass
                
                # נקה חוקים ללא סעיפים
                laws_clauses = {k: v for k, v in laws_clauses.items() if k}
                
                print(f"   ✓ Found {len(laws_clauses)} laws")
            except (ElementClickInterceptedException, TimeoutException, NoSuchElementException) as e:
                print(f"   ⚠️ Failed to extract laws")
                
    except Exception as e:
        print(f"   ⚠️ Search results method failed: {e}")
    
    # # ========== FALLBACK: אם לא הצלחנו, ננסה דרך ה-Highlighter ==========
    # has_meaningful_data = (len(judges) > 0 or len(prosecutors) > 0 or 
    #                       len(defendants) > 0 or len(laws_clauses) > 0)
    
    # if not has_meaningful_data:
    #     print("   → Search results method didn't work, trying Highlighter...")
    #     original_window = driver.current_window_handle
        
    #     try:
    #         # Click the Nevo link to open the highlighter
    #         nevo_link = result_div.find_element(By.XPATH, ".//a[contains(@class, 'nevoLink') and contains(@onclick, 'OpenHighlighter')]")
    #         driver.execute_script("arguments[0].click();", nevo_link)
    #         time.sleep(PAUSE + 1)
            
    #         # Switch to the new window that opened
    #         wait.until(lambda d: len(d.window_handles) > 1)
            
    #         # Find the new window
    #         for window_handle in driver.window_handles:
    #             if window_handle != original_window:
    #                 driver.switch_to.window(window_handle)
    #                 break
            
    #         # Wait for the page to load
    #         wait.until(EC.presence_of_element_located((By.CLASS_NAME, "tabsLinks")))
            
    #         # ========== Extract Participants (צדדים וב"כ) ==========
    #         try:
    #             participants_link = wait.until(EC.element_to_be_clickable((By.ID, "participantsLink")))
    #             driver.execute_script("arguments[0].click();", participants_link)
    #             time.sleep(PAUSE)
                
    #             wait.until(EC.presence_of_element_located((By.CLASS_NAME, "participantsList")))
    #             participants_container = driver.find_element(By.CLASS_NAME, "participantsList")
                
    #             # Find all tables in the participants section
    #             tables = participants_container.find_elements(By.TAG_NAME, "table")
                
    #             for table in tables:
    #                 rows = table.find_elements(By.TAG_NAME, "tr")
    #                 for row in rows:
    #                     cells = row.find_elements(By.TAG_NAME, "td")
                        
    #                     for cell in cells:
    #                         try:
    #                             span = cell.find_element(By.TAG_NAME, "span")
    #                             section_title = span.text.strip()
                                
    #                             # Get the list items under this section
    #                             list_items = cell.find_elements(By.XPATH, ".//ul/li")
    #                             names = [li.text.strip() for li in list_items if li.text.strip()]
                                
    #                             if "שופטים" in section_title:
    #                                 judges.extend(names)
    #                             elif "תובעים" in section_title:
    #                                 prosecutors.extend(names)
    #                             elif "משיבים" in section_title or "נאשמים" in section_title:
    #                                 defendants.extend(names)
    #                             elif "באי-כוח" in section_title or "בא-כוח" in section_title:
    #                                 attorneys.extend(names)
                                    
    #                         except NoSuchElementException:
    #                             continue
                
    #             print(f"   ✓ Highlighter: Found {len(judges)} judges, {len(prosecutors)} prosecutors, {len(defendants)} defendants")
    #         except (TimeoutException, NoSuchElementException, ElementClickInterceptedException) as e:
    #             print(f"   ⚠️ Highlighter: Failed to extract participants")
            
    #         # ========== Extract Laws & Clauses (חקיקה) ==========
    #         try:
    #             # Click on the "מקורות שאוזכרו" (mentioned sources) tab
    #             mentioned_link = wait.until(EC.element_to_be_clickable((By.ID, "mentionedLink")))
    #             driver.execute_script("arguments[0].click();", mentioned_link)
    #             time.sleep(PAUSE)
                
    #             # Wait for the content to load and click on "חקיקה" (legislation) tab
    #             wait.until(EC.presence_of_element_located((By.CLASS_NAME, "mentionTabsLinks")))
    #             hakika_link = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[@data-type='hakika']")))
    #             driver.execute_script("arguments[0].click();", hakika_link)
    #             time.sleep(PAUSE)
                
    #             wait.until(EC.presence_of_element_located((By.CLASS_NAME, "hakikaTab")))
    #             hakika_container = driver.find_element(By.CLASS_NAME, "hakikaTab")
                
    #             law_elements = hakika_container.find_elements(By.CSS_SELECTOR, ".law, .clause, .sign")
                
    #             current_law = None
    #             for element in law_elements:
    #                 element_class = element.get_attribute("class")
                    
    #                 if "law" in element_class:
    #                     # New law found
    #                     try:
    #                         law_text = element.find_element(By.CSS_SELECTOR, "a").text.strip()
    #                         if law_text:
    #                             current_law = law_text
    #                             if current_law not in laws_clauses:
    #                                 laws_clauses[current_law] = []
    #                     except NoSuchElementException:
    #                         pass
                    
    #                 elif ("clause" in element_class or "sign" in element_class) and current_law:
    #                     # Extract clause information
    #                     try:
    #                         clause_link = element.find_element(By.CSS_SELECTOR, "a.link")
    #                         span_element = clause_link.find_element(By.TAG_NAME, "span")
    #                         clause_text = span_element.text.strip()
    #                         if clause_text:
    #                             laws_clauses[current_law].append(clause_text)
    #                     except NoSuchElementException:
    #                         # Handle cases where the structure might be different
    #                         try:
    #                             clause_text = element.find_element(By.CSS_SELECTOR, "a").text.strip()
    #                             if clause_text:
    #                                 laws_clauses[current_law].append(clause_text)
    #                         except NoSuchElementException:
    #                             pass
                
    #             # נקה חוקים ללא סעיפים
    #             laws_clauses = {k: v for k, v in laws_clauses.items() if k}
                
    #             print(f"   ✓ Highlighter: Found {len(laws_clauses)} laws")
    #         except (TimeoutException, NoSuchElementException, ElementClickInterceptedException) as e:
    #             print(f"   ⚠️ Highlighter: Failed to extract laws")
            
    #         # Close the new window and switch back to original
    #         driver.close()
    #         driver.switch_to.window(original_window)
            
    #     except Exception as e:
    #         print(f"   ⚠️ Highlighter method failed: {e}")
    #         # Make sure we're back on the original window
    #         try:
    #             if len(driver.window_handles) > 1:
    #                 for window_handle in driver.window_handles:
    #                     if window_handle != original_window:
    #                         driver.switch_to.window(window_handle)
    #                         driver.close()
    #                 driver.switch_to.window(original_window)
    #         except:
    #             pass
    # else:
    #     print("   ✓ Successfully extracted data from search results page")
    
    return judges, prosecutors, defendants, laws_clauses


### ─────────────────────────  פונקציה לחילוץ מידע מתיק בודד  ─────────────────────────

def extract_case_data(result_div):
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
            case_number = result_div.find_element(By.CSS_SELECTOR, ".resultProperties span:nth-child(1)").text
        except NoSuchElementException:
            # אם לא מצאנו, ננסה לחלץ מה-parties_text
            match = re.search(r'ת"פ\s*\d+[-/]\d+', parties_text)
            if match:
                case_number = match.group(0)
        
        location_match = re.search(r"\(([^)]+)\)", parties_text)
        location = location_match.group(1) if location_match else ""
        
        # Document Link
        try:
            doc_element = result_div.find_element(By.XPATH, ".//a[contains(@title, 'הורדת Word') and contains(@class, 'docLink')]")
            doc_link = doc_element.get_attribute('href')
        except NoSuchElementException:
            doc_link = "N/A"
        
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
        judges, prosecutors, defendants, laws_clauses = extract_judges(result_div)
        
        # המר laws_clauses ל-JSON string
        law_txt = json.dumps(laws_clauses, ensure_ascii=False) if laws_clauses else "{}"
        
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


### ─────────────────────────  הפונקציה הראשית - מתודולוגיה חדשה  ─────────────────────────

def process_website_and_update_csv():
    """
    עובר על כל התוצאות באתר, בודק לכל תיק:
    1. האם הלינק קיים ב-CSV
    2. אם כן - האם יש נאשמים רשומים
       - אם כן - דלג
       - אם לא - מחק את השורה והוסף מחדש
    3. אם לא - הוסף את התיק
    """
    print("=" * 80)
    print("Starting website iteration and CSV update process...")
    print("=" * 80)
    
    # קרא את ה-CSV הקיים או צור חדש
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
    
    # # צור גיבוי
    # if len(df) > 0:
    #     backup_file = EXISTING_CSV.replace('.csv', '_backup.csv')
    #     print(f"\n2. Creating backup: {backup_file}")
    #     df.to_csv(backup_file, index=False, encoding='utf-8-sig')
    #     print(f"   ✓ Backup created")
    
    # המתן לתוצאות
    print("\n3. Waiting for search results...")
    try:
        container = wait.until(EC.presence_of_element_located((By.ID, "searchResultsMain")))
        print("   ✓ Results loaded")
    except TimeoutException:
        print("   ❌ Failed to load results")
        return df
    
    # מונים
    total_cases = 0
    new_cases = 0
    updated_cases = 0
    skipped_cases = 0
    
    # עבור על כל הדפים
    pages = total_pages()
    print(f"\n4. Processing {pages} pages...")
    all_verdicts = []
    for page_num in range(1, pages + 1):
        print(f"\n{'='*80}")
        print(f"PAGE {page_num}/{pages}")
        print(f"{'='*80}")
        
        # המתן שהדף יטען
        time.sleep(2)
        
        # שלוף את כל התוצאות בדף
        try:
            container = driver.find_element(By.ID, "searchResultsMain")
            results = container.find_elements(
                By.XPATH, ".//div[starts-with(@id,'searchItem_') and @role='article']")
            
            print(f"Found {len(results)} results on this page")
            
            # עבור על כל תיק בדף
            for i, result_div in enumerate(results, 1):
                total_cases += 1
                print(f"\n[{i}/{len(results)}] Processing case #{total_cases}...")
                
                # שלוף את הלינק תחילה
                try:
                    doc_element = result_div.find_element(
                        By.XPATH, ".//a[contains(@title, 'הורדת Word') and contains(@class, 'docLink')]")
                    doc_link = doc_element.get_attribute('href')
                    part = doc_link.split("/")[-1]

                except NoSuchElementException:
                    doc_element = result_div.find_element(
                        By.XPATH, ".//a[contains(@title, 'הורדת PDF') and contains(@class, 'pdfLink')]")
                    doc_link = doc_element.get_attribute('href')
                    part = doc_link.split("/")[-1]
                
                # if not doc_link or doc_link == "N/A":
                #     print(f"   ⚠️ No valid document link - skipping")
                #     skipped_cases += 1
                #     continue
                print(part)
                # print(f"   Document Link: {doc_link[:80]}...")
                
                # הלינק לא קיים - הוסף תיק חדש
                print(f"   🆕 New case - adding...")
                
                case_data = extract_case_data(result_div)
                all_verdicts.append(part)
                if case_data:
                    # הוסף את השורה החדשה
                    df = pd.concat([df, pd.DataFrame([case_data])], ignore_index=True)
                    new_cases += 1
                    print(f"   ✅ Successfully added new case")
                else:
                    print(f"   ❌ Failed to extract data")
                
                # שמור כל 10 תיקים
                if total_cases % 10 == 0:
                    print(f"\n💾 Saving progress... ({total_cases} cases processed)")
                    df.to_csv(EXISTING_CSV, index=False, encoding='utf-8-sig')
                    print(f"   ✓ Saved")
                
                # המתן קצת בין תיקים
                time.sleep(1)
            
        except Exception as e:
            print(f"   ❌ Error processing page {page_num}: {e}")
            import traceback
            traceback.print_exc()
        
        # עבור לדף הבא (אם לא זה האחרון)
        # עבור לדף הבא (אם לא זה האחרון)
        if page_num < pages:
            try:
                # ה-ID הנכון של כפתור "הבא"
                next_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "ContentPlaceHolder1_SearchResultsTemplate1_Paging2_btnNext")))
                
                # גלול אליו
                driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
                time.sleep(0.5)
                
                # לחץ
                driver.execute_script("arguments[0].click();", next_btn)
                print(f"\n➡️  Moving to page {page_num + 1}...")
                
                # המתן לטעינת הדף החדש
                time.sleep(2)
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "searchResultsMain")))
                
            except (NoSuchElementException, TimeoutException) as e:
                print(f"\n⚠️ Could not find next page button: {e}")
                break
    
    # שמור את הקובץ הסופי
    print(f"\n5. Saving final CSV: {EXISTING_CSV}")
    df.to_csv(EXISTING_CSV, index=False, encoding='utf-8-sig')
    print(f"   ✓ Saved")
    print(f"\n{'=' * 80}")
    print(f"✅ PROCESS COMPLETE!")
    print(f"   Total cases processed: {total_cases}")
    print(f"   New cases added: {new_cases}")
    print(f"   Cases updated: {updated_cases}")
    print(f"   Cases skipped: {skipped_cases}")
    print(f"   Final CSV rows: {len(df)}")
    print(f"{'=' * 80}\n")
    
    return all_verdicts


### ─────────────────────────  הרצה  ─────────────────────────

if __name__ == "__main__":
    try:
        all_verdicts = process_website_and_update_csv()
        # save the list 
        # import csv
        # with open("list.json", "w") as f:
        #     json.dump(all_verdicts, f)
        # with open("list.csv", "w", newline="", encoding="utf-8-sig") as f:
        #     writer = csv.writer(f)
        #     for item in all_verdicts:
        #         writer.writerow([item])
        #         print("\n✅ Process completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during processing: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        driver.quit()