# Gunicorn configuration file

# Increase timeout to handle slow ML training tasks during dataset upload
timeout = 120

# Use a specific number of workers or let Render set WEB_CONCURRENCY
# workers = 2
