import os

file_path = "C:/Users/Good PC/.gemini/antigravity/scratch/ai_study_platform/app/utils/ai_helpers.py"
file_path = os.path.normpath(file_path)

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# Line 828 is index 827
head = lines[:828]
# Line 871 is index 870
tail = lines[870:]

mid = [
    "        return json.loads(clean_text)\n",
    "    except Exception as e:\n",
    "        return {'error': str(e)}\n",
    "\n",
    "def translate_omikuji(omikuji_json_str, target_lang='zh'):\n",
    "    \"\"\"Translates the omikuji JSON into the target language.\"\"\"\n",
    "    try:\n",
    "        lang_map = {'ja': 'Japanese', 'en': 'English', 'zh': 'Traditional Chinese'}\n",
    "        target_lang_name = lang_map.get(target_lang, 'Traditional Chinese')\n",
    "        prompt = f\"\"\"\n",
    "        You are a specialized translation engine for a Japanese Shrine system.\n",
    "        Convert the following JSON string into {target_lang_name}.\n\n",
    "        INPUT JSON:\n",
    "        {omikuji_json_str}\n\n",
    "        RULES:\n",
    "        1. Keep the JSON keys (lucky_color, lucky_item, lucky_subject, advice) EXACTLY as they are.\n",
    "        2. DO NOT return the original Chinese if the target is Japanese.\n",
    "        3. Use natural {target_lang_name} terminology.\n",
    "        4. Tone: Gentle, like a shrine maiden (Miko).\n\n",
    "        Return ONLY the raw JSON string.\n",
    "        \"\"\"\n",
    "        response_text = generate_text_with_fallback(prompt)\n",
    "        import re, json\n",
    "        clean_text = response_text.strip()\n",
    "        if '```' in clean_text:\n",
    "            match = re.search(r'```(?:json)?\\s*(\\{.*?\\})\\s*```', clean_text, re.DOTALL)\n",
    "            if match: clean_text = match.group(1).strip()\n",
    "            else: clean_text = clean_text.replace('```json', '').replace('```', '').strip()\n",
    "        json.loads(clean_text)\n",
    "        return clean_text\n",
    "    except Exception:\n",
    "        return omikuji_json_str\n",
    "\n"
]

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(head + mid + tail)

print("Repair v3 (Slice) complete.")
