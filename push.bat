@echo off
git init
git add .
git commit -m "Initialize project and fix dashboard issues"
git branch -M main
git remote add origin https://github.com/Sangami24/Dropout-Signal.git
git push -u origin main
pause
