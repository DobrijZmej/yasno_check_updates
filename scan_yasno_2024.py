from datetime import datetime
import json
import logging
import os
import time

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CONFIG_FILE = './config.json'
STATES_FILE = './states.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {
        'yasno_url': 'https://api.yasno.com.ua/api/v1/pages/home/schedule-turn-off-electricity',
        'bot_token': '1:A',
        'chat_id': '-1',
        'city': 'kiev',
        'group': '6'
    }
def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)

def load_state_log(state_file=STATES_FILE):
    if os.path.exists(state_file):
        with open(state_file, "r") as f:
            return json.load(f)
    return {}

def save_state_log(state, state_file=STATES_FILE):
    with open(state_file, "w") as f:
        json.dump(state, f, indent=4)


def extract_today(json_data, target_tag):
    if isinstance(json_data, dict):
        for key, value in json_data.items():
            if key == target_tag:
                return value
            result = extract_today(value, target_tag)
            if result is not None:
                return result
    elif isinstance(json_data, list):
        for item in json_data:
            result = extract_today(item, target_tag)
            if result is not None:
                return result
    return None

def load_data(yasno_url, city_name):
    response = requests.get(yasno_url)
    if response.status_code == 200:
        data = response.json()
        data = extract_today(data, "dailySchedule")
        if city_name in data:
            data = data[city_name]
        else:
            data = None
        return data
    else:
        return None

def calculate_sum(day_data):
    total_sum = 0
    for events in day_data["groups"].values():
        for event in events:
            total_sum += event["start"] + event["end"]
    return total_sum

def is_changed(day_data):
    states = load_state_log()
    title = day_data["title"]
    days = calculate_sum(day_data)
    if title not in states:
        states[title] = days
        save_state_log(states)
        return True
    if states[title] != days:
        states[title] = days
        save_state_log(states)
        return True
    return False

def consolidate_periods(items):
    items.sort(key=lambda x: x["start"])
    
    consolidated = []
    current_period = items[0]

    for item in items[1:]:
        if item["start"] <= current_period["end"]:  # Check for continuity
            # Extend the current period
            current_period["end"] = max(current_period["end"], item["end"])
        else:
            # Save the finished period and start a new one
            consolidated.append(current_period)
            current_period = item

    # Add the last period
    consolidated.append(current_period)

    return consolidated

def process_day(day_data, group):
    result = f"Оновлення для {day_data['title']}"
    logger.info(f"start process {result}")
    periods = consolidate_periods(day_data["groups"][group])
    for row in periods:
        result = result + f"\n• {str(row['start']).zfill(2)}:00 - {str(row['end']).zfill(2)}:00"
        logger.info(row)
    logger.info(f"{result}")
    return result

def send_to_telegram(message, config):
    print(message)
    url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
    payload = {
        'chat_id': config['chat_id'],
        'text': message,
        'parse_mode': 'HTML'
    }
    requests.post(url, data=payload)

def process_alarms(day_data, group):
    states = load_state_log()
    current_time = datetime.now()
    current_time_min = current_time.hour * 60 + current_time.minute
    current_time_min = 12 * 60 + current_time.minute
    if current_time_min == 0:
        states["last_send_alarm"] = None
        save_state_log(states)
        return None
    if "last_send_alarm" in states and states["last_send_alarm"] == current_time.hour:
        return None
    result = ""
    periods = consolidate_periods(day_data["groups"][group])
    for row in periods:
        start_half_hour = row['start'] * 60 - 30
        end_half_hour = row['end'] * 60 - 30
        if(start_half_hour < current_time_min):
            result = f"🔴 Висока #ймовірність відключення після {str(row['start']).zfill(2)}:00"
        if(end_half_hour < current_time_min):
            result = f"🟢 Висока #ймовірність заживлення після {str(row['start']).zfill(2)}:00"
        logger.info(row)
    logger.info(f"{result}")
    states["last_send_alarm"] = current_time.hour
    save_state_log(states)
    return result

def process_yasno(config):
    data = load_data(config["yasno_url"], config["city"])
    #logger.info(data)
    for day_name, day_data in data.items():
        logger.info(day_data)
        title = day_data["title"]
        logger.info(f"{title}:"+str(calculate_sum(day_data)))
        if is_changed(day_data):
            message = process_day(day_data, config["group"])
            send_to_telegram(message, config)
        if(day_name == "today"):
            message = process_alarms(day_data, config["group"])
            if message is not None:
                send_to_telegram(message, config)

def main():
    try:
        while True:
            config = load_config()
            process_yasno(config)
            save_config(config)
            time.sleep(10)
    except KeyboardInterrupt:
        logger.info("Вимикаюсь...")

if __name__ == '__main__':
    main()
