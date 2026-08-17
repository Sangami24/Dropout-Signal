import subprocess
with open('app_original.py', 'wb') as f:
    f.write(subprocess.check_output(['git', 'show', 'HEAD:app.py']))
