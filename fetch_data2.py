from huggingface_hub import hf_hub_download
import pandas as pd
import os

print("Downloading parquet file directly from HuggingFace...")
path = hf_hub_download(
    repo_id="jason1966/adilshamim8_predict-students-dropout-and-academic-success",
    filename="data/train-00000-of-00001.parquet",
    repo_type="dataset"
)
print(f"Downloaded to: {path}")

df = pd.read_parquet(path)
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)[:10]}")
print(f"Target values: {df.iloc[:, -1].value_counts().to_dict()}")

# Save as semicolon-delimited CSV (original UCI format)
df.to_csv("uci_dropout.csv", sep=";", index=False)
size = os.path.getsize("uci_dropout.csv")
print(f"Saved: uci_dropout.csv ({size:,} bytes, {len(df)} rows)")
