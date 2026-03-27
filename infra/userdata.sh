#!/bin/bash
# UniEvent EC2 Bootstrap Script
# Before pasting into AWS Console User Data:
# Replace REPLACE_WITH_YOUR_KEY with your Ticketmaster Consumer Key

# ── System updates and dependencies ──────────────────────────────────────────
yum update -y
yum install -y python3 python3-pip git nano

# ── Python packages ───────────────────────────────────────────────────────────
pip3 install flask boto3 requests apscheduler gunicorn python-dotenv

# ── Clone the repo ────────────────────────────────────────────────────────────
git clone https://github.com/MSaeedShaikh/Assignment1_AWS_CE.git /home/ec2-user/unievent

# ── Write .env with API key ───────────────────────────────────────────────────
cat > /home/ec2-user/unievent/.env << 'EOF'
TICKETMASTER_API_KEY=REPLACE_WITH_YOUR_KEY
S3_BUCKET=unievent-media-bucket
EOF

# ── Start gunicorn ────────────────────────────────────────────────────────────
cd /home/ec2-user/unievent/app
gunicorn --bind 0.0.0.0:5000 --workers 2 --daemon app:app