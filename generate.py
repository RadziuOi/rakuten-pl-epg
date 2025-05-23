from lxml import etree
import requests
from datetime import datetime, timedelta, time, timezone
import pytz
import unicodedata

tz = pytz.timezone('Europe/Warsaw')


# From https://stackoverflow.com/questions/4324790/removing-control-characters-from-a-string-in-python
def remove_control_characters(s):
    return "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")


def get_days() -> list:
    now = datetime.now().replace(hour=(datetime.now()).hour, minute=0, second=0, microsecond=0)
    day_1 = (datetime.combine(datetime.now(), time(0, 0)) + timedelta(1))
    day_2 = (datetime.combine(datetime.now(), time(0, 0)) + timedelta(2))
    day_3 = (datetime.combine(datetime.now(), time(0, 0)) + timedelta(3))
    return [now, day_1, day_2, day_3]


def build_xmltv(channels: list, programmes: list) -> bytes:
    """
Make the channels and programmes into something readable by XMLTV
    :param channels: The list of channels to be generated
    :param programmes: The list of programmes to be generated
    :return: A sequence of bytes for XML
    """
    # Timezones since UK has daylight savings
    dt_format = '%Y%m%d%H%M%S %z'

    data = etree.Element("tv")
    data.set("generator-info-name", "rakuten-epg")
    data.set("generator-info-url", "https://github.com/dp247/")
    for ch in channels:
        channel = etree.SubElement(data, "channel")
        channel.set("id", str(ch.get("id")))
        name = etree.SubElement(channel, "display-name")
        name.set("lang", ch.get("language")[:-1].lower())
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

        if pr.get('tags') is not None:
            if len(pr.get('tags')) > 0:
                category = etree.SubElement(programme, "category")
                category.set('lang', 'pl')
                for tag in pr.get('tags'):
                    category.text = tag.get("name")

    return etree.tostring(data, pretty_print=True, encoding='utf-8')


days = get_days()

url_string = (f"classification_id=277&device_identifier=web"
              f"&device_stream_audio_quality=2.0&device_stream_hdr_type=NONE&device_stream_video_quality=FHD"
              f"&epg_duration_minutes=360"
              f"&epg_ends_at={days[-1].strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
              f"&epg_ends_at_timestamp={days[-1].timestamp()}"
              f"&epg_starts_at={days[0].strftime('%Y-%m-%dT%H:%M:%S.000Z')}"
              f"&epg_starts_at_timestamp={days[0].timestamp()}"
              f"&locale=en&market_code=pl"
              f"&per_page=250")

url = "https://gizmo.rakuten.tv/v3/live_channels?" + url_string.replace(":", "%3A")
print("Grabbing data")
res = requests.get(url)
if res.status_code != 200:
    raise ConnectionError(f"HTTP{res.status_code}: could not get info from server!")
print("Loading JSON")
json = res.json()['data']
print(f"\nRetrieved {len(json)} channels:")

channels_data = []
programme_data = []

for channel in json:
    ch_name = channel['title']
    print(ch_name)
    ch_number = channel['channel_number']
    ch_id = channel['id']
    if channel['images'] is not None:
        images = channel['images']
        if images.get('artwork_negative') is not None:
            ch_icon = images.get('artwork_negative')
        elif images.get('artwork') is not None:
            ch_icon = images.get('artwork')
        else:
            ch_icon = None
    if channel['labels'] is not None:
        labels = channel['labels']
        if labels.get('languages') is not None:
            ch_language = labels.get('languages')[0].get('id')
        else:
            ch_language = None
        if labels.get('tags') is not None:
            ch_tags = labels.get('tags')
        else:
            ch_tags = None
    if channel['classification'] is not None:
        ch_age_rating = channel['classification'].get('age')
    else:
        ch_age_rating = None
    channels_data.append({
        "name":       ch_name,
        "epg_number": ch_number,
        "id":         ch_id,
        "icon":       ch_icon,
        "language":   ch_language,
        "tags":       ch_tags
    })
    programmes_list = channel['live_programs']
    for item in programmes_list:
        title = item['title']
        subtitle = item['subtitle']
        description = item['description']
        start = datetime.strptime(item['starts_at'], '%Y-%m-%dT%H:%M:%S.000%z').timestamp()
        end = datetime.strptime(item['ends_at'], '%Y-%m-%dT%H:%M:%S.000%z').timestamp()

        programme_data.append({
            "title":       title,
            "subtitle":    subtitle,
            "description": description,
            "starts_at":   start,
            "ends_at":     end,
            "channel_id":  ch_id,
            "language":    ch_language,
            "tags":        ch_tags,
        })

channel_xml = build_xmltv(channels_data, programme_data)

# Write some XML
with open('epg.xml', 'wb') as f:
    f.write(channel_xml)
    f.close()
