#!/usr/bin/env python3
"""
process.py
Procesa P1_Control_Consumo_Gas_Energia_Por_Hora_Esmaltado_y_Hornos.xlsx
y genera docs/data.json para el dashboard.

El JSON guarda los datos HORARIOS de cada (línea, formato). La web agrega
a día / mes con media ponderada por m² (Σgas / Σm²) y aplica el filtro
de producción mínima por hora que elija el usuario.

Uso:
    python scripts/process.py
    python scripts/process.py --input data/mi_archivo.xlsx
"""

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── Configuración ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = ROOT / "data" / "P1_Control_Consumo_Gas_Energia_Por_Hora_Esmaltado_y_Hornos.xlsx"
OUTPUT_JSON = ROOT / "docs" / "data.json"

SHEET_HOR = "v_hornosHoraGasEnergiaDisponibi"
SHEET_ESM = "v_esmalt_HoraGasEnergiaDisponib"   # gas de los SECADEROS (en serie con esmaltado)

LINES_HOR = [1, 3]
LINES_ESM = [1, 2, 4, 5, 6]

# Límite superior de kWht/m² por hora (descarta lecturas imposibles)
LINE_CUTS_HOR = {1: 100, 3: 100}
LINE_CUTS_ESM = {1: 160, 2: 333, 4: 117, 5: 116, 6: 62}

# Un formato aparece en el dashboard si suma al menos estos m²
MIN_M2_FMT = 1000

# Filtro de producción mínima por hora que la web aplica por defecto
# (el usuario lo puede cambiar). Mismos criterios que los estudios de ahorro.
DEFAULT_MIN_M2_H = {"hor": 100, "esm": 50}

CICLO_MIN, CICLO_MAX = 20.0, 120.0

# Referencia de tiempo: las horas se guardan como enteros desde esta fecha
T0 = pd.Timestamp("2024-01-01 00:00:00")

# Eventos que se marcan en el gráfico. sect: "hor" | "esm"; line: opcional
EVENTS = [
    {"date": "2025-05-14", "sect": "esm", "label": "POPPI averiado"},
    {"date": "2026-04-16", "sect": "esm", "label": "POPPI nuevo"},
    {"date": "2026-08-25", "sect": "esm", "label": "Turbinas actuales POPPI"},
    {"date": "2026-11-09", "sect": "esm", "label": "POPPI averiado"},
    {"date": "2026-01-01", "sect": "hor", "line": 1, "label": "Calorifugado H1"},
]

# ── Normalización de formatos de secaderos ─────────────────────────────────────
FMT_ALIAS_ESM = {
    "34,5X10": "34,5X101,5",
    "34,5X101,": "34,5X101,5",
    "34X101": "34,5X101,5",
    "34,5X101": "34,5X101,5",
    "P59,5": "59,5X59,5",
}
_FMT_OK = re.compile(r"\d+(,\d+)?X\d+(,\d+)?|DVP\d+")


def norm_fmt_esm(f):
    """'GRACIA/45X45X0,95' → '45X45'; '34.5X101.5' → '34,5X101,5'; basura → None."""
    if pd.isna(f):
        return None
    s = str(f).strip().upper().replace(".", ",").replace(" ", "")
    if "/" in s:                       # prefijo de modelo o cliente
        s = s.split("/")[-1]
    s = s.replace("XX", "X")
    s = re.sub(r"X0,\d+$", "", s)       # sufijo de espesor X0,95
    s = FMT_ALIAS_ESM.get(s, s)
    return s if _FMT_OK.fullmatch(s) else None


def norm_fmt_hor(f):
    if pd.isna(f):
        return None
    s = str(f).strip()
    return None if s in ("", "No encontrado") else s


# ── Carga y filtrado ───────────────────────────────────────────────────────────
def load(path: Path, sheet: str, cuts: dict, igas_min: float, norm) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet, header=0)
    df["hora"] = pd.to_datetime(df["hora"])
    df["fe"] = df["Formato"].map(norm)
    cut = df["linea"].map(cuts).fillna(100)
    ok = (
        (df["m2_salida"] > 0)
        & (df["iGAS_kwht/m2"] > igas_min)
        & (df["iGAS_kwht/m2"] < cut)
        & df["fe"].notna()
    )
    return df[ok].copy(), df


def build_hourly(df: pd.DataFrame, lines: list, with_ciclo: bool) -> dict:
    out = {}
    for line in lines:
        sub = df[df["linea"] == line]
        m2_fmt = sub.groupby("fe")["m2_salida"].sum()
        fmts = m2_fmt[m2_fmt >= MIN_M2_FMT].sort_values(ascending=False).index
        for fe in fmts:
            s = sub[sub["fe"] == fe].sort_values("hora")
            entry = {
                "t": ((s["hora"] - T0) // pd.Timedelta(hours=1)).astype(int).tolist(),
                "g": s["iGAS_kwht/m2"].round(2).tolist(),
                "m": s["m2_salida"].round(1).tolist(),
            }
            if with_ciclo:
                c = s["ciclo"].where((s["ciclo"] >= CICLO_MIN) & (s["ciclo"] <= CICLO_MAX))
                entry["c"] = [None if pd.isna(v) else int(round(v)) for v in c]
            out[f"{line}|{fe}"] = entry
    return out


def last_hour(raw: pd.DataFrame) -> str:
    prod = raw[raw["m2_salida"] > 0]
    return prod["hora"].max().strftime("%Y-%m-%dT%H:%M") if len(prod) else None


def main():
    ap = argparse.ArgumentParser(description="Genera data.json para el dashboard.")
    ap.add_argument("--input", default=str(DEFAULT_XLSX))
    ap.add_argument("--output", default=str(OUTPUT_JSON))
    args = ap.parse_args()

    xlsx, out_path = Path(args.input), Path(args.output)
    if not xlsx.exists():
        print(f"ERROR: No se encuentra el fichero: {xlsx}", file=sys.stderr)
        sys.exit(1)
    print(f"Leyendo: {xlsx}")

    print("  → Hornos…")
    hor, hor_raw = load(xlsx, SHEET_HOR, LINE_CUTS_HOR, 3, norm_fmt_hor)
    has_ciclo = "ciclo" in hor.columns
    hor_h = build_hourly(hor, LINES_HOR, has_ciclo)

    print("  → Secaderos…")
    esm, esm_raw = load(xlsx, SHEET_ESM, LINE_CUTS_ESM, 0.3, norm_fmt_esm)
    esm_h = build_hourly(esm, LINES_ESM, False)

    all_t = [t for s in list(hor_h.values()) + list(esm_h.values()) for t in s["t"]]
    t_min, t_max = min(all_t), max(all_t)
    as_date = lambda t: (T0 + pd.Timedelta(hours=t)).strftime("%Y-%m-%d")

    output = {
        "meta": {
            "version": 2,
            "t0": T0.strftime("%Y-%m-%dT%H:%M"),
            "date_min": as_date(t_min),
            "date_max": as_date(t_max),
            "last": {"hor": last_hour(hor_raw), "esm": last_hour(esm_raw)},
            "generated": pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "source": xlsx.name,
            "has_ciclo": has_ciclo,
            "min_m2_h": DEFAULT_MIN_M2_H,
            "events": EVENTS,
        },
        "hor": hor_h,
        "esm": esm_h,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"), ensure_ascii=False)

    n_hor = sum(len(s["t"]) for s in hor_h.values())
    n_esm = sum(len(s["t"]) for s in esm_h.values())
    print(f"  ✓ Hornos:    {len(hor_h)} series ({n_hor:,} horas)")
    print(f"  ✓ Secaderos: {len(esm_h)} series ({n_esm:,} horas)")
    print(f"  ✓ Último dato: hornos {output['meta']['last']['hor']} · secaderos {output['meta']['last']['esm']}")
    print(f"  ✓ JSON: {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
