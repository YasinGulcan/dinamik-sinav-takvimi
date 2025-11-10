import re
import pandas as pd
from typing import Optional, Tuple

def try_preview_xlsx(path: str, n: int = 10) -> Tuple[Optional["pandas.DataFrame"], Optional[str]]:
    try:
        xl = pd.ExcelFile(path)
        if not xl.sheet_names:
            return None, "Çalışma sayfası bulunamadı."
        df = xl.parse(xl.sheet_names[0])          # TAM SAYFAYI AÇ
        return df, None                            # <-- head() YOK
    except ModuleNotFoundError:
        return None, "pandas/openpyxl yüklü değil. Kurulum: pip install pandas openpyxl"
    except Exception as e:
        return None, f"Hata: {e}"

def normalize_courses_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Çok bloklu 'Ders Listesi' sayfasını tek tabloya dönüştürür.
    - 1. blokta '1. Sınıf' kolon başlığında olabilir (ilk satır başlık)
    - Sonraki bloklarda 'X. Sınıf' satırda ve altında tekrar 'DERS KODU' başlığı olur.
    Çıktı kolonları: [DERS KODU, DERSİN ADI, DERSİ VEREN ÖĞR. ELEMANI, Sınıf(Yıl)]
    """
    import re
    df = df_raw.fillna("").astype(str)
    rows = df.values.tolist()

    def idx_of(labels, want):
        labs = [str(c).strip().lower() for c in labels]
        if want == "code":
            for i, c in enumerate(labs):
                if ("ders" in c) and ("kod" in c):
                    return i
        if want == "name":
            for i, c in enumerate(labs):
                if ("ders" in c) and (("adı" in c) or ("adi" in c)):
                    return i
        if want == "instr":
            for i, c in enumerate(labs):
                if ("veren" in c) or ("öğr" in c) or ("ogr" in c):
                    return i
        return None

    def is_year_text(text: str):
        m = re.search(r"\b([1-8])\s*\.?\s*sınıf\b", str(text), flags=re.I)
        return (m is not None, int(m.group(1)) if m else None)

    def is_year_row(r):
        return is_year_text(" ".join(map(str, r)))

    def find_header_below(start_idx):
        # start_idx'in altındaki 8 satırda 'DERS KODU' başlığını ara
        for j in range(start_idx + 1, min(start_idx + 9, len(rows))):
            labs = [str(x).strip().lower() for x in rows[j]]
            if any(("ders" in c and "kod" in c) for c in labs) and \
               any(("ders" in c and (("adı" in c) or ("adi" in c))) for c in labs):
                return j
        return None

    def emit_block(header_idx, next_idx, year, out):
        i_code  = idx_of(rows[header_idx], "code")
        i_name  = idx_of(rows[header_idx], "name")
        i_instr = idx_of(rows[header_idx], "instr")
        if i_code is None or i_name is None:
            return
        for j in range(header_idx + 1, next_idx):
            r = rows[j]
            if not any(str(x).strip() for x in r):
                continue
            # Muhtemel 'X. Sınıf' satırlarını veri sanma
            if is_year_row(r)[0]:
                continue
            code = str(r[i_code]).strip()
            if not code or code.lower().startswith("ders"):
                continue
            name = str(r[i_name]).strip()
            instr = str(r[i_instr]).strip() if i_instr is not None else ""
            out.append({
                "DERS KODU": code,
                "DERSİN ADI": name,
                "DERSİ VEREN ÖĞR. ELEMANI": instr,
                "Sınıf(Yıl)": int(year)
            })

    # 1) Kolon başlıklarında 'X. Sınıf' var mı? (Örn: ilk blok 1. Sınıf)
    col_text = " ".join([str(c) for c in df.columns])
    mcol = re.search(r"\b([1-8])\s*\.?\s*sınıf\b", col_text, flags=re.I)
    first_year_from_cols = int(mcol.group(1)) if mcol else None

    # 2) Satırlarda 'X. Sınıf' geçen yerleri işaretle
    year_marks = []
    for i, r in enumerate(rows):
        ok, y = is_year_row(r)
        if ok:
            year_marks.append((i, y))

    out = []

    # 3) Eğer kolonlarda '1. Sınıf' vb. varsa: İlk blok (header: satır 0), sınır: ilk year satırı
    if first_year_from_cols is not None:
        header0 = 0
        # Güvenlik: ilk birkaç satırda 'DERS KODU' başlığını doğrula
        if not any(("ders" in str(x).lower() and "kod" in str(x).lower()) for x in rows[header0]):
            for j in range(0, min(6, len(rows))):
                labs = [str(x).lower() for x in rows[j]]
                if any(("ders" in c and "kod" in c) for c in labs):
                    header0 = j
                    break
        next_idx0 = year_marks[0][0] if year_marks else len(rows)
        emit_block(header0, next_idx0, first_year_from_cols, out)

    # 4) Sonraki bloklar: 'X. Sınıf' satırından sonra gelen başlık+veriler
    for k, (yidx, year) in enumerate(year_marks):
        header_idx = find_header_below(yidx)
        if header_idx is None:
            continue
        next_idx = year_marks[k + 1][0] if k + 1 < len(year_marks) else len(rows)
        emit_block(header_idx, next_idx, year, out)

    return pd.DataFrame(out) if out else df_raw

