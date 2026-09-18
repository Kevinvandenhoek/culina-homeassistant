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

# Tags that mean talk rather than music, skipped in the country fallback.
TALK_TAGS = {"news", "talk", "news talk", "sport", "sports", "religion", "religious", "christian", "gospel", "public radio"}
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
# cliché: this is the joke. Cuisines without tags get the country fallback.
CUISINE_TAGS: dict[str, list[str]] = {
    "mexican": ["mariachi", "ranchera"],
    "italian": ["canzone italiana", "italian oldies", "italian music"],
    "french": ["chanson française", "french chanson", "variété française", "french oldies"],
    "spanish": ["flamenco", "rumba"],
    "portuguese": ["fado"],
    "greek": ["greek folk", "laika", "greek music"],
    "turkish": ["turkish folk", "turkish pop"],
    "german": ["schlager", "volksmusik"],
    "austrian": ["volksmusik", "schlager"],
    "swiss": ["volksmusik", "schlager"],
    "dutch": ["nederlandstalig", "hollandse hits", "dutch"],
    "belgian": ["nederlandstalig", "chanson"],
    "irish": ["irish folk", "celtic", "irish"],
    "british": ["britpop", "british"],
    "american": ["country", "classic country"],
    "hawaiian": ["hawaiian"],
    "cuban": ["salsa", "son cubano", "cuban"],
    "puerto_rican": ["salsa", "reggaeton"],
    "dominican": ["bachata", "merengue"],
    "jamaican": ["reggae", "dancehall"],
    "trinidadian": ["soca", "calypso"],
    "haitian": ["kompa", "haitian"],
    "brazilian": ["bossa nova", "samba", "mpb"],
    "argentine": ["tango"],
    "colombian": ["vallenato", "cumbia"],
    "peruvian": ["andean", "peruvian"],
    "chilean": ["chilean", "cueca"],
    "japanese": ["enka", "j-pop"],
    "korean": ["trot", "k-pop"],
    "chinese": ["chinese traditional", "c-pop", "mandopop"],
    "taiwanese": ["mandopop", "taiwanese"],
    "thai": ["luk thung", "thai"],
    "vietnamese": ["nhac vang", "vietnamese"],
    "filipino": ["opm", "filipino"],
    "indonesian": ["dangdut", "indonesian"],
    "malaysian": ["malay", "malaysia"],
    "singaporean": ["mandopop", "singapore"],
    "cambodian": ["khmer"],
    "laotian": ["lao"],
    "burmese": ["myanmar", "burmese"],
    "mongolian": ["mongolian"],
    "indian": ["bollywood", "hindi"],
    "pakistani": ["qawwali", "pakistani"],
    "bangladeshi": ["bangla", "bengali"],
    "sri_lankan": ["sinhala", "sri lanka"],
    "nepalese": ["nepali"],
    "afghan": ["afghan", "dari", "pashto"],
    "persian": ["persian pop", "iranian music", "persian"],
    "israeli": ["mizrahi", "israeli", "hebrew"],
    "lebanese": ["arabic oldies", "lebanese", "arabic"],
    "egyptian": ["egyptian", "arabic oldies", "arabic"],
    "moroccan": ["chaabi", "moroccan", "arabic"],
    "tunisian": ["tunisian", "arabic"],
    "georgian": ["georgian"],
    "russian": ["russian folk", "russian chanson", "russian"],
    "ukrainian": ["ukrainian folk", "ukrainian"],
    "polish": ["disco polo", "polish"],
    "czech": ["czech folk", "czech"],
    "hungarian": ["hungarian folk", "mulatós", "hungarian"],
    "romanian": ["manele", "romanian folk", "romanian"],
    "bulgarian": ["chalga", "bulgarian folk", "bulgarian"],
    "swedish": ["dansband", "swedish"],
    "danish": ["dansktop", "danish"],
    "norwegian": ["norwegian"],
    "finnish": ["humppa", "iskelmä", "finnish"],
    "icelandic": ["icelandic"],
    "ethiopian": ["ethiopian"],
    "nigerian": ["afrobeats", "nigerian"],
    "ghanaian": ["highlife", "ghanaian"],
    "senegalese": ["mbalax", "senegalese"],
    "south_african": ["amapiano", "south african"],
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


def playable(stations: list[Station], *, skip_talk: bool = False) -> list[Station]:
    """The stations a plain media player can stream, best voted first."""
    result = []
    for station in stations:
        url = station.url_resolved or ""
        if not url.startswith(("http://", "https://")) or station.hls:
            continue  # mms:// and HLS streams fail on Sonos with UPnP 701
        if station.codec and station.codec.upper() not in PLAYABLE_CODECS:
            continue
        if skip_talk and _tags(station) & TALK_TAGS:
            continue
        result.append(station)
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
