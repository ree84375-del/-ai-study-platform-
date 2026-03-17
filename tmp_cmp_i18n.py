from app.utils.i18n import TRANSLATIONS

zh_keys = set(TRANSLATIONS.get('zh', {}).keys())
ja_keys = set(TRANSLATIONS.get('ja', {}).keys())

print(f"Total ZH keys: {len(zh_keys)}")
print(f"Total JA keys: {len(ja_keys)}")

missing_in_ja = zh_keys - ja_keys
print(f"Keys in ZH but missing in JA: {len(missing_in_ja)}")
if missing_in_ja:
    print(f"First 10 missing in JA: {list(missing_in_ja)[:10]}")

only_in_ja = ja_keys - zh_keys
print(f"Keys only in JA: {len(only_in_ja)}")
if only_in_ja:
    print(f"First 10 only in JA: {list(only_in_ja)[:10]}")
