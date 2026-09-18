# Culina for Home Assistant

Your kitchen speaker follows the recipe you are cooking in [Culina](https://culina.cloud).
Start cooking mode in the app and the speaker plays music for the cuisine of the recipe and tells
you when a step is almost done, when it is done and what comes next.

Everyone in your Culina household triggers it. The announcements come from Culina in the language
of the person who created the token, so they match what the cook sees in the app.

## Install

1. Add this repository to [HACS](https://hacs.xyz) as a custom repository of type Integration,
   then install **Culina** and restart Home Assistant.
2. In Culina, open your profile page, section **Integrations**, and click **Create token**. The
   token starts with `chb_` and is shown once.
3. In Home Assistant go to **Settings, Devices & services, Add integration**, pick **Culina**,
   paste the token and choose the speaker.

That is all you need for the cooking session sensor. Announcements and music are set up in the
integration's options.

## Options

Open the integration and click **Configure**.

- **Announcements and music**: choose a text-to-speech engine for the announcements, and switch
  announcements and music on or off. Without a text-to-speech engine nothing is announced. Any
  engine works; Google Translate is built into Home Assistant and speaks every language Culina
  supports. The announcement is played as an announcement, so speakers that support it, like
  Sonos, play it over the music and resume afterwards.
- **Choose your own music for a cuisine**: pick a cuisine and what to play, from anything your
  speaker can play: a favorite, a playlist, a radio station or a file. It repeats until cooking
  stops and replaces the automatic radio station for that cuisine.
- **Save** writes the options and reconnects.

Music works without any setup. For every cuisine the integration picks an internet radio station
from [Radio Browser](https://www.radio-browser.info): first a deliberately stereotypical one,
mariachi for Mexican, fado for Portuguese, schlager for German, and when no such station exists,
the best voted music station of the country. It is meant as a joke, not as a playlist. If you
want something else for a cuisine, choose your own music in the options.

## What it does

- **Start**: music for the cuisine starts on the speaker.
- **While cooking**: one minute before a step ends, "step is almost done" (only for steps longer
  than two minutes). When a step ends, "step is done" or "step is done, next up ..." when another
  step starts at that moment. When the last step ends, "all done". Culina schedules steps in
  parallel, so a hands-off step like simmering can run next to the step you are working on.
- **Pause**: announcements stop, the music keeps playing.
- **Stop**: announcements stop and the music stops.
- **Restart**: after a Home Assistant restart, a running session is picked up again.

## For your own automations

`sensor.culina_cooking_session` is `idle`, `cooking` or `paused`, with attributes `recipe`,
`cuisine`, `active_steps`, `elapsed_seconds`, `remaining_seconds` and `ends_at`.

Events, each with `recipe`, `step`, `next_step`, `count` and the announcement `text`:

- `culina_step_ending_soon`
- `culina_step_done`
- `culina_all_done`

Switch announcements and music off in the options if you only want the sensor and the events.

## Notes

- One cooking session is followed per household. If two run at once, the most recently updated
  one wins.
- Culina keeps sessions in memory. After a Culina deploy the session is gone and the speaker goes
  quiet; start cooking mode again in the app.
- Revoking the token on culina.cloud stops everything; Home Assistant then asks for a new one.
