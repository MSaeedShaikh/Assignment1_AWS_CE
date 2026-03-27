#!/bin/bash
# UniEvent EC2 Bootstrap Script
# This script installs dependencies and starts the app.
# app.py, index.html, and .env are deployed separately via git pull.
# Ensure .env contains: TICKETMASTER_API_KEY=your_key_here

# ── System updates and dependencies ─────────────────────────────────────────
yum update -y
yum install -y python3 python3-pip git

# ── Python packages ──────────────────────────────────────────────────────────
pip3 install flask boto3 requests apscheduler gunicorn python-dotenv

# ── Pull the repo ─────────────────────────────────────────────────────────────
git clone https://github.com/<your-username>/Assignment1_AWS_CE.git /home/ec2-user/unievent

# ── Create .env with API key (replace value below before pasting) ─────────────
cat > /home/ec2-user/unievent/.env << 'EOF'
TICKETMASTER_API_KEY=REPLACE_WITH_YOUR_KEY
S3_BUCKET=unievent-media-bucket
EOF

# ── Start gunicorn ────────────────────────────────────────────────────────────
cd /home/ec2-user/unievent/app
gunicorn --bind 0.0.0.0:5000 --workers 2 --daemon app:app
