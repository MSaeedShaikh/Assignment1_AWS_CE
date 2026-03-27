# Architecture -- UniEvent on AWS

## Overview

UniEvent is deployed across two Availability Zones within a single AWS Region (`eu-north-1`) to eliminate any single point of failure at the infrastructure level. Each AZ hosts one EC2 instance running the Flask application under Gunicorn, so a hardware failure, power event, or AZ-level outage affecting one zone leaves the application fully operational through the instance in the second zone.

All compute resources sit in private subnets with no internet-routable IP addresses. Only the Application Load Balancer is placed in public subnets and exposed to inbound traffic. This public/private separation means that even if an attacker discovers the EC2 instance IDs, they cannot reach the application servers directly -- every request must pass through the ALB and its associated security group rules.

The ALB serves as the sole ingress point for user traffic. It listens on port 80 (HTTP), performs continuous health checks against each EC2 target, and forwards requests only to instances that pass. This single entry point also simplifies future changes: SSL termination, WAF rules, or path-based routing can be added at the ALB without touching the application code or EC2 configuration.

---

## VPC Design

The VPC uses the `10.0.0.0/16` CIDR block, providing 65,536 addresses and ample room for additional subnets if the application scales. The `/16` is divided into four `/24` subnets -- two public and two private -- one of each type per Availability Zone.

| Name | AZ | CIDR | Type | Role |
|---|---|---|---|---|
| UniEvent-Public-1 | eu-north-1a | 10.0.1.0/24 | Public | ALB node, internet-facing |
| UniEvent-Public-2 | eu-north-1b | 10.0.2.0/24 | Public | ALB node, internet-facing |
| UniEvent-Private-1 | eu-north-1a | 10.0.3.0/24 | Private | EC2 instance (AZ1) |
| UniEvent-Private-2 | eu-north-1b | 10.0.4.0/24 | Private | EC2 instance (AZ2) |

Four subnets are required rather than two because the ALB mandate requires at least two public subnets in different AZs for cross-zone load balancing. Placing the EC2 instances in matching private subnets per AZ keeps the traffic path local within each AZ under normal operation, reducing inter-AZ data transfer and latency. Keeping public and private subnets separate enforces the principle that application servers should never be directly internet-reachable, regardless of security group configuration.

---

## Traffic Flow

The following sequence describes the complete path of a single HTTP request from the user's browser to the Flask response and back.

1. **User browser** sends `GET http://<ALB-DNS-name>/` on port 80.
2. **Internet Gateway (IGW)** receives the packet and routes it into the VPC, forwarding it to the ALB listener.
3. **ALB listener** (port 80) evaluates the listener rule, selects a healthy target from `UniEvent-TG` using the round-robin algorithm, and forwards the request to the target's IP on port 5000.
4. **EC2 instance** (private subnet) receives the request on port 5000; Gunicorn hands it to a worker process.
5. **Flask** matches the path to the `index()` route and calls `render_template('index.html', events=EVENTS_CACHE)`.
6. **Jinja2** renders the HTML template, substituting the current in-memory `EVENTS_CACHE` list into the events grid.
7. **Gunicorn** sends the HTTP 200 response back to the ALB.
8. **ALB** forwards the response to the user's browser via the IGW.
9. **Browser** renders the GIKI-branded UniEvent portal with the current event listings.

---

## Event Data Flow

A `BackgroundScheduler` from APScheduler starts when Gunicorn loads the application module. It registers `fetch_events()` as a job with `trigger='interval', minutes=15` and immediately calls the function once on startup so that the cache is populated before the first user request arrives.

`fetch_events()` makes a single HTTP GET to `https://app.ticketmaster.com/discovery/v2/events.json` with parameters `size=20`, `countryCode=US`, and `classificationName=music,sports,arts`. From each event object in the `_embedded.events` array it extracts the following fields:

| Response Field | Cache Key | Notes |
|---|---|---|
| `name` | `name` | Event title |
| `dates.start.localDate` | `date` | ISO 8601 date string |
| `_embedded.venues[0].name` | `venue` | First venue name |
| `_embedded.venues[0].city.name` | `city` | Venue city |
| First image with `ratio == '16_9'` | `image` | URL string or `None` |
| `url` | `url` | Ticketmaster event page |
| `info` | `description` | Free-text info or empty string |

The parsed list is written atomically to the global `EVENTS_CACHE` list. The trade-off of an in-memory cache is that it is local to each EC2 instance -- the two instances maintain independent caches and may briefly show different event counts if their 15-minute refresh cycles are not in sync. For a read-only display application this is acceptable; a production system would share state via ElastiCache or a shared S3 JSON file. The in-memory approach also means the cache is lost on an instance restart, which is mitigated by the immediate `fetch_events()` call at startup.

---

## Fault Tolerance

The ALB target group is configured with the following health check settings against the `/health` endpoint (which returns HTTP 200 with body `OK`):

| Setting | Value |
|---|---|
| Protocol | HTTP |
| Path | `/health` |
| Healthy threshold | 2 consecutive successes |
| Unhealthy threshold | 2 consecutive failures |
| Interval | 30 seconds |
| Timeout | 5 seconds |

When an EC2 instance fails -- whether due to an application crash, OS hang, or AZ outage -- the ALB misses two consecutive health check responses within 60 seconds (2 × 30 s). It then marks the target `unhealthy` and immediately removes it from the active rotation. All subsequent requests are sent exclusively to the remaining healthy instance in the other AZ. The failed instance receives no traffic and no further connection draining is needed because new connections were already being distributed to both targets before the failure. When the failed instance recovers and passes two consecutive health checks, the ALB automatically adds it back into rotation without any manual intervention.

---

## Security Layers

| Layer | Mechanism | Protects Against |
|---|---|---|
| Network perimeter | Internet Gateway + public/private subnet separation | Direct internet access to EC2 instances |
| Inbound traffic control | ALB Security Group (`UniEvent-ALB-SG`) allows port 80 from `0.0.0.0/0` only | Unsolicited traffic on non-HTTP ports reaching the load balancer |
| Application server isolation | EC2 Security Group (`UniEvent-EC2-SG`) allows port 5000 from `UniEvent-ALB-SG` only | Any traffic to EC2 not originating from the ALB, including VPC-internal lateral movement |
| Credential management | IAM instance role with inline least-privilege policy; no access keys on disk | Credential theft, over-privileged S3 access, key rotation risk |
| Secret handling | Ticketmaster API key stored in `.env` file, excluded from git via `.gitignore` | Accidental secret exposure in version control history |
| Data access control | S3 Block Public Access enabled; bucket accessible only via IAM role | Unintended public exposure of static assets |
