"""Extract numerical example inputs from the user-supplied PDF, pp. 15-18.
Run with the document Python runtime (pdfplumber required only here).
"""
import json
from pathlib import Path
import re
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
rows = {'near': [], 'next': []}
with pdfplumber.open(ROOT / 'Volatility_Index_Methodology_Cboe_Volatility_Index.pdf') as pdf:
    for page in pdf.pages[14:18]:
        for side, (x0, x1) in [('near', (0, page.width/2)), ('next', (page.width/2, page.width))]:
            text = page.crop((x0, 0, x1, page.height)).extract_text() or ''
            for line in text.splitlines():
                values = line.split()
                if len(values) != 5 or not all(re.fullmatch(r'\d+(?:\.\d+)?', v) for v in values):
                    continue
                k, cb, ca, pb, pa = map(float, values)
                for kind, bid, ask in [('Call', cb, ca), ('Put', pb, pa)]:
                    rows[side].append(dict(symbol=f'{side}_{kind}_{k:g}', type=kind, strike=k, bid=bid, ask=ask))
out = ROOT / 'tests/fixtures/cboe_vix_example.json'
out.write_text(json.dumps(rows, indent=2), encoding='utf-8')
print({k: len(v) for k, v in rows.items()})
