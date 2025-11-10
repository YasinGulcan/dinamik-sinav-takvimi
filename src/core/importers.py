# src/core/importers.py
from __future__ import annotations
import pandas as pd
from typing import List, Dict, Tuple
from core.db import get_conn

REQUIRED_STU_COLS = {"numara", "ad", "sınıf"}

def _norm(s: str) -> str:
    return (s or "").strip()

def read_students_xlsx(path: str) -> Tuple[List[Dict], List[str]]:
    """
    Excel'den öğrencileri okur.
    Beklenen başlıklar (büyük-küçük fark etmez):
      - Numara
      - Ad (veya Ad Soyad)
      - Sınıf (1..8)
    Dönen:
      rows: [{number, full_name, class_year}]
      errors: ["satır 5: ...", ...]
    """
    df = pd.read_excel(path)
    cols = {c.strip().lower(): c for c in df.columns}

    # başlık eşleştirme
    num_col = cols.get("numara") or cols.get("ogrenci no") or cols.get("öğrenci no")
    name_col = cols.get("ad") or cols.get("ad soyad") or cols.get("adı soyadı")
    year_col = cols.get("sınıf") or cols.get("sinif") or cols.get("class") or cols.get("class_year")

    missing = []
    if not num_col:  missing.append("Numara")
    if not name_col: missing.append("Ad/Ad Soyad")
    if not year_col: missing.append("Sınıf")
    if missing:
        raise ValueError("Eksik başlık(lar): " + ", ".join(missing))

    rows, errors = [], []
    for i, r in df.iterrows():
        ln = i + 2  # başlık satırı 1
        number = _norm(str(r[num_col]))
        full_name = _norm(str(r[name_col]))
        try:
            class_year = int(str(r[year_col]).strip())
        except Exception:
            class_year = -1

        if not number:
            errors.append(f"satır {ln}: Numara boş")
            continue
        if not full_name:
            errors.append(f"satır {ln}: Ad/Ad Soyad boş")
            continue
        if class_year not in range(1, 9):
            errors.append(f"satır {ln}: Sınıf 1..8 arasında olmalı (gelen={class_year})")
            continue

        rows.append({"number": number, "full_name": full_name, "class_year": class_year})

    return rows, errors

def import_students(rows: List[Dict], dept_id: int) -> Tuple[int, int]:
    """
    rows: [{number, full_name, class_year}]
    dept_id özelinde INSERT OR IGNORE + UPDATE (isim/sınıf değişmişse)
    Dönen: (eklendi/güncellendi, atlanan)
    """
    added_or_updated = 0
    skipped = 0
    with get_conn() as con:
        cur = con.cursor()
        for r in rows:
            number = r["number"]
            full_name = r["full_name"]
            class_year = r["class_year"]

            # var mı?
            cur.execute("SELECT id, full_name, class_year FROM students WHERE dept_id=? AND number=?",
                        (dept_id, number))
            row = cur.fetchone()
            if row:
                sid, old_name, old_year = row
                if old_name != full_name or old_year != class_year:
                    cur.execute("UPDATE students SET full_name=?, class_year=? WHERE id=?",
                                (full_name, class_year, sid))
                    added_or_updated += 1
                else:
                    skipped += 1
            else:
                cur.execute("""INSERT INTO students(dept_id, number, full_name, class_year)
                               VALUES (?,?,?,?)""",
                            (dept_id, number, full_name, class_year))
                added_or_updated += 1
    return added_or_updated, skipped
