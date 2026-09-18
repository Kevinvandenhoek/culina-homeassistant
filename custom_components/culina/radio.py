"""Pick an internet radio station for a cuisine, via Radio Browser.

No account, no key, and it works on any media player that plays a stream URL.
First a stereotypical tag for the cuisine (mariachi for Mexican), then the
best voted music station of the country. A mapping in the options wins over
all of this. Pure Python apart from the `radios` package, so it is testable
without Home Assistant.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from radios import FilterBy, Order, RadioBrowser, Station

_LOGGER = logging.getLogger(__name__)

USER_AGENT = "culina-homeassistant"

# Tag fragments that mean talk or worship rather than music. Matched as
# substrings: Radio Browser has "talk news", "local news", "islamic" and so on.
TALK_TAGS = ("news", "talk", "sport", "relig", "christ", "cristian", "evangel", "gospel", "islam", "quran", "koran", "public radio")
PLAYABLE_CODECS = {"MP3", "AAC", "AAC+"}

# cuisine id -> ISO 3166-1 country code
CUISINE_COUNTRY: dict[str, str] = {
    "afghan": "AF", "american": "US", "argentine": "AR", "austrian": "AT", "bangladeshi": "BD",
    "belgian": "BE", "brazilian": "BR", "british": "GB", "bulgarian": "BG", "burmese": "MM",
    "cambodian": "KH", "chilean": "CL", "chinese": "CN", "colombian": "CO", "cuban": "CU",
    "czech": "CZ", "danish": "DK", "dominican": "DO", "dutch": "NL", "egyptian": "EG",
    "ethiopian": "ET", "filipino": "PH", "finnish": "FI", "french": "FR", "georgian": "GE",
    "german": "DE", "ghanaian": "GH", "greek": "GR", "haitian": "HT", "hawaiian": "US",
    "hungarian": "HU", "icelandic": "IS", "indian": "IN", "indonesian": "ID", "irish": "IE",
    "israeli": "IL", "italian": "IT", "jamaican": "JM", "japanese": "JP", "korean": "KR",
    "laotian": "LA", "lebanese": "LB", "malaysian": "MY", "mexican": "MX", "mongolian": "MN",
    "moroccan": "MA", "nepalese": "NP", "nigerian": "NG", "norwegian": "NO", "pakistani": "PK",
    "persian": "IR", "peruvian": "PE", "polish": "PL", "portuguese": "PT", "puerto_rican": "PR",
    "romanian": "RO", "russian": "RU", "senegalese": "SN", "singaporean": "SG",
    "south_african": "ZA", "spanish": "ES", "sri_lankan": "LK", "swedish": "SE", "swiss": "CH",
    "taiwanese": "TW", "thai": "TH", "trinidadian": "TT", "tunisian": "TN", "turkish": "TR",
    "ukrainian": "UA", "vietnamese": "VN",
}

# cuisine id -> Radio Browser tags, most stereotypical first. Deliberately a
# cliché: this is the joke. Every tag was checked to return at least one
# playable station on 18 September 2026. Cuisines without a usable tag
# (burmese, finnish, georgian, icelandic, laotian, mongolian, vietnamese)
# get the country fallback.
CUISINE_TAGS: dict[str, list[str]] = {
    "afghan": ["persian pop", "iranian music", "persian music"],
    "american": ["classic country", "honky tonk", "bluegrass", "country"],
    "argentine": ["tango", "cuarteto", "chamame"],
    "austrian": ["volksmusik", "oberkrain", "schlager", "apresski"],
    "bangladeshi": ["bangla", "bangladesh", "bengali"],
    "belgian": ["vlaamse muziek", "nederlandstalig", "chansons françaises", "belgium"],
    "brazilian": ["bossa nova", "samba", "sertanejo", "forró"],
    "british": ["british invasion", "britpop", "brit pop"],
    "bulgarian": ["chalga", "pop-folk", "pop folk", "bulgarian"],
    "cambodian": ["khmer", "phnom penh"],
    "chilean": ["cueca", "chile"],
    "chinese": ["chinese pop", "c-pop", "cantonese", "china"],
    "colombian": ["vallenato", "cumbia colombiana", "cumbia"],
    "cuban": ["cuban music", "cuban", "musica cubana", "salsa"],
    "czech": ["czech folk music", "polka", "czech"],
    "danish": ["dansk", "danish", "danske"],
    "dominican": ["bachata", "merengue", "merengue bachata"],
    "dutch": ["piratenhits", "piraten", "piratenmuziek", "hollands"],
    "egyptian": ["egyptian songs", "tarab", "arabic music", "oriental"],
    "ethiopian": ["ethiopia", "amharic", "tigrigna"],
    "filipino": ["opm", "pinoy", "filipino"],
    "french": ["accordéon", "chansons françaises", "french chansons", "chanson française"],
    "german": ["oktoberfest", "volksmusik", "schlager", "volkstümlicher schlager"],
    "ghanaian": ["highlife"],
    "greek": ["greek folk", "laika", "greek traditional", "greek folk music"],
    "haitian": ["konpa", "kompa", "zouk", "haitian music"],
    "hawaiian": ["ukulele", "hawaiian", "hawaiian music", "slack key"],
    "hungarian": ["gypsy", "hungarian folk music", "hungarian music", "hungarian pop music"],
    "indian": ["bollywood", "hindi bollywood", "bollywood hits", "hindi"],
    "indonesian": ["dangdut", "pop dangdut ethnic", "indonesian"],
    "irish": ["irish folk", "irish traditional", "celtic", "irish"],
    "israeli": ["mizrachit", "israeli music", "israeli pop", "hebrew"],
    "italian": ["liscio", "musica italiana", "italian oldies", "classic italian pop"],
    "jamaican": ["reggae", "roots reggae", "dancehall", "ska"],
    "japanese": ["j-pop", "japanese", "japanese music"],
    "korean": ["k-pop", "korean pop", "korean"],
    "lebanese": ["tarab", "lebanon", "arabic music", "arabic"],
    "malaysian": ["dangdut", "malaysia", "malaysian pop"],
    "mexican": ["mariachi", "ranchera", "banda norteña", "grupera"],
    "moroccan": ["chaabi", "radio amazigh", "music marocaine traditionnelle", "moroccan"],
    "nepalese": ["nepali evergreen", "nepal", "nepali"],
    "nigerian": ["highlife", "afrobeats", "afrobeat", "nigeria"],
    "norwegian": ["danseband", "norwegian music only", "norway"],
    "pakistani": ["lollywood", "urdu", "pakistani", "bhangra"],
    "persian": ["persian pop", "persian music", "iranian music", "farsi"],
    "peruvian": ["cumbia peruana", "peruvian cumbia", "música andina"],
    "polish": ["disco polo", "discopolo", "biesiada", "polish highlands"],
    "portuguese": ["fado", "pimba", "musica portuguesa"],
    "puerto_rican": ["salsa", "salsa dura", "reggaeton"],
    "romanian": ["manele", "manele vechi", "romanian folk", "muzică populară"],
    "russian": ["шансон", "shanson", "советская эстрада", "русский шансон"],
    "senegalese": ["senegal", "african music"],
    "singaporean": ["chinese pop", "c-pop"],
    "south_african": ["amapiano", "kwaito", "afrikaans", "south africa"],
    "spanish": ["flamenco", "sevillanas"],
    "sri_lankan": ["sri lanka", "srilanka radio"],
    "swedish": ["dansband", "svensk folkmusik", "swedish"],
    "swiss": ["swiss folk schlager", "volksmusik", "swiss folk music", "schlager"],
    "taiwanese": ["chinese pop", "c-pop"],
    "thai": ["fm 98.5 mhz ลูกทุ่ง ทั้งวัน ทั้งคืน", "ลูกทุ่ง ทั้งวัน ทังคืน", "ลูกทุ่ง เพื่อชีวิต", "thai"],
    "trinidadian": ["calypso", "soca"],
    "tunisian": ["arabic music", "arabic", "chaabi"],
    "turkish": ["arabesk", "türkü", "oyun havaşı", "arabesk fantazi"],
    "ukrainian": ["ukrainian", "ukraine"],
}


@dataclass(frozen=True)
class RadioStation:
    uuid: str
    name: str
    url: str
    country_code: str | None
    tag: str | None  # the tag that found it, None for the country fallback


def _tags(station: Station) -> set[str]:
    raw = station.tags
    if isinstance(raw, str):
        raw = raw.split(",")
    return {tag.strip().lower() for tag in raw or [] if tag}


def _is_talk(station: Station) -> bool:
    return any(fragment in tag for tag in _tags(station) for fragment in TALK_TAGS)


def playable(stations: list[Station], *, skip_talk: bool = False) -> list[Station]:
    """The stations a plain media player can stream, best voted first."""
    result = []
    for station in stations:
        urls = (station.url or "", station.url_resolved or "")
        if not all(url.startswith(("http://", "https://")) for url in urls) or station.hls:
            continue  # mms:// and HLS streams fail on Sonos with UPnP 701; the media source plays `url`
        if station.codec and station.codec.upper() not in PLAYABLE_CODECS:
            continue
        if skip_talk and _is_talk(station):
            continue
        result.append(station)
    # MP3 first: Sonos refused an AAC+ stream over https (UPnP 701) that Radio
    # Browser marked as working. Stable, so votes still decide within a codec.
    result.sort(key=lambda station: (station.codec or "").upper() != "MP3")
    return result


def first_playable(stations: list[Station], *, skip_talk: bool = False) -> Station | None:
    """The best voted station a plain media player can stream."""
    found = playable(stations, skip_talk=skip_talk)
    return found[0] if found else None


def _as_station(station: Station, tag: str | None) -> RadioStation:
    return RadioStation(station.uuid, station.name, station.url_resolved, station.country_code, tag)


async def find_stations(
    cuisine_id: str, *, browser: RadioBrowser | None = None, limit: int = 3
) -> list[RadioStation]:
    """Candidate stations for the cuisine, best first. A stream that Radio
    Browser marks as working can still be refused by a speaker, so the caller
    tries them in order."""
    own = browser is None
    browser = browser or RadioBrowser(user_agent=USER_AGENT)
    found: list[RadioStation] = []
    seen: set[str] = set()

    def add(stations: list[Station], tag: str | None) -> None:
        for station in stations:
            if station.uuid not in seen and len(found) < limit:
                seen.add(station.uuid)
                found.append(_as_station(station, tag))

    try:
        for tag in CUISINE_TAGS.get(cuisine_id, []):
            if len(found) >= limit:
                break
            stations = await browser.stations(
                filter_by=FilterBy.TAG_EXACT,
                filter_term=tag,
                hide_broken=True,
                limit=10,
                order=Order.VOTES,
                reverse=True,
            )
            add(playable(stations, skip_talk=True), tag)
        country = CUISINE_COUNTRY.get(cuisine_id)
        if country is not None and len(found) < limit:
            stations = await browser.stations(
                filter_by=FilterBy.COUNTRY_CODE_EXACT,
                filter_term=country,
                hide_broken=True,
                limit=25,
                order=Order.VOTES,
                reverse=True,
            )
            add(playable(stations, skip_talk=True), None)
        return found
    finally:
        if own:
            await browser.close()


async def find_station(cuisine_id: str, *, browser: RadioBrowser | None = None) -> RadioStation | None:
    """The best candidate, or None when Radio Browser has nothing usable."""
    found = await find_stations(cuisine_id, browser=browser, limit=1)
    return found[0] if found else None


async def register_click(station: RadioStation, *, browser: RadioBrowser | None = None) -> None:
    """Tell Radio Browser the station was played; keeps its popularity honest."""
    own = browser is None
    browser = browser or RadioBrowser(user_agent=USER_AGENT)
    try:
        await browser.station_click(uuid=station.uuid)
    except Exception as err:  # noqa: BLE001 - never let bookkeeping break playback
        _LOGGER.debug("Radio Browser click failed: %s", err)
    finally:
        if own:
            await browser.close()
