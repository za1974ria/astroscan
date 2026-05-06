#!/usr/bin/env python3
"""Multi-telescope feeder — NASA APOD + Hubble MAST + ESA"""
import os, time, requests, random, json, urllib.request, urllib.error
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('/root/astro_scan/.env')
NASA_KEY      = os.getenv('NASA_API_KEY', 'DEMO_KEY')
GEMINI_KEY    = os.getenv('GEMINI_API_KEY', '')
ANTHROPIC_KEY = os.getenv('ANTHROPIC_API_KEY', '')
TELESCOPE_DIR = Path('/root/astro_scan/telescope_live')
TELESCOPE_DIR.mkdir(exist_ok=True)
META_PATH     = TELESCOPE_DIR / 'apod_meta.json'


def _call_claude_fr(prompt):
    """Appelle Claude (claude-3-haiku) et retourne une réponse en français.
    Retourne (texte, None) ou (None, message_erreur)."""
    key = ANTHROPIC_KEY or os.getenv('ANTHROPIC_API_KEY', '').strip()
    if not key:
        return None, 'ANTHROPIC_API_KEY non configurée'
    body = {
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 1024,
        'messages': [{'role': 'user', 'content': (
            "Tu es AEGIS, assistant astronomique expert. "
            "Réponds UNIQUEMENT en français, de façon claire et naturelle.\n\n"
            + prompt
        )}],
    }
    try:
        r = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            },
            json=body, timeout=45
        )
        data = r.json()
        if r.status_code != 200:
            err = data.get('error', {})
            return None, (err.get('message') or str(err))[:300]
        text = data['content'][0]['text'].strip()
        return text, None
    except Exception as e:
        return None, str(e)


def _gemini_translate_fr(text):
    """Traduit un texte EN→FR via Gemini 2.0 Flash avec rotation de clés.
    Retourne le texte original si toutes les clés sont épuisées (429)."""
    if not text:
        return text
    # Collecter toutes les clés disponibles
    keys = [v for v in [
        os.getenv('GEMINI_API_KEY', ''),
        os.getenv('GEMINI_API_KEY_BACKUP', ''),
        os.getenv('GEMINI_API_KEY_3', ''),
    ] if v.strip()]
    if not keys:
        print('[TRANSLATE] Aucune clé Gemini disponible')
        return text
    prompt = (
        "Traduis ce texte astronomique en français fluide et naturel. "
        "Réponds UNIQUEMENT avec la traduction, sans guillemets ni commentaires.\n\n"
        + text[:1800]
    )
    payload = json.dumps({'contents': [{'parts': [{'text': prompt}]}]}).encode()
    for key in keys:
        try:
            req = urllib.request.Request(
                f'https://generativelanguage.googleapis.com/v1beta/models/'
                f'gemini-2.0-flash:generateContent?key={key}',
                data=payload, headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                result = json.loads(r.read())
            translated = result['candidates'][0]['content']['parts'][0]['text'].strip()
            if translated:
                return translated
        except urllib.error.HTTPError as e:
            print(f'[TRANSLATE] Clé …{key[-6:]} HTTP {e.code} — essai clé suivante')
            if e.code != 429:
                break  # Erreur non-quota → pas la peine d'essayer d'autres clés
        except Exception as e:
            print(f'[TRANSLATE] {e}')
            break
    # Fallback Groq (llama-3.3-70b) si toutes les clés Gemini sont épuisées
    groq_key = os.getenv('GROQ_API_KEY', '').strip()
    if groq_key:
        try:
            import subprocess
            payload_groq = json.dumps({
                'model': 'llama-3.3-70b-versatile',
                'messages': [
                    {'role': 'system', 'content': 'Tu es un traducteur expert. Traduis le texte suivant en français astronomique fluide et naturel. Réponds UNIQUEMENT avec la traduction.'},
                    {'role': 'user', 'content': text[:1800]}
                ],
                'max_tokens': 1024, 'temperature': 0.3
            })
            proc = subprocess.run(
                ['curl', '-s', '--max-time', '20',
                 '-H', f'Authorization: Bearer {groq_key}',
                 '-H', 'Content-Type: application/json',
                 '-d', payload_groq,
                 'https://api.groq.com/openai/v1/chat/completions'],
                capture_output=True, text=True, timeout=25
            )
            result = json.loads(proc.stdout)
            translated = result['choices'][0]['message']['content'].strip()
            if translated:
                print(f'[TRANSLATE] Groq fallback OK — {len(translated)} car.')
                return translated
        except Exception as e:
            print(f'[TRANSLATE] Groq fallback: {e}')
    print('[TRANSLATE] Toutes les clés épuisées — texte original conservé')
    return text

# Images ESA Hubble directes (URLs publiques stables)
ESA_HUBBLE_IMAGES = [
    ("Pilliers de la Création — Eagle Nebula", "https://esahubble.org/media/archives/images/screen/heic1501a.jpg"),
    ("Galaxie du Tourbillon M51", "https://esahubble.org/media/archives/images/screen/heic0506a.jpg"),
    ("Nébuleuse de la Carène", "https://esahubble.org/media/archives/images/screen/heic0707a.jpg"),
    ("Galaxie d'Andromède M31", "https://esahubble.org/media/archives/images/screen/heic1502a.jpg"),
    ("Nébuleuse de l'Œil de Chat", "https://esahubble.org/media/archives/images/screen/heic0403a.jpg"),
    ("Amas de galaxies Abell 2744", "https://esahubble.org/media/archives/images/screen/heic1401a.jpg"),
    ("Nébuleuse de la Rosette", "https://esahubble.org/media/archives/images/screen/heic0006a.jpg"),
    ("Jupiter — Grande Tache Rouge", "https://esahubble.org/media/archives/images/screen/heic1920a.jpg"),
]

def save_image(data, title, source):
    (TELESCOPE_DIR / 'current_live.jpg').write_bytes(data)
    (TELESCOPE_DIR / 'current_title.txt').write_text(f"{title}\nSource: {source}")
    print(f'[OK] {source} — {title} — {len(data)//1024} KB')

def fetch_apod():
    try:
        r = requests.get(f'https://api.nasa.gov/planetary/apod?api_key={NASA_KEY}', timeout=15)
        d = r.json()
        if d.get('media_type') == 'image':
            img = requests.get(d.get('hdurl') or d.get('url'), timeout=30)
            if img.status_code == 200:
                title_en = d.get('title', 'APOD')
                expl_en  = d.get('explanation', '')
                date     = d.get('date', '')
                # Vérifier si la traduction du jour est déjà en cache
                today = time.strftime('%Y-%m-%d', time.gmtime())
                already_translated = False
                if META_PATH.exists():
                    try:
                        cached = json.loads(META_PATH.read_text())
                        if cached.get('date') == date and cached.get('translated'):
                            # Cache valide — utiliser la traduction existante
                            title_fr = cached['title']
                            expl_fr  = cached['explanation']
                            already_translated = True
                            print(f'[TRANSLATE] Cache valide pour {date} — traduction réutilisée')
                    except Exception:
                        pass
                # Récupérer l'analyse Claude existante si le cache est valide
                analyse_claude_cached = ''
                if already_translated:
                    try:
                        analyse_claude_cached = json.loads(META_PATH.read_text()).get('analyse_claude', '')
                    except Exception:
                        pass

                if not already_translated:
                    # Traduction Gemini EN→FR (avec fallback Groq)
                    print(f'[TRANSLATE] Traduction Gemini en cours pour APOD {date}…')
                    title_fr = _gemini_translate_fr(title_en)
                    expl_fr  = _gemini_translate_fr(expl_en) if expl_en else ''

                # Analyse scientifique Claude (si pas déjà en cache)
                analyse_claude = analyse_claude_cached
                if not analyse_claude and ANTHROPIC_KEY:
                    print(f'[CLAUDE] Génération analyse scientifique APOD {date}…')
                    prompt_analyse = (
                        f"Image astronomique NASA APOD du {date}.\n"
                        f"Titre : {title_en}\n"
                        f"Description originale : {expl_en[:800]}\n\n"
                        "Rédige en 3 à 4 phrases une analyse scientifique approfondie de cette image : "
                        "type d'objet céleste, phénomènes physiques visibles, intérêt astronomique, "
                        "contexte dans l'univers observable. Style expert, en français."
                    )
                    analyse_claude, err_claude = _call_claude_fr(prompt_analyse)
                    if err_claude:
                        print(f'[CLAUDE] Erreur analyse : {err_claude}')
                        analyse_claude = ''
                    else:
                        print(f'[CLAUDE] Analyse générée — {len(analyse_claude)} car.')

                save_image(img.content, title_fr or title_en, 'NASA APOD')
                # Sauvegarder les métadonnées traduites pour /api/telescope/live
                meta = {
                    'date':                  date,
                    'title':                 title_fr or title_en,
                    'title_original':        title_en,
                    'explanation':           expl_fr or expl_en,
                    'explanation_original':  expl_en,
                    'url':                   d.get('hdurl') or d.get('url', ''),
                    'source':                'NASA APOD',
                    'translated':            bool(title_fr and title_fr != title_en),
                    'analyse_claude':        analyse_claude or '',
                    'fetched_at':            time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                }
                META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
                print(f'[META] Métadonnées APOD sauvegardées → {META_PATH}')
                return True
    except Exception as e:
        print(f'[ERR APOD] {e}')
    return False

def fetch_apod_archive():
    try:
        year = random.randint(2015, 2024)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        date = f'{year}-{month:02d}-{day:02d}'
        r = requests.get(f'https://api.nasa.gov/planetary/apod?api_key={NASA_KEY}&date={date}', timeout=15)
        d = r.json()
        if d.get('media_type') == 'image':
            img = requests.get(d.get('hdurl') or d.get('url'), timeout=30)
            if img.status_code == 200:
                save_image(img.content, d.get('title','APOD Archive'), f'NASA APOD {date}')
                return True
    except Exception as e:
        print(f'[ERR APOD ARCHIVE] {e}')
    return False

def fetch_esa_hubble():
    title, url = random.choice(ESA_HUBBLE_IMAGES)
    try:
        img = requests.get(url, timeout=30, headers={'User-Agent': 'AstroScan/1.0'})
        if img.status_code == 200 and len(img.content) > 10000:
            save_image(img.content, title, 'ESA Hubble')
            return True
    except Exception as e:
        print(f'[ERR ESA] {e}')
    return False

SOURCES = [fetch_apod, fetch_apod_archive, fetch_esa_hubble, fetch_esa_hubble]

if __name__ == '__main__':
    print('[FEEDER] Multi-Telescope Feeder démarré — NASA + ESA Hubble')
    cycle = 0
    while True:
        source = SOURCES[cycle % len(SOURCES)]
        print(f'[FEEDER] Cycle {cycle} — source: {source.__name__}')
        if not source():
            fetch_apod()  # fallback
        cycle += 1
        print(f'[FEEDER] Prochain dans 90s...')
        time.sleep(90)
