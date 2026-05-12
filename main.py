# Developed by: Mete Avcı
import os
import sys
import threading
import glob
import re
import traceback
import logging
import customtkinter as ctk
from tkinter import filedialog, messagebox
from tkinterdnd2 import TkinterDnD, DND_FILES
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph, GlyphComponent
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import ControlBoundsPen

# --- THEME OVERRIDE: ULTRA-VISIBILITY LIGHT ---
ctk.set_appearance_mode("Light")

class Tk(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

class FontTurkicizerApp(Tk):
    def __init__(self):
        super().__init__()

        self.lang = ctk.StringVar(value="TR")
        self.translations = {
            "TR": {
                "title": "Yazı Tipi Türkçeleştirici",
                "subtitle": "Font dosyalarınızda eksik olan Türkçe karakterleri (Ğ, Ş, Ç, ₺, â, î, û vb.) otomatik olarak oluşturur ve ekler.",
                "step1": "YÜKLENECEK FONTLAR",
                "add_files": "DOSYA EKLE",
                "add_folder": "KLASÖR EKLE",
                "hint_dnd": "(ya da sürükle bırak...)",
                "clear_list": "TEMİZLE",
                "step2": "ÇIKTI FORMATI:",
                "process_btn": "İŞLEMİ BAŞLAT",
                "status_ready": "SİSTEM_HAZIR",
                "status_processing": "ANALİZ VE OLUŞTURMA DEVAM EDİYOR...",
                "status_success": "TAMAMLANDI: {count} FONT İŞLENDİ",
                "status_partial": "KISMI BAŞARI: {success}/{total}",
                "status_error": "SİSTEM HATASI",
                "msg_success_title": "BAŞARILI",
                "msg_success_body": "{count} font başarıyla Türkçeleştirildi.",
                "msg_error_title": "HATA",
                "msg_error_no_file": "Lütfen önce font ekleyin.",
                "msg_error_body": "Kritik hata:\n{errors}"
            },
            "EN": {
                "title": "Font Turkicizer",
                "subtitle": "Automatically creates and adds missing Turkish characters (Ğ, Ş, Ç, ₺, â, î, û etc.) to your font files.",
                "step1": "ASSETS TO PROCESS",
                "add_files": "ADD FILES",
                "add_folder": "ADD FOLDER",
                "hint_dnd": "(or drag and drop...)",
                "clear_list": "CLEAR ALL",
                "step2": "OUTPUT FORMAT:",
                "process_btn": "START PROCESS",
                "status_ready": "SYSTEM_READY",
                "status_processing": "ANALYZING & CREATING GLYPHS...",
                "status_success": "SUCCESS: {count} FONTS PROCESSED",
                "status_partial": "PARTIAL SUCCESS: {success}/{total}",
                "status_error": "SYSTEM ERROR",
                "msg_success_title": "SUCCESS",
                "msg_success_body": "Successfully processed {count} font(s).",
                "msg_error_title": "ERROR",
                "msg_error_no_file": "Please add fonts first.",
                "msg_error_body": "Critical error:\n{errors}"
            }
        }

        self.title("Yazı Tipi Türkçeleştirici")
        self.geometry("1250x980")
        self.resizable(True, True)
        self.configure(fg_color="#ffffff") 
        
        self.input_paths = []
        self.output_format = ctk.StringVar(value="WOFF2")
        
        self.after(500, self.init_dnd)
        self.build_ui()

    def init_dnd(self):
        try:
            self.update_idletasks()
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.handle_drop)
        except Exception: pass

    def t(self, key, **kwargs):
        text = self.translations[self.lang.get()][key]
        return text.format(**kwargs) if kwargs else text

    def build_ui(self):
        # Ultra Visibility Typography
        self.title_font = ctk.CTkFont(family="Inter", size=56, weight="bold")
        self.subtitle_font = ctk.CTkFont(family="Inter", size=26)
        self.label_font = ctk.CTkFont(family="Inter", size=20, weight="bold")
        self.text_font = ctk.CTkFont(family="Consolas", size=20)
        self.btn_font = ctk.CTkFont(family="Inter", size=18, weight="bold")
        self.dropdown_font = ctk.CTkFont(family="Inter", size=22, weight="bold")
        self.hint_font = ctk.CTkFont(family="Inter", size=16, slant="italic")

        # Main Container
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=70, pady=50)

        # Header Section
        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x", pady=(0, 50))
        
        header_row = ctk.CTkFrame(header, fg_color="transparent")
        header_row.pack(fill="x")
        
        self.title_label = ctk.CTkLabel(header_row, text=self.t("title"), font=self.title_font, text_color="#000000")
        self.title_label.pack(anchor="w", side="left")
        
        # --- CUSTOM LANGUAGE SWITCH ---
        lang_container = ctk.CTkFrame(header_row, fg_color="#eeeeee", corner_radius=10)
        lang_container.pack(side="right", anchor="n")
        
        self.tr_btn = ctk.CTkButton(lang_container, text="TR", width=90, height=50, corner_radius=8, 
                                   font=self.btn_font, command=lambda: self.switch_lang("TR"))
        self.tr_btn.pack(side="left", padx=4, pady=4)
        
        self.en_btn = ctk.CTkButton(lang_container, text="EN", width=90, height=50, corner_radius=8, 
                                   font=self.btn_font, command=lambda: self.switch_lang("EN"))
        self.en_btn.pack(side="left", padx=4, pady=4)
        
        self.update_lang_ui()

        self.subtitle_label = ctk.CTkLabel(header, text=self.t("subtitle"), text_color="#000000", font=self.subtitle_font, wraplength=1000, justify="left")
        self.subtitle_label.pack(anchor="w", pady=(20, 0))

        # 1. FILE MANAGEMENT
        self.file_frame = ctk.CTkFrame(self.container, fg_color="#ffffff", border_width=4, border_color="#000000")
        self.file_frame.pack(fill="both", expand=True, pady=(0, 40))
        
        self.file_label = ctk.CTkLabel(self.file_frame, text=self.t("step1"), font=self.label_font, text_color="#000000")
        self.file_label.pack(anchor="w", padx=35, pady=(35, 20))
        
        self.file_listbox = ctk.CTkTextbox(self.file_frame, height=300, font=self.text_font, 
                                         fg_color="#fcfcfc", border_width=1, border_color="#000000",
                                         text_color="#000000", state="disabled")
        self.file_listbox.pack(fill="both", expand=True, padx=35, pady=(0, 35))
        
        btn_bar = ctk.CTkFrame(self.file_frame, fg_color="transparent")
        btn_bar.pack(fill="x", padx=35, pady=(0, 35))
        
        self.browse_file_btn = self.create_btn(btn_bar, self.t("add_files"), self.browse_files, color="#000000", text_color="#ffffff")
        self.browse_file_btn.pack(side="left", padx=(0, 20))

        self.browse_dir_btn = self.create_btn(btn_bar, self.t("add_folder"), self.browse_folder, color="#000000", text_color="#ffffff")
        self.browse_dir_btn.pack(side="left")
        
        # --- DRAG AND DROP HINT (ITALIC) ---
        self.hint_label = ctk.CTkLabel(btn_bar, text=self.t("hint_dnd"), font=self.hint_font, text_color="#666666")
        self.hint_label.pack(side="left", expand=True)
        
        self.clear_btn = self.create_btn(btn_bar, self.t("clear_list"), self.clear_files, color="#ffffff", border="#000000")
        self.clear_btn.configure(text_color="#000000")
        self.clear_btn.pack(side="right")

        # 2. CONFIGURATION & ACTION
        action_area = ctk.CTkFrame(self.container, fg_color="transparent")
        action_area.pack(fill="x")
        
        self.config_panel = ctk.CTkFrame(action_area, fg_color="#ffffff", border_width=4, border_color="#000000")
        self.config_panel.pack(side="left", fill="both", expand=True, padx=(0, 40))
        
        # --- HORIZONTAL DROP DOWN ROW ---
        format_row = ctk.CTkFrame(self.config_panel, fg_color="transparent")
        format_row.pack(fill="x", padx=35, pady=25)
        
        self.format_label = ctk.CTkLabel(format_row, text=self.t("step2"), font=self.label_font, text_color="#000000")
        self.format_label.pack(side="left")
        
        self.format_dropdown = ctk.CTkOptionMenu(format_row, values=["WOFF2", "TTF", "OTF", "WOFF"], 
                                               variable=self.output_format, font=self.dropdown_font,
                                               fg_color="#ffffff", 
                                               button_color="#f0f0f0",
                                               button_hover_color="#e0e0e0",
                                               text_color="#000000",
                                               dropdown_fg_color="#ffffff", 
                                               dropdown_text_color="#000000",
                                               dropdown_hover_color="#f5f5f5", 
                                               dropdown_font=self.dropdown_font,
                                               width=220,
                                               height=60)
        self.format_dropdown.pack(side="right")

        self.process_btn = ctk.CTkButton(action_area, text=self.t("process_btn"), height=150, width=380,
                                        font=ctk.CTkFont(family="Inter", size=32, weight="bold"), 
                                        command=self.start_processing,
                                        fg_color="#000000", text_color="#ffffff", 
                                        hover_color="#333333", corner_radius=0)
        self.process_btn.pack(side="right", fill="y")

        # Status Footer
        self.status_label = ctk.CTkLabel(self, text=self.t("status_ready"), text_color="#000000", font=self.subtitle_font)
        self.status_label.pack(pady=40)

    def switch_lang(self, lang):
        self.lang.set(lang)
        self.update_lang_ui()
        self.update_texts()

    def update_lang_ui(self):
        if self.lang.get() == "TR":
            self.tr_btn.configure(fg_color="#000000", text_color="#ffffff")
            self.en_btn.configure(fg_color="#ffffff", text_color="#000000")
        else:
            self.tr_btn.configure(fg_color="#ffffff", text_color="#000000")
            self.en_btn.configure(fg_color="#000000", text_color="#ffffff")

    def create_btn(self, parent, text, command, color="#ffffff", text_color="#000000", border="#000000"):
        return ctk.CTkButton(parent, text=text, font=self.btn_font, width=220, height=70, 
                            command=command, fg_color=color, border_width=4, 
                            border_color=border, text_color=text_color, 
                            hover_color="#f5f5f5" if color=="#ffffff" else "#333333", corner_radius=0)

    def update_texts(self, value=None):
        self.title_label.configure(text=self.t("title"))
        self.subtitle_label.configure(text=self.t("subtitle"))
        self.file_label.configure(text=self.t("step1"))
        self.browse_file_btn.configure(text=self.t("add_files"))
        self.browse_dir_btn.configure(text=self.t("add_folder"))
        self.hint_label.configure(text=self.t("hint_dnd"))
        self.clear_btn.configure(text=self.t("clear_list"))
        self.format_label.configure(text=self.t("step2"))
        self.process_btn.configure(text=self.t("process_btn"))
        self.status_label.configure(text=self.t("status_ready"))
        self.title(self.t("title"))

    def handle_drop(self, event):
        paths = self.split_dnd_paths(event.data)
        self.after(300, lambda: threading.Thread(target=self.add_paths_async, args=(paths,), daemon=True).start())

    def split_dnd_paths(self, dnd_string):
        return re.findall(r'\{.*?\}|"[^"]*"|\S+', dnd_string)

    def add_paths_async(self, paths):
        valid_exts = ('.ttf', '.otf', '.woff', '.woff2')
        added_count = 0
        new_paths = []
        for path in paths:
            clean_path = path.strip('{}').strip('"').strip("'")
            if os.path.isdir(clean_path):
                for ext in valid_exts:
                    for f in glob.glob(os.path.join(clean_path, f'**/*{ext}'), recursive=True):
                        if f not in self.input_paths and f not in new_paths:
                            new_paths.append(f); added_count += 1
            elif os.path.isfile(clean_path) and clean_path.lower().endswith(valid_exts):
                if clean_path not in self.input_paths and clean_path not in new_paths:
                    new_paths.append(clean_path); added_count += 1
        if added_count > 0:
            self.input_paths.extend(new_paths)
            self.after(0, self.update_ui_after_add, added_count)

    def update_ui_after_add(self, added_count):
        self.update_listbox()
        self.status_label.configure(text=f"SYSTEM READY: {added_count} ASSETS LOADED. TOTAL: {len(self.input_paths)}", text_color="#000000")

    def browse_files(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Font Files", "*.ttf *.otf *.woff *.woff2"), ("All Files", "*.*")])
        if file_paths: self.add_paths_async(file_paths)

    def browse_folder(self):
        folder_path = filedialog.askdirectory()
        if folder_path: self.add_paths_async([folder_path])

    def clear_files(self):
        self.input_paths = []
        self.update_listbox()
        self.status_label.configure(text=self.t("status_ready"), text_color="#000000")

    def update_listbox(self):
        self.file_listbox.configure(state="normal")
        self.file_listbox.delete("1.0", "end")
        for path in self.input_paths:
            self.file_listbox.insert("end", f" [MOUNTED] {os.path.basename(path)}\n")
        self.file_listbox.configure(state="disabled")

    def start_processing(self):
        if not self.input_paths:
            messagebox.showerror(self.t("msg_error_title"), self.t("msg_error_no_file"))
            return
        self.process_btn.configure(state="disabled", text="PROCESSING...")
        self.status_label.configure(text=self.t("status_processing"), text_color="#000000")
        threading.Thread(target=self.process_all_fonts, daemon=True).start()

    def process_all_fonts(self):
        success_count = 0
        errors = []
        out_ext = self.output_format.get().lower()
        for file_path in self.input_paths:
            try:
                input_dir = os.path.dirname(file_path)
                input_name = os.path.splitext(os.path.basename(file_path))[0]
                output_path = os.path.join(input_dir, f"{input_name}_turkish.{out_ext}")
                font = TTFont(file_path)
                font.recalcBBoxes = True
                self.inject_turkish_glyphs(font)
                font.flavor = out_ext if out_ext.startswith('woff') else None
                font.save(output_path)
                success_count += 1
            except Exception as e:
                errors.append(f"{os.path.basename(file_path)}: {str(e)}")
        self.after(0, self.processing_finished, success_count, len(self.input_paths), errors)

    def processing_finished(self, success_count, total_count, errors):
        self.process_btn.configure(state="normal", text=self.t("process_btn"))
        if success_count == total_count:
            self.status_label.configure(text=self.t("status_success", count=success_count), text_color="#000000")
            messagebox.showinfo(self.t("msg_success_title"), self.t("msg_success_body", count=success_count))
        else:
            self.status_label.configure(text=self.t("status_error"), text_color="#ff0000")

    def inject_turkish_glyphs(self, font):
        is_cff = 'CFF ' in font or 'CFF2' in font
        glyph_set = font.getGlyphSet(); hmtx = font['hmtx']; cmap = font['cmap']
        def map_unicode(name, unicode_val):
            for table in cmap.tables:
                if table.isUnicode(): table.cmap[unicode_val] = name
        def get_glyph_name(unicode_val):
            for table in cmap.tables:
                if table.isUnicode() and unicode_val in table.cmap: return table.cmap[unicode_val]
            return None
        base_unicodes = {'G': 0x0047, 'g': 0x0067, 'I': 0x0049, 'i': 0x0069, 'S': 0x0053, 's': 0x0073, 'C': 0x0043, 'c': 0x0063, 'O': 0x004F, 'o': 0x006F, 'U': 0x0055, 'u': 0x0075, 'A': 0x0041, 'a': 0x0061, 'E': 0x0045, 'e': 0x0065, 'L': 0x004C}
        bases = {k: get_glyph_name(v) for k, v in base_unicodes.items()}
        accent_unicodes = {'breve': 0x02D8, 'dotaccent': 0x02D9, 'cedilla': 0x00B8, 'dieresis': 0x00A8, 'circumflex': 0x005E}
        accents = {k: get_glyph_name(v) or k for k, v in accent_unicodes.items()}
        def add_glyph(name, unicode_val, base_key, accent_key=None, custom_logic=None):
            base_name = bases.get(base_key)
            if not base_name or base_name not in glyph_set: return
            if is_cff: self.add_cff_glyph(font, name, unicode_val, base_name, accent_key, accents, custom_logic)
            else: self.add_glyf_glyph(font, name, unicode_val, base_name, accent_key, accents, custom_logic)
        injections = [('Gbreve', 0x011E, 'G', 'breve'), ('gbreve', 0x011F, 'g', 'breve'), ('Idotaccent', 0x0130, 'I', 'dotaccent'), ('Scedilla', 0x015E, 'S', 'cedilla'), ('scedilla', 0x015F, 's', 'cedilla'), ('Ccedilla', 0x00C7, 'C', 'cedilla'), ('ccedilla', 0x00E7, 'c', 'cedilla'), ('Odieresis', 0x00D6, 'O', 'dieresis'), ('odieresis', 0x00F6, 'o', 'dieresis'), ('Udieresis', 0x00DC, 'U', 'dieresis'), ('udieresis', 0x00FC, 'u', 'dieresis'), ('Acircumflex', 0x00C2, 'A', 'circumflex'), ('acircumflex', 0x00E2, 'a', 'circumflex'), ('Icircumflex', 0x00CE, 'I', 'circumflex'), ('icircumflex', 0x00EE, 'i', 'circumflex'), ('Ucircumflex', 0x00DB, 'U', 'circumflex'), ('ucircumflex', 0x00FB, 'u', 'circumflex'), ('Ocircumflex', 0x00D4, 'O', 'circumflex'), ('ocircumflex', 0x00F4, 'o', 'circumflex'), ('Ecircumflex', 0x00CA, 'E', 'circumflex'), ('ecircumflex', 0x00EA, 'e', 'circumflex')]
        for params in injections: add_glyph(*params)
        if not get_glyph_name(0x0131): add_glyph('idotless', 0x0131, 'i', custom_logic='dotless')
        lira_unicode = 0x20BA
        for table in font['cmap'].tables:
            if lira_unicode in table.cmap: del table.cmap[lira_unicode]
        add_glyph('uni20BA', lira_unicode, 'L', custom_logic='lira')

    def draw_official_lira(self, pen, font, is_bold=False, is_italic=False):
        try:
            cap_height = font['OS/2'].sCapHeight if font['OS/2'].version >= 2 else 700
            if cap_height <= 0: cap_height = 700
        except: cap_height = 700
        scale = cap_height / 455.0; scale_x = 1.2 if is_bold else 1.0; slant = 0.212 if is_italic else 0.0
        def p(x, y):
            nx = (x - 180) * scale * scale_x; ny = (532 - y) * scale
            return (nx + (slant * ny), ny)
        pen.moveTo(p(267, 77)); pen.lineTo(p(267, 213)); pen.lineTo(p(181, 244)); pen.lineTo(p(181, 280)); pen.lineTo(p(267, 249)); pen.lineTo(p(267, 268)); pen.lineTo(p(181, 299)); pen.lineTo(p(181, 336)); pen.lineTo(p(267, 305)); pen.lineTo(p(267, 532)); pen.curveTo(p(282, 533), p(297, 533), p(312, 532)); pen.curveTo(p(320, 531), p(327, 530), p(334, 528)); pen.curveTo(p(350, 524), p(366, 517), p(381, 510)); pen.curveTo(p(450, 469), p(493, 394), p(493, 313)); pen.lineTo(p(448, 313)); pen.curveTo(p(448, 405), p(380, 482), p(289, 494)); pen.lineTo(p(289, 297)); pen.lineTo(p(429, 246)); pen.lineTo(p(429, 210)); pen.lineTo(p(289, 261)); pen.lineTo(p(289, 242)); pen.lineTo(p(429, 191)); pen.lineTo(p(429, 155)); pen.lineTo(p(289, 206)); pen.lineTo(p(289, 87)); pen.closePath()

    def add_glyf_glyph(self, font, name, unicode_val, base_name, accent_key, accents, custom_logic):
        glyf = font['glyf']; hmtx = font['hmtx']; glyph_set = font.getGlyphSet(); new_glyph = Glyph()
        if custom_logic == 'dotless':
            rec_pen = RecordingPen(); glyph_set[base_name].draw(rec_pen)
            new_rec = RecordingPen(); contours = []; current = []
            for cmd, args in rec_pen.value:
                current.append((cmd, args));
                if cmd == 'closePath': contours.append(current); current = []
            if len(contours) > 1:
                dot_idx = 0; max_y = -9999
                for i, c in enumerate(contours):
                    cb_pen = ControlBoundsPen(glyph_set); temp = RecordingPen(); temp.value = c; temp.replay(cb_pen)
                    if cb_pen.bounds and cb_pen.bounds[3] > max_y: max_y, dot_idx = cb_pen.bounds[3], i
                for i, c in enumerate(contours):
                    if i != dot_idx:
                        for cmd, args in c: new_rec.value.append((cmd, args))
            tt_pen = TTGlyphPen(glyph_set); new_rec.replay(tt_pen); new_glyph = tt_pen.glyph()
        elif custom_logic == 'lira':
            is_bold = bool(font['OS/2'].fsSelection & (1 << 5)) if 'OS/2' in font else bool(font['head'].macStyle & (1 << 0))
            is_italic = bool(font['OS/2'].fsSelection & (1 << 0)) if 'OS/2' in font else bool(font['head'].macStyle & (1 << 1))
            tt_pen = TTGlyphPen(glyph_set); self.draw_official_lira(tt_pen, font, is_bold, is_italic); new_glyph = tt_pen.glyph()
            if hasattr(new_glyph, 'flags'): new_glyph.flags = [f & ~(1 << 7) for f in new_glyph.flags]
            if 'head' in font: font['head'].flags |= (1 << 3)
            new_glyph.recalcBounds(glyf)
            hmtx.metrics[name] = (int(hmtx.metrics.get('L', (600, 0))[0] * (1.3 if is_bold else 1.1)), 0)
        elif accent_key:
            accent_name = accents.get(accent_key)
            if not accent_name: return
            new_glyph.numberOfContours = -1; comp_base = GlyphComponent(); comp_base.glyphName = base_name; comp_base.x, comp_base.y, comp_base.flags = 0, 0, 0x0204
            comp_accent = GlyphComponent(); comp_accent.glyphName = accent_name
            b_xmin, b_ymin, b_xmax, b_ymax = self.get_glyph_bounds(glyph_set, base_name)
            a_xmin, a_ymin, a_xmax, a_ymax = self.get_glyph_bounds(glyph_set, accent_name)
            comp_accent.x = int(((b_xmin + b_xmax) / 2) - ((a_xmin + a_xmax) / 2))
            comp_accent.y = b_ymin - a_ymax + 20 if accent_key == 'cedilla' else b_ymax - a_ymin + 50
            comp_accent.flags = 0x0004; new_glyph.components = [comp_base, comp_accent]
        glyf.glyphs[name] = new_glyph
        if name not in hmtx.metrics: hmtx.metrics[name] = list(hmtx.metrics.get(base_name, (500, 0)))
        self.map_unicode(font, name, unicode_val)
        if name not in font.glyphOrder: font.glyphOrder.append(name)

    def add_cff_glyph(self, font, name, unicode_val, base_name, accent_key, accents, custom_logic):
        charstrings = font['CFF '].cff.topDictIndex[0].CharStrings; glyph_set = font.getGlyphSet(); hmtx = font['hmtx']
        if custom_logic == 'lira':
            is_bold = bool(font['OS/2'].fsSelection & (1 << 5)) if 'OS/2' in font else False
            is_italic = bool(font['OS/2'].fsSelection & (1 << 0)) if 'OS/2' in font else False
            t2_pen = T2CharStringPen(600, glyph_set); self.draw_official_lira(t2_pen, font, is_bold, is_italic)
            charstrings[name] = t2_pen.getCharString()
            hmtx.metrics[name] = (int(hmtx.metrics.get('L', (600, 0))[0] * (1.3 if is_bold else 1.1)), 0)
        else:
            rec_pen = RecordingPen(); glyph_set[base_name].draw(rec_pen); t2_pen = T2CharStringPen(hmtx.metrics[base_name][0], glyph_set); rec_pen.replay(t2_pen); charstrings[name] = t2_pen.getCharString()
        self.map_unicode(font, name, unicode_val)
        if name not in font.glyphOrder: font.glyphOrder.append(name)

    def get_glyph_bounds(self, glyph_set, name):
        try:
            cb_pen = ControlBoundsPen(glyph_set); glyph_set[name].draw(cb_pen)
            return cb_pen.bounds if cb_pen.bounds else (0, 0, 0, 0)
        except: return (0, 0, 0, 0)

    def map_unicode(self, font, name, unicode_val):
        for table in font['cmap'].tables:
            if table.isUnicode(): table.cmap[unicode_val] = name

if __name__ == "__main__":
    app = FontTurkicizerApp(); app.mainloop()