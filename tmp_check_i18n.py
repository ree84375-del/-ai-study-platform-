from app.utils.i18n import TRANSLATIONS
import json

ja_keys = list(TRANSLATIONS.get('ja', {}).keys())
print(f"Total JA keys: {len(ja_keys)}")
print(f"omikuji_lucky_color in JA: {'omikuji_lucky_color' in TRANSLATIONS.get('ja', {})}")
if 'omikuji_lucky_color' in TRANSLATIONS.get('ja', {}):
    print(f"Value: {TRANSLATIONS['ja']['omikuji_lucky_color']}")

# Check for duplicates or overriding ja block
# (In Python dict literal, last 'ja' wins)
# We can't see the literal duplicates from the compiled dict, 
# but we can see if common keys have Japanese values.
print(f"nav_home: {TRANSLATIONS.get('ja', {}).get('nav_home')}")
print(f"draw_omikuji: {TRANSLATIONS.get('ja', {}).get('draw_omikuji')}")
