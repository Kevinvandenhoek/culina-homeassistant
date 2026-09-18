"""Constants for the Culina integration."""

DOMAIN = "culina"
BASE_URL = "https://bites.culina.cloud"

CONF_TOKEN = "token"
CONF_MEDIA_PLAYER = "media_player"
CONF_TTS_ENTITY = "tts_entity"
CONF_ANNOUNCEMENTS = "announcements"
CONF_MUSIC = "music"

# "Step is almost done" fires this many seconds before the end of a step,
# and only for steps longer than ENDING_SOON_MIN_DURATION, otherwise it
# would sound right at the start of the step.
ENDING_SOON_SECONDS = 60
ENDING_SOON_MIN_DURATION = 120

EVENT_STEP_ENDING_SOON = "culina_step_ending_soon"
EVENT_STEP_DONE = "culina_step_done"
EVENT_ALL_DONE = "culina_all_done"

STATE_IDLE = "idle"
STATE_COOKING = "cooking"
STATE_PAUSED = "paused"
