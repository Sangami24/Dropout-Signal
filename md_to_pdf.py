"""Convert Round2_Prep_Guide.md to Round2_Prep_Guide.pdf with Unicode support."""
import re
from fpdf import FPDF

MD_PATH = r"c:\Users\VERRIL\Desktop\FloraMind\Round2_Prep_Guide.md"
PDF_PATH = r"c:\Users\VERRIL\Desktop\FloraMind\Round2_Prep_Guide.pdf"

def asciify(text):
    reps = {
        "\u2192": "->", "\u2190": "<-", "\u27a1": "->", "\ufe0f": "",
        "\u2b50": "[*]", "\u2714": "OK", "\u2022": "-", "\u2013": "-",
        "\u2014": "--", "\u2018": "'", "\u2019": "'", "\u201c": '"',
        "\u201d": '"', "\u2026": "...", "\u2265": ">=", "\u2264": "<=",
        "\u00d7": "x", "\u2248": "~", "\u2212": "-", "\u2713": "OK",
        "\u25b8": ">", "\u25cf": "*", "\u25cb": "o",
        "\U0001f534": "[!]",  # red circle
    }
    for k, v in reps.items():
        text = text.replace(k, v)
    out = []
    for ch in text:
        try:
            ch.encode("latin-1")
            out.append(ch)
        except UnicodeEncodeError:
            pass
    return "".join(out)

def clean(text):
    text = text.replace("**", "").replace("*", "").replace("`", "")
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    return asciify(text.strip())

class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 6, "The Dropout Signal -- Round 2 Prep Guide | HackBricks 2026", align="C")
            self.ln(8)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

CR = (200, 30, 30)
CD = (50, 50, 50)
CB = (40, 80, 180)
CG = (30, 120, 50)
CA = (160, 110, 10)

def build():
    lines = open(MD_PATH, "r", encoding="utf-8").read().split("\n")
    pdf = PDF()
    pdf.alias_nb_pages()

    # Cover
    pdf.add_page()
    pdf.ln(55)
    pdf.set_font("Helvetica", "B", 30); pdf.set_text_color(*CR)
    pdf.cell(0, 14, "THE DROPOUT SIGNAL", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 16); pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 10, "Round 2 Cell-by-Cell Presentation Guide", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 12); pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, "HackBricks 2026  |  46 cells across 3 notebooks", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_draw_color(*CR); pdf.set_line_width(0.8)
    pdf.line(60, pdf.get_y(), pdf.w - 60, pdf.get_y()); pdf.ln(6)
    pdf.set_font("Helvetica", "", 11); pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 7, asciify("Demo Flow:  dropout_pipeline.ipynb  ->  dropout_ml.ipynb  ->  dropout_layer2.ipynb  ->  Voice Server Live"), align="C")
    pdf.ln(16)
    pdf.set_font("Helvetica", "", 10); pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 7, "April 11, 2026", align="C", new_x="LMARGIN", new_y="NEXT")

    in_table = False
    table_rows = []
    skip_h1 = True

    def pgchk(n=25):
        if pdf.get_y() > pdf.h - n: pdf.add_page()

    def flush_tbl():
        nonlocal table_rows, in_table
        if len(table_rows) < 3:
            in_table = False; table_rows = []; return
        hdrs = [clean(c) for c in table_rows[0].strip("|").split("|")]
        rows = [[clean(c) for c in r.strip("|").split("|")] for r in table_rows[2:]]
        nc = len(hdrs)
        if nc == 0: in_table = False; table_rows = []; return
        aw = pdf.w - 20
        ws = [aw * 0.42, aw * 0.58] if nc == 2 else [aw * 0.38, aw * 0.24, aw * 0.38] if nc == 3 else [aw / nc] * nc
        pgchk(30)
        pdf.set_font("Helvetica", "B", 8); pdf.set_fill_color(235, 235, 235); pdf.set_text_color(*CD)
        for j, h in enumerate(hdrs[:nc]):
            pdf.cell(ws[j] if j < len(ws) else ws[-1], 7, h[:60], border=1, fill=True)
        pdf.ln()
        for dr in rows:
            pgchk(14)
            x0, y0 = pdf.get_x(), pdf.get_y()
            my = y0
            for j, c in enumerate(dr[:nc]):
                w = ws[j] if j < len(ws) else ws[-1]
                pdf.set_xy(x0 + sum(ws[:j]), y0)
                pdf.set_font("Helvetica", "B" if j == 0 else "", 8); pdf.set_text_color(*CD)
                pdf.multi_cell(w, 5, c[:120], border=1)
                if pdf.get_y() > my: my = pdf.get_y()
            pdf.set_y(my)
        pdf.ln(4)
        table_rows = []; in_table = False

    def callout(label, lc, bg, bc, tc, txt):
        pgchk(25)
        x, w = 14, pdf.w - 28
        pdf.set_font("Helvetica", "B", 7); pdf.set_text_color(*lc)
        pdf.set_xy(x, pdf.get_y()); pdf.cell(0, 5, label); pdf.ln(5)
        y = pdf.get_y()
        pdf.set_font("Helvetica", "", 9)
        lw = w - 8
        nl = max(1, int(pdf.get_string_width(txt) / lw) + 2)
        h = max(12, nl * 5 + 6)
        if y + h > pdf.h - 20: pdf.add_page(); y = pdf.get_y()
        pdf.set_fill_color(*bg); pdf.rect(x, y, w, h, style="F")
        pdf.set_draw_color(*bc); pdf.set_line_width(0.8); pdf.line(x, y, x, y + h)
        pdf.set_text_color(*tc); pdf.set_xy(x + 4, y + 3); pdf.multi_cell(lw, 5, txt)
        rh = max(h, pdf.get_y() - y + 2)
        if rh > h:
            pdf.set_draw_color(*bc); pdf.set_line_width(0.8); pdf.line(x, y, x, y + rh)
        pdf.set_y(y + max(h, rh) + 3)

    i = 0
    while i < len(lines):
        s = lines[i].strip()

        # Table
        if "|" in s and s.startswith("|") and s.endswith("|"):
            if not in_table: in_table = True; table_rows = []
            table_rows.append(s); i += 1; continue
        elif in_table:
            flush_tbl()

        if not s: i += 1; continue

        # HR
        if re.match(r'^-{3,}$', s):
            pdf.set_draw_color(200, 200, 200); pdf.set_line_width(0.3)
            pdf.line(10, pdf.get_y() + 2, pdf.w - 10, pdf.get_y() + 2); pdf.ln(6)
            i += 1; continue

        # H1
        if s.startswith("# ") and not s.startswith("## "):
            t = clean(s[2:])
            if skip_h1: skip_h1 = False; i += 1; continue
            pdf.add_page(); pdf.ln(3)
            pdf.set_font("Helvetica", "B", 20); pdf.set_text_color(*CR)
            pdf.multi_cell(0, 10, t); pdf.ln(2); i += 1; continue

        # H2
        if s.startswith("## "):
            t = clean(s[3:]); pgchk(30); pdf.ln(3)
            y = pdf.get_y()
            pdf.set_draw_color(*CR); pdf.set_line_width(0.6); pdf.line(10, y + 1, 14, y + 1)
            pdf.set_font("Helvetica", "B", 14); pdf.set_text_color(*CR)
            pdf.set_x(17); pdf.multi_cell(0, 8, t); pdf.ln(2); i += 1; continue

        # H3
        if s.startswith("### "):
            t = clean(s[4:]); pgchk(28); pdf.ln(3)
            star = any(m in lines[i] for m in ["\u2b50", "\U0001f534"])
            trans = "TRANSITION" in t.upper()
            if star:
                pdf.set_fill_color(255, 238, 238)
                pdf.set_font("Helvetica", "B", 10); pdf.set_text_color(180, 20, 20)
                y = pdf.get_y()
                tw = pdf.get_string_width(t) + 8
                h = 8 if tw < pdf.w - 24 else 14
                pdf.rect(10, y, pdf.w - 20, h, style="F")
                pdf.set_draw_color(200, 40, 40); pdf.set_line_width(0.6)
                pdf.line(10, y, 10, y + h)
                pdf.set_xy(14, y + 1); pdf.multi_cell(pdf.w - 28, 6, t)
                pdf.set_y(y + h + 2)
            elif trans:
                pdf.set_font("Helvetica", "BI", 10); pdf.set_text_color(*CB)
                pdf.multi_cell(0, 7, t)
            else:
                pdf.set_font("Helvetica", "B", 10); pdf.set_text_color(*CD)
                pdf.multi_cell(0, 7, t)
            pdf.ln(1); i += 1; continue

        # Blockquote
        if s.startswith("> "):
            bql = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                bql.append(lines[i].strip()[2:].strip()); i += 1
            bt = clean(" ".join(bql))
            if "SAY THIS" in bt.upper():
                t = re.sub(r'^.*?SAY THIS:?\s*', '', bt, flags=re.I).strip('" ')
                callout("SAY THIS", CA, (255, 250, 235), (200, 160, 30), (100, 70, 0), t)
            elif "SCORING POINT" in bt.upper():
                t = re.sub(r'^.*?SCORING POINT[:\s-]*', '', bt, flags=re.I).strip()
                callout("SCORING POINT", CR, (255, 240, 240), (200, 50, 50), (140, 30, 30), t)
            elif "EXPECTED OUTPUT" in bt.upper():
                t = re.sub(r'^.*?EXPECTED OUTPUT:?\s*', '', bt, flags=re.I).strip()
                callout("EXPECTED OUTPUT", CG, (240, 255, 240), (40, 140, 60), (30, 100, 40), t)
            elif "BONUS" in bt.upper():
                t = re.sub(r'^.*?BONUS[A-Z ]*:?\s*', '', bt, flags=re.I).strip()
                callout("BONUS", CB, (235, 245, 255), (40, 80, 180), (30, 60, 140), t)
            elif "TRANSITION" in bt.upper():
                t = re.sub(r'^.*?TRANSITION:?\s*', '', bt, flags=re.I).strip('" ')
                callout("TRANSITION", CB, (235, 245, 255), (40, 80, 180), (30, 60, 140), t)
            else:
                pgchk(15)
                pdf.set_font("Helvetica", "I", 9); pdf.set_text_color(80, 80, 80)
                pdf.set_x(14); pdf.multi_cell(pdf.w - 28, 5, bt); pdf.ln(2)
            continue

        # Bullets
        if s.startswith("- ") or s.startswith("* "):
            pgchk(12); t = clean(s[2:])
            pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*CD)
            pdf.set_x(14); pdf.cell(5, 5.5, "-"); pdf.multi_cell(pdf.w - 33, 5.5, t)
            i += 1; continue

        # Numbered
        m = re.match(r'^(\d+)\.\s+(.+)', s)
        if m:
            pgchk(12)
            pdf.set_font("Helvetica", "B", 9); pdf.set_text_color(*CR)
            pdf.set_x(14); pdf.cell(8, 5.5, f"{m.group(1)}.")
            pdf.set_font("Helvetica", "", 9); pdf.set_text_color(*CD)
            pdf.multi_cell(pdf.w - 36, 5.5, clean(m.group(2)))
            i += 1; continue

        # Paragraph
        if s:
            pgchk(12); t = clean(s)
            pdf.set_font("Helvetica", "", 10); pdf.set_text_color(*CD)
            pdf.set_x(10); pdf.multi_cell(0, 6, t); pdf.ln(2)
        i += 1

    if in_table: flush_tbl()
    pdf.output(PDF_PATH)
    print(f"PDF saved: {PDF_PATH}")
    print(f"Pages: {pdf.page_no()}")

if __name__ == "__main__":
    build()
