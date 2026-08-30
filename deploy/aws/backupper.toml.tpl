app_env = "demo"

[[databases]]
id = "shop"
url = "postgres://backupper:${POSTGRES_PASSWORD}@postgres:5432/shop?sslmode=disable"

[[databases]]
id = "billing"
url = "postgres://backupper:${POSTGRES_PASSWORD}@postgres:5432/billing?sslmode=disable"

[[databases]]
id = "analytics"
url = "postgres://backupper:${POSTGRES_PASSWORD}@postgres:5432/analytics?sslmode=disable"

[s3]
bucket = "${S3_BUCKET}"
prefix = "backups"
region = "${AWS_REGION}"

[schedule]
backup = "0 2 * * *"
retention = "0 3 1 * *"

[backup]
zstd_level = 3

[metrics]
port = 8080
slow_query_ms = 5000

[anonymize]
salt = "backupper"

[scheduler]
max_failures = 5

[notify]
webhook_url = ""

[data]
dir = "/var/lib/backupper"
