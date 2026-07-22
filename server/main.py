import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# Now you can access the API key
api_key = os.getenv("GMI_API_KEY")

# Verify it's loaded (optional)
if api_key:
    print("API key loaded successfully!")
    # print(f"API Key: {api_key[:5]}...{api_key[-5:]}") # Uncomment to see a snippet
else:
    print("API key not found. Check your .env file.")