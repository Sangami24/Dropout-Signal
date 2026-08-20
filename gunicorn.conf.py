# Gunicorn configuration file

# Increase timeout to handle slow ML training tasks during dataset upload
# Render free tier CPU is very slow — XGBoost + SHAP can take 2-4 minutes
timeout = 300

# Single worker to stay within Render free tier's 512MB RAM limit
workers = 1

# Bind to the port Render expects
import os
bind = f"0.0.0.0:{os.environ.get('PORT', '10000')}"
