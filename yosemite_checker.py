#!/usr/bin/env python3
"""
Yosemite Valley Lodge Availability Checker

This script checks for weekend availability at Yosemite Valley Lodge and sends
email notifications when rooms become available. It supports two methods:
1. Selenium for full browser automation
2. Requests/BeautifulSoup for lightweight checking

The script can be configured to run periodically with randomized intervals.
"""

import argparse
import datetime
import json
import logging
import os
import random
import re
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Set, Tuple, Union

# Third-party imports - install via pip
try:
    import requests
    from bs4 import BeautifulSoup
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
except ImportError as e:
    print(f"Error: Missing required package - {e}")
    print("Please install required packages using: pip install selenium webdriver-manager requests beautifulsoup4")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("yosemite_checker.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = {
    "method": "selenium",  # or "requests"
    "browser": "chrome",   # or "firefox"
    "headless": True,
    "check_interval_hours": 3,
    "interval_variation_percent": 20,
    "months_ahead": 6,
    "weekends_only": True,
    "check_friday_saturday": True,
    "check_saturday_sunday": True,
    "email": {
        "enabled": True,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "username": "",
        "password": "",
        "from_address": "",
        "to_address": "",
        "consecutive_subject": "Consecutive Weekend Available at Yosemite Valley Lodge!",
        "single_day_subject": "Weekend Day Available at Yosemite Valley Lodge"
    },
    "urls": {
        "base_url": "https://reservations.ahlsmsworld.com/Yosemite/Plan-Your-Trip/Accommodations/Yosemite-Valley-Lodge/",
        "widget_config_url": "https://reservations.ahlsmsworld.com/Yosemite/Search/GetWidgetConfigData"
    },
    "max_retries": 3,
    "retry_delay_seconds": 60,
    "adults": 1,
    "children": 0
}

def load_config(config_path: str = "config.json") -> Dict:
    """Load configuration from JSON file or use defaults."""
    config = DEFAULT_CONFIG.copy()
    
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                user_config = json.load(f)
            
            # Merge user config with defaults (shallow merge for nested dicts)
            for key, value in user_config.items():
                if isinstance(value, dict) and key in config and isinstance(config[key], dict):
                    config[key].update(value)
                else:
                    config[key] = value
                    
            logger.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            logger.info("Using default configuration")
    else:
        logger.info(f"Config file {config_path} not found. Using default configuration")
        # Save default config for user to edit
        try:
            with open(config_path, "w") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            logger.info(f"Created default configuration file at {config_path}")
        except Exception as e:
            logger.error(f"Error creating default config file: {e}")
    
    return config

def get_weekend_dates(months_ahead: int) -> List[datetime.date]:
    """Generate a list of weekend dates (Fri-Sun) for the specified period."""
    today = datetime.date.today()
    end_date = today + datetime.timedelta(days=30 * months_ahead)
    
    weekend_dates = []
    current = today
    
    while current <= end_date:
        # 4 = Friday, 5 = Saturday, 6 = Sunday
        if current.weekday() in [4, 5, 6]:
            weekend_dates.append(current)
        current += datetime.timedelta(days=1)
    
    return weekend_dates

def format_date_for_url(date: datetime.date) -> str:
    """Format date for URL parameters (e.g., Apr+07%2C+2023)."""
    month_name = date.strftime("%b")
    day = date.strftime("%d")
    year = date.strftime("%Y")
    return f"{month_name}+{day}%2C+{year}"

def format_date_for_display(date: datetime.date) -> str:
    """Format date for display (e.g., Friday, April 7, 2023)."""
    return date.strftime("%A, %B %d, %Y")

def find_consecutive_days(available_dates: List[datetime.date]) -> List[Tuple[datetime.date, datetime.date]]:
    """Find consecutive available weekend days (Fri-Sat or Sat-Sun pairs)."""
    consecutive_pairs = []
    
    for i in range(len(available_dates) - 1):
        date1 = available_dates[i]
        date2 = available_dates[i + 1]
        
        # Check if dates are consecutive
        if (date2 - date1).days == 1:
            # Check if it's a weekend pair
            if (date1.weekday() == 4 and date2.weekday() == 5) or \
               (date1.weekday() == 5 and date2.weekday() == 6):
                consecutive_pairs.append((date1, date2))
    
    return consecutive_pairs

class YosemiteSeleniumChecker:
    """Check Yosemite Valley Lodge availability using Selenium."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.browser = None
        self.available_dates = set()
    
    def setup_browser(self):
        """Initialize and configure the browser."""
        browser_name = self.config["browser"].lower()
        headless = self.config["headless"]
        
        try:
            if browser_name == "chrome":
                options = ChromeOptions()
                if headless:
                    options.add_argument("--headless=new")
                
                # Set window size to a common resolution
                options.add_argument("--window-size=1920,1080")
                
                # Standard options for stability
                options.add_argument("--disable-gpu")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                
                # Set a realistic user agent (use a recent Chrome version)
                options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
                
                # Enhanced anti-bot detection configurations
                options.add_argument("--disable-blink-features=AutomationControlled")  # Hide automation
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option("useAutomationExtension", False)
                
                # Add more realistic browser settings
                options.add_argument("--lang=en-US,en;q=0.9")
                options.add_argument("--disable-web-security")  # Helps with some CORS issues
                options.add_argument("--enable-cookies")
                options.add_argument("--disable-dev-shm-usage")
                
                # Set a more realistic viewport size
                options.add_argument("--window-size=1920,1080")
                
                # Add timezone to appear more human-like
                options.add_argument("--timezone=America/Los_Angeles")
                
                # Add random delays between actions using a custom JavaScript
                prefs = {
                    "profile.default_content_setting_values.notifications": 2,  # Block notifications
                    "credentials_enable_service": False,  # Disable password saving prompts
                    "profile.password_manager_enabled": False
                }
                options.add_experimental_option("prefs", prefs)
                
                self.browser = webdriver.Chrome(
                    service=ChromeService(ChromeDriverManager().install()),
                    options=options
                )
            elif browser_name == "firefox":
                options = FirefoxOptions()
                if headless:
                    options.add_argument("--headless")
                options.add_argument("--width=1920")
                options.add_argument("--height=1080")
                
                self.browser = webdriver.Firefox(
                    service=FirefoxService(GeckoDriverManager().install()),
                    options=options
                )
            else:
                raise ValueError(f"Unsupported browser: {browser_name}")
            
            self.browser.implicitly_wait(10)
            logger.info(f"Browser {browser_name} initialized successfully")
            
        except Exception as e:
            logger.error(f"Error setting up browser: {e}")
            raise
    
    def check_availability(self) -> List[datetime.date]:
        """Check availability for weekend dates in the specified period."""
        if not self.browser:
            self.setup_browser()
        
        weekend_dates = get_weekend_dates(self.config["months_ahead"])
        available_dates = []
        
        try:
            # Process dates in pairs for consecutive nights
            for i in range(len(weekend_dates) - 1):
                check_in_date = weekend_dates[i]
                check_out_date = weekend_dates[i] + datetime.timedelta(days=1)
                
                # Only check Friday-Saturday and Saturday-Sunday pairs if specified in config
                if check_in_date.weekday() == 4 and not self.config["check_friday_saturday"]:  # Friday
                    continue
                if check_in_date.weekday() == 5 and not self.config["check_saturday_sunday"]:  # Saturday
                    continue
                
                # Skip non-weekend date pairs
                if check_in_date.weekday() not in [4, 5]:  # Not Friday or Saturday
                    continue
                
                try:
                    # Construct URL for this date pair
                    check_in_str = format_date_for_url(check_in_date)
                    check_out_str = format_date_for_url(check_out_date)
                    adults = self.config["adults"]
                    children = self.config["children"]
                    
                    url = f"{self.config['urls']['base_url']}?ArrivalDate={check_in_str}&DepartureDate={check_out_str}&Adults={adults}&Children={children}"
                    logger.debug(f"Checking URL: {url}")
                    
                    # Navigate to the search URL
                    logger.info(f"Checking availability for {format_date_for_display(check_in_date)} to {format_date_for_display(check_out_date)}")
                    self.browser.get(url)
                    
                    # Wait for page to load fully
                    WebDriverWait(self.browser, 20).until(
                        EC.presence_of_element_located((By.TAG_NAME, "body"))
                    )
                    
                    # Check for PleaseWait page and wait for it to redirect
                    current_url = self.browser.current_url
                    if "PleaseWait" in current_url:
                        logger.info("Detected PleaseWait page, waiting for redirect...")
                        wait_time = 0
                        max_wait = 30  # Maximum seconds to wait
                        
                        # Wait until we're no longer on the PleaseWait page
                        while "PleaseWait" in self.browser.current_url and wait_time < max_wait:
                            time.sleep(1)
                            wait_time += 1
                        
                        # Log where we ended up
                        logger.info(f"After waiting, redirected to: {self.browser.current_url}")
                    
                    # Check for "Action Not Allowed" message
                    if "Action Not Allowed" in self.browser.page_source:
                        logger.error("Detected 'Action Not Allowed' message - site may be blocking automated access")
                        # Take a screenshot of the error
                        error_screenshot = f"error_{check_in_date.strftime('%Y%m%d')}.png"
                        self.browser.save_screenshot(error_screenshot)
                        logger.info(f"Error screenshot saved to {error_screenshot}")
                        
                        # Try a different approach - use a more deliberate, human-like interaction
                        logger.info("Trying alternative approach with slower, more human-like interaction...")
                        
                    # Wait for search form to be ready - longer wait to make sure JavaScript loads
                    time.sleep(8)  # Allow more time for any AJAX calls to complete
                    
                    # Fill in dates if needed
                    try:
                        # Try to locate date fields - might already be filled from URL params
                        arrival_date = self.browser.find_element(By.ID, "box-widget_ArrivalDate")
                        departure_date = self.browser.find_element(By.ID, "box-widget_DepartureDate")
                        
                        # Check if fields are empty
                        if not arrival_date.get_attribute("value"):
                            # Clear and fill date fields
                            arrival_date.clear()
                            arrival_date.send_keys(check_in_date.strftime("%m/%d/%Y"))
                            logger.info("Filled arrival date field")
                            
                        if not departure_date.get_attribute("value"):
                            departure_date.clear()  
                            departure_date.send_keys(check_out_date.strftime("%m/%d/%Y"))
                            logger.info("Filled departure date field")
                    except Exception as e:
                        logger.debug(f"Date fields not found or already filled: {e}")
                    
                    # Use more human-like interactions to avoid detection
                    try:
                        # Try to use the most human-like approach - find and fill the form elements individually
                        logger.info("Attempting human-like form interactions...")
                        
                        # First, scroll down a bit to simulate a human viewing the form
                        try:
                            self.browser.execute_script("window.scrollBy(0, 200);")
                            time.sleep(random.uniform(0.5, 1.5))  # Random delay like a human
                        except Exception:
                            pass
                        
                        # Try finding the form elements explicitly
                        try:
                            # Click on each element with small random delays
                            selectors_to_try = [
                                "box-widget_ArrivalDate",  # By ID
                                "box-widget_DepartureDate"  # By ID
                            ]
                            
                            for selector in selectors_to_try:
                                try:
                                    elem = self.browser.find_element(By.ID, selector)
                                    # Execute a click using JavaScript - sometimes more reliable
                                    self.browser.execute_script("arguments[0].click();", elem)
                                    time.sleep(random.uniform(0.5, 1.2))
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        
                        # Now try to find and click the submit button
                        selectors = [
                            "//button[contains(text(), 'Check Availability')]",
                            "//input[@value='Check Availability']", 
                            "//input[contains(@class, 'wxa-form-button')]",
                            "//form[contains(@class, 'wxa-form')]//input[@type='submit']",
                            "//button[contains(@class, 'btn-primary')]"
                        ]
                        
                        button_found = False
                        for selector in selectors:
                            try:
                                check_button = WebDriverWait(self.browser, 2).until(
                                    EC.element_to_be_clickable((By.XPATH, selector))
                                )
                                logger.info(f"Found availability button using selector: {selector}")
                                
                                # Scroll to make button visible
                                self.browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", check_button)
                                time.sleep(random.uniform(0.8, 1.5))  # Pause like a human would
                                
                                # Click the button using JavaScript - more reliable
                                self.browser.execute_script("arguments[0].click();", check_button)
                                logger.info("Clicked search button with JavaScript")
                                
                                button_found = True
                                time.sleep(random.uniform(6, 10))  # Wait longer for results like a human would
                                break
                            except Exception:
                                continue
                        
                        # If direct button click fails, try multiple alternative approaches
                        if not button_found:
                            # Try finding the form and using JavaScript submit
                            try:
                                form = self.browser.find_element(By.XPATH, "//form[contains(@class, 'wxa-form')]")
                                logger.info("Found search form, submitting with JavaScript")
                                self.browser.execute_script("arguments[0].submit();", form)
                                time.sleep(7)  # Wait for results
                            except Exception as e:
                                logger.debug(f"Could not submit form with JavaScript: {e}")
                                
                                # Last resort - try pressing Enter on the last form field
                                try:
                                    departure_date = self.browser.find_element(By.ID, "box-widget_DepartureDate")
                                    logger.info("Attempting to submit by sending Enter key to date field")
                                    departure_date.send_keys("\n")  # Send Enter key
                                    time.sleep(7)  # Wait for results
                                except Exception as e:
                                    logger.debug(f"Could not send Enter key: {e}")
                    except Exception as e:
                        logger.debug(f"Form interaction failed: {e}")
                    
                    # Save first screenshot showing search page or early results
                    search_screenshot = f"search_{check_in_date.strftime('%Y%m%d')}.png"
                    try:
                        self.browser.save_screenshot(search_screenshot)
                        logger.info(f"Search screenshot saved to {search_screenshot}")
                    except Exception as e:
                        logger.error(f"Failed to save search screenshot: {e}")
                    
                    # Check if we're on a results page by looking at URL and page content
                    current_url = self.browser.current_url
                    logger.info(f"Current URL after search: {current_url}")
                    
                    # Handle PleaseWait redirect again - it can happen after form submission
                    if "PleaseWait" in current_url:
                        logger.info("Detected PleaseWait after form submission, waiting for redirect...")
                        wait_time = 0
                        max_wait = 30  # Maximum seconds to wait
                        
                        # Wait until we're no longer on the PleaseWait page
                        while "PleaseWait" in self.browser.current_url and wait_time < max_wait:
                            time.sleep(1)
                            wait_time += 1
                        
                        current_url = self.browser.current_url
                        logger.info(f"After waiting, redirected to: {current_url}")
                    
                    # Sometimes we're not redirected to the Results page - check different patterns
                    result_patterns = [
                        "Accommodation-Search/Results", 
                        "accommodation-search/results",
                        "Availability", 
                        "results",
                        "search"
                    ]
                    
                    is_results_url = any(pattern in current_url.lower() for pattern in result_patterns)
                    
                    # If we're still on the search page, the search may not have gone through
                    if not is_results_url:
                        logger.info("Not on results page - search may not have been submitted properly")
                        # Try a more aggressive approach to submit the form
                        try:
                            # First try to find and click any submit button
                            submit_buttons = self.browser.find_elements(By.XPATH, 
                                "//button[@type='submit'] | //input[@type='submit']")
                            
                            if submit_buttons:
                                logger.info(f"Found {len(submit_buttons)} submit buttons, clicking the first one")
                                self.browser.execute_script("arguments[0].click();", submit_buttons[0])
                                time.sleep(7)
                            else:
                                # If no submit button found, try form.submit()
                                logger.info("No submit buttons found, trying form.submit()")
                                self.browser.execute_script(
                                    "document.querySelector('form').submit();"
                                )
                                time.sleep(7)
                            
                            current_url = self.browser.current_url
                            logger.info(f"URL after aggressive submit: {current_url}")
                        except Exception as e:
                            logger.error(f"Failed to submit form with aggressive method: {e}")
                    
                    # Save screenshot for results verification
                    results_screenshot = f"availability_{check_in_date.strftime('%Y%m%d')}.png"
                    try:
                        self.browser.save_screenshot(results_screenshot)
                        logger.info(f"Results screenshot saved to {results_screenshot}")
                    except Exception as e:
                        logger.error(f"Failed to save results screenshot: {e}")
                    
                    # Add a delay to simulate human reading the page
                    time.sleep(random.uniform(2, 4))
                    
                    # Try to handle "Action Not Allowed" differently if detected
                    if "Action Not Allowed" in self.browser.page_source:
                        logger.warning("Detected 'Action Not Allowed' message - attempting recovery...")
                        
                        # Take a screenshot for debugging
                        error_screenshot = f"action_not_allowed_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                        self.browser.save_screenshot(error_screenshot)
                        
                        # Try clearing cookies and visiting again with a different approach
                        self.browser.delete_all_cookies()
                        logger.info("Cleared cookies and cache")
                        
                        # Wait a bit
                        time.sleep(random.uniform(5, 10))
                        
                        # Go to the homepage first
                        base_url = self.config['urls']['base_url'].split("/Plan-Your-Trip")[0]
                        logger.info(f"Visiting main site first: {base_url}")
                        self.browser.get(base_url)
                        time.sleep(random.uniform(4, 8))
                        
                        # Now try a more direct booking approach
                        logger.info("Using alternate booking path...")
                        try:
                            # Look for a "Book Now" or similar link on the main page
                            booking_selectors = [
                                "//a[contains(text(), 'Book') or contains(@class, 'book')]",
                                "//a[contains(text(), 'Reserve') or contains(@class, 'reserve')]",
                                "//a[contains(text(), 'Stay') or contains(@class, 'stay')]",
                                "//a[contains(text(), 'Lodging')]"
                            ]
                            
                            for selector in booking_selectors:
                                elements = self.browser.find_elements(By.XPATH, selector)
                                if elements:
                                    logger.info(f"Found booking link with selector: {selector}")
                                    # Use JavaScript to click to avoid detection
                                    self.browser.execute_script("arguments[0].click();", elements[0])
                                    time.sleep(random.uniform(3, 5))
                                    break
                        except Exception as e:
                            logger.error(f"Error during recovery attempt: {e}")
                    
                    # Get page source after possible redirect
                    page_source = self.browser.page_source.lower()
                    
                    # Log page title to help with debugging
                    page_title = self.browser.title
                    logger.info(f"Page title: {page_title}")
                    
                    # Check for common error messages
                    error_phrases = [
                        "action not allowed",
                        "access denied",
                        "error",
                        "unavailable",
                        "forbidden"
                    ]
                    
                    has_error = any(phrase in page_source.lower() for phrase in error_phrases)
                    if has_error:
                        logger.error(f"Detected error phrase in page content: {[p for p in error_phrases if p in page_source.lower()]}")
                    
                    # Check for "No availability" text and messages
                    no_availability_phrases = [
                        "no availability",
                        "not available", 
                        "no rooms available",
                        "sold out",
                        "no lodging available",
                        "no results found",
                        "couldn't find any results",
                        "we couldn't find any results"
                    ]
                    
                    no_availability_found = any(phrase in page_source.lower() for phrase in no_availability_phrases)
                    
                    # Check for results heading that would indicate we're on a proper results page
                    results_heading = len(self.browser.find_elements(By.XPATH, 
                        "//h1[contains(text(), 'Results')] | //h2[contains(text(), 'Results')] | " + 
                        "//div[contains(@class, 'results-heading')] | //div[contains(@class, 'results')]")) > 0
                    
                    # Look for positive indicators of availability - we need specific elements found on the results page
                    has_book_button = len(self.browser.find_elements(By.XPATH, 
                        "//button[contains(text(), 'Book') or contains(text(), 'Reserve') or contains(text(), 'Select') or " + 
                        "contains(@class, 'book') or contains(@class, 'reserve') or contains(@class, 'select')]")) > 0
                    
                    # Look for prices with dollar signs - strong indicator of availability
                    try:
                        price_elements1 = self.browser.find_elements(By.XPATH, "//*[contains(text(), '$')]")
                        price_elements2 = self.browser.find_elements(By.XPATH, "//*[contains(@class, 'price')]")
                        price_elements3 = self.browser.find_elements(By.XPATH, "//*[contains(@class, 'rate')]")
                        has_price = len(price_elements1) + len(price_elements2) + len(price_elements3) > 0
                        logger.info(f"Found {len(price_elements1)} price texts, {len(price_elements2)} price elements, {len(price_elements3)} rate elements")
                    except Exception as e:
                        logger.error(f"Error checking for price elements: {e}")
                        has_price = False
                    
                    # Look for actual room items in search results
                    has_room_details = len(self.browser.find_elements(By.XPATH, 
                        "//div[contains(@class, 'room') or contains(@class, 'accommodation') or " + 
                        "contains(@class, 'result-item') or contains(@class, 'lodging')]")) > 0
                    
                    # Check if page has loaded search results and not just showing the search form
                    is_search_form_visible = "search" in page_source.lower() and "check availability" in page_source.lower()
                    
                    # Determine if we're on a results page by URL patterns or page content
                    is_results_page = (
                        is_results_url or 
                        results_heading or 
                        "results" in page_title.lower() or
                        "availability" in page_title.lower() or
                        ("search results" in page_source.lower() and not is_search_form_visible)
                    )
                    
                    # Log what we found
                    logger.info(f"Has error message: {has_error}")
                    logger.info(f"No availability phrases found: {no_availability_found}")
                    logger.info(f"Has book button: {has_book_button}")
                    logger.info(f"Has price: {has_price}")
                    logger.info(f"Has room details: {has_room_details}")
                    logger.info(f"Is results page: {is_results_page}")
                    
                    # Determine true availability: 
                    # 1. Must be on the results page
                    # 2. Must have at least one positive indicator (book buttons, prices, or room details)
                    # 3. Must NOT have "no availability" messages
                    # 4. Must NOT have error messages
                    true_availability = (
                        is_results_page and 
                        (has_book_button or has_price or has_room_details) and 
                        not no_availability_found and
                        not has_error
                    )
                    
                    if true_availability:
                        logger.info(f"TRUE AVAILABILITY FOUND for {format_date_for_display(check_in_date)}")
                        available_dates.append(check_in_date)
                    else:
                        logger.info(f"No availability for {format_date_for_display(check_in_date)}")
                    
                except Exception as e:
                    logger.error(f"Error checking date {check_in_date}: {e}")
                
                # Random delay between checks to avoid being blocked
                time.sleep(random.uniform(2, 5))
        
        except Exception as e:
            logger.error(f"Error during availability check: {e}")
        
        finally:
            if self.browser:
                self.browser.quit()
                self.browser = None
        
        return available_dates
    
    def run_check(self) -> Tuple[List[datetime.date], List[Tuple[datetime.date, datetime.date]]]:
        """Run availability check and return results."""
        retries = 0
        max_retries = self.config["max_retries"]
        retry_delay = self.config["retry_delay_seconds"]
        
        while retries < max_retries:
            try:
                available_dates = self.check_availability()
                consecutive_pairs = find_consecutive_days(available_dates)
                return available_dates, consecutive_pairs
            
            except Exception as e:
                retries += 1
                logger.error(f"Check failed (attempt {retries}/{max_retries}): {e}")
                
                if retries < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries reached. Check failed.")
                    return [], []

class YosemiteRequestsChecker:
    """Check Yosemite Valley Lodge availability using Requests/BeautifulSoup."""
    
    def __init__(self, config: Dict):
        self.config = config
        self.session = requests.Session()
        # Set a realistic user agent
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive"
        })
    
    def get_widget_config(self) -> Dict:
        """Get the widget configuration data containing lodge information."""
        try:
            timestamp = int(time.time() * 1000)
            url = f"{self.config['urls']['widget_config_url']}?callback=jQuery_callback&_={timestamp}"
            
            response = self.session.get(url)
            response.raise_for_status()
            
            # Extract the JSON data from the JSONP response
            jsonp_data = response.text
            json_str = re.search(r'jQuery_callback\((.*)\)', jsonp_data, re.DOTALL)
            
            if json_str:
                return json.loads(json_str.group(1))
            else:
                logger.error("Could not extract JSON data from widget config response")
                return {}
                
        except Exception as e:
            logger.error(f"Error getting widget config: {e}")
            return {}
    
    def check_availability(self) -> List[datetime.date]:
        """Check availability using HTTP requests and BeautifulSoup."""
        weekend_dates = get_weekend_dates(self.config["months_ahead"])
        available_dates = []
        
        try:
            # First visit the main page to get any cookies or session data
            main_page = self.session.get(self.config["urls"]["base_url"])
            main_page.raise_for_status()
            
            # Process dates in pairs for consecutive nights
            for i in range(len(weekend_dates) - 1):
                check_in_date = weekend_dates[i]
                check_out_date = weekend_dates[i] + datetime.timedelta(days=1)
                
                # Only check Friday-Saturday and Saturday-Sunday pairs if specified in config
                if check_in_date.weekday() == 4 and not self.config["check_friday_saturday"]:  # Friday
                    continue
                if check_in_date.weekday() == 5 and not self.config["check_saturday_sunday"]:  # Saturday
                    continue
                
                # Skip non-weekend date pairs
                if check_in_date.weekday() not in [4, 5]:  # Not Friday or Saturday
                    continue
                
                try:
                    # Construct URL for this date pair
                    check_in_str = format_date_for_url(check_in_date)
                    check_out_str = format_date_for_url(check_out_date)
                    adults = self.config["adults"]
                    children = self.config["children"]
                    
                    url = f"{self.config['urls']['base_url']}?ArrivalDate={check_in_str}&DepartureDate={check_out_str}&Adults={adults}&Children={children}"
                    logger.info(f"Checking availability for {format_date_for_display(check_in_date)} to {format_date_for_display(check_out_date)}")
                    
                    response = self.session.get(url)
                    response.raise_for_status()
                    
                    # Parse the response to check for availability
                    soup = BeautifulSoup(response.text, "html.parser")
                    
                    # Check for "No availability" message or similar phrases
                    no_availability_phrases = [
                        "no availability",
                        "not available", 
                        "no rooms available",
                        "sold out",
                        "no lodging available",
                        "no results found",
                        "couldn't find any results",
                        "we couldn't find any results"
                    ]
                    
                    page_text = soup.get_text().lower()
                    no_availability = any(phrase in page_text for phrase in no_availability_phrases)
                    
                    # Look for booking elements that indicate availability
                    rate_elements = soup.find_all('div', class_=lambda c: c and ('rate' in c.lower() or 'room' in c.lower()))
                    book_buttons = soup.find_all(['button', 'a'], string=re.compile(r'Book|Reserve', re.IGNORECASE))
                    price_elements = soup.find_all(text=re.compile(r'\$\d+'))
                    
                    # Check for specific strings that strongly indicate availability
                    available_phrases = [
                        "add to cart",
                        "book now",
                        "reserve now",
                        "best available rate",
                        "average/night",
                        "$"
                    ]
                    # SIMPLIFIED CHECK: if there's a price or rate element, it's available
                    # This is a more permissive check to catch more availability
                    has_dollar_sign = "$" in page_text
                    
                    # If we find prices or rate elements, that's enough to indicate availability
                    has_availability = (rate_elements or book_buttons or price_elements or has_dollar_sign)
                    
                    if has_availability:
                        logger.info(f"Availability found for {format_date_for_display(check_in_date)}")
                        available_dates.append(check_in_date)
                    else:
                        logger.info(f"No availability for {format_date_for_display(check_in_date)}")
                
                except Exception as e:
                    logger.error(f"Error checking date {check_in_date}: {e}")
                
                # Random delay between requests
                time.sleep(random.uniform(2, 5))
        
        except Exception as e:
            logger.error(f"Error during availability check: {e}")
        
        return available_dates
    
    def run_check(self) -> Tuple[List[datetime.date], List[Tuple[datetime.date, datetime.date]]]:
        """Run availability check and return results."""
        retries = 0
        max_retries = self.config["max_retries"]
        retry_delay = self.config["retry_delay_seconds"]
        
        while retries < max_retries:
            try:
                available_dates = self.check_availability()
                consecutive_pairs = find_consecutive_days(available_dates)
                return available_dates, consecutive_pairs
            
            except Exception as e:
                retries += 1
                logger.error(f"Check failed (attempt {retries}/{max_retries}): {e}")
                
                if retries < max_retries:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
                else:
                    logger.error("Max retries reached. Check failed.")
                    return [], []

def send_email_notification(config: Dict, available_dates: List[datetime.date], consecutive_pairs: List[Tuple[datetime.date, datetime.date]]):
    """Send email notification about available dates."""
    if not config["email"]["enabled"]:
        logger.info("Email notifications are disabled in config")
        return
    
    if not available_dates:
        logger.info("No available dates to send notification about")
        return
    
    # Check if email credentials are provided
    if not config["email"]["username"] or not config["email"]["password"]:
        logger.error("Email credentials are not configured properly in config.json")
        logger.info("Please edit config.json and add your email username and password")
        return
        
    # Make sure from_address and to_address are set correctly
    if not config["email"]["from_address"] or not config["email"]["to_address"]:
        logger.info("Missing from_address or to_address, using username for both")
        config["email"]["from_address"] = config["email"]["username"]
        config["email"]["to_address"] = config["email"]["username"]
    
    logger.info(f"Preparing to send email notification for {len(available_dates)} dates")
    logger.info(f"Email will be sent from {config['email']['username']} to {config['email']['to_address']}")
    
    try:
        # Create email body content
        email_body = "Yosemite Valley Lodge Availability Alert\n\n"
        
        if consecutive_pairs:
            email_body += "Consecutive weekend days available:\n"
            for start_date, end_date in consecutive_pairs:
                email_body += f"* {format_date_for_display(start_date)} - {format_date_for_display(end_date)}\n"
            email_body += "\n"
        
        if available_dates:
            email_body += "All available weekend days:\n"
            for date in sorted(available_dates):
                email_body += f"* {format_date_for_display(date)}\n"
        
        # Generate direct booking URLs for found dates
        email_body += "\nDirect booking links:\n"
        for date in sorted(available_dates):
            check_in_str = format_date_for_url(date)
            check_out_str = format_date_for_url(date + datetime.timedelta(days=1))
            adults = config["adults"]
            children = config["children"]
            booking_url = f"{config['urls']['base_url']}?ArrivalDate={check_in_str}&DepartureDate={check_out_str}&Adults={adults}&Children={children}"
            email_body += f"* {format_date_for_display(date)}: {booking_url}\n"
        
        email_body += f"\nThis alert was generated on {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        # Use a more reliable, simpler approach
        logger.info("Sending email notification...")
        
        # Create a simple MIME message
        msg = MIMEMultipart()
        
        # Set the subject
        if consecutive_pairs:
            msg["Subject"] = config["email"]["consecutive_subject"]
        else:
            msg["Subject"] = config["email"]["single_day_subject"]
        
        # Use proper email formatting
        from_addr = config["email"]["from_address"]
        if '@' not in from_addr:
            from_addr = f"{from_addr}@gmail.com"
            logger.info(f"Adding @gmail.com to from_address: {from_addr}")
            
        to_addr = config["email"]["to_address"]
        if '@' not in to_addr:
            to_addr = f"{to_addr}@gmail.com"
            logger.info(f"Adding @gmail.com to to_address: {to_addr}")
            
        # Set From and To headers
        msg["From"] = from_addr
        msg["To"] = to_addr
        
        # Add email content
        msg.attach(MIMEText(email_body, "plain"))
        
        try:
            # Connect to the server
            with smtplib.SMTP(config["email"]["smtp_server"], config["email"]["smtp_port"]) as server:
                # Identify to the server
                server.ehlo()
                
                # Start encryption
                server.starttls()
                
                # Re-identify after encryption
                server.ehlo()
                
                # Login
                username = config["email"]["username"]
                password = config["email"]["password"]
                
                if '@' not in username:
                    username = f"{username}@gmail.com" 
                    logger.info(f"Adding @gmail.com to username: {username}")
                
                logger.info(f"Logging in as {username}")
                server.login(username, password)
                
                # Send the message
                logger.info(f"Sending email from {from_addr} to {to_addr}")
                server.sendmail(from_addr, to_addr, msg.as_string())
                logger.info("Email sent successfully")
        except Exception as e:
            logger.error(f"Failed to send email through standard method: {e}")
            
            # Fallback method using direct SSL connection
            try:
                import ssl
                context = ssl.create_default_context()
                
                logger.info("Trying SSL direct connection...")
                with smtplib.SMTP_SSL(config["email"]["smtp_server"], 465, context=context) as server:
                    logger.info(f"Logging in with SSL as {username}")
                    server.login(username, password)
                    server.sendmail(from_addr, to_addr, msg.as_string())
                    logger.info("Email sent successfully via SSL")
            except Exception as ssl_error:
                logger.error(f"SSL method also failed: {ssl_error}")
                raise
        
        logger.info(f"Email notification sent to {config['email']['to_address']}")
        
    except Exception as e:
        logger.error(f"Error sending email notification: {e}")
        # Log more details about the exception
        import traceback
        logger.error(f"Email error details: {traceback.format_exc()}")

def calculate_next_check_time(config: Dict) -> int:
    """Calculate next check time with randomization."""
    base_interval = config["check_interval_hours"] * 3600  # Convert to seconds
    variation_percent = config["interval_variation_percent"]
    
    # Calculate variation range
    variation_seconds = base_interval * (variation_percent / 100)
    
    # Apply random variation
    next_interval = random.uniform(
        base_interval - variation_seconds,
        base_interval + variation_seconds
    )
    
    return int(max(1800, next_interval))  # Ensure at least 30 minutes

def save_results(available_dates: List[datetime.date], consecutive_pairs: List[Tuple[datetime.date, datetime.date]]):
    """Save results to a file for comparison with future runs."""
    try:
        results = {
            "timestamp": datetime.datetime.now().isoformat(),
            "available_dates": [d.isoformat() for d in available_dates],
            "consecutive_pairs": [(d1.isoformat(), d2.isoformat()) for d1, d2 in consecutive_pairs]
        }
        
        with open("last_results.json", "w") as f:
            json.dump(results, f, indent=4)
        
        logger.debug("Saved results to last_results.json")
    
    except Exception as e:
        logger.error(f"Error saving results: {e}")

def load_last_results() -> Tuple[List[datetime.date], List[Tuple[datetime.date, datetime.date]]]:
    """Load results from previous run for comparison."""
    try:
        if not os.path.exists("last_results.json"):
            return [], []
        
        with open("last_results.json", "r") as f:
            data = json.load(f)
        
        available_dates = [datetime.date.fromisoformat(d) for d in data.get("available_dates", [])]
        consecutive_pairs = [(datetime.date.fromisoformat(d1), datetime.date.fromisoformat(d2)) 
                            for d1, d2 in data.get("consecutive_pairs", [])]
        
        return available_dates, consecutive_pairs
    
    except Exception as e:
        logger.error(f"Error loading previous results: {e}")
        return [], []

def compare_results(current: List[datetime.date], previous: List[datetime.date]) -> List[datetime.date]:
    """Compare current and previous results to find new availabilities."""
    current_set = set(current)
    previous_set = set(previous)
    
    return list(current_set - previous_set)

def run_availability_checker(config_path: str = "config.json", single_run: bool = False):
    """Main function to run the availability checker."""
    config = load_config(config_path)
    
    # Initialize checker based on configured method
    if config["method"].lower() == "selenium":
        checker = YosemiteSeleniumChecker(config)
    else:
        checker = YosemiteRequestsChecker(config)
    
    previous_available_dates, previous_consecutive_pairs = load_last_results()
    
    while True:
        try:
            logger.info("Starting availability check")
            
            # Run the availability check
            available_dates, consecutive_pairs = checker.run_check()
            
            # Save current results
            save_results(available_dates, consecutive_pairs)
            
            # Check for new availabilities
            new_dates = compare_results(available_dates, previous_available_dates)
            new_consecutive = find_consecutive_days(new_dates)
            
            # Send notifications only if there are new availabilities
            if new_dates:
                logger.info(f"New availability found for {len(new_dates)} dates")
                logger.info(f"New available dates: {[format_date_for_display(d) for d in new_dates]}")
                send_email_notification(config, new_dates, new_consecutive)
            elif available_dates:
                logger.info(f"Found availability for {len(available_dates)} dates but none are new")
                logger.info(f"Available dates: {[format_date_for_display(d) for d in available_dates]}")
                
                # Test email for debugging purposes - uncomment if needed
                # logger.info("Attempting to send test notification for all dates anyway")
                # send_email_notification(config, available_dates, consecutive_pairs)
            else:
                logger.info("No availability found")
            
            # Update previous results for next comparison
            previous_available_dates = available_dates
            previous_consecutive_pairs = consecutive_pairs
            
            if single_run:
                break
            
            # Calculate next check time
            next_check = calculate_next_check_time(config)
            next_check_time = datetime.datetime.now() + datetime.timedelta(seconds=next_check)
            logger.info(f"Next check scheduled for {next_check_time.strftime('%Y-%m-%d %H:%M:%S')} "
                      f"({next_check // 3600}h {(next_check % 3600) // 60}m {next_check % 60}s from now)")
            
            # Sleep until next check
            time.sleep(next_check)
        
        except KeyboardInterrupt:
            logger.info("Check interrupted by user")
            break
        
        except Exception as e:
            logger.error(f"Unexpected error during check: {e}")
            if single_run:
                break
            
            # Sleep for a shorter time before retrying
            logger.info("Retrying in 15 minutes...")
            time.sleep(900)

def check_specific_date(date_str: str, config: Dict):
    """Check availability for a specific date."""
    try:
        # Parse the date string (expecting MM-DD-YYYY format)
        month, day, year = map(int, date_str.split('-'))
        check_date = datetime.date(year, month, day)
        logger.info(f"Checking specific date: {format_date_for_display(check_date)}")
        
        # Create a checker based on configured method
        if config["method"].lower() == "selenium":
            checker = YosemiteSeleniumChecker(config)
        else:
            checker = YosemiteRequestsChecker(config)
        
        # The next day for checkout
        checkout_date = check_date + datetime.timedelta(days=1)
        
        # Initialize the browser if using Selenium
        if isinstance(checker, YosemiteSeleniumChecker) and not checker.browser:
            checker.setup_browser()
        
        try:
            # Temporarily override config to check only this specific date
            original_months_ahead = checker.config["months_ahead"]
            checker.config["months_ahead"] = 24  # Allow checking dates further in the future
            
            check_in_str = format_date_for_url(check_date)
            check_out_str = format_date_for_url(checkout_date)
            adults = checker.config["adults"]
            children = checker.config["children"]
            
            # Construct URL for the specified date
            url = f"{config['urls']['base_url']}?ArrivalDate={check_in_str}&DepartureDate={check_out_str}&Adults={adults}&Children={children}"
            logger.info(f"Checking URL: {url}")
            
            if isinstance(checker, YosemiteSeleniumChecker):
                # More human-like browsing pattern - first go to the main site
                base_url = config['urls']['base_url']
                main_url = base_url.split('Plan-Your-Trip')[0]  # Get just the domain part
                
                logger.info(f"First visiting main page: {main_url}")
                checker.browser.get(main_url)
                
                # Wait randomly like a human would
                time.sleep(random.uniform(3, 5))
                
                # Now navigate to the search URL
                logger.info(f"Now navigating to search URL: {url}")
                checker.browser.get(url)
                
                # Add some randomized mouse movements to appear more human-like
                try:
                    # Simulate random mouse movements with JavaScript
                    move_mouse_script = """
                    function simulateMouseMovement() {
                        let x = 100 + Math.floor(Math.random() * 600);
                        let y = 100 + Math.floor(Math.random() * 400);
                        
                        let element = document.elementFromPoint(x, y);
                        if (element) {
                            element.dispatchEvent(new MouseEvent('mouseover', {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            }));
                        }
                    }
                    
                    // Execute a few random movements
                    for (let i = 0; i < 5; i++) {
                        setTimeout(simulateMouseMovement, i * 300);
                    }
                    """
                    checker.browser.execute_script(move_mouse_script)
                except Exception:
                    pass  # Ignore if this fails
                
                # Wait for page to load fully
                WebDriverWait(checker.browser, 20).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                # Follow the same logic as in check_availability method
                # Handle potential PleaseWait page
                current_url = checker.browser.current_url
                if "PleaseWait" in current_url:
                    logger.info("Detected PleaseWait page, waiting for redirect...")
                    wait_time = 0
                    max_wait = 30
                    
                    while "PleaseWait" in checker.browser.current_url and wait_time < max_wait:
                        time.sleep(1)
                        wait_time += 1
                    
                    logger.info(f"After waiting, redirected to: {checker.browser.current_url}")
                
                # Rest of the check logic from YosemiteSeleniumChecker.check_availability
                time.sleep(8)  # Allow time for AJAX calls
                
                # Try to submit the search form
                try:
                    # Try finding and clicking the submit button
                    selectors = [
                        "//button[contains(text(), 'Check Availability')]",
                        "//input[@value='Check Availability']", 
                        "//input[contains(@class, 'wxa-form-button')]",
                        "//form[contains(@class, 'wxa-form')]//input[@type='submit']",
                        "//button[contains(@class, 'btn-primary')]"
                    ]
                    
                    button_found = False
                    for selector in selectors:
                        try:
                            check_button = WebDriverWait(checker.browser, 2).until(
                                EC.element_to_be_clickable((By.XPATH, selector))
                            )
                            logger.info(f"Found availability button using selector: {selector}")
                            
                            # Scroll to make button visible
                            checker.browser.execute_script("arguments[0].scrollIntoView({block: 'center'});", check_button)
                            time.sleep(random.uniform(0.8, 1.5))
                            
                            # Click the button
                            checker.browser.execute_script("arguments[0].click();", check_button)
                            logger.info("Clicked search button with JavaScript")
                            
                            button_found = True
                            time.sleep(random.uniform(6, 10))
                            break
                        except Exception:
                            continue
                    
                    # If direct button click fails, try alternatives
                    if not button_found:
                        # Try submitting the form with JavaScript
                        try:
                            form = checker.browser.find_element(By.XPATH, "//form[contains(@class, 'wxa-form')]")
                            logger.info("Found search form, submitting with JavaScript")
                            checker.browser.execute_script("arguments[0].submit();", form)
                            time.sleep(7)
                        except Exception as e:
                            logger.debug(f"Could not submit form with JavaScript: {e}")
                except Exception as e:
                    logger.debug(f"Form interaction failed: {e}")
                
                # Save screenshot showing search results
                search_screenshot = f"specific_date_{check_date.strftime('%Y%m%d')}.png"
                try:
                    checker.browser.save_screenshot(search_screenshot)
                    logger.info(f"Search screenshot saved to {search_screenshot}")
                except Exception as e:
                    logger.error(f"Failed to save search screenshot: {e}")
                
                # Check if we're on a results page
                current_url = checker.browser.current_url
                logger.info(f"Current URL after search: {current_url}")
                
                # Handle PleaseWait redirect again
                if "PleaseWait" in current_url:
                    logger.info("Detected PleaseWait after form submission, waiting for redirect...")
                    wait_time = 0
                    max_wait = 30
                    
                    while "PleaseWait" in checker.browser.current_url and wait_time < max_wait:
                        time.sleep(1)
                        wait_time += 1
                    
                    current_url = checker.browser.current_url
                    logger.info(f"After waiting, redirected to: {current_url}")
                
                # Check for results page patterns in URL
                result_patterns = [
                    "Accommodation-Search/Results", 
                    "accommodation-search/results",
                    "Availability", 
                    "results",
                    "search"
                ]
                
                is_results_url = any(pattern in current_url.lower() for pattern in result_patterns)
                
                # Get page source
                page_source = checker.browser.page_source.lower()
                
                # Log page title
                page_title = checker.browser.title
                logger.info(f"Page title: {page_title}")
                
                # Check only for serious error messages
                error_phrases = [
                    "action not allowed",
                    "access denied",
                    "forbidden"
                ]
                
                # More exact matching for errors to avoid false positives
                has_error = any(f" {phrase} " in f" {page_source.lower()} " for phrase in error_phrases)
                if has_error:
                    logger.error(f"Detected error phrase in page content: {[p for p in error_phrases if p in page_source.lower()]}")
                
                # Check for "No availability" text
                no_availability_phrases = [
                    "no availability",
                    "not available", 
                    "no rooms available",
                    "sold out",
                    "no lodging available",
                    "no results found",
                    "couldn't find any results",
                    "we couldn't find any results"
                ]
                
                no_availability_found = any(phrase in page_source.lower() for phrase in no_availability_phrases)
                
                # Check for results heading
                results_heading = len(checker.browser.find_elements(By.XPATH, 
                    "//h1[contains(text(), 'Results')] | //h2[contains(text(), 'Results')] | " + 
                    "//div[contains(@class, 'results-heading')] | //div[contains(@class, 'results')]")) > 0
                
                # Look for positive indicators
                has_book_button = len(checker.browser.find_elements(By.XPATH, 
                    "//button[contains(text(), 'Book') or contains(text(), 'Reserve') or contains(text(), 'Select') or " + 
                    "contains(@class, 'book') or contains(@class, 'reserve') or contains(@class, 'select')]")) > 0
                
                # Look for prices
                try:
                    price_elements1 = checker.browser.find_elements(By.XPATH, "//*[contains(text(), '$')]")
                    price_elements2 = checker.browser.find_elements(By.XPATH, "//*[contains(@class, 'price')]")
                    price_elements3 = checker.browser.find_elements(By.XPATH, "//*[contains(@class, 'rate')]")
                    has_price = len(price_elements1) + len(price_elements2) + len(price_elements3) > 0
                    logger.info(f"Found {len(price_elements1)} price texts, {len(price_elements2)} price elements, {len(price_elements3)} rate elements")
                except Exception as e:
                    logger.error(f"Error checking for price elements: {e}")
                    has_price = False
                
                # Look for room items - expanded with more precise selectors for Yosemite's site
                room_selectors = [
                    "//div[contains(@class, 'room') or contains(@class, 'accommodation') or contains(@class, 'result-item') or contains(@class, 'lodging')]",
                    "//*[contains(text(), 'Traditional Room')]",
                    "//*[contains(text(), 'Double Beds')]",
                    "//*[contains(text(), 'ADD TO CART')]",
                    "//button[contains(@class, 'cart')]",
                    "//*[contains(text(), 'AVERAGE/NIGHT')]"
                ]
                
                # Check each selector and report success if any match
                has_room_details = False
                for selector in room_selectors:
                    elements = checker.browser.find_elements(By.XPATH, selector)
                    if elements:
                        has_room_details = True
                        logger.info(f"Found room details with selector: {selector} ({len(elements)} elements)")
                        break
                
                # Check if page has loaded search results
                is_search_form_visible = "search" in page_source.lower() and "check availability" in page_source.lower()
                
                # Determine if we're on a results page
                is_results_page = (
                    is_results_url or 
                    results_heading or 
                    "results" in page_title.lower() or
                    "availability" in page_title.lower() or
                    ("search results" in page_source.lower() and not is_search_form_visible)
                )
                
                # Log what we found
                logger.info(f"Has error message: {has_error}")
                logger.info(f"No availability phrases found: {no_availability_found}")
                logger.info(f"Has book button: {has_book_button}")
                logger.info(f"Has price: {has_price}")
                logger.info(f"Has room details: {has_room_details}")
                logger.info(f"Is results page: {is_results_page}")
                
                # SIMPLIFIED AVAILABILITY CHECK
                # If we find price information or room details, consider it available
                
                # Check if we see a dollar amount in the page text, which is a strong indicator of availability
                dollar_amount_pattern = re.compile(r'\$\d+')
                has_dollar_amount = bool(dollar_amount_pattern.search(page_source))
                
                logger.info(f"Has dollar amount: {has_dollar_amount}")
                
                # ROOM DETAILS FOCUSED CHECK
                # Room details seems to be the most reliable indicator
                # Only consider it available if room details are found
                true_availability = has_room_details
                
                # Log the decision criteria
                logger.info(f"Final availability determination: {true_availability} (based on room details)")
                
                if true_availability:
                    logger.info(f"TRUE AVAILABILITY FOUND for {format_date_for_display(check_date)}")
                    available_dates = [check_date]
                    consecutive_pairs = [(check_date, checkout_date)]
                    
                    # Send email notification
                    send_email_notification(config, available_dates, consecutive_pairs)
                else:
                    logger.info(f"No availability found for {format_date_for_display(check_date)}")
            else:
                # For RequestsChecker implementation
                response = checker.session.get(url)
                response.raise_for_status()
                
                # Parse the response to check for availability
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Check for "No availability" message
                no_availability_phrases = [
                    "no availability",
                    "not available", 
                    "no rooms available",
                    "sold out",
                    "no lodging available",
                    "no results found",
                    "couldn't find any results",
                    "we couldn't find any results"
                ]
                
                page_text = soup.get_text().lower()
                no_availability = any(phrase in page_text for phrase in no_availability_phrases)
                
                # Look for booking elements
                rate_elements = soup.find_all('div', class_=lambda c: c and ('rate' in c.lower() or 'room' in c.lower()))
                book_buttons = soup.find_all(['button', 'a'], string=re.compile(r'Book|Reserve', re.IGNORECASE))
                price_elements = soup.find_all(text=re.compile(r'\$\d+'))
                
                # Check for specific strings that strongly indicate availability
                available_phrases = [
                    "add to cart",
                    "book now",
                    "reserve now",
                    "best available rate",
                    "average/night",
                    "$"
                ]
                # ROOM DETAILS FOCUSED CHECK
                # Look specifically for room details which are the most reliable indicator
                room_text_indicators = [
                    "traditional room", 
                    "double beds",
                    "add to cart",
                    "best available rate",
                    "average/night"
                ]
                
                has_room_text = any(indicator in page_text for indicator in room_text_indicators)
                
                # Focus on rate elements and room text indicators as the most reliable
                has_availability = (rate_elements or has_room_text)
                
                logger.info(f"Has room text indicators: {has_room_text}")
                logger.info(f"Final availability determination: {has_availability} (based on room details and rates)")
                
                if has_availability:
                    logger.info(f"Availability found for {format_date_for_display(check_date)}")
                    available_dates = [check_date]
                    consecutive_pairs = [(check_date, checkout_date)]
                    
                    # Send email notification
                    send_email_notification(config, available_dates, consecutive_pairs)
                else:
                    logger.info(f"No availability found for {format_date_for_display(check_date)}")
            
            # Restore original config
            checker.config["months_ahead"] = original_months_ahead
            
        finally:
            # Clean up
            if isinstance(checker, YosemiteSeleniumChecker) and checker.browser:
                checker.browser.quit()
    
    except ValueError:
        logger.error(f"Invalid date format: {date_str}. Please use MM-DD-YYYY format.")
    except Exception as e:
        logger.error(f"Error checking specific date: {e}")
        import traceback
        logger.error(traceback.format_exc())

def main():
    """Parse command line arguments and run the script."""
    parser = argparse.ArgumentParser(description="Yosemite Valley Lodge Availability Checker")
    parser.add_argument("-c", "--config", type=str, default="config.json",
                        help="Path to configuration file (default: config.json)")
    parser.add_argument("-s", "--single-run", action="store_true",
                        help="Run once and exit (default: continuous checking)")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Enable debug logging")
    parser.add_argument("-t", "--test-email", action="store_true",
                        help="Send a test email and exit")
    parser.add_argument("--date", type=str, 
                        help="Check a specific date (format: MM-DD-YYYY)")
    
    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    config = load_config(args.config)
    
    if args.test_email:
        # Send a test email
        test_date = datetime.date.today() + datetime.timedelta(days=3)
        test_dates = [test_date]
        test_consecutive = [(test_date, test_date + datetime.timedelta(days=1))]
        send_email_notification(config, test_dates, test_consecutive)
        sys.exit(0)
    
    if args.date:
        # Check a specific date
        check_specific_date(args.date, config)
        sys.exit(0)
    
    run_availability_checker(args.config, args.single_run)

if __name__ == "__main__":
    main()