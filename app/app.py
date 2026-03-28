from flask import Flask, render_template, jsonify, request
import boto3
import requests
from apscheduler.schedulers.background import BackgroundScheduler
import os
import json
import datetime
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

TICKETMASTER_API_KEY = os.getenv('TICKETMASTER_API_KEY')
S3_BUCKET = os.getenv('S3_BUCKET', 'unievent-media-bucket-706257133013-eu-north-1-an')
EVENTS_CACHE = []

app = Flask(__name__)
s3_client = boto3.client('s3', region_name='eu-north-1')



def upload_image_to_s3(image_url, event_id):
    key = f"events/{event_id}.jpg"
    try:
        s3_client.head_object(Bucket=S3_BUCKET, Key=key)
    except ClientError as e:
        code = e.response['Error']['Code']
        if code not in ('404', 'NoSuchKey'):
            print(f"[{datetime.datetime.now()}] S3 head_object error ({code}) for {event_id}: {e}")
            return None
        try:
            img_response = requests.get(image_url, timeout=10)
            img_response.raise_for_status()
            s3_client.put_object(
                Bucket=S3_BUCKET,
                Key=key,
                Body=img_response.content,
                ContentType='image/jpeg',
            )
        except Exception as e:
            print(f"[{datetime.datetime.now()}] S3 upload failed for {event_id}: {e}")
            return None
    try:
        return s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': key},
            ExpiresIn=604800,
        )
    except Exception as e:
        print(f"[{datetime.datetime.now()}] S3 presign failed for {event_id}: {e}")
        return None


def fetch_events():
    global EVENTS_CACHE
    try:
        response = requests.get(
            'https://app.ticketmaster.com/discovery/v2/events.json',
            params={
                'apikey': TICKETMASTER_API_KEY,
                'size': 50,
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
            raw_image = next((img['url'] for img in images if img.get('ratio') == '16_9'), None)
            event_id = event.get('id', '')
            image = upload_image_to_s3(raw_image, event_id) if raw_image and event_id else None
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

        current_keys = {f"events/{event.get('id')}.jpg" for event in events_raw if event.get('id')}
        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=S3_BUCKET, Prefix='events/'):
                for obj in page.get('Contents', []):
                    if obj['Key'] not in current_keys:
                        s3_client.delete_object(Bucket=S3_BUCKET, Key=obj['Key'])
                        print(f"[{datetime.datetime.now()}] Deleted stale image: {obj['Key']}")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] S3 cleanup error: {e}")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] Error fetching events: {e}")


scheduler = BackgroundScheduler()
scheduler.add_job(fetch_events, trigger='interval', minutes=15)
scheduler.start()
fetch_events()


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
