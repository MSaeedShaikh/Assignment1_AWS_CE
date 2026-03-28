# IAM Design -- UniEvent

## Principle of Least Privilege

The principle of least privilege states that any identity -- human or machine -- should be granted only the minimum set of permissions required to perform its intended function, and nothing more. In a cloud environment this matters because over-permissioned roles amplify the blast radius of a compromise: if an attacker gains access to an EC2 instance with broad IAM permissions they can read all S3 buckets, spin up new resources, or exfiltrate data far beyond the scope of the original vulnerability. By scoping permissions tightly to a single bucket and three specific actions, the IAM design for UniEvent ensures that even full instance compromise cannot be leveraged to reach other AWS resources.

---

## Role: UniEvent-EC2-Role

**Trusted entity:** AWS service -- EC2

The role is attached to both EC2 instances as an instance profile. When the Flask application calls the AWS SDK (`boto3`), the SDK automatically retrieves short-lived credentials from the EC2 Instance Metadata Service (IMDS) at `http://169.254.169.254/latest/meta-data/iam/security-credentials/`. No credentials are written to disk, environment variables, or application code.

A role is used in place of IAM user access keys for the following reasons:

- **No credential storage** -- there are no long-lived access key IDs or secret keys to store, rotate, or accidentally commit to version control; the instance receives temporary credentials automatically.
- **Automatic rotation** -- the temporary credentials issued via the instance profile are rotated by AWS every few hours with no action required; a leaked credential expires on its own within minutes to hours.
- **Instance metadata injection** -- the AWS SDK discovers and refreshes credentials transparently via the IMDS endpoint, meaning the application code contains zero authentication logic and no secrets appear in `app.py`, `.env`, or `userdata.sh`.

---

## Policy: UniEvent-S3-Policy

The inline policy attached to `UniEvent-EC2-Role` grants access to the `unievent-media-bucket-706257133013-eu-north-1-an` S3 bucket only.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UniEventS3Access",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::unievent-media-bucket-706257133013-eu-north-1-an",
        "arn:aws:s3:::unievent-media-bucket-706257133013-eu-north-1-an/*"
      ]
    }
  ]
}
```

| Action | What It Allows | Why Needed |
|---|---|---|
| `s3:GetObject` | Download individual objects from the bucket | Retrieve the GIKI logo and any stored media assets for serving |
| `s3:PutObject` | Upload individual objects to the bucket | Store new media assets or cached data if the application writes to S3 |
| `s3:ListBucket` | List the keys (filenames) within the bucket | Required by the SDK before performing `GetObject` on a path; also needed for directory-style listings |

**Resource ARN scoping** uses two entries deliberately. `arn:aws:s3:::unievent-media-bucket-706257133013-eu-north-1-an` (without a trailing path) is required for bucket-level actions such as `s3:ListBucket`. `arn:aws:s3:::unievent-media-bucket-706257133013-eu-north-1-an/*` (with the `/*` wildcard) is required for object-level actions such as `s3:GetObject` and `s3:PutObject`. Using both ensures the policy covers exactly what is needed without broadening to `arn:aws:s3:::*`, which would grant the same permissions across every bucket in the account.

---

## Risks Prevented

- **Credential theft via source code** -- because no access keys exist, an attacker who reads `app.py`, `userdata.sh`, or any environment file finds no usable AWS credentials to exfiltrate.
- **Lateral movement to other buckets** -- the `Resource` ARN is scoped to `unievent-media-bucket-706257133013-eu-north-1-an` only; even with full control of the EC2 instance an attacker cannot read, write, or delete objects in any other S3 bucket in the account.
- **Privilege escalation via S3** -- omitting IAM actions (`iam:*`), EC2 actions, and other service permissions means a compromised instance cannot be used to create new users, attach policies, or provision additional infrastructure.
- **Persistent access after instance termination** -- temporary credentials tied to the instance profile are invalidated when the instance is stopped or terminated; there are no long-lived keys that remain valid after the compute resource is gone.
