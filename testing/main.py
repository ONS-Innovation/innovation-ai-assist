from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
import undetected_chromedriver as uc
import os
import pandas as pd
import time
import pickle
import logging
import sys
import random
from pathlib import Path
import json


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler('automation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)


with open('config.json') as f:
    config = json.load(f)
human_like_delay = config['human_like_delay']


def setup_driver():
    """Setup Chrome with undetected-chromedriver"""
    options = uc.ChromeOptions()
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    # Add common browser headers
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-extensions')
    options.add_argument('--start-maximized')
    options.add_argument('--headless=new')
    
    # Add user agent
    options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    return uc.Chrome(options=options)

def wait_and_find_element(driver, by, value, timeout=10):
    """Wait for and return an element, with retry logic"""
    for attempt in range(3):  # Try 3 times
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except Exception as e:
            if attempt == 2:  # Last attempt
                logging.error(f"Failed to find element {value}: {str(e)}")
                raise
            time.sleep(2)  # Wait before retry


def human_like_type(element, text):
    """Type text like a human with random delays between characters"""

    for char in text:
        element.send_keys(char)
        if human_like_delay:
            time.sleep(random.uniform(0.1, 0.3))

def click_with_retry(driver, element, max_attempts=3):
    """Click an element with retry logic and human-like behavior"""
    for attempt in range(max_attempts):
        try:
            # Move mouse to element
            ActionChains(driver).move_to_element(element).perform()
            
            # Scroll element into view
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(0.5)
            
            # Click the element
            element.click()
            return True
        except Exception as e:
            if attempt == max_attempts - 1:
                logging.error(f"Failed to click element after {max_attempts} attempts: {str(e)}")
                raise
            time.sleep(2)



def load_session(driver, filename='session.pkl'):
    """Load the session cookies from a file"""
    logging.info("Loading session data...")
    try:
        with open(filename, 'rb') as f:
            session_data = pickle.load(f)
        
        driver.get(session_data['url'])
        for cookie in session_data['cookies']:
            driver.add_cookie(cookie)
        logging.info("Session data loaded successfully")
        return True
    except FileNotFoundError:
        logging.error("No session file found. Please login first.")
        return False
    except Exception as e:
        logging.error(f"Error loading session: {str(e)}")
        return False

def move_row_to_tested(row_data):
    """Move a row from testData.csv to testedData.csv"""
    tested_file = Path('testedData.csv')
    
    # Create testedData.csv if it doesn't exist
    if not tested_file.exists():
        row_data.to_frame().T.to_csv(tested_file, index=False)
    else:
        row_data.to_frame().T.to_csv(tested_file, mode='a', header=False, index=False)
    
    # Read the original file
    test_data = pd.read_csv('testData.csv')
    
    # Remove the processed row
    test_data = test_data.iloc[1:]
    
    # Save back to testData.csv
    test_data.to_csv('testData.csv', index=False)

def wait_for_element(driver, by, value, timeout=10, message=None):
    """Wait for an element to be present and visible"""
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        # time.sleep(1)  # Standard 1 second wait after finding element
        return element
    except Exception as e:
        if message:
            logging.error(f"{message}: {str(e)}")
        raise

def wait_for_url(driver, url_pattern, timeout=30):
    """Wait for URL to match pattern"""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: url_pattern in d.current_url
        )
        return True
    except:
        return False

def extract_sic_data(driver):
    """Extract SIC codes and justification from results page"""
    final_sic = wait_for_element(driver, By.CSS_SELECTOR, "#final-sic ul li").text
    final_justification = wait_for_element(driver, By.CSS_SELECTOR, "#final-sic p").text
    
    # Switch to Initial SIC tab
    initial_tab = wait_for_element(driver, By.CSS_SELECTOR, "#tab_sic")
    initial_tab.click()
    # time.sleep(1)
    
    initial_sic = wait_for_element(driver, By.CSS_SELECTOR, "#sic ul li").text
    
    return {
        'final_sic': final_sic.split(' - ')[0],
        'initial_sic': initial_sic.split(' - ')[0],
        'justification': final_justification
    }

def extract_question_text(driver):
    """Extract question text from the page"""
    try:
        question = driver.find_element(By.CSS_SELECTOR, "#fieldset-legend-title").text
        return question
    except:
        return None

def extract_selected_radio_value(driver):
    """Extract the selected radio button value"""
    try:
        selected_radio = driver.find_element(By.CSS_SELECTOR, "input[type='radio']:checked")
        return selected_radio.get_attribute("value")
    except:
        return None

def handle_survey_assist(driver, current_row):
    """Handle the survey assist flow including organization type and results"""
    # Wait for survey assist page
    if not wait_for_url(driver, '/survey_assist', timeout=30):
        logging.error("Failed to reach survey assist page within 30 seconds")
        return False
        
    # Wait for first question
    try:
        # Get question 1
        question1 = wait_for_element(driver, By.CSS_SELECTOR, "#fieldset-legend-title", timeout=30).text
        logging.info(f"\nQuestion 1: {question1}")
        current_row['TEST question 1'] = question1
        
        # Get user input for text field
        response1 = input("\nEnter your response: ")
        
        # Find and fill the text input
        input_field = wait_for_element(driver, By.ID, 'resp-ai-assist-followup')
        input_field.send_keys(response1)
        logging.info(f"Entered: {response1}")
        current_row['Question response 1'] = response1
        
        # Click save and continue
        save_button = wait_for_element(driver, By.ID, 'save-values-button')
        save_button.click()
        time.sleep(1)
        
        # Get question 2
        question2 = wait_for_element(driver, By.CSS_SELECTOR, "#fieldset-legend-title", timeout=30).text
        logging.info(f"\nQuestion 2: {question2}")
        current_row['Test question 2'] = question2
        
        # Get available radio options for question 2
        radio_options = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        print("\nAvailable options:\033[92m")
        for i, option in enumerate(radio_options, 1):
            value = option.get_attribute("value")
            print(f"\033[92m{i}. {value}\033[0m")
            
        # Get user input for question 2
        while True:
            try:
                choice = int(input("\nEnter the number of your choice: "))
                if 1 <= choice <= len(radio_options):
                    break
                print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a number.")
        
        # Select the chosen radio button
        chosen_radio = radio_options[choice - 1]
        chosen_radio.click()
        response2 = chosen_radio.get_attribute("value")
        logging.info(f"Selected: {response2}")
        current_row['Question response 2'] = response2
        
        # Click save and continue
        save_button = wait_for_element(driver, By.ID, 'save-values-button')
        save_button.click()
        time.sleep(1)
        
    except Exception as e:
        logging.error(f"Failed to capture survey assist questions: {str(e)}")
        return False
        
    # Wait for organization type form
    wait_for_element(driver, By.CSS_SELECTOR, "#fieldset-legend-title", text="What kind of organisation was it?")

    # Select public limited company
    plc_radio = wait_for_element(driver, By.ID, 'limited-company')
    plc_radio.click()
    time.sleep(1)
    current_row['What type of company'] = "A public limited company"
    
    # Click save and continue
    save_button = wait_for_element(driver, By.ID, 'save-values-button')
    save_button.click()
    
    # Wait for summary page
    if not wait_for_url(driver, '/summary', timeout=30):
        logging.error("Failed to reach summary page")
        return False
        
    # Click submit
    submit_button = wait_for_element(driver, By.ID, 'submit-button')
    submit_button.click()
    
    # Wait for results page
    if not wait_for_url(driver, '/survey_assist_results', timeout=30):
        logging.error("Failed to reach results page")
        return False
        
    # Extract SIC data
    try:
        sic_data = extract_sic_data(driver)
        current_row['FIRST SIC'] = sic_data['initial_sic']
        current_row['FINAL SIC'] = sic_data['final_sic']
        current_row['AI Justification'] = sic_data['justification']
    except Exception as e:
        logging.error(f"Failed to extract SIC data: {str(e)}")
        return False
        
    # Click finish
    finish_button = wait_for_element(driver, By.ID, 'submit-button')
    finish_button.click()
    
    # Wait for start survey page
    if not wait_for_url(driver, '/', timeout=30):
        logging.error("Failed to return to start page")
        return False
        
    return True

def run_login_and_survey():
    """Handle both login and survey in one session"""
    logging.info("Starting combined login and survey process...")
    
    # Get environment variables
    email = os.getenv('EMAIL')
    password = os.getenv('PASSWORD')
    
    if not email or not password:
        logging.error("EMAIL and PASSWORD environment variables must be set")
        raise ValueError("EMAIL and PASSWORD environment variables must be set")

    # Setup Chrome driver
    driver = setup_driver()
    
    try:
        # Navigate to the login page
        logging.info("Navigating to login page...")
        driver.get('https://tlfs-poc.ai-assist.gcp.onsdigital.uk/login')
        
        # Find and fill in email field
        logging.info("Filling in email...")
        email_field = wait_and_find_element(driver, By.ID, 'email-username')
        human_like_type(email_field, email)
        
        # Find and fill in password field
        logging.info("Filling in password...")
        password_field = wait_and_find_element(driver, By.ID, 'password')
        human_like_type(password_field, password)
        
        # Click login button
        logging.info("Clicking login button...")
        login_button = wait_and_find_element(driver, By.TAG_NAME, 'button')
        click_with_retry(driver, login_button)
        
        # Check for error message
        try:
            error_message = driver.find_element(By.XPATH, "//p[contains(text(), 'Invalid credentials')]")
            if error_message.is_displayed():
                logging.error("Login failed: Invalid credentials")
                return
        except:
            logging.info("Login successful")

        # Accept additional cookies if present
        try:
            accept_cookies_button = driver.find_element(By.XPATH, "//button[@data-button='accept']")
            if accept_cookies_button.is_displayed():
                logging.info("Accepting additional cookies...")
                click_with_retry(driver, accept_cookies_button)
        except:
            logging.info("No additional cookies to accept.")
            
        # Start Survey Process
        logging.info("Starting survey process...")
        
        # Navigate to survey page
        logging.info("Navigating to survey page...")
        driver.get('https://tlfs-poc.ai-assist.gcp.onsdigital.uk/survey')
        time.sleep(1)
        
        # Read the CSV file
        logging.info("Reading data from CSV...")
        csv_path = Path('testData.csv')
        if not csv_path.exists():
            logging.error(f"CSV file not found at {csv_path}")
            return
            
        df = pd.read_csv(csv_path)
        if len(df) == 0:
            logging.error("No more data in testData.csv")
            return
            
        # Create a copy of the first row to avoid the SettingWithCopyWarning
        row_data = df.iloc[0].copy()
        
        # Paid job question
        logging.info("Answering paid job question...")
        yes_radio = wait_and_find_element(driver, By.ID, 'paid-job-yes')
        yes_radio.click()
        time.sleep(1)
        
        save_button = wait_and_find_element(driver, By.ID, 'save-values-button')
        save_button.click()
        time.sleep(1)
        
        # Job title question
        logging.info(f"Filling in job title: \033[93m{row_data['soc2020_job_title_main_job']}\033[0m")
        job_title_field = wait_and_find_element(driver, By.ID, 'job-title')
        job_title_field.send_keys(row_data['soc2020_job_title_main_job'])
        time.sleep(1)
        
        save_button = wait_and_find_element(driver, By.ID, 'save-values-button')
        save_button.click()
        time.sleep(1)
        
        # Job description question
        logging.info(f"Filling in job description: \033[93m{row_data['soc2020_job_description_main_job']}\033[0m")
        job_desc_field = wait_and_find_element(driver, By.ID, 'job-description')
        job_desc_field.send_keys(row_data['soc2020_job_description_main_job'])
        time.sleep(1)
        
        save_button = wait_and_find_element(driver, By.ID, 'save-values-button')
        save_button.click()
        time.sleep(1)
        
        # Organization activity question
        logging.info(f"Filling in organization activity: \033[93m{row_data['sic2007_employed_main_job']}\033[0m")
        org_field = wait_and_find_element(driver, By.ID, 'organisation-activity')
        org_field.send_keys(row_data['sic2007_employed_main_job'])
        time.sleep(1)
        
        save_button = wait_and_find_element(driver, By.ID, 'save-values-button')
        save_button.click()
        time.sleep(1)
        
        # Survey assist consent
        logging.info("Answering survey assist consent...")
        consent_yes = wait_and_find_element(driver, By.ID, 'consent-yes')
        consent_yes.click()
        time.sleep(1)
        
        save_button = wait_and_find_element(driver, By.ID, 'save-values-button')
        save_button.click()
        
        # Wait for survey assist page
        logging.info("Waiting for survey assist page...")
        if not wait_for_url(driver, '/survey_assist', timeout=30):
            logging.error("Failed to reach survey assist page within 30 seconds")
            return
            
        # Handle first question
        logging.info("Handling first survey assist question...")
        question1 = wait_and_find_element(driver, By.CSS_SELECTOR, "#fieldset-legend-title", timeout=30).text
        logging.info(f"\n\033[92mQuestion 1: {question1}\033[0m")
        row_data['TEST question 1'] = question1
        
        # Get user input for text field
        response1 = input("\nEnter your response: ")
        
        # Find and fill the text input
        input_field = wait_and_find_element(driver, By.ID, 'resp-ai-assist-followup')
        input_field.send_keys(response1)
        logging.info(f"Entered: {response1}")
        row_data['Question response 1'] = response1
        
        # Click save and continue
        save_button = wait_and_find_element(driver, By.ID, 'save-values-button')
        save_button.click()
        time.sleep(1)
        
        # Get question 2
        question2 = wait_for_element(driver, By.CSS_SELECTOR, "#fieldset-legend-title", timeout=30).text
        logging.info(f"\n\033[92mQuestion 2: {question2}\033[0m")
        row_data['Test question 2'] = question2
        
        # Get available radio options for question 2
        radio_options = driver.find_elements(By.CSS_SELECTOR, "input[name='resp-ai-assist-followup']")
        print("\nAvailable options:")
        for i, option in enumerate(radio_options, 1):
            value = option.get_attribute("value")
            print(f"{i}. {value}")
            
        # Get user input for question 2
        while True:
            try:
                choice = int(input("\nEnter the number of your choice: "))
                if 1 <= choice <= len(radio_options):
                    break
                print("Invalid choice. Please try again.")
            except ValueError:
                print("Please enter a number.")
        
        # Select the chosen radio button using JavaScript
        chosen_radio = radio_options[choice - 1]
        driver.execute_script("arguments[0].click();", chosen_radio)
        response2 = chosen_radio.get_attribute("value")
        logging.info(f"Selected: {response2}")
        row_data['Question response 2'] = response2
        
        # Click save and continue using JavaScript
        save_button = wait_for_element(driver, By.ID, 'save-values-button')
        driver.execute_script("arguments[0].click();", save_button)
        time.sleep(1)
        
        # Wait for organization type question
        logging.info("Waiting for organization type question...")
        wait_for_element(driver, By.CSS_SELECTOR, "input[name='organisation-type']", timeout=30)
        
        # Get all radio options for organization type
        radio_options = driver.find_elements(By.CSS_SELECTOR, "input[name='organisation-type']")
        target_value = "A public limited company"
        
        # Find and click the correct radio button using JavaScript
        for radio in radio_options:
            if radio.get_attribute("value") == target_value:
                driver.execute_script("arguments[0].click();", radio)
                time.sleep(1)
                row_data['What type of company'] = target_value
                logging.info(f"Selected organization type: {target_value}")
                break
        
        # Click save and continue using JavaScript
        save_button = wait_for_element(driver, By.ID, 'save-values-button')
        driver.execute_script("arguments[0].click();", save_button)
        time.sleep(1)
        
        # Wait for summary page
        if not wait_for_url(driver, '/summary', timeout=30):
            logging.error("Failed to reach summary page")
            return
            
        # Click submit
        submit_button = wait_and_find_element(driver, By.ID, 'submit-button')
        submit_button.click()
        
        # Wait for results page
        if not wait_for_url(driver, '/survey_assist_results', timeout=30):
            logging.error("Failed to reach results page")
            return
            
        # Extract SIC data
        logging.info("Extracting SIC codes and justification...")
        try:
            # Get final SIC data first
            final_sic = wait_and_find_element(driver, By.CSS_SELECTOR, "#final-sic ul li").text
            final_justification = wait_and_find_element(driver, By.CSS_SELECTOR, "#final-sic p").text
            
            driver.get("https://tlfs-poc.ai-assist.gcp.onsdigital.uk/survey_assist_results#sic")
            # Wait for the initial SIC content to be visible
            initial_sic = wait_and_find_element(driver, By.CSS_SELECTOR, "#sic ul li").text
            
            # Store the data
            row_data['FIRST SIC'] = initial_sic.split(' - ')[0]
            row_data['FINAL SIC'] = final_sic.split(' - ')[0]
            row_data['AI Justification'] = final_justification
            row_data['Test ran by (CA, JH, JA, AY)'] = 'SET-BOT'
            
            logging.info(f"Initial SIC: {row_data['FIRST SIC']}")
            logging.info(f"Final SIC: {row_data['FINAL SIC']}")
        except Exception as e:
            logging.error(f"Failed to extract SIC data: {str(e)}")
            return
            
        # Click finish
        finish_button = wait_and_find_element(driver, By.ID, 'submit-button')
        finish_button.click()
        
        # Wait for start survey page
        if not wait_for_url(driver, '/', timeout=30):
            logging.error("Failed to return to start page")
            return
            
        # Move the processed row to testedData.csv
        logging.info("Moving processed data to testedData.csv...")
        move_row_to_tested(row_data)
        
        # Start new survey
        # start_button = wait_and_find_element(driver, By.CSS_SELECTOR, 'a[href="/survey"]')
        # start_button.click()
        
        
    finally:
        driver.quit()

def run_survey():
    while True:
        run_login_and_survey()
        choice = input("Run program again? (Y/n): ")
        if choice == "n":
            break

def show_menu():
    """Display the main menu"""
    while True:
        print("""\n=== AI ASSIST AUTOMATION ===

Please make sure you have exported your email and password as environment variables.

You will have to manually enter 2 questions in the survey.

============================
        """)

        print("1. Login and Run Survey Together")
        print("2. Exit")
        
        choice = input("\nEnter your choice (1-2): ")
        
        if choice == '1':
            run_survey()
        elif choice == '2':
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    show_menu()
