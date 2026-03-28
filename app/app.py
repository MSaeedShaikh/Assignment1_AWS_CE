from flask import Flask, render_template, jsonify, request
import boto3
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import os
import json
import datetime
from dotenv import load_dotenv

load_dotenv()


TICKETMASTER_API_KEY = os.getenv('TICKETMASTER_API_KEY')
S3_BUCKET = os.getenv('S3_BUCKET', 'unievent-media-bucket')
EVENTS_CACHE = []

app = Flask(__name__)


def fetch_events():
    global EVENTS_CACHE
    try:
        response = requests.get(
            'https://app.ticketmaster.com/discovery/v2/events.json',
            params={
                'apikey': TICKETMASTER_API_KEY,
                'size': 20,
                'countryCode': 'SE',
                'classificationName': 'music,sports,arts',
            }
        )
        response.raise_for_status()
        data = response.json()
        events_raw = data.get('_embedded', {}).get('events', [])

        events = []
        for event in events_raw:
            images = event.get('images', [])
            image = next((img['url'] for img in images if img.get('ratio') == '16_9'), None)
            events.append({
                'name': event.get('name'),
                'date': event.get('dates', {}).get('start', {}).get('localDate'),
                'venue': event.get('_embedded', {}).get('venues', [{}])[0].get('name'),
                'city': event.get('_embedded', {}).get('venues', [{}])[0].get('city', {}).get('name'),
                'image': image,
                'url': event.get('url'),
                'description': event.get('info', ''),
                'classification': event.get('classifications', [{}])[0].get('segment', {}).get('name', ''),
            })

        EVENTS_CACHE = events
        print(f"[{datetime.datetime.now()}] Fetched {len(EVENTS_CACHE)} events successfully.")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Error fetching events: {e}")


scheduler = BackgroundScheduler()
scheduler.add_job(fetch_events, trigger='interval', minutes=15)
scheduler.start()


@app.route('/')
def index():
    category = request.args.get('category', '').strip()
    if category and category.lower() != 'all':
        filtered = [
            e for e in EVENTS_CACHE
            if category.lower() in (e.get('name') or '').lower()
            or category.lower() in (e.get('classification') or '').lower()
        ]
    else:
        filtered = EVENTS_CACHE
        category = 'All'
    return render_template('index.html', events=filtered, active_category=category)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


@app.route('/api/events')
def api_events():
    return jsonify(EVENTS_CACHE)


@app.route('/health')
def health():
    return 'OK', 200


if __name__ == '__main__':
    fetch_events()
    app.run(host='0.0.0.0', port=5000, debug=False)
