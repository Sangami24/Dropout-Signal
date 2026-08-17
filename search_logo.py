import re
with open('app.py', 'r', encoding='utf-8') as f:
    text = f.read()

idx1 = text.find('<div class="login-icon">')
if idx1 != -1: print('LOGIN:', text[idx1:idx1+200])

idx2 = text.find('<div class="sb-icon"')
if idx2 != -1: print('ADMIN:', text[idx2:idx2+400])

idx3 = text.find('<div class="sb-icon"', idx2 + 100)
if idx3 != -1: print('COUNSELOR:', text[idx3:idx3+400])
