#!/usr/bin/env python3
"""
process.py
Procesa P1_Control_Consumo_Gas_Energia_Por_Hora_Esmaltado_y_Hornos.xlsx
y genera docs/data.json listo para el dashboard.

Uso:
    python scripts/process.py
    python scripts/process.py --input data/mi_archivo.xlsx
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from scipy import stats as spstats

# ── Configuración ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = ROOT / "data" / "P1_Control_Consumo_Gas_Energia_Por_Hora_Esmaltado_y_Hornos.xlsx"
OUTPUT_JSON  = ROOT / "docs" / "data.json"

SHEET_HOR = "v_hornosHoraGasEnergiaDisponibi"
SHEET_ESM = "v_esmalt_HoraGasEnergiaDisponib"

LINE_CUTS_HOR = {1: 100, 3: 100}
LINE_CUTS_ESM = {1: 160, 2: 333, 4: 117, 5: 116, 6: 62}

TOP_N_HOR = 10
TOP_N_ESM = 8

# ── Normalización de formatos esmaltado ────────────────────────────────────────
FMT_MAP_ESM = {
    "45,6x45,6": "45,6X45,6",
    "45,2X45,2X0,95": "45,2X45,2",
    "45X45x0,95": "45X45",
    "34,5X101,": "34,5X101,5",
    "34X101": "34,5X101,5",
}

def norm_fmt_esm(f):
    if pd.isna(f):
        return None
    f = str(f).strip()
    return FMT_MAP_ESM.get(f, f)


# ── KDE mode para ciclo ────────────────────────────────────────────────────────
def kde_mode(vals: np.ndarray):
    v = vals[~np.isnan(vals)]
    if len(v) < 3:
        return round(float(np.median(v)), 0) if len(v) > 0 else None
    try:
        kde = spstats.gaussian_kde(v, bw_method="silverman")
        x = np.linspace(np.percentile(v, 5), np.percentile(v, 95), 400)
        return round(float(x[np.argmax(kde(x))]), 0)
    except Exception:
        return round(float(np.median(v)), 0)


CICLO_MIN = 20.0
CICLO_MAX = 120.0


# ── Carga y filtrado ───────────────────────────────────────────────────────────
def load_hornos(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET_HOR, header=0)
    df["hora"] = pd.to_datetime(df["hora"])
    df = df[(df["m2_salida"] > 0) & (df["iGAS_kwht/m2"] > 3)].copy()
    df = df[df.apply(lambda r: r["iGAS_kwht/m2"] < LINE_CUTS_HOR.get(r["linea"], 100), axis=1)]
    # === CAMBIO: usar "Formato" en vez de "Formato + Espesor" ===
    df["fe"] = df["Formato"]
    df = df[df["fe"].notna()]
    return df


def load_esmaltado(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=SHEET_ESM, header=0)
    df["hora"] = pd.to_datetime(df["hora"])
    df = df[(df["m2_salida"] > 0) & (df["iGAS_kwht/m2"] > 0.3)].copy()
    df["fe"] = df["Formato"].apply(norm_fmt_esm)
    df = df[df["fe"].notna()]
    df = df[df.apply(lambda r: r["iGAS_kwht/m2"] < LINE_CUTS_ESM.get(r["linea"], 200), axis=1)]
    return df


# ── Agregación diaria ──────────────────────────────────────────────────────────
def daily_series(df: pd.DataFrame, line_col: str, fe_col: str,
                 gas_col: str, m2_col: str,
                 ciclo_col: str | None = None) -> pd.DataFrame:
    df = df.copy()
    df["day"] = df["hora"].dt.date

    def agg_group(g):
        m2_sum = g[m2_col].sum()
        gas_wm = (g[gas_col] * g[m2_col]).sum() / m2_sum if m2_sum > 0 else None
        result = {"gas_wm": gas_wm, "m2": m2_sum}
        if ciclo_col and ciclo_col in g.columns:
            ciclo_vals = g[ciclo_col].dropna().values
            ciclo_vals = ciclo_vals[(ciclo_vals >= CICLO_MIN) & (ciclo_vals <= CICLO_MAX)]
            result["ciclo_mode"] = kde_mode(ciclo_vals) if len(ciclo_vals) >= 3 else None
        return pd.Series(result)

    agg = (
        df.groupby(["day", line_col, fe_col])
        .apply(agg_group)
        .reset_index()
    )
    return agg


# ── Construcción del dict de series ───────────────────────────────────────────
def build_series(daily: pd.DataFrame, line_col: str, fe_col: str,
                 tops: dict, include_ciclo: bool = False) -> dict:
    out = {}
    for line, fmts in tops.items():
        sub = daily[(daily[line_col] == line) & (daily[fe_col].isin(fmts))]
        for fe in fmts:
            fe_sub = sub[sub[fe_col] == fe].sort_values("day")
            if fe_sub.empty:
                continue
            key = f"{line}|{fe}"
            entry = {
                "d": [str(r["day"]) for _, r in fe_sub.iterrows()],
                "g": [
                    round(float(r["gas_wm"]), 2) if pd.notna(r["gas_wm"]) else None
                    for _, r in fe_sub.iterrows()
                ],
                "m": [round(float(r["m2"]), 0) for _, r in fe_sub.iterrows()],
            }
            if include_ciclo and "ciclo_mode" in fe_sub.columns:
                entry["c"] = [
                    int(r["ciclo_mode"]) if pd.notna(r["ciclo_mode"]) else None
                    for _, r in fe_sub.iterrows()
                ]
            out[key] = entry
    return out


def main():
    parser = argparse.ArgumentParser(description="Genera data.json para el dashboard.")
    parser.add_argument("--input", type=str, default=str(DEFAULT_XLSX))
    parser.add_argument("--output", type=str, default=str(OUTPUT_JSON))
    args = parser.parse_args()

    xlsx_path = Path(args.input)
    out_path  = Path(args.output)

    if not xlsx_path.exists():
        print(f"ERROR: No se encuentra el fichero: {xlsx_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Leyendo: {xlsx_path}")

    # Hornos
    print("  → Procesando Hornos…")
    df_hor = load_hornos(xlsx_path)

    has_ciclo = "ciclo" in df_hor.columns
    if has_ciclo:
        print("     columna 'ciclo' detectada ✓")
    else:
        print("     columna 'ciclo' NO encontrada (se omite)")

    hor_tops = {}
    for line in [1, 3]:
        hor_tops[line] = (
            df_hor[df_hor["linea"] == line]
            .groupby("fe")["m2_salida"].sum()
            .sort_values(ascending=False)
            .head(TOP_N_HOR)
            .index.tolist()
        )
    hor_daily = daily_series(
        df_hor, "linea", "fe", "iGAS_kwht/m2", "m2_salida",
        ciclo_col="ciclo" if has_ciclo else None,
    )
    hor_series = build_series(hor_daily, "linea", "fe", hor_tops, include_ciclo=has_ciclo)

    # Esmaltado
    print("  → Procesando Esmaltado…")
    df_esm = load_esmaltado(xlsx_path)
    esm_tops = {}
    for line in [1, 2, 4, 5, 6]:
        esm_tops[line] = (
            df_esm[df_esm["linea"] == line]
            .groupby("fe")["m2_salida"].sum()
            .sort_values(ascending=False)
            .head(TOP_N_ESM)
            .index.tolist()
        )
    esm_daily = daily_series(df_esm, "linea", "fe", "iGAS_kwht/m2", "m2_salida")
    esm_series = build_series(esm_daily, "linea", "fe", esm_tops)

    all_dates_hor = [d for s in hor_series.values() for d in s["d"]]
    all_dates_esm = [d for s in esm_series.values() for d in s["d"]]
    date_min = min(all_dates_hor + all_dates_esm)
    date_max = max(all_dates_hor + all_dates_esm)

    output = {
        "meta": {
            "date_min": date_min,
            "date_max": date_max,
            "generated": pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "source": xlsx_path.name,
            "has_ciclo": has_ciclo,
        },
        "hor": hor_series,
        "esm": esm_series,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, separators=(",", ":"), ensure_ascii=False)

    size_kb = out_path.stat().st_size / 1024
    print(f"  ✓ Hornos:    {len(hor_series)} series")
    print(f"  ✓ Esmaltado: {len(esm_series)} series")
    print(f"  ✓ Rango: {date_min} → {date_max}")
    print(f"  ✓ JSON generado: {out_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
