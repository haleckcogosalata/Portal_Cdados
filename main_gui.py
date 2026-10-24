"""
main_gui.py — Central de Execução com Interface Gráfica
========================================================
Versão visual do main.py. Mantém todas as funcionalidades:
  - Extração Moodle / Acadêmico (headless ou visual)
  - Upload de CSV para Google Sheets
  - Log de execução em tempo real na tela
"""

import os
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, font, messagebox, scrolledtext, ttk

from config import SHEET_NAME_ACADEMICO, SHEET_NAME_MOODLE, SHEET_NAME_PARTICIPANTES
from upload_to_sheets import upload_csv_to_sheet
from supabase_sync import get_name_adjustments, save_name_adjustment, delete_name_adjustment, get_all_moodle_names

# ---------------------------------------------------------------------------
# Caminhos
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
SCRIPT_MOODLE = BASE_DIR / "Moodle" / "playwright_robo_moodle_notas.py"
SCRIPT_PARTICIPANTES = BASE_DIR / "Moodle" / "playwright_robo_moodle_participantes.py"
SCRIPT_MESCLADO = BASE_DIR / "Moodle" / "playwright_robo_moodle_mesclado.py"
SCRIPT_ACADEMICO = BASE_DIR / "Acadêmico" / "playwright_robo_academico_notas.py"

# ---------------------------------------------------------------------------
# Paleta de cores (tema escuro)
# ---------------------------------------------------------------------------
BG_DARK      = "#0f1117"
BG_PANEL     = "#1a1d27"
BG_CARD      = "#21253a"
BG_INPUT     = "#2a2f45"
ACCENT       = "#4f8ef7"
ACCENT_HOVER = "#6fa3ff"
SUCCESS      = "#34d399"
WARNING      = "#fbbf24"
ERROR        = "#f87171"
TEXT_PRIMARY = "#e2e8f0"
TEXT_MUTED   = "#6b7280"
BORDER       = "#2e3347"

# ---------------------------------------------------------------------------
# Aplicação principal
# ---------------------------------------------------------------------------
class CentralApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Central de Execução — Automação Pós CDADOS")
        self.geometry("920x680")
        self.minsize(800, 580)
        self.configure(bg=BG_DARK)
        self._running = False          # flag: algum processo em execução?
        self._proc: subprocess.Popen | None = None
        self._log_history = []
        self._current_log_student = ""
        self._observed_errors = set()
        self._student_errors = {}
        self._student_tags = {}

        self._build_ui()
        self._log_welcome()

    # ------------------------------------------------------------------
    # Construção da UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        # Fontes
        self._font_title  = font.Font(family="Segoe UI", size=13, weight="bold")
        self._font_label  = font.Font(family="Segoe UI", size=10)
        self._font_btn    = font.Font(family="Segoe UI", size=10, weight="bold")
        self._font_mono   = font.Font(family="Consolas",  size=9)
        self._font_small  = font.Font(family="Segoe UI", size=8)

        # ── Header ──────────────────────────────────────────────────────
        header = tk.Frame(self, bg=BG_PANEL, pady=14)
        header.pack(fill="x")

        tk.Label(
            header, text="⚙  CENTRAL DE EXECUÇÃO",
            font=self._font_title, bg=BG_PANEL, fg=TEXT_PRIMARY,
        ).pack(side="left", padx=20)

        self._status_label = tk.Label(
            header, text="● Pronto",
            font=self._font_small, bg=BG_PANEL, fg=SUCCESS,
        )
        self._status_label.pack(side="right", padx=20)

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x")

        # ── Corpo principal ──────────────────────────────────────────────
        body = tk.Frame(self, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # Coluna esquerda (wrapper com scroll)
        left_wrapper = tk.Frame(body, bg=BG_DARK, width=330)
        left_wrapper.pack(side="left", fill="y", padx=(0, 10))
        left_wrapper.pack_propagate(False)

        left_canvas = tk.Canvas(left_wrapper, bg=BG_DARK, highlightthickness=0)
        left_scrollbar = ttk.Scrollbar(left_wrapper, orient="vertical", command=left_canvas.yview)
        left = tk.Frame(left_canvas, bg=BG_DARK)

        left.bind(
            "<Configure>",
            lambda e: left_canvas.configure(
                scrollregion=left_canvas.bbox("all")
            )
        )
        
        # Mantém a largura original dos cards (310px) dentro do canvas
        left_canvas.create_window((0, 0), window=left, anchor="nw", width=310)
        left_canvas.configure(yscrollcommand=left_scrollbar.set)

        left_canvas.pack(side="left", fill="both", expand=True)
        left_scrollbar.pack(side="right", fill="y")

        # Scroll pelo scroll do mouse (roda do mouse)
        def _on_mousewheel(event):
            left_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        left_wrapper.bind("<Enter>", lambda _: left_wrapper.bind_all("<MouseWheel>", _on_mousewheel))
        left_wrapper.bind("<Leave>", lambda _: left_wrapper.unbind_all("<MouseWheel>"))

        self._build_extraction_card(left)
        self._build_upload_card(left)
        self._build_supabase_card(left)
        self._build_tools_card(left)
        self._build_stop_btn(left)

        # Coluna direita (log)
        right = tk.Frame(body, bg=BG_DARK)
        right.pack(side="left", fill="both", expand=True)

        self._build_log_panel(right)

    # ── Card: Extração ───────────────────────────────────────────────────
    def _build_extraction_card(self, parent):
        card = self._card(parent, "📥  EXTRAÇÃO DE DADOS")

        # Modo de execução
        tk.Label(card, text="Modo de execução:", font=self._font_label,
                 bg=BG_CARD, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 4))

        self._modo_var = tk.StringVar(value="headless")
        row_modo = tk.Frame(card, bg=BG_CARD)
        row_modo.pack(fill="x", pady=(0, 10))

        for texto, valor in [("Headless (rápido)", "headless"), ("Visual (navegador)", "visual")]:
            tk.Radiobutton(
                row_modo, text=texto, variable=self._modo_var, value=valor,
                bg=BG_CARD, fg=TEXT_PRIMARY, selectcolor=BG_INPUT,
                activebackground=BG_CARD, activeforeground=ACCENT,
                font=self._font_label,
            ).pack(side="left", padx=(0, 12))

        btns = [
            ("Extrair Moodle Completo",     self._abrir_modal_moodle_mesclado),
            ("Extrair Moodle Notas",        self._abrir_modal_moodle),
            ("Extrair Moodle Participantes",self._abrir_modal_participantes),
            ("Extrair Acadêmico",           self._abrir_modal_academico),
            ("Extrair Moodle → Acadêmico",  self._abrir_modal_pipeline),
        ]
        for txt, cmd in btns:
            self._btn(card, txt, cmd, color=ACCENT).pack(fill="x", pady=3)

    # ── Card: Upload ──────────────────────────────────────────────────────
    def _build_upload_card(self, parent):
        card = self._card(parent, "☁  UPLOAD → GOOGLE SHEETS")

        self._btn(card, "Enviar CSV do Moodle",    self._upload_moodle,   color="#7c3aed").pack(fill="x", pady=3)
        self._btn(card, "Enviar CSV de Participantes", self._upload_participantes, color="#7c3aed").pack(fill="x", pady=3)
        self._btn(card, "Enviar CSV do Acadêmico", self._upload_academico, color="#7c3aed").pack(fill="x", pady=3)

    # ── Card: Supabase ────────────────────────────────────────────────────
    def _build_supabase_card(self, parent):
        card = self._card(parent, "🗄️  SUPABASE → SHEETS")

        self._btn(card, "Sincronizar Todos", self._supabase_todos, color="#8b5cf6").pack(fill="x", pady=2)
        self._btn(card, "Sincronizar Moodle Notas",    self._supabase_moodle,   color="#10b981").pack(fill="x", pady=2)
        self._btn(card, "Sincronizar Moodle Acessos", self._supabase_participantes, color="#10b981").pack(fill="x", pady=2)
        self._btn(card, "Sincronizar Acadêmico", self._supabase_academico, color="#10b981").pack(fill="x", pady=2)
        self._btn(card, "Comparar Moodle x Acadêmico", self._comparar_moodle_academico, color="#f59e0b").pack(fill="x", pady=2)
        self._btn(card, "Reprocessar Acadêmico (Faltantes)", self._reprocessar_academico_faltantes, color="#f59e0b").pack(fill="x", pady=2)

    # ── Card: Ferramentas ──────────────────────────────────────────────────
    def _build_tools_card(self, parent):
        card = self._card(parent, "🔧  FERRAMENTAS")
        self._btn(card, "Ajuste de Nomes (Moodle → SIORG)", self._abrir_modal_ajuste_nomes, color="#3b82f6").pack(fill="x", pady=2)

    # ── Botão parar ───────────────────────────────────────────────────────
    def _build_stop_btn(self, parent):
        self._stop_btn = self._btn(parent, "⏹  Interromper execução", self._stop_process, color=ERROR)
        self._stop_btn.pack(fill="x", pady=(8, 0))
        self._stop_btn.config(state="disabled")

        self._history_btn = self._btn(parent, "📜  Histórico de Logs", self._abrir_modal_historico, color=TEXT_MUTED)
        self._history_btn.pack(fill="x", pady=(8, 0))

    # ── Painel de log ─────────────────────────────────────────────────────
    def _build_log_panel(self, parent):
        header = tk.Frame(parent, bg=BG_PANEL, pady=6)
        header.pack(fill="x")

        # Controles superiores (Título + Filtros)
        controls = tk.Frame(header, bg=BG_PANEL)
        controls.pack(fill="x", padx=10)

        # Linha 1: Título + Radiobuttons
        row1 = tk.Frame(controls, bg=BG_PANEL)
        row1.pack(fill="x", pady=(0, 4))
        
        tk.Label(row1, text="📋  LOG DE EXECUÇÃO",
                 font=self._font_label, bg=BG_PANEL, fg=TEXT_PRIMARY).pack(side="left")

        radio_frame = tk.Frame(row1, bg=BG_PANEL)
        radio_frame.pack(side="right")

        self._filter_var = tk.StringVar(value="Todos")
        for f_text in ["Todos", "Sucesso", "Avisos", "Falhas", "Erros"]:
            tk.Radiobutton(
                radio_frame, text=f_text, variable=self._filter_var, value=f_text,
                bg=BG_PANEL, fg=TEXT_PRIMARY, selectcolor=BG_CARD,
                activebackground=BG_PANEL, activeforeground=ACCENT,
                font=self._font_small, indicatoron=0, bd=1, relief="flat", padx=6,
                command=self._schedule_filter
            ).pack(side="left", padx=2)

        tk.Button(
            radio_frame, text="Limpar", font=self._font_small,
            bg=BG_INPUT, fg=TEXT_MUTED, relief="flat", bd=0,
            activebackground=BG_CARD, activeforeground=TEXT_PRIMARY,
            cursor="hand2", command=self._clear_log,
        ).pack(side="left", padx=(6, 0))

        # Linha 2: Dropdown de Erros + Barra de Busca
        row2 = tk.Frame(controls, bg=BG_PANEL)
        row2.pack(fill="x", pady=2)

        error_frame = tk.Frame(row2, bg=BG_INPUT, bd=0)
        error_frame.pack(side="left")

        tk.Label(error_frame, text="⚠ Filtrar Problema:", bg=BG_INPUT, fg=TEXT_MUTED, font=self._font_small).pack(side="left", padx=(6, 2))
        self._error_filter_var = tk.StringVar(value="Todos")
        self._error_combo = ttk.Combobox(
            error_frame, textvariable=self._error_filter_var, state="readonly",
            font=self._font_small, width=45, values=["Todos"]
        )
        self._error_combo.pack(side="left", padx=(0, 2), pady=2)
        self._error_combo.bind("<<ComboboxSelected>>", self._schedule_filter)

        search_frame = tk.Frame(row2, bg=BG_INPUT, bd=0)
        search_frame.pack(side="right")

        tk.Label(search_frame, text="🔍", bg=BG_INPUT, fg=TEXT_MUTED).pack(side="left", padx=(4, 2))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._schedule_filter)
        
        search_entry = tk.Entry(
            search_frame, textvariable=self._search_var, font=self._font_small,
            bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", bd=0, width=25
        )
        search_entry.pack(side="left", padx=2, ipady=3)

        # Barra de Progresso Exclusiva
        prog_frame = tk.Frame(header, bg=BG_PANEL)
        prog_frame.pack(fill="x", padx=10, pady=(6, 0))

        self._progress_var = tk.DoubleVar()
        self._progress_bar = ttk.Progressbar(prog_frame, variable=self._progress_var, maximum=100)
        self._progress_bar.pack(side="left", fill="x", expand=True)

        self._progress_label = tk.Label(prog_frame, text="0%", font=self._font_small, bg=BG_PANEL, fg=TEXT_PRIMARY, anchor="e")
        self._progress_label.pack(side="right", padx=(5, 0))

        # Cronometro e ETA
        self._timer_label = tk.Label(header, text="Tempo: 00:00 | Estimativa: --:--", font=self._font_small, bg=BG_PANEL, fg=TEXT_MUTED)
        self._timer_label.pack(anchor="e", padx=10, pady=(2, 0))

        self._log = scrolledtext.ScrolledText(
            parent, bg=BG_DARK, fg=TEXT_PRIMARY,
            font=self._font_mono, relief="flat", bd=0,
            state="disabled", wrap="word",
            insertbackground=TEXT_PRIMARY,
        )
        self._log.pack(fill="both", expand=True, padx=4, pady=(4, 0))

        # Tags de cores
        self._log.tag_config("ok",      foreground=SUCCESS)
        self._log.tag_config("erro",    foreground=ERROR)
        self._log.tag_config("falha",   foreground="#f97316") # Laranja
        self._log.tag_config("warn",    foreground=WARNING)
        self._log.tag_config("info",    foreground=ACCENT)
        self._log.tag_config("muted",   foreground=TEXT_MUTED)
        self._log.tag_config("header",  foreground=ACCENT, font=self._font_btn)
        self._log.tag_config("default", foreground=TEXT_PRIMARY)

    # ------------------------------------------------------------------
    # Helpers de UI
    # ------------------------------------------------------------------
    def _card(self, parent, title: str) -> tk.Frame:
        wrapper = tk.Frame(parent, bg=BG_CARD, bd=0, relief="flat",
                           highlightbackground=BORDER, highlightthickness=1)
        wrapper.pack(fill="x", pady=(0, 10))

        tk.Label(wrapper, text=title, font=self._font_btn,
                 bg=BG_CARD, fg=TEXT_PRIMARY).pack(anchor="w", padx=12, pady=(10, 6))

        sep = tk.Frame(wrapper, bg=BORDER, height=1)
        sep.pack(fill="x", padx=12)

        inner = tk.Frame(wrapper, bg=BG_CARD, padx=12, pady=10)
        inner.pack(fill="x")
        return inner

    def _btn(self, parent, text: str, command, color: str = ACCENT) -> tk.Button:
        btn = tk.Button(
            parent, text=text, command=command,
            bg=color, fg="white", relief="flat", bd=0,
            font=self._font_btn, cursor="hand2",
            activebackground=ACCENT_HOVER, activeforeground="white",
            pady=9,
        )
        btn.bind("<Enter>", lambda e: btn.config(bg=self._lighten(color)))
        btn.bind("<Leave>", lambda e: btn.config(bg=color))
        return btn

    @staticmethod
    def _lighten(hex_color: str) -> str:
        """Clareia levemente uma cor hex."""
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        factor = 1.15
        r = min(255, int(r * factor))
        g = min(255, int(g * factor))
        b = min(255, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _build_multiselect(self, parent):
        frame = tk.Frame(parent, bg=BG_CARD)
        
        search_var = tk.StringVar()
        search_entry = tk.Entry(frame, textvariable=search_var, bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", font=self._font_label, bd=0)
        search_entry.pack(fill="x", pady=(0, 5), ipady=3)

        btn_frame = tk.Frame(frame, bg=BG_CARD)
        btn_frame.pack(fill="x", pady=(0, 5))
        
        state = {
            "all_items": [],
            "selected": set(),
            "displayed": []
        }

        def render_list(*args):
            search_text = search_var.get().lower()
            listbox.delete(0, tk.END)
            state["displayed"] = []
            for item in state["all_items"]:
                if search_text in item.lower():
                    prefix = "[ X ] " if item in state["selected"] else "[   ] "
                    listbox.insert(tk.END, prefix + item)
                    if item in state["selected"]:
                        listbox.itemconfig(tk.END, foreground=SUCCESS)
                    state["displayed"].append(item)

        def select_all():
            for item in state["displayed"]:
                state["selected"].add(item)
            render_list()

        def deselect_all():
            state["selected"].clear()
            render_list()

        tk.Button(btn_frame, text="Selecionar Visíveis", font=self._font_small, bg=BG_INPUT, fg=TEXT_PRIMARY, relief="flat", bd=0, command=select_all, padx=5, pady=2).pack(side="left", padx=(0, 5))
        tk.Button(btn_frame, text="Desmarcar Todos", font=self._font_small, bg=BG_INPUT, fg=TEXT_PRIMARY, relief="flat", bd=0, command=deselect_all, padx=5, pady=2).pack(side="left")
        
        list_frame = tk.Frame(frame, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        listbox = tk.Listbox(list_frame, bg=BG_INPUT, fg=TEXT_PRIMARY, bd=0, highlightthickness=0, font=self._font_small, selectbackground=ACCENT, yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=listbox.yview)
        
        search_var.trace_add("write", render_list)
        
        def on_click(evt):
            sel = listbox.curselection()
            if not sel: return
            idx = sel[0]
            item = state["displayed"][idx]
            if item in state["selected"]:
                state["selected"].remove(item)
            else:
                state["selected"].add(item)
            render_list()
            
        listbox.bind("<ButtonRelease-1>", on_click)
        
        def set_items(items):
            state["all_items"] = items
            state["selected"].clear()
            search_var.set("")
            render_list()
            
        def get_selected():
            return list(state["selected"])
            
        return frame, set_items, get_selected


    # ------------------------------------------------------------------
    # Log
    # ------------------------------------------------------------------
    def _log_write(self, text: str, tag: str = "default"):
        # Detect student context
        if "Processando:" in text:
            match = re.search(r"Processando:\s*(.+)", text)
            if match:
                self._current_log_student = match.group(1).lower()
        elif "AUTOMACAO FINALIZADA" in text or "Pipeline concluído" in text or "Iniciando instancia" in text:
            self._current_log_student = ""

        # We can also detect "🧑‍🎓 Aluno" to reset context
        if "🧑‍🎓 Aluno" in text:
            self._current_log_student = ""

        student_context = self._current_log_student
        
        log_entry = {"text": text, "tag": tag, "student": student_context}
        self._log_history.append(log_entry)

        # Atualizar tags do estudante para filtros baseados em bloco
        if student_context:
            if student_context not in self._student_tags:
                self._student_tags[student_context] = set()
            old_tags = self._student_tags[student_context].copy()
            self._student_tags[student_context].add(tag)

            # Redesenhar log se a nova tag alterar a visibilidade do bloco no filtro ativo
            f = self._filter_var.get()
            if f == "Avisos" and "warn" not in old_tags and tag == "warn":
                self._schedule_filter()
            elif f == "Falhas" and "falha" not in old_tags and tag == "falha":
                self._schedule_filter()
            elif f == "Erros" and "erro" not in old_tags and tag == "erro":
                self._schedule_filter()
            elif f == "Sucesso" and ("erro" not in old_tags and "falha" not in old_tags) and (tag in ("erro", "falha")):
                self._schedule_filter()

        # Registro de erros para o filtro por tipo de erro
        if tag in ("erro", "falha", "warn") and student_context:
            # Limpar formatações e emojis
            clean_text = re.sub(r"\[ERRO\]|\[AVISO\]|[⚠️⛔❌✅ℹ️]", "", text).strip()
            # Limita a 80 caracteres para não estourar o combobox visualmente
            display_error = (clean_text[:77] + "...") if len(clean_text) > 80 else clean_text
            
            if student_context not in self._student_errors:
                self._student_errors[student_context] = set()
            self._student_errors[student_context].add(display_error)
            
            if display_error not in self._observed_errors:
                self._observed_errors.add(display_error)
                current_vals = ["Todos"] + sorted(list(self._observed_errors))
                self._error_combo["values"] = current_vals

        if self._should_show_line(text, tag, student_context):
            self._log.config(state="normal")
            self._log.insert("end", text + "\n", tag)
            self._log.see("end")
            self._log.config(state="disabled")

    def _should_show_line(self, text: str, tag: str, student_context: str) -> bool:
        f = self._filter_var.get()
        error_f = self._error_filter_var.get()
        search_text = getattr(self, "_search_var", tk.StringVar()).get().strip().lower()

        # Ocultar logs globais se um filtro específico estiver ativo
        if f != "Todos" and not student_context:
            return False

        tags_of_student = self._student_tags.get(student_context, set()) if student_context else {tag}

        if f == "Sucesso":
            if "erro" in tags_of_student or "falha" in tags_of_student:
                return False
        elif f == "Avisos":
            if "warn" not in tags_of_student:
                return False
        elif f == "Falhas":
            if "falha" not in tags_of_student:
                return False
        elif f == "Erros":
            if "erro" not in tags_of_student:
                return False

        if error_f != "Todos":
            if not student_context:
                return False
            elif error_f not in self._student_errors.get(student_context, set()):
                return False

        if search_text:
            if search_text not in text.lower() and search_text not in student_context:
                return False

        return True

    def _log_welcome(self):
        self._log_write("=" * 56, "muted")
        self._log_write("  CENTRAL DE EXECUÇÃO — AUTOMAÇÃO PÓS CDADOS", "header")
        self._log_write(f"  {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", "muted")
        self._log_write("=" * 56, "muted")
        self._log_write("Selecione uma ação no painel à esquerda.", "muted")
        self._log_write("")

    def _log_separator(self):
        self._log_write("-" * 56, "muted")

    def _clear_log(self):
        self._log_history = []
        self._current_log_student = ""
        self._observed_errors = set()
        self._student_errors = {}
        self._student_tags = {}
        if hasattr(self, "_error_combo"):
            self._error_combo["values"] = ["Todos"]
            self._error_filter_var.set("Todos")
        
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._update_progress(0)
        self._log_welcome()

    def _update_progress(self, pct: int, texto: str = ""):
        self._progress_var.set(pct)
        if texto:
            self._progress_label.config(text=f"{texto} - {pct}%")
            
            # Extrai quantidade de buscas (ex: "1/5") para o cálculo do ETA
            match = re.search(r"(\d+)/(\d+)", texto)
            if match:
                self._current_item = int(match.group(1))
                self._total_items = int(match.group(2))
        else:
            self._progress_label.config(text=f"{pct}%")

    def _schedule_filter(self, *args):
        if hasattr(self, "_filter_timer"):
            self.after_cancel(self._filter_timer)
        self._filter_timer = self.after(300, self._apply_filter)

    def _apply_filter(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        
        for entry in self._log_history:
            text = entry["text"]
            tag = entry["tag"]
            student_context = entry["student"]

            if self._should_show_line(text, tag, student_context):
                self._log.insert("end", text + "\n", tag)

        self._log.see("end")
        self._log.config(state="disabled")

    def _save_current_log(self):
        if len(self._log_history) < 6:
            return
        last_entry = self._log_history[-1]["text"]
        if hasattr(self, "_last_saved_log_text") and self._last_saved_log_text == last_entry:
            return
        self._last_saved_log_text = last_entry
            
        logs_dir = BASE_DIR / "Logs"
        logs_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / f"log_{timestamp}.txt"
        
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                for entry in self._log_history:
                    f.write(entry["text"] + "\n")
        except Exception as e:
            print(f"Erro ao salvar log: {e}")

    # ------------------------------------------------------------------
    # Estado de execução
    # ------------------------------------------------------------------
    def _set_running(self, running: bool):
        self._running = running
        state = "disabled" if running else "normal"
        stop_state = "normal" if running else "disabled"

        # Altera todos os botões de ação (exceto "Interromper")
        for widget in self.winfo_children():
            self._toggle_buttons(widget, state)

        self._stop_btn.config(state=stop_state)

        if running:
            self._status_label.config(text="● Executando...", fg=WARNING)
            self._start_time = datetime.now()
            self._current_item = 0
            self._total_items = 0
            self._timer_label.config(text="Tempo: 00:00 | Estimativa: --:--")
            self._update_timer_ui()
        else:
            self._status_label.config(text="● Pronto", fg=SUCCESS)
            self._proc = None
            self._start_time = None
            if hasattr(self, '_timer_label'):
                self._timer_label.config(text="Tempo: --:-- | Estimativa: --:--")
            
            if hasattr(self, "_log_history") and self._log_history:
                self._save_current_log()

    def _update_timer_ui(self):
        if not self._running or not self._start_time:
            return

        elapsed = (datetime.now() - self._start_time).total_seconds()
        m, s = divmod(int(elapsed), 60)
        elapsed_str = f"{m:02d}:{s:02d}"

        eta_str = "--:--"
        if hasattr(self, '_current_item') and self._current_item > 0 and self._total_items > self._current_item:
            items_per_sec = self._current_item / elapsed if elapsed > 0 else 0
            if items_per_sec > 0:
                remaining = self._total_items - self._current_item
                eta_sec = remaining / items_per_sec
                eta_m, eta_s = divmod(int(eta_sec), 60)
                eta_str = f"{eta_m:02d}:{eta_s:02d}"

        self._timer_label.config(text=f"Tempo: {elapsed_str} | Estimativa de conclusão: {eta_str}")
        self.after(1000, self._update_timer_ui)

    def _toggle_buttons(self, widget, state):
        if isinstance(widget, tk.Button) and widget != self._stop_btn:
            try:
                widget.config(state=state)
            except Exception:
                pass
        for child in widget.winfo_children():
            self._toggle_buttons(child, state)

    # ------------------------------------------------------------------
    # Execução de script em thread
    # ------------------------------------------------------------------
    def _executar_script(self, caminho: Path, nome: str, args: list[str] | None = None,
                         callback=None):
        """Executa um script externo em background, streamando o output no log."""
        if not caminho.exists():
            self._log_write(f"[ERRO] Script não encontrado: {caminho}", "erro")
            self._set_running(False)
            return False

        self._log_write(f"\n▶  Iniciando: {nome}", "info")
        self._log_separator()

        cmd = [sys.executable, "-u", str(caminho)]
        if args:
            cmd.extend(args)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
            self._proc = proc

            for line in iter(proc.stdout.readline, ""):
                stripped = line.rstrip()
                
                # Detecta a barra de progresso ex: 🧑‍🎓 Aluno 1/5 [████---] 45%
                match = re.search(r"^(.*?)\s*\[.*?\]\s+(\d+)%", stripped)
                if match:
                    texto = match.group(1).strip()
                    pct = int(match.group(2))
                    self.after(0, self._update_progress, pct, texto)
                    continue  # Pula a escrita no log!

                tag = "default"
                if "[ERRO]" in stripped or "ERROR" in stripped.upper() or "❌" in stripped:
                    tag = "erro"
                elif "⛔" in stripped:
                    tag = "falha"
                elif "[OK]" in stripped or "✅" in stripped:
                    tag = "ok"
                elif "[AVISO]" in stripped or "⚠️" in stripped:
                    tag = "warn"
                elif "ℹ️" in stripped or "[SHEETS]" in stripped or "▶" in stripped:
                    tag = "info"
                    
                self.after(0, self._log_write, stripped, tag)

            proc.wait()
            ok = proc.returncode == 0

            tag_res = "ok" if ok else "erro"
            msg_res = f"[OK] {nome} concluído." if ok else f"[ERRO] {nome} finalizou com código {proc.returncode}."
            self.after(0, self._log_write, msg_res, tag_res)

            if callback:
                callback(ok)
            return ok

        except Exception as e:
            self.after(0, self._log_write, f"[ERRO] {e}", "erro")
            if callback:
                callback(False)
            return False

    def _run_in_thread(self, target, *args, **kwargs):
        if self._running:
            messagebox.showwarning("Em execução", "Aguarde o término da execução atual.")
            return
        self._set_running(True)
        t = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
        t.start()

    def _stop_process(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            self._log_write("\n[INTERROMPIDO] Processo encerrado pelo usuário.", "warn")
        self._set_running(False)

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    def _get_modo_arg(self) -> tuple[str, str]:
        """Retorna (arg_modo, label_modo)."""
        headless = self._modo_var.get() == "headless"
        return ("2", "headless") if headless else ("1", "visual")

    def _abrir_modal_ajuste_nomes(self):
        modal = tk.Toplevel(self)
        modal.title("Ajuste de Nomes (Moodle -> SIORG)")
        modal.geometry("650x500")
        modal.configure(bg=BG_CARD)
        modal.transient(self)
        modal.grab_set()

        modal.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 650) // 2
        y = self.winfo_y() + (self.winfo_height() - 500) // 2
        modal.geometry(f"+{x}+{y}")

        # (Cache será carregado mais abaixo, após os componentes da UI)
        moodle_names_cache = []


        tk.Label(modal, text="Ajustes de Nomes Cadastrados", font=self._font_title, bg=BG_CARD, fg=TEXT_PRIMARY).pack(pady=(15, 10))

        list_frame = tk.Frame(modal, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        # Configurar cores para o Treeview
        style = ttk.Style(modal)
        style.theme_use("default")
        style.configure("Custom.Treeview", background=BG_INPUT, foreground=TEXT_PRIMARY, fieldbackground=BG_INPUT, borderwidth=0, font=self._font_label)
        style.configure("Custom.Treeview.Heading", background=BG_PANEL, foreground=TEXT_PRIMARY, font=self._font_small)
        style.map("Custom.Treeview", background=[('selected', ACCENT)])

        tree = ttk.Treeview(list_frame, columns=("Moodle", "SIORG"), show="headings", yscrollcommand=scrollbar.set, style="Custom.Treeview")
        tree.heading("Moodle", text="Nome no Moodle")
        tree.heading("SIORG", text="Nome no SIORG")
        tree.column("Moodle", width=300)
        tree.column("SIORG", width=300)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=tree.yview)

        def carregar_lista():
            for item in tree.get_children():
                tree.delete(item)
            ajustes = get_name_adjustments()
            for k, v in ajustes.items():
                tree.insert("", tk.END, values=(k, v))

        carregar_lista()

        form_frame = tk.Frame(modal, bg=BG_CARD)
        form_frame.pack(fill="x", padx=20, pady=15)

        lbl_moodle = tk.Label(form_frame, text="Nome Moodle (Carregando...):", bg=BG_CARD, fg=WARNING, font=self._font_label)
        lbl_moodle.grid(row=0, column=0, sticky="w", pady=2)
        var_moodle = tk.StringVar()
        entry_moodle = tk.Entry(form_frame, textvariable=var_moodle, bg=BG_INPUT, fg=TEXT_PRIMARY, font=self._font_label, relief="flat", insertbackground=TEXT_PRIMARY)
        entry_moodle.grid(row=0, column=1, sticky="ew", padx=10, pady=2, ipady=3)
        entry_moodle.config(state="disabled")

        # --- Carregar cache em background e destravar o campo ---
        def load_moodle_names():
            try:
                nomes = get_all_moodle_names()
                moodle_names_cache.clear()
                moodle_names_cache.extend(sorted(list(nomes)))
            except Exception as e:
                print("Erro ao carregar nomes Moodle:", e)
            finally:
                def unlock_ui():
                    try:
                        lbl_moodle.config(text="Nome Moodle:", fg=TEXT_PRIMARY)
                        entry_moodle.config(state="normal")
                    except:
                        pass # Janela já pode ter sido fechada
                modal.after(0, unlock_ui)
        
        threading.Thread(target=load_moodle_names, daemon=True).start()
        # --------------------------------------------------------

        # Dropdown de Autocomplete
        listbox_moodle = tk.Listbox(form_frame, bg=BG_INPUT, fg=TEXT_PRIMARY, font=self._font_small, bd=1, highlightthickness=1, highlightbackground=BORDER, selectbackground=ACCENT)
        
        def on_moodle_type(*args):
            val = var_moodle.get().strip().lower()
            if not val or not moodle_names_cache:
                listbox_moodle.place_forget()
                return
            
            matches = [n for n in moodle_names_cache if val in n.lower()]
            if not matches or (len(matches) == 1 and matches[0].lower() == val):
                listbox_moodle.place_forget()
                return
                
            listbox_moodle.delete(0, tk.END)
            for m in matches[:10]:
                listbox_moodle.insert(tk.END, m)
                
            h = min(10, len(matches)) * 22
            listbox_moodle.place(in_=entry_moodle, x=0, rely=1, relwidth=1, height=h)
            listbox_moodle.lift()

        var_moodle.trace_add("write", on_moodle_type)

        def on_listbox_select(event):
            if not listbox_moodle.curselection():
                return
            selected = listbox_moodle.get(listbox_moodle.curselection())
            var_moodle.set(selected)
            listbox_moodle.place_forget()
            entry_siorg.focus_set()

        listbox_moodle.bind("<<ListboxSelect>>", on_listbox_select)
        
        def on_entry_keydown(event):
            if not listbox_moodle.winfo_ismapped():
                return
            sel = listbox_moodle.curselection()
            if event.keysym == "Down":
                if not sel:
                    listbox_moodle.selection_set(0)
                elif sel[0] < listbox_moodle.size() - 1:
                    listbox_moodle.selection_clear(0, tk.END)
                    listbox_moodle.selection_set(sel[0] + 1)
                return "break"
            elif event.keysym == "Up":
                if sel and sel[0] > 0:
                    listbox_moodle.selection_clear(0, tk.END)
                    listbox_moodle.selection_set(sel[0] - 1)
                return "break"
            elif event.keysym in ("Return", "Tab"):
                if sel:
                    selected = listbox_moodle.get(sel[0])
                    var_moodle.set(selected)
                    listbox_moodle.place_forget()
                    return "break"
        
        entry_moodle.bind("<KeyPress-Down>", on_entry_keydown)
        entry_moodle.bind("<KeyPress-Up>", on_entry_keydown)
        entry_moodle.bind("<KeyPress-Return>", on_entry_keydown)
        entry_moodle.bind("<KeyPress-Tab>", on_entry_keydown)
        entry_moodle.bind("<FocusOut>", lambda e: modal.after(200, listbox_moodle.place_forget))
        entry_moodle.bind("<FocusIn>", lambda e: on_moodle_type())

        tk.Label(form_frame, text="Nome Correto (SIORG):", bg=BG_CARD, fg=TEXT_PRIMARY, font=self._font_label).grid(row=1, column=0, sticky="w", pady=2)
        var_siorg = tk.StringVar()
        entry_siorg = tk.Entry(form_frame, textvariable=var_siorg, bg=BG_INPUT, fg=TEXT_PRIMARY, font=self._font_label, relief="flat", insertbackground=TEXT_PRIMARY)
        entry_siorg.grid(row=1, column=1, sticky="ew", padx=10, pady=2, ipady=3)
        
        form_frame.columnconfigure(1, weight=1)

        btn_frame = tk.Frame(modal, bg=BG_CARD)
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        def salvar():
            m = var_moodle.get().strip()
            s = var_siorg.get().strip()
            if m and s:
                if moodle_names_cache and m not in moodle_names_cache:
                    if not messagebox.askyesno("Nome não encontrado", f"O nome '{m}' não foi encontrado na base de dados do Moodle.\nIsso pode ser um erro de digitação.\n\nDeseja salvar o mapeamento mesmo assim?", parent=modal):
                        return

                if save_name_adjustment(m, s):
                    messagebox.showinfo("Sucesso", "Ajuste salvo com sucesso!", parent=modal)
                    var_moodle.set("")
                    var_siorg.set("")
                    carregar_lista()
                else:
                    messagebox.showerror("Erro", "Falha ao salvar no Supabase.", parent=modal)
            else:
                messagebox.showwarning("Aviso", "Preencha ambos os campos.", parent=modal)

        def remover():
            selecionado = tree.selection()
            if not selecionado:
                messagebox.showwarning("Aviso", "Selecione um item na lista para remover.", parent=modal)
                return
            item = tree.item(selecionado[0])
            moodle_name = item['values'][0]
            if delete_name_adjustment(moodle_name):
                messagebox.showinfo("Sucesso", "Ajuste removido.", parent=modal)
                carregar_lista()
                var_moodle.set("")
                var_siorg.set("")
            else:
                messagebox.showerror("Erro", "Falha ao remover do Supabase.", parent=modal)
        
        def on_tree_select(event):
            selecionado = tree.selection()
            if selecionado:
                item = tree.item(selecionado[0])
                var_moodle.set(item['values'][0])
                var_siorg.set(item['values'][1])

        tree.bind('<<TreeviewSelect>>', on_tree_select)

        btn_salvar = self._btn(btn_frame, "Adicionar / Atualizar", salvar, color=SUCCESS)
        btn_salvar.pack(side="left", fill="x", expand=True, padx=(0, 5))

        btn_remover = self._btn(btn_frame, "Remover Selecionado", remover, color=ERROR)
        btn_remover.pack(side="right", fill="x", expand=True, padx=(5, 0))

    def _abrir_modal_academico(self):
        if self._running:
            messagebox.showwarning("Em execução", "Aguarde o término da execução atual.")
            return

        modal = tk.Toplevel(self)
        modal.title("Configuração - Extrair Acadêmico")
        modal.geometry("500x350")
        modal.configure(bg=BG_CARD)
        modal.transient(self)
        modal.grab_set()

        modal.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 500) // 2
        y = self.winfo_y() + (self.winfo_height() - 350) // 2
        modal.geometry(f"+{x}+{y}")

        tk.Label(modal, text="Configuração do Robô SIORG", font=self._font_title, bg=BG_CARD, fg=TEXT_PRIMARY).pack(pady=(15, 10))

        # CSV Selection
        csv_frame = tk.Frame(modal, bg=BG_CARD)
        csv_frame.pack(fill="x", padx=20, pady=5)
        
        tk.Label(csv_frame, text="1. Arquivo CSV (Lista de Alunos):", font=self._font_btn, bg=BG_CARD, fg=TEXT_PRIMARY).pack(anchor="w")
        
        caminho_var = tk.StringVar()
        
        def selecionar_csv():
            caminho = filedialog.askopenfilename(
                title="Selecione o CSV",
                initialdir=str(BASE_DIR),
                filetypes=[("Arquivos CSV", "*.csv")],
                parent=modal
            )
            if caminho:
                caminho_var.set(caminho)

        btn_csv = tk.Button(csv_frame, text="Procurar...", font=self._font_small, command=selecionar_csv, bg=BG_INPUT, fg=TEXT_PRIMARY, relief="flat", bd=0, padx=10, pady=4)
        btn_csv.pack(side="left", pady=5)
        
        lbl_caminho = tk.Label(csv_frame, textvariable=caminho_var, font=self._font_small, bg=BG_CARD, fg=TEXT_MUTED, wraplength=350, justify="left")
        lbl_caminho.pack(side="left", padx=10, pady=5)

        # Filtro
        filtro_frame = tk.Frame(modal, bg=BG_CARD)
        filtro_frame.pack(fill="both", expand=True, padx=20, pady=(15, 5))
        tk.Label(filtro_frame, text="2. Modo de Filtro:", font=self._font_btn, bg=BG_CARD, fg=TEXT_PRIMARY).pack(anchor="w")

        filtro_var = tk.StringVar(value="1")
        termo_var = tk.StringVar()

        # Cria os containers do filtro
        entry_frame = tk.Frame(filtro_frame, bg=BG_CARD)
        multi_frame, set_multi_items, get_multi_selected = self._build_multiselect(filtro_frame)
        
        lbl_entry_info = tk.Label(entry_frame, text="Nenhum filtro será aplicado (processar tudo).", font=self._font_small, bg=BG_CARD, fg=TEXT_MUTED)
        lbl_entry_info.pack(anchor="w", pady=(5, 2))
        
        entry_termo = tk.Entry(entry_frame, textvariable=termo_var, bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", font=self._font_label, bd=0)

        def carregar_csv(modo):
            caminho = caminho_var.get()
            if not caminho or not os.path.exists(caminho):
                return []
            import csv
            itens = set()
            try:
                with open(caminho, mode="r", encoding="utf-8-sig") as f:
                    leitor = csv.reader(f, delimiter=";")
                    next(leitor, None)
                    next(leitor, None)
                    for linha in leitor:
                        if len(linha) < 4: continue
                        if modo == "2" and linha[0].strip():
                            itens.add(linha[0].strip())
                        elif modo == "3" and linha[2].strip():
                            itens.add(linha[2].strip())
            except Exception as e:
                print("Erro ao ler CSV:", e)
            return sorted(list(itens))

        def on_filtro_change(*args):
            f_val = filtro_var.get()
            if f_val == "1":
                multi_frame.pack_forget()
                entry_frame.pack(fill="x")
                lbl_entry_info.config(text="Nenhum filtro será aplicado (processar tudo do CSV).")
                entry_termo.pack_forget()
            elif f_val == "3":
                multi_frame.pack_forget()
                entry_frame.pack(fill="x")
                lbl_entry_info.config(text="Digite o nome do aluno (ou separe vários com '|'):")
                entry_termo.pack(fill="x", ipady=7)
                entry_termo.focus_set()
            else:
                entry_frame.pack_forget()
                multi_frame.pack(fill="both", expand=True, pady=5)
                # Carregar lista
                set_multi_items(carregar_csv(f_val))

        filtro_var.trace_add("write", on_filtro_change)

        row_radios = tk.Frame(filtro_frame, bg=BG_CARD)
        row_radios.pack(fill="x", pady=5)
        for texto, valor in [("Todos do CSV", "1"), ("Por Curso", "2"), ("Por Aluno", "3")]:
            tk.Radiobutton(row_radios, text=texto, variable=filtro_var, value=valor, bg=BG_CARD, fg=TEXT_PRIMARY, selectcolor=BG_INPUT, activebackground=BG_CARD, activeforeground=ACCENT).pack(side="left", padx=(0, 10))

        # Inicializa a visualização
        on_filtro_change()

        # Buttons
        btn_frame = tk.Frame(modal, bg=BG_CARD)
        btn_frame.pack(side="bottom", fill="x", pady=20, padx=20)

        def iniciar():
            f_modo = filtro_var.get()
            termo = ""
            
            if f_modo == "3":
                termo = termo_var.get().strip()
                if not termo:
                    messagebox.showerror("Erro", "Digite o nome do aluno.", parent=modal)
                    return
                # CSV é opcional no modo 3, mas se o usuário não selecionou e o modo não for 3, bloqueamos abaixo.
            
            if f_modo != "3" and not caminho_var.get():
                messagebox.showerror("Erro", "Selecione o arquivo CSV de entrada primeiro.", parent=modal)
                return
            
            if f_modo == "2":
                selecionados = get_multi_selected()
                if not selecionados:
                    messagebox.showerror("Erro", "Selecione ao menos um item na lista.", parent=modal)
                    return
                termo = "|".join(selecionados)

            caminho_csv = caminho_var.get()
            
            ignorar_estado = False
            state_file = BASE_DIR / "Acadêmico" / "state_academico.json"
            if state_file.exists():
                import json
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    if state.get("csv_entrada") == caminho_csv and state.get("filtro_modo") == f_modo and state.get("termo") == termo:
                        processed_list = state.get("processed_students", [])
                        qtd_processados = len(processed_list)
                        total = state.get("total_students", qtd_processados + 1)
                        ultimo_aluno = processed_list[-1] if qtd_processados > 0 else "Nenhum"
                        percentual = int((qtd_processados / total) * 100) if total > 0 else 0
                        
                        msg = (
                            f"Foi encontrada uma extração incompleta para esta configuração.\n\n"
                            f"Progresso: {qtd_processados} de {total} alunos concluídos ({percentual}%).\n"
                            f"Último processado: {ultimo_aluno}\n\n"
                            f"Deseja continuar de onde parou?\n"
                            f"(Se escolher 'Não', a extração recomeçará do zero)"
                        )
                        if not messagebox.askyesno("Retomar execução?", msg, parent=modal):
                            ignorar_estado = True
                except Exception:
                    pass

            modal.destroy()
            self._run_in_thread(self._thread_academico, caminho_csv, f_modo, termo, ignorar_estado)

        btn_iniciar = tk.Button(btn_frame, text="Iniciar Extração", font=self._font_btn, bg=ACCENT, fg="white", relief="flat", bd=0, padx=20, pady=8, command=iniciar)
        btn_iniciar.pack(side="right")
        
        btn_cancelar = tk.Button(btn_frame, text="Cancelar", font=self._font_btn, bg=BG_INPUT, fg=TEXT_PRIMARY, relief="flat", bd=0, padx=20, pady=8, command=modal.destroy)
        btn_cancelar.pack(side="right", padx=10)

    def _abrir_modal_filtro_moodle(self, title, callback):
        if self._running:
            messagebox.showwarning("Em execução", "Aguarde o término da execução atual.")
            return

        modal = tk.Toplevel(self)
        modal.title(title)
        modal.geometry("450x400")
        modal.configure(bg=BG_CARD)
        modal.transient(self)
        modal.grab_set()

        modal.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 450) // 2
        y = self.winfo_y() + (self.winfo_height() - 400) // 2
        modal.geometry(f"+{x}+{y}")

        tk.Label(modal, text=title, font=self._font_title, bg=BG_CARD, fg=TEXT_PRIMARY).pack(pady=(15, 10))

        filtro_frame = tk.Frame(modal, bg=BG_CARD)
        filtro_frame.pack(fill="both", expand=True, padx=20, pady=(5, 5))
        
        tk.Label(filtro_frame, text="Modo de Filtro:", font=self._font_btn, bg=BG_CARD, fg=TEXT_PRIMARY).pack(anchor="w")

        filtro_var = tk.StringVar(value="1")
        termo_var = tk.StringVar()

        # Containers
        entry_frame = tk.Frame(filtro_frame, bg=BG_CARD)
        multi_frame, set_multi_items, get_multi_selected = self._build_multiselect(filtro_frame)
        
        tk.Label(entry_frame, text="Filtro livre (ex: '2026', '>=2025' — vazio = TODOS):",
                 font=self._font_small, bg=BG_CARD, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 4))
        entry_termo = tk.Entry(entry_frame, textvariable=termo_var, bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", font=self._font_label, bd=0)
        entry_termo.pack(fill="x", ipady=7)
        
        def carregar_supabase(modo):
            import threading
            from supabase_sync import get_distinct_from_supabase
            
            # Executa a query em background para não travar a UI
            def run_query():
                tabela = "moodle_notas" if "Participantes" not in title else "moodle_participantes"
                coluna = "disciplina" if modo == "2" else "nome_aluno"
                itens = get_distinct_from_supabase(tabela, coluna)
                self.after(0, lambda: set_multi_items(itens))
                
            set_multi_items(["Carregando dados do Supabase... aguarde."])
            threading.Thread(target=run_query, daemon=True).start()

        def on_filtro_change(*args):
            f_val = filtro_var.get()
            if f_val == "1":
                multi_frame.pack_forget()
                entry_frame.pack(fill="x")
                entry_termo.focus_set()
            else:
                entry_frame.pack_forget()
                multi_frame.pack(fill="both", expand=True, pady=5)
                carregar_supabase(f_val)

        filtro_var.trace_add("write", on_filtro_change)

        row_radios = tk.Frame(filtro_frame, bg=BG_CARD)
        row_radios.pack(fill="x", pady=5)
        for texto, valor in [("Livre (Texto)", "1"), ("Por Curso", "2"), ("Por Aluno", "3")]:
            tk.Radiobutton(row_radios, text=texto, variable=filtro_var, value=valor, bg=BG_CARD, fg=TEXT_PRIMARY, selectcolor=BG_INPUT, activebackground=BG_CARD, activeforeground=ACCENT).pack(side="left", padx=(0, 10))

        on_filtro_change()

        # Buttons
        btn_frame = tk.Frame(modal, bg=BG_CARD)
        btn_frame.pack(side="bottom", fill="x", pady=15, padx=20)

        def iniciar():
            f_modo = filtro_var.get()
            termo = ""
            
            if f_modo == "1":
                termo = termo_var.get().strip()
            else:
                selecionados = get_multi_selected()
                if not selecionados:
                    messagebox.showerror("Erro", "Selecione ao menos um item na lista.", parent=modal)
                    return
                # Se for lista, agrupamos os termos separados por barra vertical
                termo = "|".join(selecionados)

            modal.destroy()
            # Precisamos passar o f_modo pro callback para o script saber qual tipo de filtro é
            callback(termo, f_modo)

        btn_iniciar = tk.Button(btn_frame, text="Iniciar Extração", font=self._font_btn, bg=ACCENT, fg="white", relief="flat", bd=0, padx=20, pady=8, command=iniciar)
        btn_iniciar.pack(side="right")
        
        btn_cancelar = tk.Button(btn_frame, text="Cancelar", font=self._font_btn, bg=BG_INPUT, fg=TEXT_PRIMARY, relief="flat", bd=0, padx=20, pady=8, command=modal.destroy)
        btn_cancelar.pack(side="right", padx=10)
        
        # Ativar com ENTER apenas se for modo 1
        modal.bind('<Return>', lambda event: iniciar() if filtro_var.get() == "1" else None)

    def _abrir_modal_historico(self):
        if self._running:
            messagebox.showwarning("Em execução", "Aguarde o término da execução atual.")
            return

        modal = tk.Toplevel(self)
        modal.title("Histórico de Logs")
        modal.geometry("950x600")
        modal.configure(bg=BG_DARK)
        modal.transient(self)
        modal.grab_set()
        
        modal.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - 950) // 2
        y = self.winfo_y() + (self.winfo_height() - 600) // 2
        modal.geometry(f"+{x}+{y}")

        header = tk.Frame(modal, bg=BG_PANEL, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="📜  HISTÓRICO DE LOGS", font=self._font_title, bg=BG_PANEL, fg=TEXT_PRIMARY).pack(pady=(0, 5))

        filtros_frame = tk.Frame(header, bg=BG_PANEL)
        filtros_frame.pack(fill="x", padx=10)
        
        hist_filter_var = tk.StringVar(value="Todos")
        for f_text in ["Todos", "Sucesso", "Avisos", "Falhas", "Erros"]:
            tk.Radiobutton(
                filtros_frame, text=f_text, variable=hist_filter_var, value=f_text,
                bg=BG_PANEL, fg=TEXT_PRIMARY, selectcolor=BG_CARD,
                activebackground=BG_PANEL, activeforeground=ACCENT,
                font=self._font_small, indicatoron=0, bd=1, relief="flat", padx=6,
                command=lambda: render_historico()
            ).pack(side="left", padx=2)
            
        search_frame = tk.Frame(filtros_frame, bg=BG_INPUT, bd=0)
        search_frame.pack(side="right")
        tk.Label(search_frame, text="🔍 Busca:", bg=BG_INPUT, fg=TEXT_MUTED, font=self._font_small).pack(side="left", padx=(4, 2))
        hist_search_var = tk.StringVar()
        hist_search_var.trace_add("write", lambda *args: render_historico())
        search_entry = tk.Entry(
            search_frame, textvariable=hist_search_var, font=self._font_small,
            bg=BG_INPUT, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat", bd=0, width=25
        )
        search_entry.pack(side="left", padx=2, ipady=3)

        body = tk.Frame(modal, bg=BG_DARK)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        left = tk.Frame(body, bg=BG_CARD, width=280)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="Arquivos Salvos", font=self._font_btn, bg=BG_CARD, fg=TEXT_PRIMARY).pack(anchor="w", padx=10, pady=(10, 5))
        
        listbox = tk.Listbox(left, bg=BG_INPUT, fg=TEXT_PRIMARY, bd=0, highlightthickness=0, font=self._font_small, selectbackground=ACCENT)
        listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        right = tk.Frame(body, bg=BG_DARK)
        right.pack(side="left", fill="both", expand=True)
        
        log_text = scrolledtext.ScrolledText(
            right, bg=BG_INPUT, fg=TEXT_PRIMARY,
            font=self._font_mono, relief="flat", bd=0,
            state="disabled", wrap="word",
            insertbackground=TEXT_PRIMARY,
        )
        log_text.pack(fill="both", expand=True)

        log_text.tag_config("ok",      foreground=SUCCESS)
        log_text.tag_config("erro",    foreground=ERROR)
        log_text.tag_config("falha",   foreground="#f97316")
        log_text.tag_config("warn",    foreground=WARNING)
        log_text.tag_config("info",    foreground=ACCENT)
        log_text.tag_config("muted",   foreground=TEXT_MUTED)
        log_text.tag_config("header",  foreground=ACCENT, font=self._font_btn)
        log_text.tag_config("default", foreground=TEXT_PRIMARY)

        logs_dir = BASE_DIR / "Logs"
        if logs_dir.exists():
            arquivos = sorted([f for f in logs_dir.glob("*.txt")], key=lambda x: x.stat().st_mtime, reverse=True)
            for arq in arquivos:
                listbox.insert("end", arq.name)
        else:
            arquivos = []

        current_history = []
        current_student_tags = {}

        def render_historico():
            f = hist_filter_var.get()
            search_text = hist_search_var.get().strip().lower()

            log_text.config(state="normal")
            log_text.delete("1.0", "end")
            
            for entry in current_history:
                text = entry["text"]
                tag = entry["tag"]
                student_context = entry["student"]

                show = True
                if f != "Todos" and not student_context:
                    show = False
                else:
                    tags_of_student = current_student_tags.get(student_context, set()) if student_context else {tag}
                    if f == "Sucesso" and ("erro" in tags_of_student or "falha" in tags_of_student):
                        show = False
                    elif f == "Avisos" and "warn" not in tags_of_student:
                        show = False
                    elif f == "Falhas" and "falha" not in tags_of_student:
                        show = False
                    elif f == "Erros" and "erro" not in tags_of_student:
                        show = False

                if show and search_text:
                    if search_text not in text.lower() and search_text not in student_context:
                        show = False

                if show:
                    log_text.insert("end", text + "\n", tag)
                    
            log_text.config(state="disabled")

        def on_select(evt):
            nonlocal current_history, current_student_tags
            sel = listbox.curselection()
            if not sel: return
            idx = sel[0]
            arq_selecionado = arquivos[idx]
            try:
                with open(arq_selecionado, "r", encoding="utf-8") as f:
                    linhas = f.readlines()
                
                current_history = []
                current_student_tags = {}
                student = ""
                
                for line in linhas:
                    line = line.rstrip('\n')
                    
                    if "Processando:" in line:
                        match = re.search(r"Processando:\s*(.+)", line)
                        if match:
                            student = match.group(1).lower()
                    elif "AUTOMACAO FINALIZADA" in line or "Pipeline concluído" in line or "Iniciando instancia" in line:
                        student = ""
                    elif "🧑‍🎓 Aluno" in line:
                        student = ""

                    tag = "default"
                    if "=======================================================" in line or "--------------------------------------------------------" in line:
                        tag = "muted"
                    elif "CENTRAL DE EXECUÇÃO" in line:
                        tag = "header"
                    elif "[ERRO]" in line or "ERROR" in line.upper() or "❌" in line:
                        tag = "erro"
                    elif "⛔" in line:
                        tag = "falha"
                    elif "[OK]" in line or "✅" in line:
                        tag = "ok"
                    elif "[AVISO]" in line or "⚠️" in line:
                        tag = "warn"
                    elif "ℹ️" in line or "[SHEETS]" in line or "▶" in line:
                        tag = "info"

                    current_history.append({"text": line, "tag": tag, "student": student})
                    if student:
                        if student not in current_student_tags:
                            current_student_tags[student] = set()
                        current_student_tags[student].add(tag)

                render_historico()

            except Exception as e:
                log_text.config(state="normal")
                log_text.delete("1.0", "end")
                log_text.insert("end", f"Erro ao ler arquivo: {e}")
                log_text.config(state="disabled")

        listbox.bind("<<ListboxSelect>>", on_select)
        
        btn_frame = tk.Frame(modal, bg=BG_DARK)
        btn_frame.pack(side="bottom", fill="x", pady=10, padx=10)
        btn_fechar = tk.Button(btn_frame, text="Fechar", font=self._font_btn, bg=BG_INPUT, fg=TEXT_PRIMARY, relief="flat", bd=0, padx=20, pady=8, command=modal.destroy)
        btn_fechar.pack(side="right")

    def _abrir_modal_moodle(self):
        self._abrir_modal_filtro_moodle("Configuração - Extrair Moodle", lambda termo, modo: self._run_in_thread(self._thread_moodle, termo, modo))

    def _abrir_modal_moodle_mesclado(self):
        self._abrir_modal_filtro_moodle("Configuração - Extrair Moodle (Notas+Part.)", lambda termo, modo: self._run_in_thread(self._thread_moodle_mesclado, termo, modo))

    def _abrir_modal_participantes(self):
        self._abrir_modal_filtro_moodle("Configuração - Extrair Participantes", lambda termo, modo: self._run_in_thread(self._thread_participantes, termo, modo))

    def _abrir_modal_pipeline(self):
        self._abrir_modal_filtro_moodle("Configuração - Extrair Moodle → Acad.", lambda termo, modo: self._run_in_thread(self._thread_pipeline, termo, modo))

    def _thread_moodle(self, filtro: str, filtro_modo: str = "1"):
        modo_arg, modo_label = self._get_modo_arg()
        args = ["--modo", modo_arg, "--filtro-modo", filtro_modo, "--filtro", filtro]
        ok = self._executar_script(SCRIPT_MOODLE, f"Moodle ({modo_label})", args)
        self.after(0, self._set_running, False)

    def _thread_moodle_mesclado(self, filtro: str, filtro_modo: str = "1"):
        modo_arg, modo_label = self._get_modo_arg()
        args = ["--modo", modo_arg, "--filtro-modo", filtro_modo, "--filtro", filtro]
        ok = self._executar_script(SCRIPT_MESCLADO, f"Moodle Mesclado ({modo_label})", args)
        self.after(0, self._set_running, False)

    def _thread_participantes(self, filtro: str, filtro_modo: str = "1"):
        modo_arg, modo_label = self._get_modo_arg()
        args = ["--modo", modo_arg, "--filtro-modo", filtro_modo, "--filtro", filtro]
        ok = self._executar_script(SCRIPT_PARTICIPANTES, f"Participantes ({modo_label})", args)
        self.after(0, self._set_running, False)

    def _extrair_academico(self):
        self._abrir_modal_academico()

    def _thread_academico(self, csv_entrada: str, filtro_modo: str, termo: str, ignorar_estado: bool = False):
        modo_arg, modo_label = self._get_modo_arg()
        args = [
            "--modo", modo_arg,
            "--csv-entrada", csv_entrada,
            "--filtro-modo", filtro_modo,
        ]
        if termo:
            args.extend(["--termo", termo])
        if ignorar_estado:
            args.append("--ignorar-estado")
            
        self._executar_script(SCRIPT_ACADEMICO, f"Acadêmico ({modo_label})", args)
        self.after(0, self._set_running, False)

    def _thread_pipeline(self, filtro: str, filtro_modo: str = "1"):
        modo_arg, modo_label = self._get_modo_arg()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pasta_moodle_csvs = BASE_DIR / "Moodle" / "CSVs"
        pasta_moodle_csvs.mkdir(exist_ok=True)
        csv_moodle = pasta_moodle_csvs / f"notas_extraidas_pipeline_{timestamp}.csv"

        self.after(0, self._log_write,
                   f"\n🔄  Pipeline Moodle → Acadêmico ({modo_label})", "info")

        # 1. Moodle
        args_moodle = ["--modo", modo_arg, "--filtro-modo", filtro_modo, "--filtro", filtro, "--output", str(csv_moodle)]
        ok_moodle = self._executar_script(SCRIPT_MOODLE, f"Moodle ({modo_label})", args_moodle)

        if not ok_moodle:
            self.after(0, self._log_write,
                       "\n[ERRO] Pipeline interrompido após falha no Moodle.", "erro")
            self.after(0, self._set_running, False)
            return

        if not csv_moodle.exists():
            self.after(0, self._log_write,
                       f"\n[ERRO] CSV esperado não foi gerado: {csv_moodle}", "erro")
            self.after(0, self._set_running, False)
            return

        # 2. Upload Moodle → Sheets
        self.after(0, self._log_write, "\n[SHEETS] Enviando Moodle → Google Sheets...", "info")
        upload_csv_to_sheet(csv_moodle, SHEET_NAME_MOODLE)

        # 3. Acadêmico
        pasta_acad_csvs = BASE_DIR / "Acadêmico" / "CSVs"
        pasta_acad_csvs.mkdir(exist_ok=True)
        csv_antes = set(pasta_acad_csvs.glob("Extracao_Geral_SIORG_*.csv"))
        args_acad = ["--modo", modo_arg, "--csv-entrada", str(csv_moodle), "--filtro-modo", "1"]
        self._executar_script(SCRIPT_ACADEMICO, f"Acadêmico ({modo_label})", args_acad)

        # 4. Upload Acadêmico → Sheets
        csv_depois = set(pasta_acad_csvs.glob("Extracao_Geral_SIORG_*.csv"))
        novos = csv_depois - csv_antes
        if novos:
            csv_acad = max(novos, key=lambda p: p.stat().st_mtime)
            self.after(0, self._log_write,
                       "\n[SHEETS] Enviando Acadêmico → Google Sheets...", "info")
            upload_csv_to_sheet(csv_acad, SHEET_NAME_ACADEMICO)
        else:
            self.after(0, self._log_write,
                       "\n[SHEETS] ⚠️  CSV do Acadêmico não encontrado. Upload pulado.", "warn")

        # 5. Participantes
        self.after(0, self._log_write, "\n🔄  Extraindo Participantes...", "info")
        csv_participantes = pasta_moodle_csvs / f"participantes_extraidos_pipeline_{timestamp}.csv"
        args_part = ["--modo", modo_arg, "--filtro-modo", filtro_modo, "--filtro", filtro, "--output", str(csv_participantes)]
        ok_part = self._executar_script(SCRIPT_PARTICIPANTES, f"Participantes ({modo_label})", args_part)
        
        # 6. Upload Participantes
        if csv_participantes.exists():
            self.after(0, self._log_write, "\n[SHEETS] Enviando Participantes → Google Sheets...", "info")
            upload_csv_to_sheet(csv_participantes, SHEET_NAME_PARTICIPANTES)
        else:
            self.after(0, self._log_write, "\n[SHEETS] ⚠️  CSV de Participantes não encontrado. Upload pulado.", "warn")

        self.after(0, self._log_write, "\n✅  Pipeline concluído.", "ok")
        self.after(0, self._set_running, False)

    def _upload_moodle(self):
        self._upload_csv("Selecione o CSV do Moodle",
                         BASE_DIR / "Moodle" / "CSVs", SHEET_NAME_MOODLE)

    def _upload_participantes(self):
        self._upload_csv("Selecione o CSV de Participantes",
                         BASE_DIR / "Moodle" / "CSVs", SHEET_NAME_PARTICIPANTES)

    def _upload_academico(self):
        self._upload_csv("Selecione o CSV do Acadêmico (Extracao_Geral_SIORG)",
                         BASE_DIR / "Acadêmico" / "CSVs", SHEET_NAME_ACADEMICO)

    def _supabase_todos(self):
        self._log_write("\n[SUPABASE] Iniciando sincronização TOTAL (Moodle Notas, Acessos e Acadêmico)...", "info")
        self._run_in_thread(self._thread_supabase_todos)

    def _supabase_moodle(self):
        self._log_write("\n[SUPABASE] Iniciando sincronização: Moodle Notas → Google Sheets...", "info")
        self._run_in_thread(self._thread_supabase, "moodle_notas")

    def _supabase_participantes(self):
        self._log_write("\n[SUPABASE] Iniciando sincronização: Moodle Participantes → Google Sheets...", "info")
        self._run_in_thread(self._thread_supabase, "moodle_participantes")

    def _supabase_academico(self):
        self._log_write("\n[SUPABASE] Iniciando sincronização: Acadêmico → Google Sheets...", "info")
        self._run_in_thread(self._thread_supabase, "academico_notas")

    def _comparar_moodle_academico(self):
        self._log_write("\n[SUPABASE] Iniciando comparação Moodle x Acadêmico...", "info")
        self._run_in_thread(self._thread_comparar)

    def _thread_comparar(self):
        script_path = BASE_DIR / "comparar_bases.py"
        self._executar_script(script_path, "Comparar Bases", [])
        self.after(0, self._set_running, False)

    def _reprocessar_academico_faltantes(self):
        csv_faltantes = BASE_DIR / "Acadêmico" / "CSVs" / "faltantes_moodle_academico.csv"
        if not csv_faltantes.exists():
            self._log_write("\n[ERRO] CSV de faltantes não encontrado. Execute a comparação primeiro.", "erro")
            return
            
        ignorar_estado = False
        state_file = BASE_DIR / "Acadêmico" / "state_academico.json"
        if state_file.exists():
            import json
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if state.get("csv_entrada") == str(csv_faltantes) and state.get("filtro_modo") == "1":
                    processed_list = state.get("processed_students", [])
                    qtd_processados = len(processed_list)
                    total = state.get("total_students", qtd_processados + 1)
                    ultimo_aluno = processed_list[-1] if qtd_processados > 0 else "Nenhum"
                    percentual = int((qtd_processados / total) * 100) if total > 0 else 0
                    
                    msg = (
                        f"Foi encontrada uma extração incompleta para os alunos faltantes.\n\n"
                        f"Progresso: {qtd_processados} de {total} alunos concluídos ({percentual}%).\n"
                        f"Último processado: {ultimo_aluno}\n\n"
                        f"Deseja continuar de onde parou?\n"
                        f"(Se escolher 'Não', a extração recomeçará do zero)"
                    )
                    if not messagebox.askyesno("Retomar execução?", msg):
                        ignorar_estado = True
            except Exception:
                pass
            
        self._log_write("\n[ACADÊMICO] Reprocessando apenas alunos faltantes...", "info")
        self._run_in_thread(self._thread_reprocessar_faltantes, csv_faltantes, ignorar_estado)

    def _thread_reprocessar_faltantes(self, csv_faltantes, ignorar_estado=False):
        modo_label = "visual" if self._modo_var.get() == "visual" else "headless"
        modo_arg = "1" if self._modo_var.get() == "visual" else "2"
        args = ["--modo", modo_arg, "--csv-entrada", str(csv_faltantes), "--filtro-modo", "1"]
        if ignorar_estado:
            args.append("--ignorar-estado")
        script_path = BASE_DIR / "Acadêmico" / "playwright_robo_academico_notas.py"
        self._executar_script(script_path, f"Acadêmico Faltantes ({modo_label})", args)
        self.after(0, self._set_running, False)

    def _thread_supabase(self, tabela: str):
        script_path = BASE_DIR / "supabase_to_sheets.py"
        args = ["--tabela", tabela]
        self._executar_script(script_path, f"Sincronizar {tabela} para Sheets", args)
        self.after(0, self._set_running, False)

    def _thread_supabase_todos(self):
        script_path = BASE_DIR / "supabase_to_sheets.py"
        self._executar_script(script_path, "Sincronizar moodle_notas para Sheets", ["--tabela", "moodle_notas"])
        self._executar_script(script_path, "Sincronizar moodle_participantes para Sheets", ["--tabela", "moodle_participantes"])
        self._executar_script(script_path, "Sincronizar academico_notas para Sheets", ["--tabela", "academico_notas"])
        self.after(0, self._set_running, False)

    def _upload_csv(self, titulo: str, pasta: Path, sheet_name: str):
        caminho = filedialog.askopenfilename(
            title=titulo,
            initialdir=str(pasta) if pasta.exists() else str(BASE_DIR),
            filetypes=[("Arquivos CSV", "*.csv"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            self._log_write("\n[CANCELADO] Nenhum arquivo selecionado.", "muted")
            return

        csv_path = Path(caminho)
        self._log_write(f"\n[SHEETS] Enviando '{csv_path.name}' → aba '{sheet_name}'...", "info")
        self._run_in_thread(self._thread_upload, csv_path, sheet_name)

    def _thread_upload(self, csv_path: Path, sheet_name: str):
        ok = upload_csv_to_sheet(csv_path, sheet_name)
        tag = "ok" if ok else "erro"
        msg = "✅  Upload concluído com sucesso!" if ok else "❌  Falha no upload. Veja o log acima."
        self.after(0, self._log_write, msg, tag)
        self.after(0, self._set_running, False)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = CentralApp()
    app.mainloop()
