from lxml import etree
import requests
from datetime import datetime, timedelta, time
import pytz
import unicodedata

# Konfiguracja strefy czasowej
tz = pytz.timezone('Europe/Warsaw')

def remove_control_characters(s: str) -> str:
    """Usuwa znaki kontrolne z ciągu znaków."""
    if not s:
        return s
    return "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")

def get_valid_lang(lang_str: str) -> str:
    """Zwraca poprawny 2-literowy kod języka. Jeśli API zwróci 'asian', zamieni to na 'pl'."""
    if not lang_str:
        return "pl"
    code = lang_str[:2].lower()
    valid_codes = {'pl', 'en', 'de', 'fr', 'es', 'it', 'pt', 'ru', 'uk', 'cs', 'sk'}
    return code if code in valid_codes else "pl"

def get_days() -> list:
    """Zwraca listę dat: dzisiaj (zaokrąglona do godziny), jutro, pojutrze, za 3 dni."""
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    day_1 = datetime.combine(datetime.now(), time(0, 0)) + timedelta(days=1)
    day_2 = datetime.combine(datetime.now(), time(0, 0)) + timedelta(days=2)
    day_3 = datetime.combine(datetime.now(), time(0, 0)) + timedelta(days=3)
    return [now, day_1, day_2, day_3]

def build_xmltv(channels: list, programmes: list) -> bytes:
    """Buduje drzewo XML w formacie XMLTV."""
    dt_format = '%Y%m%d%H%M%S %z'
    data = etree.Element("tv")
    data.set("generator-info-name", "rakuten-epg")
    data.set("generator-info-url", "https://github.com/dp247/")
    
    for ch in channels:
        channel = etree.SubElement(data, "channel")
        channel.set("id", str(ch.get("id")))
        
        lang = get_valid_lang(ch.get("language"))
        name = etree.SubElement(channel, "display-name")
        name.set("lang", lang)
        name.text = ch.get("name")
        
        if ch.get("icon") is not None:
            icon_src = etree.SubElement(channel, "icon")
            icon_src.set("src", ch.get("icon"))
            icon_src.text = ''

    for pr in programmes:
        programme = etree.SubElement(data, 'programme')
        start_time = datetime.fromtimestamp(pr.get('starts_at'), tz).strftime(dt_format).strip()
        end_time = datetime.fromtimestamp(pr.get('ends_at'), tz).strftime(dt_format).strip()
        
        programme.set("channel", str(pr.get('channel_id')))
        programme.set("start", start_time)
        programme.set("stop", end_time)
        
        title = etree.SubElement(programme, "title")
        title.set('lang', 'pl')
        title.text = pr.get("title")
        
        if pr.get("subtitle") is not None:
            subtitle = etree.SubElement(programme, "sub-title")
            subtitle.set('lang', 'pl')
            subtitle.text = remove_control_characters(pr.get("subtitle"))
            
        if pr.get('description') is not None:
            description = etree.SubElement(programme, "desc")
            description.set('lang', 'pl')
            description.text = remove_control_characters(pr.get("description"))
            
        if pr.get('tags') and len(pr.get('tags')) > 0:
            for tag in pr.get('tags'):
                tag_name = tag.get("name")
                # Filtrowanie niechcianych kategorii
                if tag_name and tag_name.lower() not in ["asian", "azja", "asia"]:
                    category = etree.SubElement(programme, "category")
                    category.set('lang', 'pl')
                    category.text = tag_name

    return etree.tostring(data, pretty_print=True, encoding='utf-8')

# --- Główna logika pobierania ---
days = get_days()
url = "https://gizmo.rakuten.tv/v3/live_channels"

base_params = {
    "classification_id": "277",
    "device_identifier": "web",
    "device_stream_audio_quality": "2.0",
    "device_stream_hdr_type": "NONE",
    "device_stream_video_quality": "FHD",
    "epg_duration_minutes": "360",
    "epg_ends_at": days[-1].strftime('%Y-%m-%dT%H:%M:%S.000Z'),
    "epg_ends_at_timestamp": int(days[-1].timestamp()),
    "epg_starts_at": days[0].strftime('%Y-%m-%dT%H:%M:%S.000Z'),
    "epg_starts_at_timestamp": int(days[0].timestamp()),
    "locale": "en",
    "market_code": "pl",
    "per_page": "50"
}

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://rakuten.tv",
    "Referer": "https://rakuten.tv/"
}

print("Pobieranie danych...")
all_channels_data = []
page = 1

try:
    while True:
        params = base_params.copy()
        params["page"] = str(page)
        
        res = requests.get(url, params=params, headers=headers, timeout=30)
        if res.status_code != 200:
            print(f"Błąd serwera ({res.status_code}): {res.text}")
            raise ConnectionError(f"HTTP {res.status_code}: nie udało się pobrać danych!")
        
        page_data = res.json().get('data', [])
        if not page_data:
            break
            
        all_channels_data.extend(page_data)
        print(f"Strona {page}: {len(page_data)} kanałów")
        page += 1
        
except requests.exceptions.RequestException as e:
    print(f"Błąd połączenia: {e}")
    exit(1)

print(f"\nŁącznie pobrano {len(all_channels_data)} kanałów.")

channels_data = []
programme_data = []

for channel in all_channels_data:
    ch_name = channel.get('title', 'Unknown Channel')
    print(f"Przetwarzanie: {ch_name}")
    
    ch_number = channel.get('channel_number')
    ch_id = channel.get('id')
    
    images = channel.get('images') or {}
    ch_icon = images.get('artwork_negative') or images.get('artwork')
    
    labels = channel.get('labels') or {}
    languages = labels.get('languages') or []
    ch_language = languages[0].get('id') if languages else "pl"
    ch_tags = labels.get('tags')
    
    channels_data.append({
        "name": ch_name,
        "epg_number": ch_number,
        "id": ch_id,
        "icon": ch_icon,
        "language": ch_language,
        "tags": ch_tags
    })
    
    programmes_list = channel.get('live_programs', [])
    for item in programmes_list:
        try:
            start = datetime.strptime(item['starts_at'], '%Y-%m-%dT%H:%M:%S.000%z').timestamp()
            end = datetime.strptime(item['ends_at'], '%Y-%m-%dT%H:%M:%S.000%z').timestamp()
        except (ValueError, KeyError) as e:
            print(f"  Pomijam program z błędną datą: {e}")
            continue
            
        programme_data.append({
            "title": item.get('title', 'Brak tytułu'),
            "subtitle": item.get('subtitle'),
            "description": item.get('description'),
            "starts_at": start,
            "ends_at": end,
            "channel_id": ch_id,
            "language": ch_language,
            "tags": ch_tags,
        })

print("\nGenerowanie pliku XML...")
channel_xml = build_xmltv(channels_data, programme_data)

with open('epg.xml', 'wb') as f:
    f.write(channel_xml)

print("Sukces! Plik epg.xml został zapisany.")
