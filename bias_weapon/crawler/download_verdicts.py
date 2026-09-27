import os, time, random
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

### ─────────────────────────  הגדרות בסיס  ─────────────────────────
EMAIL         = os.environ["NEVO_EMAIL"]
PASSWORD      = os.environ["NEVO_PASSWORD"]
MISSING_CSV   = r"C:\Users\user\OneDrive\טל\projects\justice-tal\bias_weapon\data\missing_files.csv"
DOWNLOAD_DIR  = r"C:\Users\user\OneDrive\טל\projects\justice-tal\bias_weapon\all_verdicts"

# הפסקה בין הורדות: 12–25 שניות אקראיות
MIN_INTERVAL  = 12
MAX_INTERVAL  = 25

# כל כמה קבצים לקחת הפסקה ארוכה (כמו בן-אדם שמסתכל על הממצאים)
LONG_BREAK_EVERY  = random.randint(8, 14)   # כל 8–14 קבצים
LONG_BREAK_MIN    = 45   # שניות
LONG_BREAK_MAX    = 90

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

### ─────────────────────────  הגדרת Chrome  ─────────────────────────
chrome_options = Options()
chrome_options.add_argument("--start-maximized")

# הסרת סימני automation שמזהים בוטים
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option("useAutomationExtension", False)
chrome_options.add_argument("--disable-blink-features=AutomationControlled")

chrome_options.add_experimental_option("prefs", {
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "plugins.always_open_pdf_externally": True,
    "safebrowsing.enabled": True,
})

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=chrome_options,
)

# הסתר navigator.webdriver (סימן בוט)
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
    "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
})

wait = WebDriverWait(driver, 15)

### ─────────────────────────  פונקציות עזר אנושיות  ─────────────────────────
def human_sleep(min_s, max_s):
    """המתנה אקראית בין min ל-max שניות"""
    t = random.uniform(min_s, max_s)
    time.sleep(t)

def random_scroll():
    """גלילה קטנה אקראית כמו בן-אדם שסוקר עמוד"""
    scroll_amount = random.randint(100, 400)
    driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
    human_sleep(0.5, 1.5)
    driver.execute_script(f"window.scrollBy(0, -{scroll_amount // 2});")

def human_type(element, text):
    """הקלדה אנושית - כל תו עם עיכוב קטן"""
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.18))

### ─────────────────────────  זיהוי ופתרון CAPTCHA  ─────────────────────────
def wait_for_captcha_if_present():
    original_window = driver.current_window_handle
    original_handles = set(driver.window_handles)

    time.sleep(2)

    # מקרה 1: נפתח חלון חדש (popup captcha)
    current_handles = set(driver.window_handles)
    new_windows = current_handles - original_handles
    if new_windows:
        popup = new_windows.pop()
        driver.switch_to.window(popup)
        print("         ⚠️  CAPTCHA window detected! Please solve it manually...")
        while popup in driver.window_handles:
            time.sleep(2)
        print("         ✅ CAPTCHA window closed – resuming")
        driver.switch_to.window(original_window)
        return

    # מקרה 2: CAPTCHA בדף הנוכחי
    try:
        page_src = driver.page_source.lower()
        if "captcha" in page_src or "recaptcha" in page_src or "robot" in page_src:
            print("         ⚠️  CAPTCHA detected on page! Please solve it manually...")
            while True:
                time.sleep(2)
                try:
                    current_src = driver.page_source.lower()
                    if "captcha" not in current_src and "recaptcha" not in current_src:
                        break
                except Exception:
                    break
            print("         ✅ CAPTCHA solved – resuming")
    except Exception:
        pass

### ─────────────────────────  כניסה לחשבון  ─────────────────────────
print("Logging in to nevo.co.il...")
driver.get("https://www.nevo.co.il/PsikaSearch.aspx")
human_sleep(2, 4)

wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "לחץ/י כאן"))).click()
human_sleep(1, 2)

username_field = wait.until(EC.element_to_be_clickable(
    (By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_UserName")))
human_type(username_field, EMAIL)
human_sleep(0.5, 1.2)

password_field = wait.until(EC.element_to_be_clickable(
    (By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_Password")))
human_type(password_field, PASSWORD)
human_sleep(0.8, 2.0)

wait.until(EC.element_to_be_clickable(
    (By.ID, "ContentPlaceHolder1_NevoLoginCard_Login1_LoginButton"))).click()

human_sleep(3, 5)
print("✓ Logged in successfully")

### ─────────────────────────  טעינת ה-CSV  ─────────────────────────
df = pd.read_csv(MISSING_CSV, encoding='utf-8-sig')
links = df["Document Link"].dropna().tolist()
total = len(links)
print(f"✓ Loaded {total} links from CSV")
print(f"✓ Long break every ~{LONG_BREAK_EVERY} files\n")

### ─────────────────────────  לולאת הורדה  ─────────────────────────
downloaded_count = 0

for i, link in enumerate(links, 1):
    filename = link.split("/")[-1]
    dest_path = os.path.join(DOWNLOAD_DIR, filename)

    # דלג אם כבר קיים
    if os.path.exists(dest_path):
        print(f"[{i}/{total}] ⏭️  Already exists – skipping: {filename}")
        continue

    print(f"[{i}/{total}] ⬇️  Downloading: {filename}")
    try:
        driver.get(link)

        # בדוק CAPTCHA
        wait_for_captcha_if_present()

        # גלילה קצרה אקראית (לא תמיד, רק 40% מהפעמים)
        if random.random() < 0.4:
            random_scroll()

        # המתנה אקראית בין הורדות (12–25 שניות)
        interval = random.uniform(MIN_INTERVAL, MAX_INTERVAL)
        print(f"         ✅ Done – waiting {interval:.1f}s")
        time.sleep(interval)

        downloaded_count += 1

        # הפסקה ארוכה כל כמה קבצים
        if downloaded_count % LONG_BREAK_EVERY == 0:
            long_break = random.uniform(LONG_BREAK_MIN, LONG_BREAK_MAX)
            print(f"\n☕ Taking a long break ({long_break:.0f}s) after {downloaded_count} downloads...\n")
            time.sleep(long_break)
            # קבע מחדש מתי תהיה הפסקה ארוכה הבאה
            LONG_BREAK_EVERY = random.randint(8, 14)

    except Exception as e:
        print(f"         ❌ Error: {e}")
        human_sleep(MIN_INTERVAL, MAX_INTERVAL)

print("\n✅ All downloads finished!")
driver.quit()
