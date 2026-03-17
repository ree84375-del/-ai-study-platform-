
import sys
import os

# Add the project root to sys.path
sys.path.append(r'c:\Users\Good PC\.gemini\antigravity\scratch\ai_study_platform')

import app.utils.i18n
from app.utils.i18n import get_text, TRANSLATIONS

keys = ['welcome_back', 'omikuji_lucky_color', 'omikuji_lucky_item', 'omikuji_lucky_subject', 'daily_fortune']

with open('i18n_test_result.txt', 'w', encoding='utf-8') as f:
    f.write(f"Imported i18n from: {app.utils.i18n.__file__}\n")
    f.write(f"TRANSLATIONS keys: {list(TRANSLATIONS.keys())}\n")
    
    if 'ja' in TRANSLATIONS:
        f.write(f"Number of keys in 'ja': {len(TRANSLATIONS['ja'])}\n")
        f.write(f"omikuji_lucky_color in 'ja': {'omikuji_lucky_color' in TRANSLATIONS['ja']}\n")
        if 'omikuji_lucky_color' in TRANSLATIONS['ja']:
            f.write(f"Value in 'ja': {TRANSLATIONS['ja']['omikuji_lucky_color']}\n")
        
        f.write("\n--- Testing 'ja' locale ---\n")
        for key in keys:
            f.write(f"{key}: {get_text(key, 'ja')}\n")

    f.write("\n--- Testing 'zh' locale ---\n")
    for key in keys:
        f.write(f"{key}: {get_text(key, 'zh')}\n")
