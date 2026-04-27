import os
import threading
import time
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv
from pyairtable import Api
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

# --- Event config ---
EVENT_NAME = "Lock In Call"
EVENT_JOIN_INFO = "[Join the call in #horizons!](https://hackclub.enterprise.slack.com/archives/C0AGKQ6K476)"
EVENT_TAGLINE = "Lock in!!!!"
EVENT_DESCRIPTION = "Come hang out and lock in!"
# --------------------

app = App(token=os.environ["SLACK_BOT_TOKEN"])

airtable = Api(os.environ["AIRTABLE_API_KEY"]).table(
    os.environ["AIRTABLE_BASE_ID"],
    os.environ["AIRTABLE_TABLE_NAME"],
)


def reminder_loop():
    while True:
        try:
            now = datetime.now(pytz.utc)
            for record in airtable.all():
                fields = record["fields"]
                if fields.get("Reminder Sent"):
                    continue
                tz = pytz.timezone(fields["Timezone"])
                start_dt = tz.localize(
                    datetime.strptime(
                        f"{fields['Start Date']} {fields['Start Time']}",
                        "%Y-%m-%d %H:%M",
                    )
                )
                reminder_dt = start_dt - timedelta(minutes=15)
                if (
                    timedelta(0)
                    <= (now - reminder_dt.astimezone(pytz.utc))
                    < timedelta(minutes=2)
                ):
                    app.client.chat_postMessage(
                        channel=fields["Slack ID"],
                        text=f"Reminder: your lock-in call starts in 15 minutes at {start_dt.strftime('%H:%M %Z')}!",
                    )
                    airtable.update(record["id"], {"Reminder Sent": True})
        except Exception as e:
            print(f"Reminder loop error: {e}")
        time.sleep(60)


threading.Thread(target=reminder_loop, daemon=True).start()


@app.command("/lockin")
def handle_lockin(ack, body, client):
    ack()
    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "lockin_modal",
            "title": {"type": "plain_text", "text": "Lock In"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "timezone_block",
                    "label": {"type": "plain_text", "text": "Your timezone"},
                    "element": {
                        "type": "external_select",
                        "action_id": "timezone",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "e.g. America/New_York",
                        },
                        "min_query_length": 0,
                    },
                },
                {
                    "type": "input",
                    "block_id": "start_date_block",
                    "label": {"type": "plain_text", "text": "Lock-in start date"},
                    "element": {
                        "type": "datepicker",
                        "action_id": "start_date",
                        "placeholder": {"type": "plain_text", "text": "Select a date"},
                    },
                },
                {
                    "type": "input",
                    "block_id": "start_time_block",
                    "label": {"type": "plain_text", "text": "Start time"},
                    "element": {
                        "type": "static_select",
                        "action_id": "start_time",
                        "placeholder": {"type": "plain_text", "text": "Select a time"},
                        "options": [
                            {
                                "text": {
                                    "type": "plain_text",
                                    "text": f"{h % 12 or 12}:{m:02d} {'AM' if h < 12 else 'PM'}",
                                },
                                "value": f"{h:02d}:{m:02d}",
                            }
                            for h in range(24)
                            for m in (0, 30)
                        ],
                    },
                },
                {
                    "type": "input",
                    "block_id": "hours_block",
                    "label": {
                        "type": "plain_text",
                        "text": "How many hours can you stay? (1–24)",
                    },
                    "element": {
                        "type": "number_input",
                        "action_id": "hours",
                        "is_decimal_allowed": False,
                        "min_value": "1",
                        "max_value": "24",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter a number between 1 and 24",
                        },
                    },
                },
                {
                    "type": "input",
                    "block_id": "notes_block",
                    "optional": True,
                    "label": {"type": "plain_text", "text": "Additional notes"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "notes",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Anything else you'd like to add...",
                        },
                    },
                },
            ],
        },
    )


@app.options("timezone")
def handle_timezone_options(ack, payload):
    query = payload.get("value", "").lower()
    # Common timezones — expand as needed
    all_zones = [
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Anchorage",
        "Pacific/Honolulu",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "Europe/Moscow",
        "Asia/Kolkata",
        "Asia/Shanghai",
        "Asia/Tokyo",
        "Asia/Singapore",
        "Australia/Sydney",
        "Pacific/Auckland",
    ]
    matches = [z for z in all_zones if query in z.lower()] if query else all_zones
    ack(
        options=[
            {"text": {"type": "plain_text", "text": z}, "value": z}
            for z in matches[:20]
        ]
    )


@app.view("lockin_modal")
def handle_lockin_submission(ack, body, view, client):
    values = view["state"]["values"]
    user_id = body["user"]["id"]

    timezone = values["timezone_block"]["timezone"]["selected_option"]["value"]
    start_date = values["start_date_block"]["start_date"]["selected_date"]
    start_time = values["start_time_block"]["start_time"]["selected_option"]["value"]
    hours = values["hours_block"]["hours"]["value"]
    notes = values.get("notes_block", {}).get("notes", {}).get("value") or ""

    try:
        airtable.create(
            {
                "Slack ID": user_id,
                "Timezone": timezone,
                "Start Date": start_date,
                "Start Time": start_time,
                "Hours": int(hours),
                "Notes": notes,
            }
        )
    except Exception as e:
        print(f"Airtable error: {e}")
        ack(
            response_action="errors",
            errors={"start_date_block": "Failed to save, please try again."},
        )
        return

    ack()
    print(
        f"New lock-in: user={user_id}, tz={timezone}, start={start_date} {start_time}, hours={hours}"
    )

    notes_line = f"\n*Notes:* {notes}" if notes else ""

    client.chat_postMessage(
        channel=user_id,
        text=(
            f"Thanks for signing up!\n"
            f"*Start:* {start_date} {start_time}  |  *Duration:* {hours} hours  |  *Timezone:* {timezone}"
            f"{notes_line}\n\n"
            f"you will get a reminder 15 minutes before the call, "
            f"If you have any issues, or something came up/you are no longer available to run the call, "
            f"please send <@{os.environ['ADMIN_SLACK_ID']}> a message on slack or send an email to violet@hackclub.com"
        ),
    )

    tz = pytz.timezone(timezone)
    start_dt = tz.localize(
        datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
    )
    end_dt = start_dt + timedelta(hours=int(hours))

    yaml_block = (
        f"```## {EVENT_NAME}\n"
        f"yaml\n"
        f"Start: {start_dt.isoformat()}\n"
        f"End: {end_dt.isoformat()}\n"
        f'JoinInfo: "{EVENT_JOIN_INFO}"\n'
        f'Tagline: "{EVENT_TAGLINE}"\n'
        f"\n"
        f"{EVENT_DESCRIPTION}```"
    )

    client.chat_postMessage(
        channel=os.environ["ADMIN_SLACK_ID"],
        text=(
            f"New lock-in from <@{user_id}>!\n"
            f"*Start:* {start_date} {start_time}  |  *Duration:* {hours} hours  |  *Timezone:* {timezone}"
            f"{notes_line}\n\n"
            f"{yaml_block}"
        ),
    )


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("Bot is running...")
    handler.start()
