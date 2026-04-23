import os

from dotenv import load_dotenv
from pyairtable import Api
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

load_dotenv()

app = App(token=os.environ["SLACK_BOT_TOKEN"])

airtable = Api(os.environ["AIRTABLE_API_KEY"]).table(
    os.environ["AIRTABLE_BASE_ID"],
    os.environ["AIRTABLE_TABLE_NAME"],
)


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
                        "type": "timepicker",
                        "action_id": "start_time",
                        "placeholder": {"type": "plain_text", "text": "Select a time"},
                    },
                },
                {
                    "type": "input",
                    "block_id": "end_date_block",
                    "label": {"type": "plain_text", "text": "Lock-in end date"},
                    "element": {
                        "type": "datepicker",
                        "action_id": "end_date",
                        "placeholder": {"type": "plain_text", "text": "Select a date"},
                    },
                },
                {
                    "type": "input",
                    "block_id": "end_time_block",
                    "label": {"type": "plain_text", "text": "End time"},
                    "element": {
                        "type": "timepicker",
                        "action_id": "end_time",
                        "placeholder": {"type": "plain_text", "text": "Select a time"},
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
    start_time = values["start_time_block"]["start_time"]["selected_time"]
    end_date = values["end_date_block"]["end_date"]["selected_date"]
    end_time = values["end_time_block"]["end_time"]["selected_time"]

    if (end_date, end_time) <= (start_date, start_time):
        ack(
            response_action="errors",
            errors={
                "end_date_block": "End must be after start",
                "end_time_block": "End must be after start",
            },
        )
        return

    try:
        airtable.create({
            "Slack ID": user_id,
            "Timezone": timezone,
            "Start Date": start_date,
            "Start Time": start_time,
            "End Date": end_date,
            "End Time": end_time,
        })
    except Exception as e:
        print(f"Airtable error: {e}")
        ack(response_action="errors", errors={"start_date_block": "Failed to save, please try again."})
        return

    ack()
    print(
        f"New lock-in: user={user_id}, tz={timezone}, start={start_date} {start_time}, end={end_date} {end_time}"
    )

    client.chat_postMessage(
        channel=user_id,
        text=(
            f"Thanks for signing up!\n"
            f"*Start:* {start_date} {start_time}  |  *End:* {end_date} {end_time}  |  *Timezone:* {timezone}"
        ),
    )

    client.chat_postMessage(
        channel=os.environ["ADMIN_SLACK_ID"],
        text=(
            f"New lock-in from <@{user_id}>!\n"
            f"*Start:* {start_date} {start_time}  |  *End:* {end_date} {end_time}  |  *Timezone:* {timezone}"
        ),
    )


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("Bot is running...")
    handler.start()
