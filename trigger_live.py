import urllib.request
import time

url = "https://ai-study-platform-seven.vercel.app/fix_schema_emergency"

print(f"Waiting 10 seconds for Vercel deployment to finalize before triggering {url}")
time.sleep(10)

try:
    response = urllib.request.urlopen(url)
    print("Response Status:", response.getcode())
    print("Response Body:", response.read().decode('utf-8'))
except Exception as e:
    print(f"Error fetching {url}: {e}")
