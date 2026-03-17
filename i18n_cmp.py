
import sys
import os

# Add the project root to sys.path
sys.path.append(r'c:\Users\Good PC\.gemini\antigravity\scratch\ai_study_platform')

from app.utils.i18n import TRANSLATIONS

zh = TRANSLATIONS['zh']
ja = TRANSLATIONS['ja']

print("--- Keys in 'ja' that are identical to 'zh' ---")
for key, value in ja.items():
    if key in zh and zh[key] == value:
        # Some are expected to be the same, but let's see
        print(f"'{key}': '{value}'")
