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

- **Text-to-speech engine**: the voice for the announcements. Without one nothing is announced.
  Any engine works; Google Translate is built into Home Assistant and speaks every language Culina
  supports. The announcement is played as an announcement, so speakers that support it, like
  Sonos, play it over the music and resume afterwards.
- **Announce the steps** and **Play music**: on or off.
- **Announcement volume** and **Music volume**: optional. The music volume is set on the speaker
  when the music starts, so cooking always sounds the same. The announcement volume only works on
  speakers that play announcements at their own level, like Sonos; elsewhere the speaker's volume
  is used.

The same settings are also entities on the Culina device, for dashboards and automations: the
switches **Announcements** and **Music**, and the sliders **Announcement volume** and **Music
volume**. Home Assistant names them `switch.culina_announcements` and so on, with the area in
front when the device is in one.

## The music

The music is the same for every household and there is nothing to set up. For every cuisine the
integration picks an internet radio station from [Radio Browser](https://www.radio-browser.info),
deliberately the cliché: mariachi for Mexican, fado for Portuguese, oktoberfest for German, pirate
hits for Dutch, arabesk for Turkish, liscio for Italian. It is meant as a joke, not as a playlist.
The tags per cuisine live in
[`custom_components/culina/radio.py`](custom_components/culina/radio.py); every tag was checked
to return a working station, and cuisines without a usable tag get the best voted music station
of the country. Each time cooking starts one of the stations for the cuisine is picked at random, so
German is oktoberfest one night and schlager the next. Which stations a tag holds depends on the
votes on Radio Browser, so it changes over time.

The stations play through Home Assistant's own **Radio Browser** integration, which the Culina
integration adds for you when it is missing. Sonos only accepts the streams that way.

## What it does

- **Start**: the radio station for the cuisine starts on the speaker.
- **Start**: the speaker reads the step you are on, with its instructions.
- **While cooking**: one minute before a step ends, "one minute left". When a step ends and the
  next one starts, "done with ..., now ..." followed by the instructions of the new step. A step
  that starts while another one keeps running is read on its own, so you never have to look at the
  screen. When the last step ends, "all done". Culina schedules steps in parallel, so a hands-off
  step like simmering can run next to the step you are working on.
- **Pause**: announcements stop, the music keeps playing.
- **Stop**: announcements stop and the music stops.
- **Restart**: after a Home Assistant restart, a running session is picked up again.

## For your own automations

`sensor.culina_cooking_session` is `idle`, `cooking` or `paused`, with attributes `recipe`,
`cuisine`, `active_steps`, `active_step_descriptions`, `elapsed_seconds`, `remaining_seconds`
and `ends_at`.

Events, each with `recipe`, `kind`, `step`, `next_step`, `description`, `count` and the spoken
`text`:

- `culina_step_started`
- `culina_step_ending_soon`
- `culina_step_done` (kind `step_done` or `step_done_next`)
- `culina_all_done`

Switch announcements and music off in the options if you only want the sensor and the events.

## Notes

- One cooking session is followed per household. If two run at once, the most recently updated
  one wins.
- Culina keeps sessions in memory. After a Culina deploy the session is gone and the speaker goes
  quiet; start cooking mode again in the app.
- Revoking the token on culina.cloud stops everything; Home Assistant then asks for a new one.
