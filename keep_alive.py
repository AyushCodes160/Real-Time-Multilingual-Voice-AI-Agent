import time
import requests
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# Use RENDER_EXTERNAL_URL if available, else replace with your actual Render URL
# Make sure to add RENDER_EXTERNAL_URL in your Render Environment Variables
URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")

# Ping every 14 minutes (Render free tier sleeps services after 15 minutes of inactivity)
PING_INTERVAL_MIN = 14 

def keep_alive():
    """
    Pings the specified URL periodically to prevent the Render service from sleeping.
    
    WARNING: Keeping a Render Free Tier service awake 24/7 consumes your free tier hours.
    Render provides 750 free hours per month across all projects. A single 24/7 service uses ~744 hours.
    If you have multiple projects, keeping them all awake will cause your account to run out 
    of free hours and be suspended until the next month.
    """
    logging.info(f"Starting keep-alive script. Pinging {URL} every {PING_INTERVAL_MIN} minutes.")
    while True:
        try:
            response = requests.get(URL, timeout=10)
            logging.info(f"Pinged {URL} - Status Code: {response.status_code}")
        except Exception as e:
            logging.error(f"Ping failed: {e}")
        
        # Wait for the specified interval before pinging again
        time.sleep(PING_INTERVAL_MIN * 60)

if __name__ == "__main__":
    if URL == "https://your-app-name.onrender.com":
        logging.warning("Please update the URL variable in this script or set RENDER_EXTERNAL_URL in your environment.")
    keep_alive()
