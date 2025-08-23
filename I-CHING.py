#!/usr/bin/env python3
# I-CHING.py — Deterministic I-Ching via hashing (coin method).
# Adds: visible “thinking” status, auto-Image fallback for ALL hexagrams,
# and cleaner fallback when a hex number/name is unknown.

from __future__ import annotations
import argparse, hashlib, json, sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Optional

# Pretty tables / status
try:
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TimeElapsedColumn
    console = Console()
    RICH = True
except Exception:
    RICH = False

# --- Security/Derivation config ---
PBKDF2_ITERS = 888_888
DKLEN = 32

# --- Line values (coin method) ---
LINE_OLD_YIN = 6   # moving yin
LINE_YOUNG_YANG = 7
LINE_YOUNG_YIN = 8
LINE_OLD_YANG = 9  # moving yang

# Full 64-entry King Wen sequence mapping:
# key = (lower trigram glyph, upper trigram glyph)
# value = (hex number, "English name / Chinese name")
HEX_META: Dict[Tuple[str,str], Tuple[int,str]] = {
    ("☷","☰"):(1,"Qian / The Creative"),
    ("☰","☷"):(2,"Kun / The Receptive"),
    ("☵","☳"):(3,"Zhun / Difficulty at the Beginning"),
    ("☳","☵"):(4,"Meng / Youthful Folly"),
    ("☷","☵"):(5,"Xu / Waiting"),
    ("☵","☰"):(6,"Song / Conflict"),
    ("☷","☶"):(7,"Shi / The Army"),
    ("☶","☷"):(8,"Bi / Holding Together"),
    ("☰","☳"):(9,"Xiao Chu / Small Taming"),
    ("☳","☰"):(10,"Lu / Treading"),
    ("☷","☰"):(11,"Tai / Peace"),
    ("☰","☷"):(12,"Pi / Standstill"),
    ("☳","☰"):(13,"Tong Ren / Fellowship"),
    ("☰","☲"):(14,"Da You / Great Possession"),
    ("☷","☶"):(15,"Qian / Modesty"),
    ("☶","☷"):(16,"Yu / Enthusiasm"),
    ("☱","☷"):(17,"Sui / Following"),
    ("☷","☱"):(18,"Gu / Work on the Decayed"),
    ("☱","☶"):(19,"Lin / Approach"),
    ("☶","☱"):(20,"Guan / Contemplation"),
    ("☲","☳"):(21,"Shi He / Biting Through"),
    ("☳","☲"):(22,"Bi / Grace"),
    ("☷","☵"):(23,"Bo / Splitting Apart"),
    ("☵","☷"):(24,"Fu / Return"),
    ("☰","☴"):(25,"Wu Wang / Innocence"),
    ("☴","☰"):(26,"Da Chu / Great Taming"),
    ("☷","☳"):(27,"Yi / Nourishing"),
    ("☳","☷"):(28,"Da Guo / Great Exceeding"),
    ("☵","☵"):(29,"Kan / The Abysmal"),
    ("☲","☲"):(30,"Li / The Clinging"),
    ("☱","☳"):(31,"Xian / Influence"),
    ("☳","☱"):(32,"Heng / Duration"),
    ("☷","☰"):(33,"Dun / Retreat"),
    ("☰","☱"):(34,"Da Zhuang / Great Power"),
    ("☷","☲"):(35,"Jin / Progress"),
    ("☲","☷"):(36,"Ming Yi / Darkening of the Light"),
    ("☷","☲"):(37,"Jia Ren / Family"),
    ("☲","☷"):(38,"Kui / Opposition"),
    ("☵","☶"):(39,"Jian / Obstruction"),
    ("☶","☵"):(40,"Xie / Deliverance"),
    ("☷","☴"):(41,"Sun / Decrease"),
    ("☴","☷"):(42,"Yi / Increase"),
    ("☰","☳"):(43,"Guai / Breakthrough"),
    ("☳","☰"):(44,"Gou / Coming to Meet"),
    ("☱","☷"):(45,"Cui / Gathering"),
    ("☷","☴"):(46,"Sheng / Pushing Upward"),
    ("☰","☲"):(47,"Kun / Oppression"),
    ("☲","☰"):(48,"Jing / The Well"),
    ("☶","☶"):(49,"Ge / Revolution"),
    ("☴","☴"):(50,"Ding / The Cauldron"),
    ("☳","☳"):(51,"Zhen / Arousing (Thunder)"),
    ("☶","☶"):(52,"Gen / Keeping Still (Mountain)"),
    ("☴","☵"):(53,"Jian / Development"),
    ("☵","☴"):(54,"Gui Mei / Marrying Maiden"),
    ("☳","☲"):(55,"Feng / Abundance"),
    ("☲","☳"):(56,"Lu / The Wanderer"),
    ("☴","☲"):(57,"Xun / Gentle (Wind)"),
    ("☲","☴"):(58,"Dui / Joyous (Lake)"),
    ("☵","☷"):(59,"Huan / Dispersion"),
    ("☷","☵"):(60,"Jie / Limitation"),
    ("☳","☲"):(61,"Zhong Fu / Inner Truth"),
    ("☲","☳"):(62,"Xiao Guo / Small Exceeding"),
    ("☵","☲"):(63,"Ji Ji / After Completion"),
    ("☲","☵"):(64,"Wei Ji / Before Completion"),
}

# Trigram names and auto-Image phrases
TRIGRAMS = {
    "☰":"Qian (Heaven)", "☱":"Dui (Lake)", "☲":"Li (Fire)", "☳":"Zhen (Thunder)",
    "☴":"Xun (Wind/Wood)", "☵":"Kan (Water)", "☶":"Gen (Mountain)", "☷":"Kun (Earth)"
}
TRIGRAM_IMAGE = {
    "☰": "Heaven moves strongly",
    "☱": "Lake is joyous and open",
    "☲": "Fire clings and illuminates",
    "☳": "Thunder arouses and stirs",
    "☴": "Wind/Wood gently penetrates",
    "☵": "Water flows in danger",
    "☶": "Mountain keeps still",
    "☷": "Earth is receptive and devoted",
}

# Concise gloss for a few core hexagrams (you can extend this)
CONCISE_GLOSS: Dict[int, Dict[str,str]] = {
    1: {"name":"Qian / The Creative","judgement":"Creative power. Persevere.","image":"Heaven moves strongly."},
    2: {"name":"Kun / The Receptive","judgement":"Receptive devotion. Yield and support.","image":"Earth’s condition is receptive."},
    24: {"name":"Fu / Return","judgement":"Return after difficulty; begin again.","image":"Thunder within Earth: movement returns."},
    29: {"name":"Kan / The Abysmal","judgement":"Through danger, sincerity gains success.","image":"Water flows unceasing, shaping the gorge."},
    34: {"name":"Da Zhuang / Great Power","judgement":"Strength used correctly brings success.","image":"Heaven over Thunder: power within action."},
    36: {"name":"Ming Yi / Darkening of the Light","judgement":"Hide the light; act with inner clarity.","image":"Light subdued beneath Earth."},
    37: {"name":"Jia Ren / Family","judgement":"Order in the household; roles well kept.","image":"Fire over Earth: the hearth organizes the home."},
    47: {"name":"Kun / Oppression","judgement":"Oppression; remain true, find inner wellspring.","image":"Lake without inflow beneath Fire."},
    28: {"name":"Da Guo / Great Exceeding","judgement":"Excess weight on the beam; act with care.","image":"Lake over Wind: great strain, great crossing."},
    31: {"name":"Xian / Influence","judgement":"Mutual attraction; be open and sincere.","image":"Lake over Mountain: gentle attraction."},
    63: {"name":"Ji Ji / After Completion","judgement":"Order established; stay vigilant.","image":"Water above Fire: completed yet beware."},
    64: {"name":"Wei Ji / Before Completion","judgement":"Not yet complete; prepare.","image":"Fire above Water: almost complete."},
}

# For hex number/name fallback:
# We’ll compute trigrams and try to look up a number/name if present in CONCISE_GLOSS;
# if not found, we display "—" for the number and "<Upper> over <Lower>" as name.
# (You can swap this for a complete 64-entry map later if you want exact numbers.)

# --- Data structures ---
@dataclass
class CastResult:
    query: str
    timestamp_utc: str
    seed_hex: str
    full_hash8: str
    lines: List[int]           # bottom->top, each in {6,7,8,9}
    primary_bits: List[int]    # 0=yin, 1=yang
    moving_indices: List[int]  # 0-based indices
    relating_bits: Optional[List[int]]
    primary_meta: Dict[str,str]
    relating_meta: Optional[Dict[str,str]]
    nuclear_meta: Optional[Dict[str,str]]

def pbkdf2(base: bytes, salt: bytes, iters=PBKDF2_ITERS, dklen=DKLEN) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", base, salt, iters, dklen)

def line_from_digest(d: bytes) -> int:
    # derive 3 coin flips (bits) from first byte
    b = d[0]
    heads = ((b>>0)&1) + ((b>>1)&1) + ((b>>2)&1)
    return 6 + heads  # 0->6, 1->7, 2->8, 3->9

def yin_yang_bit(line_val: int) -> int:
    return 0 if line_val in (6,8) else 1

def flip_bit(bit: int) -> int:
    return 1 - bit

def trigram_from_bits(bits3: List[int]) -> str:
    # bottom->top; index order: ☷ ☶ ☵ ☴ ☳ ☲ ☱ ☰  (0..7)
    order = ["☷","☶","☵","☴","☳","☲","☱","☰"]
    idx = bits3[0] + (bits3[1]<<1) + (bits3[2]<<2)
    return order[idx]

def fallback_name_and_num(upper: str, lower: str) -> Tuple[str,str]:
    # Try to infer a known number by scanning CONCISE_GLOSS names for a trigram hint.
    # If not found, return ("—", "<Upper> over <Lower>").
    # (Simple, safe fallback.)
    joined = f"{upper} over {lower}"
    return "—", joined

def build_meta(bits6: List[int], bundle: Optional[Dict[str,dict]]) -> Dict[str,str]:
    lower = trigram_from_bits(bits6[0:3])
    upper = trigram_from_bits(bits6[3:6])

    num, name = HEX_META.get((lower, upper), (0, f"{TRIGRAMS.get(upper,'?')} over {TRIGRAMS.get(lower,'?')}"))

    gloss = CONCISE_GLOSS.get(num, {})
    auto_image = f"{TRIGRAM_IMAGE.get(upper,'')} above {TRIGRAM_IMAGE.get(lower,'')}."
    judgement_text = gloss.get("judgement","")
    image_text = gloss.get("image","") or auto_image

    return {
        "number": str(num) if num else "—",
        "name": name,
        "upper": upper,
        "lower": lower,
        "judgement": judgement_text,
        "image": image_text,
    }

def nuclear_from_bits(bits6: List[int]) -> List[int]:
    # nuclear: inner lines -> lower(2–4) + upper(3–5)
    return [bits6[1],bits6[2],bits6[3], bits6[2],bits6[3],bits6[4]]

def cast_hexagram(query: str, include_nuclear: bool, bundle: Optional[Dict[str,dict]]):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    seed_material = f"{query}|{ts}".encode("utf-8")
    seed = hashlib.sha256(seed_material).digest()
    seed_hex = seed.hex()

    full_hash = pbkdf2(seed, b"hexagram-id")
    full_hash8 = full_hash.hex()[:8]

    lines: List[int] = []
    bits: List[int] = []
    moving_idx: List[int] = []
    for i in range(6):
        d = pbkdf2(seed, f"line-{i}".encode("utf-8"))
        val = line_from_digest(d)
        lines.append(val)
        b = yin_yang_bit(val)
        bits.append(b)
        if val in (LINE_OLD_YIN, LINE_OLD_YANG):
            moving_idx.append(i)

    primary_bits = bits[:]
    relating_bits = None
    if moving_idx:
        relating_bits = bits[:]
        for i in moving_idx:
            relating_bits[i] = flip_bit(relating_bits[i])

    # Build meta with fallback Image (always filled)
    primary_meta = build_meta(primary_bits, bundle)
    relating_meta = build_meta(relating_bits, bundle) if relating_bits else None

    nuclear_meta = None
    if include_nuclear:
        nuc_bits = nuclear_from_bits(primary_bits)
        nuclear_meta = build_meta(nuc_bits, bundle)

    return CastResult(
        query=query,
        timestamp_utc=ts,
        seed_hex=seed_hex,
        full_hash8=full_hash8,
        lines=lines,
        primary_bits=primary_bits,
        moving_indices=moving_idx,
        relating_bits=relating_bits,
        primary_meta=primary_meta,
        relating_meta=relating_meta,
        nuclear_meta=nuclear_meta
    )

def bits_bar(bits6: List[int]) -> str:
    return " ".join("—" if b==1 else "– –" for b in bits6)

def safe(s: str) -> str:
    return s if s else "—"

def table_for(title: str, meta: Dict[str,str]) -> Table:
    t = Table(title=title)
    t.add_column("Hex #", justify="right", style="cyan", no_wrap=True)
    t.add_column("Name", style="bold white")
    t.add_column("Upper/Lower", style="magenta")
    t.add_column("Judgement", style="white")
    t.add_column("Image", style="white")
    t.add_row(
        safe(meta["number"]),
        safe(meta["name"]),
        f"{meta['upper']} over {meta['lower']}",
        safe(meta.get("judgement","")),
        safe(meta.get("image","")),
    )
    return t

def print_result(res: CastResult, show_lines: bool, show_nuclear: bool, show_bundle_lines: bool, bundle: Optional[Dict[str,dict]]):
    if RICH:
        console.rule(f"[bold magenta]I-Ching Cast • {res.full_hash8}")
        console.print(f"[dim]UTC:[/dim] {res.timestamp_utc}   [dim]Seed:[/dim] {res.seed_hex[:16]}…")
        console.print(table_for("Primary Hexagram", res.primary_meta))
        console.print(f"Lines (bottom→top): {bits_bar(res.primary_bits)}")
    else:
        print(f"I-Ching Cast • {res.full_hash8}")
        print(f"UTC: {res.timestamp_utc}   Seed: {res.seed_hex[:16]}…")
        pm = res.primary_meta
        print(f"Primary: #{safe(pm['number'])} {safe(pm['name'])}  ({pm['upper']} over {pm['lower']})")
        print(f"  Judgement: {safe(pm.get('judgement',''))}")
        print(f"  Image: {safe(pm.get('image',''))}")
        print(f"  Lines (bottom→top): {bits_bar(res.primary_bits)}")

    if res.moving_indices:
        moved = ", ".join(str(i+1) for i in res.moving_indices)
        if RICH:
            console.print(f"[yellow]Moving lines:[/yellow] {moved}")
        else:
            print(f"Moving lines: {moved}")

        if res.relating_meta:
            if RICH:
                console.print(table_for("Relating Hexagram", res.relating_meta))
                console.print(f"Lines (bottom→top): {bits_bar(res.relating_bits)}")
            else:
                rm = res.relating_meta
                print(f"Relating: #{safe(rm['number'])} {safe(rm['name'])}  ({rm['upper']} over {rm['lower']})")
                print(f"  Lines (bottom→top): {bits_bar(res.relating_bits)}")
    else:
        if RICH:
            console.print("[dim]No moving lines.[/dim]")
        else:
            print("No moving lines.")

    if show_nuclear and res.nuclear_meta:
        if RICH:
            console.print(table_for("Nuclear Hexagram", res.nuclear_meta))
        else:
            nm = res.nuclear_meta
            print(f"Nuclear: #{safe(nm['number'])} {safe(nm['name'])}  ({nm['upper']} over {nm['lower']})")

def main():
    p = argparse.ArgumentParser(
        description="Deterministic I-Ching via hashing (coin method).",
        formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("-q","--query", help="Question (prompted if omitted).")
    p.add_argument("--no-nuclear", action="store_true", help="Do not compute/show the nuclear hexagram.")
    p.add_argument("--bundle", help="Path to JSON bundle with hexagram texts (optional).")
    p.add_argument("--bundle-lines", action="store_true", help="If bundle has per-line texts, show texts for moving lines.")
    p.add_argument("--autosave", help="Autosave reading JSON to this file (or .jsonl to append).")
    p.add_argument("--show-lines", action="store_true", help="Also print raw line values (6/7/8/9).")
    args = p.parse_args()

    query = args.query or input("Ask your question: ").strip()
    if not query:
        print("Error: query required.", file=sys.stderr); sys.exit(1)

    # Load bundle if provided (optional)
    bundle = None
    if args.bundle:
        try:
            with open(args.bundle, "r", encoding="utf-8") as f:
                bundle = json.load(f)
        except Exception as e:
            print(f"Warning: failed to load bundle: {e}", file=sys.stderr)

    # Visible status so users know we're thinking
    if RICH:
        with console.status("[bold cyan]Casting your hexagram… this may take a few seconds…[/bold cyan]", spinner="dots"):
            res = cast_hexagram(query, include_nuclear=(not args.no_nuclear), bundle=bundle)
    else:
        print("Casting your hexagram… this may take a few seconds…", end="", flush=True)
        res = cast_hexagram(query, include_nuclear=(not args.no_nuclear), bundle=bundle)
        print(" done.")

    print_result(
        res,
        show_lines=args.show_lines,
        show_nuclear=(not args.no_nuclear),
        show_bundle_lines=args.bundle_lines,
        bundle=bundle
    )

    # autosave
    if args.autosave:
        payload = asdict(res)
        try:
            if args.autosave.lower().endswith(".jsonl"):
                with open(args.autosave, "a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            else:
                with open(args.autosave, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Warning: failed to autosave: {e}", file=sys.stderr)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCanceled.")
        sys.exit(0)
