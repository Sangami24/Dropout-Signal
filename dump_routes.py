import os
with open("all_routes.txt", "w", encoding="utf-8") as out:
    for f in os.listdir("."):
        if f.endswith(".py"):
            try:
                lines = open(f, encoding="utf-8").readlines()
                for i, l in enumerate(lines):
                    if ".route(" in l:
                        out.write(f"{f}:{i+1}:{l.strip()}\n")
            except Exception as e:
                pass
