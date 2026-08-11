import os
import traceback

try:
    from datasets import load_dataset
    print("Loading dataset from HuggingFace...")
    ds = load_dataset("mstz/student_dropout", "default")
    print(ds)

    df = ds["train"].to_pandas()
    print(f"Shape: {df.shape}")
    print(f"Columns: {list(df.columns)[:10]}")

    # Save as semicolon-delimited CSV (matching UCI original format)
    df.to_csv("uci_dropout.csv", sep=";", index=False)
    size = os.path.getsize("uci_dropout.csv")
    print(f"Saved: uci_dropout.csv ({size:,} bytes, {len(df)} rows, {len(df.columns)} cols)")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
