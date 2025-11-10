# src/ui/import_view.py
# Ders/Öğrenci Excel: önizleme + sütun eşleme + dry-run + DB'ye aktar (PDF akışına birebir)

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Tuple, Optional, Dict
import re
import traceback

from core.db import get_conn
from core.excel.preview import try_preview_xlsx, normalize_courses_df

# --- PDF'teki alan isimleri (ekranda bu başlıklar görünecek) ---
REQUIRED_COURSE_FIELDS  = ("Kod", "Ad", "Sınıf(Yıl)", "Zorunlu(E/H)", "Öğretim Üyesi")
REQUIRED_STUDENT_FIELDS = ("Numara", "Ad Soyad", "Sınıf(Yıl)", "Dersler(virgülle kodlar)")


class ImportView(ttk.Frame):

    def __init__(self, master, user, **kwargs):
        super().__init__(master, **kwargs)
        self.user = user
        self._df_cache: Dict[str, object] = {"courses": None, "students": None}
        self._maps: Dict[str, Dict[str, tk.StringVar]] = {}
        self._fixed_year = tk.StringVar(value="")   # Ders importunda sabit sınıf/yıl (opsiyonel)
        self._top = self.winfo_toplevel()

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.tab_courses = ttk.Frame(nb)
        self.tab_students = ttk.Frame(nb)
        nb.add(self.tab_courses, text="Ders Listesi")
        nb.add(self.tab_students, text="Öğrenci Listesi")

        self._build_tab(self.tab_courses, kind="courses")
        self._build_tab(self.tab_students, kind="students")

        info = ttk.Label(
            self,
            text=f"Giriş: {self.user.get('email','?')} • Bölüm ID: {self.user.get('department_id')}",
            foreground="#666"
        )
        info.pack(anchor="w", padx=10, pady=(0, 6))

    # ------------------ UI Kurulum ------------------

    def _build_tab(self, parent, kind: str):
        # Üst satır: dosya yolu + önizleme
        top = ttk.Frame(parent); top.pack(fill="x", padx=10, pady=8)
        path_var = tk.StringVar()
        ttk.Entry(top, textvariable=path_var).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(top, text="Dosya Seç", command=lambda: self._choose_file(path_var)).pack(side="left")
        ttk.Button(top, text="Önizle", command=lambda: self._preview(parent, path_var.get(), kind)).pack(side="left", padx=(6, 0))

        ttk.Label(parent, text="Not: Önce Önizle → Sütun Eşle → Dry-Run → DB'ye Aktar.").pack(anchor="w", padx=10)

        # Sütun eşleme alanı
        map_frame = ttk.LabelFrame(parent, text="Sütun Eşleme")
        map_frame.pack(fill="x", padx=10, pady=(4, 6))
        setattr(parent, "map_frame", map_frame)

        # Ders importu için opsiyonel sabit sınıf(yıl)
        if kind == "courses":
            fy = ttk.Frame(parent); fy.pack(fill="x", padx=10, pady=(0, 6))
            ttk.Label(fy, text="Sınıf(Yıl) sabit (opsiyonel):").pack(side="left")
            ttk.Combobox(fy, textvariable=self._fixed_year,
                         values=["", "1","2","3","4","5","6","7","8"],
                         width=5, state="readonly").pack(side="left", padx=6)

        # Buton bar
        bar = ttk.Frame(parent); bar.pack(fill="x", padx=10, pady=(0, 4))
        ttk.Button(bar, text="Eşlemeyi Doğrula (Dry-Run)", command=lambda: self._dry_run(parent, kind)).pack(side="left")
        ttk.Button(bar, text="DB'ye Aktar", command=lambda: self._import_to_db(parent, kind)).pack(side="left", padx=8)

        # Sonuç mesajı
        result = ttk.Label(parent, text="", foreground="#444")
        result.pack(anchor="w", padx=10)
        setattr(parent, "result_label", result)

        # Önizleme tablosu
        tree = ttk.Treeview(parent, show="headings", height=12)
        tree.pack(fill="both", expand=True, padx=10, pady=8)
        setattr(parent, "tree", tree)

    # ------------------ Dosya/Önizleme ------------------

    def _choose_file(self, var: tk.StringVar):
        path = filedialog.askopenfilename(
            title="Excel dosyası seç",
            filetypes=[("Excel", "*.xlsx *.xls")]
        )
        if path:
            var.set(path)

    def _preview(self, parent, path: str, kind: str):
        try:
            if not path:
                messagebox.showwarning("Uyarı", "Önce bir dosya seçin."); return

            df, err = try_preview_xlsx(path)
            if err:
                messagebox.showerror("Hata", err); return
            if df is None or df.empty:
                messagebox.showinfo("Bilgi", "Veri bulunamadı."); return

            # Ders sayfasını normalize etmeyi dene (üst başlık bloklarını tek tabloya çevirir)
            if kind == "courses":
                try:
                    df2 = normalize_courses_df(df)
                    if df2 is not None and not df2.empty:
                        df = df2
                except Exception:
                    pass

            # Bazı Excel'lerde kolon isimleri üst satırlarda olabilir → basit başlık arama
            if self._looks_like_misheaded(df):
                df = self._repair_headers(df)

            # Önizlemeyi doldur
            tree: ttk.Treeview = getattr(parent, "tree")
            for i in tree.get_children(): tree.delete(i)
            cols = list(map(str, df.columns))
            tree["columns"] = cols
            for c in cols:
                tree.heading(c, text=c)
                tree.column(c, width=160 if c.lower() not in ("ad", "ad soyad", "dersin adı", "name") else 240)

            for _, row in df.head(10).iterrows():
                tree.insert("", "end", values=[row.get(c, "") for c in cols])

            # Özet/dağılım bilgisi
            info = getattr(parent, "result_label")
            year_col = self._find_year_col(df.columns)
            if year_col:
                dist = df[year_col].value_counts(dropna=False).to_dict()
                info.config(text=f"Önizleme — {year_col} dağılımı: {dist}")
            else:
                info.config(text=f"Önizleme — Kolonlar: {list(df.columns)}")

            self._df_cache[kind] = df
            # Sütun eşleme varsayılanlarını akıllıca öner
            self._build_mapping(parent, cols, kind, suggest_from=cols)

        except Exception:
            messagebox.showerror("Önizleme Hatası", traceback.format_exc())

    @staticmethod
    def _looks_like_misheaded(df) -> bool:
        if len(df.columns) == 0: return False
        unnamed_ratio = sum(str(c).startswith("Unnamed") for c in df.columns) / len(df.columns)
        return unnamed_ratio > 0.5

    def _repair_headers(self, df):
        df0 = df.copy()
        header_row = None
        for i in range(min(5, len(df0))):
            row_vals = df0.iloc[i].astype(str).str.upper().tolist()
            if any("DERS" in v or "KOD" in v for v in row_vals):
                header_row = i; break
        if header_row is not None:
            new_cols = df0.iloc[header_row].astype(str).tolist()
            df = df0.iloc[header_row + 1:].reset_index(drop=True)
            df.columns = new_cols
            for c in df0.columns:
                m = re.search(r"([1-8])\s*\.?\s*sınıf", str(c), re.I)
                if m and "Sınıf(Yıl)" not in df.columns:
                    df["Sınıf(Yıl)"] = int(m.group(1))
                    break
        return df

    # ------------------ Sütun Eşleme ------------------

    def _build_mapping(self, parent, cols: List[str], kind: str, suggest_from: List[str]):
        frame: ttk.LabelFrame = getattr(parent, "map_frame")
        for w in frame.winfo_children(): w.destroy()

        fields = REQUIRED_COURSE_FIELDS if kind == "courses" else REQUIRED_STUDENT_FIELDS
        self._maps.setdefault(kind, {})

        suggestions = self._suggest_mapping(fields, suggest_from)

        for i, field in enumerate(fields):
            ttk.Label(frame, text=field).grid(row=i, column=0, sticky="e", padx=6, pady=4)
            var = tk.StringVar(value=suggestions.get(field, (cols[0] if cols else "")))
            cb = ttk.Combobox(frame, textvariable=var, values=cols, state="readonly", width=36)
            cb.grid(row=i, column=1, sticky="w", padx=6, pady=4)
            self._maps[kind][field] = var

    @staticmethod
    def _suggest_mapping(fields: Tuple[str, ...], cols: List[str]) -> Dict[str, str]:
        # Kolon adlarını normalize edip alanlarla eşleştirir
        norm_cols = {ImportView._norm_colname(c): c for c in cols}
        suggestions = {}
        for f in fields:
            nf = ImportView._norm_colname(f)
            aliases = {
                "kod": ["kod", "derskodu", "ders kodu", "code"],
                "ad": ["ad", "adı", "dersinadı", "dersin adı", "name", "ders adı"],
                "sınıfyıl": ["sınıf", "sınıf(yıl)", "sinif", "classyear", "class_year", "yıl", "yil"],
                # Zorunluluk alanını genişlettik:
                "zorunlueh": [
                    "zorunlu", "zorunlu(e/h)", "zorunluluk",
                    "compulsory", "zorunluluk(e/h)",
                    "dersin yapısı", "dersin yapişi", "ders yapısı", "dersin yapişi",
                    "zorunlu/seçmeli", "zorunlu secmeli", "ders tipi", "ders türü"
                ],

                "öğretimüy": ["öğretim üyesi", "ogretim uyesi", "öğr. elemanı", "instructor", "ogretimuyesi", "hoca", "öğretim elemanı"],
                "numara": ["numara", "öğrenci no", "ogrenci no", "number", "ogrno", "ogr no"],
                "adsoyad": ["ad soyad", "ad-soyad", "full name", "fullname", "full_name", "name"],
                "derslervirgüllekodlar": ["dersler", "ders kodları", "courses", "course codes", "kodlar"]
            }
            key = nf.replace(" ", "")
            for k, alist in aliases.items():
                if key.startswith(k):
                    for a in alist:
                        nc = ImportView._norm_colname(a)
                        if nc in norm_cols:
                            suggestions[f] = norm_cols[nc]
                            break
                    break
        return suggestions

    @staticmethod
    def _norm_colname(x: str) -> str:
        return re.sub(r"[\s_\-()]+", "", str(x or "").strip().lower())

    # ------------------ Dry-Run ------------------

    def _dry_run(self, parent, kind: str):
        result: ttk.Label = getattr(parent, "result_label")
        df = self._df_cache.get(kind)
        if df is None:
            result.config(text="Önce dosyayı önizleyin."); return

        colmap = {k: v.get() for k, v in self._maps.get(kind, {}).items()}
        if any(not v for v in colmap.values()):
            result.config(text="⚠️ Lütfen tüm alanlar için sütun seçin."); return

        if kind == "courses":
            ok, warn = self._validate_courses(df, colmap)
        else:
            ok, warn = self._validate_students(df, colmap)

        if ok == 0:
            result.config(text="Hiç geçerli satır bulunamadı.")
        else:
            msg = f"✅ {ok} satır geçerli."
            if warn: msg += f"  ⚠️ {warn} satır atlandı (eksik/hatalı)."
            result.config(text=msg)

    def _validate_courses(self, df, colmap) -> Tuple[int, int]:
        ok = warn = 0
        for _, row in df.iterrows():
            try:
                code = self._norm_code(row[colmap["Kod"]])
                name = str(row[colmap["Ad"]]).strip()
                cls  = self._to_int(row[colmap["Sınıf(Yıl)"]])
                if self._fixed_year.get():
                    cls = int(self._fixed_year.get())
                comp_raw = str(row[colmap["Zorunlu(E/H)"]]).strip().upper()
                if not code or not name or cls is None or not (1 <= cls <= 8):
                    warn += 1; continue
                _ = self._to_compulsory(comp_raw)  # sadece doğrulama
                ok += 1
            except Exception:
                warn += 1
        return ok, warn

    def _validate_students(self, df, colmap) -> Tuple[int, int]:
        ok = warn = 0
        for _, row in df.iterrows():
            try:
                num = self._clean_number(row[colmap["Numara"]])
                name = str(row[colmap["Ad Soyad"]]).strip()
                cls  = self._to_int(row[colmap["Sınıf(Yıl)"]])
                codes = [self._norm_code(c) for c in self._split_codes(str(row[colmap["Dersler(virgülle kodlar)"]]))]
                if not num or not name or cls is None or not (1 <= cls <= 8):
                    warn += 1; continue
                _ = codes  # boş olabilir
                ok += 1
            except Exception:
                warn += 1
        return ok, warn

    # ------------------ DB'ye Aktar ------------------

    def _import_to_db(self, parent, kind: str):
        df = self._df_cache.get(kind)
        if df is None:
            messagebox.showwarning("Uyarı", "Önce dosyayı önizleyin."); return

        colmap = {k: v.get() for k, v in self._maps.get(kind, {}).items()}
        if any(not v for v in colmap.values()):
            messagebox.showwarning("Uyarı", "Tüm alanlar için sütun seçin."); return

        dept_id = self.user.get("department_id") or 1
        try:
            with get_conn() as con:
                cur = con.cursor()

                if kind == "courses":
                    ok = warn = 0
                    for _, row in df.iterrows():
                        try:
                            code = self._norm_code(row[colmap["Kod"]])
                            name = str(row[colmap["Ad"]]).strip()
                            cls  = self._to_int(row[colmap["Sınıf(Yıl)"]])
                            if self._fixed_year.get():
                                cls = int(self._fixed_year.get())
                            comp = self._to_compulsory(str(row[colmap["Zorunlu(E/H)"]]).strip())
                            instr = str(row[colmap["Öğretim Üyesi"]]).strip()

                            if not code or not name or cls is None or not (1 <= cls <= 8):
                                warn += 1; continue

                            # UPSERT (öncelik: dept_id + code benzersizliği)
                            try:
                                cur.execute("""
                                    INSERT INTO courses(dept_id, code, name, instructor, class_year, is_compulsory)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                    ON CONFLICT(dept_id, code) DO UPDATE SET
                                        name          = excluded.name,
                                        instructor    = excluded.instructor,
                                        class_year    = excluded.class_year,
                                        is_compulsory = excluded.is_compulsory
                                """, (dept_id, code, name, instr, cls, comp))
                            except Exception:
                                # Şemanızda UNIQUE yoksa graceful fallback:
                                cur.execute("""
                                    INSERT OR IGNORE INTO courses(dept_id, code, name, instructor, class_year, is_compulsory)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (dept_id, code, name, instr, cls, comp))
                                # varsa güncelle
                                cur.execute("""
                                    UPDATE courses
                                    SET name=?, instructor=?, class_year=?, is_compulsory=?
                                    WHERE dept_id=? AND code=?
                                """, (name, instr, cls, comp, dept_id, code))

                            ok += 1
                        except Exception:
                            warn += 1
                    messagebox.showinfo("Tamam", f"✅ Dersler işlendi. Başarılı: {ok}  ⚠️ Atlanan: {warn}")
                    getattr(parent, "result_label").config(text=f"Dersler: {ok} ok, {warn} atlandı")
                    return

                # --- STUDENTS ---
                ok = warn = 0
                errors = []
                missing_codes_global = set()

                for _, row in df.iterrows():
                    try:
                        num = self._clean_number(row[colmap["Numara"]])
                        name = str(row[colmap["Ad Soyad"]]).strip()
                        cls  = self._to_int(row[colmap["Sınıf(Yıl)"]])
                        codes = [self._norm_code(c) for c in self._split_codes(str(row[colmap["Dersler(virgülle kodlar)"]]))]

                        if not num or not name or cls is None or not (1 <= cls <= 8):
                            warn += 1; continue

                        # Öğrenciyi ekle
                        cur.execute("""
                            INSERT OR IGNORE INTO students(dept_id, number, full_name, class_year)
                            VALUES (?, ?, ?, ?)
                        """, (dept_id, num, name, cls))

                        # id al
                        cur.execute("SELECT id FROM students WHERE dept_id=? AND number=?", (dept_id, num))
                        r = cur.fetchone()
                        if not r:
                            warn += 1; continue
                        sid = r[0]

                        # Ders ilişkileri
                        for code in codes:
                            cur.execute("SELECT id FROM courses WHERE dept_id=? AND code=?", (dept_id, code))
                            rc = cur.fetchone()
                            if not rc:
                                missing_codes_global.add(code)
                                continue
                            cid = rc[0]
                            cur.execute("""
                                INSERT OR IGNORE INTO enrollments(student_id, course_id)
                                VALUES (?, ?)
                            """, (sid, cid))

                        ok += 1

                    except Exception as e:
                        warn += 1
                        if len(errors) < 3:
                            errors.append(str(e))

                extra = ""
                if missing_codes_global:
                    sample = ", ".join(sorted(list(missing_codes_global))[:15])
                    extra = f"\nEşleşmeyen ders kodu örnekleri ({min(len(missing_codes_global), 15)} / {len(missing_codes_global)}): {sample}"

                msg = f"✅ DB güncellendi. Başarılı: {ok}"
                if warn: msg += f"  ⚠️ Atlanan: {warn}"
                if extra: msg += extra
                messagebox.showinfo("Tamam", msg)
                getattr(parent, "result_label").config(text=msg)

        except Exception as e:
            messagebox.showerror("Hata", f"İçe aktarma başarısız: {e}")

    # ------------------ Yardımcılar ------------------

    @staticmethod
    def _norm_code(text: str) -> str:
        """Ders kodunu karşılaştırmaya uygun forma getirir (MAT 101 → MAT101)."""
        return re.sub(r"[\s\-_]+", "", (str(text) if text is not None else "").strip().upper())

    @staticmethod
    def _clean_number(num) -> str:
        """Öğrenci numarasından rakam dışını temizler (210059017 gibi)."""
        return re.sub(r"\D", "", str(num or ""))

    @staticmethod
    def _to_int(val) -> Optional[int]:
        """'5', '5.0', '5. Sınıf' gibi metinlerden 1–8'i yakalar."""
        if val is None:
            return None
        m = re.search(r"[1-8]", str(val))
        return int(m.group()) if m else None

    @staticmethod
    def _to_compulsory(val: str) -> int:
        """
        Zorunluluk bilgisini çok daha esnek yorumlar.
        Örnek kabul edilenler:
          - Zorunlu:  E, EVET, 1, TRUE, YES, Z, ZORUNLU, ZORUNLU DERS
          - Seçmeli:  H, HAYIR, 0, FALSE, NO, S, SEÇMELİ, SECMELI, SEÇMELİ DERS, SECMELI DERS
        Ayrıca 'Seçmeli ders', 'Zorunlu ders', 'Secmeli', küçük/büyük/şapkalı-şapkasız hepsi desteklenir.
        """
        t = (val or "").strip().upper()

        # TR normalize: ÇŞĞİÜÖ → C S G I U O, ayrıca boşluk/çizgi/alt çizgi sil
        tr_map = str.maketrans({
            "Ç": "C", "Ş": "S", "Ğ": "G", "İ": "I", "Ü": "U", "Ö": "O",
            "ç": "C", "ş": "S", "ğ": "G", "ı": "I", "i": "I", "ü": "U", "ö": "O",
        })
        norm = t.translate(tr_map)
        norm = "".join(ch for ch in norm if ch.isalnum())  # harf-rakam dışını at

        # Bazı yaygın varyantları yakala (içerme veya baş harf)
        # Önce 'SEC' geçen her şeyi seçmeli kabul et (SECMELI, SECMELIDERS vb.)
        if "SEC" in norm:  # SEÇ.../SEC... gördüysek → seçmeli
            return 0
        if "ZORUNLU" in norm or "ZORUNLUDERS" in norm:
            return 1

        # Tek harfli/dijitli kısaltmalar
        if norm in {"E", "EVET", "1", "TRUE", "T", "YES", "Z"}:
            return 1
        if norm in {"H", "HAYIR", "0", "FALSE", "F", "NO", "S"}:
            return 0

        # 'Z' ile başlıyorsa zorunlu, 'S' ile başlıyorsa seçmeli
        if norm.startswith("Z"):
            return 1
        if norm.startswith("S"):
            return 0

        # Belirsizde default PDF uyumluluğu için 'zorunlu'ya düşürmeyelim; uyarı vermek daha güvenli
        # Ancak mevcut akışa dokunmadan geriye 1 yerine 0 döndürmek istersen, aşağıyı 0 yap.
        return 1

    @staticmethod
    def _split_codes(text: str) -> List[str]:
        """Ders kodlarını , ; / ve boşlukla ayırır, boşları atar."""
        t = (text or "").replace(";", ",").replace("/", ",")
        parts = re.split(r"[,\s]+", t)
        return [p for p in parts if p and p.strip()]

    @staticmethod
    def _find_year_col(cols) -> Optional[str]:
        lower = {str(c).strip().lower(): str(c) for c in cols}
        for key in ("sınıf(yıl)", "sinif(yil)", "sınıf", "sinif", "class_year", "classyear", "sınıf (yıl)"):
            if key in lower:
                return lower[key]
        return None
