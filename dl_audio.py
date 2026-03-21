import urllib.request
import os

os.makedirs('app/static/audio', exist_ok=True)
tracks = {
    'lofi.ogg': 'https://upload.wikimedia.org/wikipedia/commons/d/df/Debussy_-_Clair_de_Lune.ogg',
    'rain.ogg': 'https://upload.wikimedia.org/wikipedia/commons/e/e0/Chopin_Prelude_No_15_in_D_Flat_Major.ogg', 
    'cafe.ogg': 'https://upload.wikimedia.org/wikipedia/commons/c/cb/Gymnopedie_No_1.ogg',
    'forest.ogg': 'https://upload.wikimedia.org/wikipedia/commons/b/b5/Bird_songs_in_a_forest.ogg'
}

for name, url in tracks.items():
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req) as response, open(f'app/static/audio/{name}', 'wb') as out_file:
            data = response.read()
            out_file.write(data)
            print(f"Downloaded {name} ({len(data)} bytes)")
    except Exception as e:
        print(f"Failed {name}: {e}")
