"""Download the UCI Dropout dataset from available sources."""
import urllib.request
import json
import os

OUTPUT = "uci_dropout.csv"

# Strategy 1: GitHub search for raw CSV files
print("Searching GitHub for the dataset...")
try:
    url = "https://api.github.com/search/code?q=predict+students+dropout+filename:dataset.csv&per_page=5"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    print(f"Found {data['total_count']} results on GitHub")
    for item in data.get("items", [])[:5]:
        repo = item["repository"]["full_name"]
        path = item["path"]
        raw_url = f"https://raw.githubusercontent.com/{repo}/main/{path}"
        print(f"  Trying: {raw_url}")
        try:
            urllib.request.urlretrieve(raw_url, OUTPUT)
            size = os.path.getsize(OUTPUT)
            if size > 50000:  # Dataset should be ~470KB
                with open(OUTPUT, "r") as f:
                    header = f.readline()
                    lines = sum(1 for _ in f) + 1
                print(f"  SUCCESS: {size:,} bytes, {lines} rows")
                print(f"  Header: {header[:120]}...")
                exit(0)
            else:
                # Try master branch
                raw_url2 = f"https://raw.githubusercontent.com/{repo}/master/{path}"
                urllib.request.urlretrieve(raw_url2, OUTPUT)
                size = os.path.getsize(OUTPUT)
                if size > 50000:
                    with open(OUTPUT, "r") as f:
                        header = f.readline()
                        lines = sum(1 for _ in f) + 1
                    print(f"  SUCCESS (master): {size:,} bytes, {lines} rows")
                    print(f"  Header: {header[:120]}...")
                    exit(0)
        except Exception as e:
            print(f"  Failed: {e}")
except Exception as e:
    print(f"GitHub search failed: {e}")

# Strategy 2: Try known HuggingFace datasets
print("\nTrying HuggingFace...")
try:
    hf_url = "https://huggingface.co/api/datasets/mstz/student_dropout"
    resp = urllib.request.urlopen(hf_url)
    print("HuggingFace dataset found, but may need auth")
except Exception as e:
    print(f"HuggingFace: {e}")

# Strategy 3: Direct Kaggle download URL (public datasets)
print("\nTrying alternative Kaggle/direct sources...")
alt_urls = [
    "https://raw.githubusercontent.com/ShubhPathak18/Student-Dropout-Prediction/main/dataset.csv",
    "https://raw.githubusercontent.com/diogo-fernan/data/master/predict-students-dropout-and-academic-success.csv",
]
for url in alt_urls:
    try:
        print(f"  Trying: {url[:80]}...")
        urllib.request.urlretrieve(url, OUTPUT)
        size = os.path.getsize(OUTPUT)
        if size > 50000:
            print(f"  Downloaded: {size:,} bytes")
            exit(0)
    except:
        pass

print("\n" + "=" * 60)
print("AUTOMATIC DOWNLOAD FAILED - UCI site is down today.")
print("=" * 60)
print("""
MANUAL DOWNLOAD - Do one of these:

Option A (Kaggle - FASTEST):
  1. Go to: https://www.kaggle.com/datasets/thedevastator/higher-education-predictors-of-student-retention
  2. Click "Download" (you need a free Kaggle account)
  3. Extract dataset.csv from the zip
  4. Rename to uci_dropout.csv
  5. Place in: C:\\Users\\VERRIL\\Desktop\\FloraMind\\

Option B (Databricks direct upload):
  1. Same Kaggle download
  2. In Databricks: Catalog > workspace > default > Volumes > raw > Upload
  3. Upload the CSV directly to /Volumes/workspace/default/raw/uci_dropout.csv
""")
