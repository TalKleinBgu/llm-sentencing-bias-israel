import os
import csv, os, re, time, json
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
from selenium.webdriver.common.keys import Keys

### ─────────────────────────  הגדרות בסיס  ─────────────────────────
EMAIL     = os.environ["NEVO_EMAIL"]
PASSWORD  = os.environ["NEVO_PASSWORD"]
FROM_DATE = "01/01/2013"
PAUSE     = 1        # שניות לעצירה קבועה בין פעולות

# תיקיית יעד לשמירת קבצים להורדה
OUTPUT_DIR = r"C:\\Users\\user\\OneDrive\\טל\\projects\\justice-tal\\resources\\data\\source\\drugs_new"

chrome_options = Options()
chrome_options.add_argument("--start-maximized")
chrome_options.add_argument("--disable-popup-blocking")
# Optional stability flags
chrome_options.add_argument("--disable-dev-shm-usage")
# chrome_options.add_argument("--no-sandbox")  # avoid unless needed
# הגדרות הורדה עבור Chrome
chrome_prefs = {
    # Let Chrome use its default Downloads folder (avoid overriding path)
    # "download.default_directory": OUTPUT_DIR,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True,
    # Loosen download restrictions that can cause 'Failed - Download error'
    "safebrowsing.disable_download_protection": True,
    "download_restrictions": 0,
    # Allow multiple automatic downloads
    "profile.default_content_setting_values.automatic_downloads": 1,
    # Avoid in-browser PDF viewer intercepting downloads
    "plugins.always_open_pdf_externally": True,
    "download.open_pdf_in_system_reader": False,
    # Reduce popup blockers on download windows
    "profile.default_content_setting_values.popups": 0,
}
chrome_options.add_experimental_option("prefs", chrome_prefs)
try:
    # Enable browser and performance logs for troubleshooting
    chrome_options.set_capability('goog:loggingPrefs', {"browser": "ALL", "performance": "ALL"})
    chrome_options.set_capability('acceptInsecureCerts', True)
except Exception:
    pass
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                          options=chrome_options)
wait   = WebDriverWait(driver, 10)
# Ensure download directory exists
try:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
except Exception as _e:
    print(f"! Could not ensure OUTPUT_DIR exists: {OUTPUT_DIR} -> {_e}")

# ──────────────── פונקציות עזר ────────────────

def sanitize_filename(name: str | None) -> str:
    """Return a Windows-safe filename derived from name.
    Allows letters (including Hebrew), digits, space, dash, underscore; replaces others with '_'.
    """
    if not name or (isinstance(name, float) and pd.isna(name)):
        return "document"
    safe = []
    for ch in str(name):
        # Hebrew unicode range \u0590-\u05FF
        if ch.isalnum() or ch in [' ', '-', '_'] or ('\u0590' <= ch <= '\u05FF'):
            safe.append(ch)
        else:
            safe.append('_')
    cleaned = ''.join(safe).strip()
    return cleaned or "document"

def dismiss_terms_overlay(wait: WebDriverWait):
    """סגירת הודעת אישור ראשונית ('אישור' בתנאי שימוש) אם מופיעה."""
    try:
        # כפתור אישור במודאל
        btn = wait.until(EC.element_to_be_clickable((By.ID, "btUploadDocumentsConfirm")))
        btn.click()
        time.sleep(0.3)
        return
    except TimeoutException:
        pass
    except Exception:
        pass
    # נסה לסגור ב-X אם קיים
    try:
        close_a = driver.find_element(By.CSS_SELECTOR, "a.modal_ReturnMessageClose")
        close_a.click()
        time.sleep(0.3)
    except Exception:
        pass


def go_home(driver: webdriver.Chrome, wait: WebDriverWait):
    """Return to the NGCS homepage so the next case can be entered cleanly."""
    try:
        # Try clicking the header Home button if present
        home_btn = driver.find_element(By.CSS_SELECTOR, "a[id$='_Header_webbtnGoHome']")
        home_btn.click()
        time.sleep(0.5)
    except Exception:
        # Fallback: direct navigation
        driver.get("https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx")
    # try:
    #     dismiss_terms_overlay(wait)
    # except Exception:
    #     pass
    time.sleep(0.3)


### ─────────────────────────  כניסה לחשבון  ─────────────────────────
driver.get("https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx")
dismiss_terms_overlay(wait)


### ─────────────────────────  קריאת מספרי תיקים מקובץ CSV  ─────────────────────────
one_defendant = pd.read_csv("defendants/one_defendant.csv")
case_numbers = one_defendant['Case Number'].tolist()
new = r"C:\\Users\\user\\OneDrive\\טל\\projects\\justice-tal\\resources\\data\\source\\drugs_new"
pdf = []
for file in os.listdir(new):
    if file.endswith('.pdf'):
        pdf.append(file[:-4])

case_ = one_defendant['verdict'].tolist()

path_ = r"C:\\Users\\user\\OneDrive\\טל\\projects\\justice-tal\\resources\\data\\source\\drugs_docx"
output = OUTPUT_DIR
lst = []
pending_items = []  # list of tuples: (original_df_index, case_number)
for file in os.listdir(path_):
    lst.append(file[:-5])
for i,row in one_defendant.iterrows():
    verdict = row['verdict']
    case_num = row['Case Number']
    if verdict not in lst or verdict not in pdf:
        pending_items.append((i, case_num))
        # shutil.copy(os.path.join(path_, file), os.path.join(output, file))

case_numbers = [cn for _, cn in pending_items]
print(len(case_numbers), "cases to process.")
# הכנת קובץ פלט להתקדמות אינקרמנטלית
out_path = os.path.join('bias', 'defendants', 'one_defendant_with_decision_type2.csv')
if os.path.exists(out_path):
    df_out = pd.read_csv(out_path)
    # אם האורך שונה, אתחל מחדש מהקלט
    if len(df_out) != len(one_defendant):
        print("Warning: output CSV length differs from input; reinitializing from input.")
        df_out = one_defendant.copy()
else:
    df_out = one_defendant.copy()
if 'decision_type' not in df_out.columns:
    df_out['decision_type'] = pd.NA

def persist_decision_type(idx: int, value: str | None):
    """NO-OP: Persistence disabled per user request.
    Original implementation (commented out) wrote decision_type to CSV per row.
    """
    # if 0 <= idx < len(df_out):
    #     df_out.loc[idx, 'decision_type'] = value
    #     df_out.to_csv(out_path, index=False, encoding='utf-8-sig')
    #     print(f"       · Persisted decision_type at row {idx}: {value}")
    # else:
    #     print(f"       · Index {idx} out of range; not persisting")
    pass

### ─────────────────────────  חיפוש לפי מספר תיק  ─────────────────────────
def parse_case_components(case_str):
    """Parse case string into components.
    Returns (case_num, month_year, lent) where lent indicates detected format:
    - 3: 'number-mm-yy' style
    - 2: 'number-yy' style
    - 0: unknown/other format (returns safe defaults)
    """
    if not isinstance(case_str, str):
        case_str = str(case_str or "").strip()
    parts = [p.strip() for p in case_str.split("-") if p is not None and str(p).strip() != ""]
    if len(parts) == 3:
        return parts[0], f"{parts[1]}-{parts[2]}", 3
    if len(parts) == 2:
        return parts[0], parts[1], 2
    # Fallback: unknown format
    return case_str, None, 0


def normalize_date_str(val) -> str | None:
    """Normalize various date representations to dd/mm/YYYY string.
    Accepts strings like '04/06/2018', '2018-06-04', datetime-like, or pandas Timestamp.
    Returns None if cannot parse.
    """
    if val is None:
        return None
    try:
        # Already in dd/mm/YYYY?
        s = str(val).strip()
        if not s:
            return None
        # Handle numeric excel-like dates or timestamps via pandas
        dt = pd.to_datetime(s, dayfirst=True, errors='coerce')
        if pd.isna(dt):
            return None
        return dt.strftime('%d/%m/%Y')
    except Exception:
        return None


def get_expected_date_from_row(df: pd.DataFrame, idx: int) -> str | None:
    """Extract an expected decision date string (dd/mm/YYYY) from the DF row.
    Tries multiple common column names.
    """
    if idx < 0 or idx >= len(df):
        return None
    candidates = [
        'decision_date', 'DecisionDate', 'date', 'Date', 'Judgment Date', 'judgment_date', 'תאריך', 'תאריך החלטה', 'תאריך גזר דין'
    ]
    for col in candidates:
        if col in df.columns:
            val = df.loc[idx, col]
            norm = normalize_date_str(val)
            if norm:
                return norm
    # If nothing matched, try any column that contains 'תאריך'
    try:
        for col in df.columns:
            if 'תאריך' in str(col):
                val = df.loc[idx, col]
                norm = normalize_date_str(val)
                if norm:
                    return norm
    except Exception:
        pass
    return None


def search_header_case(driver, wait, month_year: str, case_num: str):
    """Fill the header case locator inputs and submit search."""
    # Ensure we're on the homepage with the header form available
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[id$='_BamaMonthYearTextBoxHT']")))
    except TimeoutException:
        driver.get("https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[id$='_BamaMonthYearTextBoxHT']")))
    # ודא שאין מודאל פתוח שיחסום
    # dismiss_terms_overlay(wait)

    # Ensure the "new case" radio is selected
    try:
        new_case_radio = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_BamaCaseIdentifierOptionBoxHT']")))
        if not new_case_radio.is_selected():
            new_case_radio.click()
            time.sleep(0.2)
    except Exception:
        pass

    ym_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_BamaMonthYearTextBoxHT']")))
    num_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_BamaCaseNumberTextBoxHT']")))
    ym_box.clear(); ym_box.send_keys(month_year)
    num_box.clear(); num_box.send_keys(case_num)

    # Submit by clicking the button (suffix-agnostic)
    try:
        btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_SearchHeaderCaseButton']")))
        btn.click()
    except Exception:
        # Fallback to JS postback with the known pattern; may still work on some pages
        try:
            driver.execute_script("__doPostBack('Header1:CaseLocatorHeaderUC2:SearchHeaderCaseButton','')")
        except Exception:
            pass
    time.sleep(PAUSE + 1)


def select_option_by_text(wait, select_id: str, text: str) -> bool:
    """Try to select a dropdown option by exact text, fallback to contains."""
    sel = wait.until(EC.element_to_be_clickable((By.ID, select_id)))
    try:
        Select(sel).select_by_visible_text(text)
        return True
    except Exception:
        # Fallback: look for partial match
        options = sel.find_elements(By.TAG_NAME, "option")
        for opt in options:
            if text and text.strip() and text.strip() in (opt.text or "").strip():
                opt.click()
                return True
    return False


def search_old_case(driver, wait, yy: str, case_num: str, court_text: str, case_type_text: str = "פ - תיק פלילי"):
    """Use the 'old case identifier' flow: select radio, pick court & type, fill year and number, submit."""
    # Ensure we're on the homepage and radio exists
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[id$='_OldCaseIdentifierOptionBoxHT']")))
    except TimeoutException:
        driver.get("https://www.court.gov.il/NGCS.Web.Site/HomePage.aspx")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[id$='_OldCaseIdentifierOptionBoxHT']")))
    # ודא שאין מודאל פתוח שיחסום
    # dismiss_terms_overlay(wait)

    # Click radio for old case identifier
    wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_OldCaseIdentifierOptionBoxHT']"))).click()
    time.sleep(0.2)

    # Select previous court (Court + Location)
    if court_text:
        try:
            sel = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "select[id$='_PreviousCourtComboBoxHT']")))
            try:
                Select(sel).select_by_visible_text(court_text)
                ok_court = True
            except Exception:
                ok_court = False
                options = sel.find_elements(By.TAG_NAME, "option")
                for opt in options:
                    if court_text and court_text.strip() and court_text.strip() in (opt.text or "").strip():
                        opt.click()
                        ok_court = True
                        break
            if not ok_court:
                print(f"     ! Court option not found for: {court_text}")
        except Exception:
            print(f"     ! Court select not found")

    # Select previous case type (e.g., פלילי)
    try:
        sel_type = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "select[id$='_PreviousCaseTypeComboBoxHT']")))
        try:
            Select(sel_type).select_by_visible_text(case_type_text)
            ok_type = True
        except Exception:
            ok_type = False
            options = sel_type.find_elements(By.TAG_NAME, "option")
            for opt in options:
                if case_type_text and case_type_text.strip() and case_type_text.strip() in (opt.text or "").strip():
                    opt.click()
                    ok_type = True
                    break
        if not ok_type:
            print(f"     ! Case type option not found: {case_type_text}")
    except Exception:
        print("     ! Case type select not found")

    # Fill year and case number inputs
    year_box = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_OldYearTextBoxHT']")))
    num_box  = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_OldCaseNumberTextBoxHT']")))
    year_box.clear(); year_box.send_keys(yy)
    num_box.clear();  num_box.send_keys(case_num)

    # Submit the form
    try:
        btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[id$='_SearchHeaderCaseButton']")))
        btn.click()
    except Exception:
        try:
            driver.execute_script("__doPostBack('Header1:CaseLocatorHeaderUC2:SearchHeaderCaseButton','')")
        except Exception:
            pass
    time.sleep(PAUSE + 1)


def open_psak_din_and_details(driver, wait, expected_date: str | None = None):
    """Open decision details by matching date.
    Tries folder 21 (פסקי דין) first; if not found, tries folder 18 (החלטות בתיק).
    Returns True if a matching decision was opened; otherwise False.
    """
    def try_folder(folder_id: str, exp_date: str) -> bool:
        # Navigate to folder
        try:
            link = wait.until(EC.element_to_be_clickable((
                By.XPATH, f"//a[contains(@class,'FolderLink')][contains(@href, 'NavigateToFolder','{folder_id}')]|//a[contains(@href, '\\'{folder_id}\\') and contains(@href,'NavigateToFolder')]"
            )))
            link.click()
            time.sleep(0.6)
        except Exception:
            try:
                driver.execute_script(f"__doPostBack('_ctl0$ElectronicCaseFolderTreeView1$NavigateToFolder','{folder_id}')")
                time.sleep(0.8)
            except Exception as e:
                print(f"     - Could not navigate to folder {folder_id}: {e}")
                return False

        # Read grid store if available
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "DecisionListGrid")))
        except Exception:
            pass
        items = []
        try:
            store_el = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.ID, "DecisionListGridArrayStore"))
            )
            raw = store_el.get_attribute("value") or "[]"
            items = json.loads(raw)
        except Exception:
            items = []

        exp = normalize_date_str(exp_date)
        # Try JSON store
        if items and exp:
            for it in items:
                for key in ("DecisionSignatureDate", "DecisionDate", "DecisionDisplayDate", "DecisionSignatureDateDisplay"):
                    if normalize_date_str(it.get(key)) == exp:
                        decision_id = it.get("DecisionID") or it.get("DecisionId") or it.get("DocumentID")
                        if decision_id:
                            try:
                                driver.execute_script(f"__doPostBack('_ctl0:btnDetails','{decision_id}')")
                                time.sleep(1.0)
                                return True
                            except Exception:
                                pass
                        break

        # Fallback: find row by date text and click details
        if exp:
            try:
                row = wait.until(EC.element_to_be_clickable((
                    By.XPATH, f"//div[@id='DecisionListGrid']//tr[.//*[contains(text(), '{exp}')]]"
                )))
                details = row.find_element(By.XPATH, ".//a[contains(@href, '_ctl0:btnDetails')]")
                details.click()
                time.sleep(1.0)
                return True
            except Exception:
                return False
        return False

    if not expected_date:
        print("     - No expected date provided; not opening any decision.")
        return False
    # Try פסקי דין (21), then החלטות בתיק (18)
    if try_folder('21', expected_date):
        return True
    print("     - No matching decision in פסקי דין; trying החלטות בתיק...")
    return try_folder('18', expected_date)


def extract_decision_type(driver, wait, timeout: int = 10) -> str | None:
    """Extract the decision type ('סוג ההחלטה') from the decision details view.
    Tries to find an input whose id ends with '_tbDecisionType' and returns its value.
    Fallback to span/text content if needed. Returns None if not found.
    """
    try:
        # המתן לעמוד פירוט להיטען
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[id$='_tbDecisionType'], span[id$='_tbDecisionType']"))
        )
        # אם זה input – קח value, אחרת טקסט
        tag = el.tag_name.lower()
        if tag == "input":
            val = el.get_attribute("value")
            return (val or "").strip() or None
        else:
            txt = el.text
            return (txt or "").strip() or None
    except TimeoutException:
        # נסה שיטה מבוססת תווית: מצא td עם הטקסט 'סוג ההחלטה:' וקח השכן
        try:
            label_td = driver.find_element(By.XPATH, "//td[normalize-space(text())='סוג ההחלטה:']")
            # האיבר הבא אחרי שני td הוא ה-input/טקסט עם הערך
            val_el = label_td.find_element(By.XPATH, "following-sibling::td[2]/*[1]")
            if val_el.tag_name.lower() == "input":
                val = val_el.get_attribute("value")
            else:
                val = val_el.text
            return (val or "").strip() or None
        except Exception:
            return None
    except Exception:
        return None


def _latest_downloaded_file(directory: str, since_ts: float) -> str | None:
    """Return the most recent fully-downloaded file (not .crdownload) in directory after since_ts."""
    try:
        candidates = []
        for name in os.listdir(directory):
            if name.endswith('.crdownload'):
                continue
            full = os.path.join(directory, name)
            try:
                mtime = os.path.getmtime(full)
                if mtime >= since_ts:
                    candidates.append((mtime, full))
            except Exception:
                continue
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][1]
    except Exception:
        return None


def _print_recent_browser_logs(driver, prefix: str = ""):
    try:
        logs = driver.get_log('browser')
        if logs:
            print(prefix + "Browser logs (last 10):")
            for entry in logs[-10:]:
                lvl = entry.get('level')
                msg = entry.get('message')
                print(prefix + f"[{lvl}] {msg}")
    except Exception:
        pass


def download_first_document(driver, wait, verdict_name: str, out_dir: str, timeout: int = 10) -> str | None:
    """Click the document icon (מסמך) to open new window, click Save, and store file as verdict_name.* in out_dir.
    Returns saved file path or None.
    """
    # Look for a document link in the current page (details/grid)
    try:
        orig_handle = driver.current_window_handle
        doc_link = wait.until(EC.element_to_be_clickable((
            By.XPATH, "//a[contains(@href, '_ctl0:btnDocument')]"
        )))
        before_windows = set(driver.window_handles)
        doc_link.click()
        # Wait for new window
        WebDriverWait(driver, 10).until(lambda d: len(set(d.window_handles) - before_windows) == 1)
        new_win = (set(driver.window_handles) - before_windows).pop()
        driver.switch_to.window(new_win)
    except Exception as e:
        print(f"     - Could not open document window: {e}")
        return None

    # Click save button in the new window (with retries)
    started = time.time()
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        pass
    before_set = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()
    try:
        btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "btnSave")))
        # Single composite attempt: scroll, click, JS click fallback, Enter fallback
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        except Exception:
            pass
        try:
            btn.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", btn)
            except Exception:
                try:
                    btn.send_keys(Keys.RETURN)
                except Exception:
                    raise
    except Exception as e:
        print(f"     - Could not click Save in document window: {e}")
        # Print browser logs to help diagnose issues like 'Failed - Download error'
        _print_recent_browser_logs(driver, prefix="     - ")
        try:
            driver.close()
        except Exception:
            pass
        # switch back to original
        try:
            if orig_handle in driver.window_handles:
                driver.switch_to.window(orig_handle)
            else:
                # Fallback to last tab
                remaining = driver.window_handles
                if remaining:
                    driver.switch_to.window(remaining[-1])
        except Exception:
            pass
        return None

    # Wait for download to complete and rename
    end_time = time.time() + timeout
    saved = None
    # Optional fallbacks: user's default Downloads dirs (including OneDrive)
    default_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    onedrive_root = os.environ.get('OneDrive') or os.environ.get('ONEDRIVE')
    onedrive_downloads = os.path.join(onedrive_root, "Downloads") if onedrive_root else None
    candidate_download_dirs = [p for p in [default_downloads, onedrive_downloads] if p and os.path.isdir(p)]
    while time.time() < end_time:
        # Ensure any active .crdownload finished
        has_partial = any(f.endswith('.crdownload') for f in os.listdir(out_dir)) if os.path.isdir(out_dir) else False
        latest = _latest_downloaded_file(out_dir, since_ts=started)
        if latest and not has_partial:
            saved = latest
            break
        # Fallback: detect any new file by directory diff
        if os.path.isdir(out_dir):
            after_set = set(os.listdir(out_dir))
            new_files = [f for f in (after_set - before_set) if not f.endswith('.crdownload')]
            if new_files:
                # choose the most recent
                try:
                    new_full = max((os.path.join(out_dir, f) for f in new_files), key=lambda p: os.path.getmtime(p))
                    saved = new_full
                    break
                except Exception:
                    pass
        # Try detected Downloads folders if nothing in out_dir
        try:
            for dl_dir in candidate_download_dirs:
                cand = _latest_downloaded_file(dl_dir, since_ts=started)
                if cand and not cand.endswith('.crdownload'):
                    try:
                        os.makedirs(out_dir, exist_ok=True)
                        ext = os.path.splitext(cand)[1]
                        target = os.path.join(out_dir, f"{sanitize_filename(verdict_name)}{ext}")
                        if os.path.exists(target):
                            base = os.path.join(out_dir, sanitize_filename(verdict_name))
                            k = 1
                            while os.path.exists(f"{base}_{k}{ext}"):
                                k += 1
                            target = f"{base}_{k}{ext}"
                        os.replace(cand, target)
                        print(f"       · Moved from Downloads ('{dl_dir}') to: {target}")
                        # Close doc tab and switch back before returning
                        try:
                            driver.close()
                        except Exception:
                            pass
                        try:
                            if 'orig_handle' in locals() and orig_handle in driver.window_handles:
                                driver.switch_to.window(orig_handle)
                            else:
                                remaining = driver.window_handles
                                if remaining:
                                    driver.switch_to.window(remaining[-1])
                        except Exception:
                            pass
                        return target
                    except Exception:
                        pass
        except Exception:
            pass
        time.sleep(0.5)

    # Close the document window and return to main
    try:
        driver.close()
    except Exception:
        pass
    try:
        # switch back to the first available window (original)
        remaining = driver.window_handles
        if remaining:
            driver.switch_to.window(remaining[0])
    except Exception:
        pass

    if not saved:
        print("     - Download did not complete in time.")
        # Print browser logs for additional diagnostics
        _print_recent_browser_logs(driver, prefix="     - ")
        return None

    # Rename to verdict_name with same extension
    try:
        ext = os.path.splitext(saved)[1] or ''
        target = os.path.join(out_dir, f"{sanitize_filename(verdict_name)}{ext}")
        # If target exists, add a suffix to avoid overwrite
        if os.path.exists(target):
            base = os.path.join(out_dir, sanitize_filename(verdict_name))
            k = 1
            while os.path.exists(f"{base}_{k}{ext}"):
                k += 1
            target = f"{base}_{k}{ext}"
        os.rename(saved, target)
        print(f"       · Saved document to: {target}")
        return target
    except Exception as e:
        print(f"     - Could not rename downloaded file: {e}")
        return saved


def download_document_by_date(driver, wait, expected_date: str | None, verdict_name: str, out_dir: str, timeout: int = 10) -> str | None:
    """Download a document from the case grid by matching the decision date, without opening details.
    Tries folder 21 (פסקי דין) first; if not found, tries folder 18 (החלטות בתיק).
    Returns saved file path or None.
    """
    if not expected_date:
        print("     - No expected date provided; skipping download.")
        return None
    exp = normalize_date_str(expected_date)
    if not exp:
        print("     - Expected date not in valid format; skipping download.")
        return None

    def navigate_to_folder(folder_id: str) -> bool:
        try:
            link = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((
                By.XPATH, f"//a[contains(@class,'FolderLink')][contains(@href,'NavigateToFolder') and contains(@href,'{folder_id}')]"
            )))
            link.click()
            time.sleep(0.6)
            return True
        except Exception:
            try:
                driver.execute_script(f"__doPostBack('_ctl0$ElectronicCaseFolderTreeView1$NavigateToFolder','{folder_id}')")
                time.sleep(0.8)
                return True
            except Exception as e:
                print(f"     - Could not navigate to folder {folder_id}: {e}")
                return False

    def read_grid_items() -> list:
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "DecisionListGrid")))
        except Exception:
            pass
        try:
            store_el = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.ID, "DecisionListGridArrayStore"))
            )
            raw = store_el.get_attribute("value") or "[]"
            return json.loads(raw)
        except Exception:
            return []

    def save_from_document_window(before_windows: set[str], orig_handle: str | None = None) -> str | None:
        try:
            WebDriverWait(driver, 10).until(lambda d: len(set(d.window_handles) - before_windows) == 1)
            new_win = (set(driver.window_handles) - before_windows).pop()
            driver.switch_to.window(new_win)
        except Exception as e:
            print(f"     - Document window did not open: {e}")
            return None

        # Click save (with retries)
        started = time.time()
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception:
            pass
        before_set = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()
        try:
            btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "btnSave")))
            # Single composite attempt: scroll, click, JS click fallback, Enter fallback
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            except Exception:
                pass
            try:
                btn.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", btn)
                except Exception:
                    try:
                        btn.send_keys(Keys.RETURN)
                    except Exception:
                        raise
        except Exception as e:
            print(f"     - Could not click Save in document window: {e}")
            _print_recent_browser_logs(driver, prefix="     - ")
            try:
                driver.close()
            except Exception:
                pass
            try:
                # Prefer original handle; otherwise switch to the last remaining tab
                if orig_handle and orig_handle in driver.window_handles:
                    driver.switch_to.window(orig_handle)
                else:
                    remaining = driver.window_handles
                    if remaining:
                        driver.switch_to.window(remaining[-1])
            except Exception:
                pass
            return None

        # Wait for download and rename
        end_time = time.time() + timeout
        saved = None
        time.sleep(10)

        # Optional fallbacks: user's default Downloads dirs (including OneDrive)
        default_downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        onedrive_root = os.environ.get('OneDrive') or os.environ.get('ONEDRIVE')
        onedrive_downloads = os.path.join(onedrive_root, "Downloads") if onedrive_root else None
        candidate_download_dirs = [p for p in [default_downloads, onedrive_downloads] if p and os.path.isdir(p)]
        # while time.time() < end_time:
        #     has_partial = any(f.endswith('.crdownload') for f in os.listdir(out_dir)) if os.path.isdir(out_dir) else False
        #     latest = _latest_downloaded_file(out_dir, since_ts=started)
        #     if latest and not has_partial:
        #         saved = latest
        #         break
        #     # Fallback: directory diff
        #     if os.path.isdir(out_dir):
        #         after_set = set(os.listdir(out_dir))
        #         new_files = [f for f in (after_set - before_set) if not f.endswith('.crdownload')]
        #         if new_files:
        #             try:
        #                 new_full = max((os.path.join(out_dir, f) for f in new_files), key=lambda p: os.path.getmtime(p))
        #                 saved = new_full
        #                 break
        #             except Exception:
        #                 pass
        # Try detected Downloads folders
        try:
            for dl_dir in candidate_download_dirs:
                cand = _latest_downloaded_file(dl_dir, since_ts=started)
                if cand and not cand.endswith('.crdownload'):
                    try:
                        os.makedirs(out_dir, exist_ok=True)
                        ext = os.path.splitext(cand)[1]
                        target = os.path.join(out_dir, f"{sanitize_filename(verdict_name)}{ext}")
                        if os.path.exists(target):
                            base = os.path.join(out_dir, sanitize_filename(verdict_name))
                            k = 1
                            while os.path.exists(f"{base}_{k}{ext}"):
                                k += 1
                            target = f"{base}_{k}{ext}"
                        os.replace(cand, target)
                        print(f"       · Moved from Downloads ('{dl_dir}') to: {target}")
                        # Close doc tab and switch back before returning
                        try:
                            driver.close()
                        except Exception:
                            pass
                        try:
                            if orig_handle and orig_handle in driver.window_handles:
                                driver.switch_to.window(orig_handle)
                            else:
                                remaining = driver.window_handles
                                if remaining:
                                    driver.switch_to.window(remaining[-1])
                        except Exception:
                            pass
                        return target
                    except Exception as e:
                        print(e)
                        pass
        except Exception:
            pass
        time.sleep(0.5)

        # Close window and go back
        try:
            driver.close()
        except Exception:
            pass
        try:
            # Prefer original handle; otherwise switch to the last remaining tab
            if orig_handle and orig_handle in driver.window_handles:
                driver.switch_to.window(orig_handle)
            else:
                remaining = driver.window_handles
                if remaining:
                    driver.switch_to.window(remaining[-1])
        except Exception:
            pass

        if not saved:
            print("     - Download did not complete in time.")
            _print_recent_browser_logs(driver, prefix="     - ")
            return None

        try:
            ext = os.path.splitext(saved)[1] or ''
            target = os.path.join(out_dir, f"{sanitize_filename(verdict_name)}{ext}")
            if os.path.exists(target):
                base = os.path.join(out_dir, sanitize_filename(verdict_name))
                k = 1
                while os.path.exists(f"{base}_{k}{ext}"):
                    k += 1
                target = f"{base}_{k}{ext}"
            os.rename(saved, target)
            print(f"       · Saved document to: {target}")
            return target
        except Exception as e:
            print(f"     - Could not rename downloaded file: {e}")
            return saved

    def try_folder(folder_id: str) -> str | None:
        if not navigate_to_folder(folder_id):
            return None
        items = read_grid_items()
        exp_local = exp
        if items:
            for it in items:
                for key in ("DecisionSignatureDate", "DecisionDate", "DecisionDisplayDate", "DecisionSignatureDateDisplay"):
                    if normalize_date_str(it.get(key)) == exp_local:
                        # Prefer DocumentID (as used by the document button), accept common variants
                        decision_id = (
                            it.get("DocumentID") or it.get("documentid") or it.get("DocID") or
                            it.get("DecisionID") or it.get("DecisionId")
                        )
                        if decision_id:
                            # Single attempt only: one __doPostBack call with '&1'
                            try:
                                before = set(driver.window_handles)
                                orig_handle_local = driver.current_window_handle
                                driver.execute_script(f"__doPostBack('_ctl0:btnDocument','{decision_id}&1')")
                                return save_from_document_window(before, orig_handle_local)
                            except Exception as e:
                                print(f"     - Could not trigger document open (single attempt): {e}")
                                return None
                        # If no decision_id found, stop after first matched item (single attempt policy)
                        return None
        # No items or no match -> do not try any DOM fallback; single-attempt policy enforced
        return None

    # Try folder 21 (פסקי דין); if not found, try folder 18 (החלטות בתיק)
    path = try_folder('21')
    if path:
        return path
    print("     - No matching decision in פסקי דין; trying החלטות בתיק...")
    path = try_folder('18')
    if path:
        return path
    print("     - No matching decision in החלטות בתיק.")
    return None

for pos, (i, case_number) in enumerate(pending_items):
    verdict = one_defendant.loc[i, 'verdict'] if 'verdict' in one_defendant.columns and i in one_defendant.index else None
    # Skip rows that already have decision_type in the output CSV
    # try:
    #     if 'decision_type' in df_out.columns:
    #         cur = df_out.loc[i, 'decision_type'] if i < len(df_out) else None
    #         if pd.notna(cur) and str(cur).strip() not in ('', 'nan', 'None'):
    #             print(f"     - Row {i} already filled (decision_type), skipping.")
    #             continue
    # except Exception:
    #     pass
    # If Court is district (מחוזי) – skip and persist None
    try:
        if 'Court' in one_defendant.columns:
            court_val_simple = str(one_defendant.loc[i, 'Court']) if pd.notna(one_defendant.loc[i, 'Court']) else ''
            if 'מחוזי' in court_val_simple:
                print("     - Skipping district court (מחוזי); persisting None.")
                persist_decision_type(i, None)
                continue
    except Exception:
        pass
    print(f"\n========== Searching case {pos+1}/{len(pending_items)}: {case_number} (row {i}) ==========")
    case_num, month_year, lent = parse_case_components(case_number)
    expected_date = get_expected_date_from_row(one_defendant, i)
    if expected_date:
        print(f"     - Expected decision date from DF: {expected_date}")
    if lent == 3:
        try:
            search_header_case(driver, wait, month_year, case_num)
            print(f"     - Submitted {month_year} / {case_num}. URL: {driver.current_url}")
            time.sleep(PAUSE + 1)
            # Download directly by date without opening details
            try:
                downloaded = download_document_by_date(driver, wait, expected_date=expected_date, verdict_name=verdict or case_number, out_dir=output)
                if not downloaded:
                    print("       · No document downloaded (no matching date or error).")
            except Exception as e:
                print(f"       · Download failed: {e}")
        except Exception as e:
            print(f"     - ❌ Failed: {e}")
            continue
        finally:
            # Return to homepage so we can enter the next case cleanly
            try:
                go_home(driver, wait)
            except Exception:
                pass
    elif lent == 2:
        # Expect format: xx-yy (no month). Use old-case flow with Court + Location and type פלילי
        yy = month_year  # here month_year holds 'yy'
        # Normalize to 2-digit year if needed
        yy_digits = re.sub(r"\D", "", str(yy))[-2:] if str(yy) else ""
        # Case number: digits only, up to 6
        case_digits = re.sub(r"\D", "", str(case_num))
        if not case_digits:
            print("     - ❌ No digits in case number; skipping")
            continue
        case_digits = case_digits[-6:]

        # Build court text from row: 'Court Location', e.g., 'שלום חיפה'
        court_val = ''
        if 'Court' in one_defendant.columns and 'Location' in one_defendant.columns:
            c = one_defendant.loc[i, 'Court'] if pd.notna(one_defendant.loc[i, 'Court']) else ''
            l = one_defendant.loc[i, 'Location'] if pd.notna(one_defendant.loc[i, 'Location']) else ''
            if l =="ק' גת":
                l="קריית גת"
            if l =="ק' שמונה":
                l="קריית שמונה"
                
            court_val = (str(c) + ' ' + str(l)).strip()
        try:
            search_old_case(driver, wait, yy=yy_digits, case_num=case_digits, court_text=court_val, case_type_text='פ - תיק פלילי')
            print(f"     - Old-case submitted yy={yy_digits}, num={case_digits}, court='{court_val}'. URL: {driver.current_url}")
            time.sleep(PAUSE + 1)
            # Download directly by date without opening details
            try:
                downloaded = download_document_by_date(driver, wait, expected_date=expected_date, verdict_name=verdict or case_number, out_dir=output)
                if not downloaded:
                    print("       · No document downloaded (no matching date or error).")
            except Exception as e:
                print(f"       · Download failed: {e}")

        except Exception as e:
            print(f"     - ❌ Old-case failed: {e}")
            continue
        finally:
            # Return to homepage so we can enter the next case cleanly
            try:
                go_home(driver, wait)
            except Exception:
                pass

print("\n✅ Finished. Downloads saved to:", OUTPUT_DIR)
driver.quit()