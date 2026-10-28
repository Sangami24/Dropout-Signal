import subprocess

# Get the version of app.py from 2 commits ago (before my broken edits)
original_bytes = subprocess.check_output(
    ['git', 'show', 'HEAD~2:app.py'],
    cwd=r'c:\Users\achal\Documents\Projects\Dropout Signal'
)

original = original_bytes.decode('utf-8', errors='replace')
lines = original.splitlines(True)

# Find where app.run( is
run_line_idx = None
for i, line in enumerate(lines):
    if '    app.run(host="0.0.0.0"' in line or "    app.run(host='0.0.0.0'" in line:
        run_line_idx = i
        break

# Look for the block that starts app.run() call and ensure it's under if __name__
# Check what's 5 lines before it
if run_line_idx:
    block_start = None
    for i in range(run_line_idx, max(0, run_line_idx-20), -1):
        if lines[i].startswith('if __name__'):
            block_start = i
            break
    
    if block_start:
        print(f"Already has if __name__ at line {block_start+1}")
        # Already has it, just overwrite app.py with the clean original
        with open(r'c:\Users\achal\Documents\Projects\Dropout Signal\app.py', 'w', encoding='utf-8') as f:
            f.write(original)
        print("Restored clean original app.py")
    else:
        print("No if __name__ found - need to add it")
        # Find the startup print block
        for i, line in enumerate(lines):
            if line.strip().startswith('print()') and i > len(lines) - 60:
                block_start = i
                break
        print(f"Startup print block at line {block_start+1}")
        # Insert if __name__ guard before that block  
        lines.insert(block_start, 'if __name__ == "__main__":\n')
        # Indent all following lines until end
        for j in range(block_start+1, len(lines)):
            lines[j] = '    ' + lines[j]
        with open(r'c:\Users\achal\Documents\Projects\Dropout Signal\app.py', 'w', encoding='utf-8') as f:
            f.writelines(lines)
        print("Added if __name__ guard and saved app.py")
else:
    print("ERROR: Could not find app.run() line")
    # Just restore clean original
    with open(r'c:\Users\achal\Documents\Projects\Dropout Signal\app.py', 'w', encoding='utf-8') as f:
        f.write(original)
    print("Restored clean original app.py without modification")
