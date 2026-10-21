#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

BG = "#0f1419"
CARD = "#171f27"
CARD2 = "#1c2630"
ROW_ALT = "#151d25"
TEXT = "#e6edf3"
MUTED = "#8b98a5"
ACCENT = "#4cc2ff"
GREEN = "#3ddc84"
RED = "#ff5c5c"

FONT = "DejaVu Sans"
HOME = Path.home()
DESKTOP = HOME / "Bureau"
ARCHIVES = HOME / "Archives"
STATE_DIR = HOME / ".local" / "share" / "rangement-bureau"
JOURNAL = STATE_DIR / "journal.json"
UNIQUE_DIR = DESKTOP / "Rangé"


def xdg_dir(key, fallback):
    try:
        result = subprocess.run(
            ["xdg-user-dir", key], capture_output=True, text=True, timeout=3
        )
        value = result.stdout.strip()
        if value:
            return Path(value)
    except (OSError, subprocess.SubprocessError):
        pass
    return HOME / fallback


DOCUMENTS = xdg_dir("DOCUMENTS", "Documents")
PICTURES = xdg_dir("PICTURES", "Images")
MUSIC = xdg_dir("MUSIC", "Musique")
VIDEOS = xdg_dir("VIDEOS", "Vidéos")
DOWNLOADS = xdg_dir("DOWNLOAD", "Téléchargements")
DESKTOP = xdg_dir("DESKTOP", "Bureau")
UNIQUE_DIR = DESKTOP / "Rangé"

EXTENSIONS = {
    "Documents": {
        ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".tex",
        ".xls", ".xlsx", ".ods", ".csv", ".ppt", ".pptx", ".odp", ".epub",
    },
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic",
        ".tif", ".tiff", ".ico", ".avif",
    },
    "Musique": {
        ".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus", ".wma",
        ".aiff", ".mid",
    },
    "Vidéos": {
        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v", ".mpg", ".mpeg",
        ".wmv",
    },
    "Archives": {
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".zst", ".tgz",
    },
    "Programmes": {
        ".deb", ".rpm", ".appimage", ".run", ".sh", ".py", ".bin",
        ".flatpakref",
    },
}

DESTINATIONS = {
    "Documents": DOCUMENTS,
    "Images": PICTURES,
    "Musique": MUSIC,
    "Vidéos": VIDEOS,
    "Archives": ARCHIVES,
    "Programmes": DOWNLOADS,
    "Autres": UNIQUE_DIR,
}

CATEGORY_ORDER = [
    "Documents", "Images", "Musique", "Vidéos", "Archives", "Programmes",
    "Autres",
]


def category_for(path):
    suffix = path.suffix.lower()
    for category, extensions in EXTENSIONS.items():
        if suffix in extensions:
            return category
    return "Autres"


def format_size(size):
    value = float(size)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if value < 1024 or unit == "To":
            if unit == "o":
                return f"{int(value)} o"
            return f"{value:.1f} {unit}".replace(".", ",")
        value /= 1024
    return f"{size} o"


def pretty(path):
    try:
        resolved = Path(path).resolve()
        relative = resolved.relative_to(HOME.resolve())
    except (OSError, ValueError):
        return str(path)
    if str(relative) == ".":
        return "~"
    return "~/" + str(relative)


def unique_path(path):
    if not path.exists():
        return path
    for index in range(1, 10000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError("aucun nom de fichier disponible")


class DesktopSorter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Rangement du bureau")
        self.configure(bg=BG)
        self.geometry("1020x700")
        self.minsize(860, 590)
        self.items = []
        self.dir_count = 0
        self.shortcut_count = 0
        self.hidden_count = 0
        self.dest_mode = tk.StringVar(value="home")
        self._load_icon()
        self._build_style()
        self._build_ui()
        self.update_idletasks()
        self._center()
        self.refresh()

    def _load_icon(self):
        try:
            self._icon = tk.PhotoImage(
                file="/usr/share/icons/oxygen/base/48x48/places/folder.png"
            )
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass

    def _center(self):
        width = self.winfo_width()
        height = self.winfo_height()
        x = max(0, (self.winfo_screenwidth() - width) // 2)
        y = max(0, (self.winfo_screenheight() - height) // 2)
        self.geometry(f"+{x}+{y}")

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure(
            "Treeview",
            background=CARD2,
            fieldbackground=CARD2,
            foreground=TEXT,
            borderwidth=0,
            rowheight=29,
            font=(FONT, 9),
        )
        style.map(
            "Treeview",
            background=[("selected", "#2b4354")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Treeview.Heading",
            background=CARD,
            foreground=MUTED,
            relief="flat",
            borderwidth=0,
            font=(FONT, 9, "bold"),
            padding=(8, 8),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", CARD)],
            foreground=[("active", TEXT)],
        )
        style.configure(
            "Vertical.TScrollbar",
            background="#2a3540",
            troughcolor=CARD2,
            bordercolor=CARD2,
            arrowcolor=MUTED,
            darkcolor="#2a3540",
            lightcolor="#2a3540",
            relief="flat",
        )
        style.map("Vertical.TScrollbar", background=[("active", "#3a4855")])
        style.configure(
            "Ghost.TButton",
            background=CARD2,
            foreground=TEXT,
            borderwidth=0,
            focusthickness=0,
            padding=(13, 8),
            font=(FONT, 9),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", "#25313d"), ("pressed", "#2c3a47")],
            foreground=[("disabled", "#5b6773")],
        )
        style.configure(
            "Accent.TButton",
            background="#1b4a67",
            foreground="#c5ecff",
            borderwidth=0,
            focusthickness=0,
            padding=(16, 9),
            font=(FONT, 9, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", "#246080"),
                ("pressed", "#2a6f94"),
                ("disabled", "#1a2833"),
            ],
            foreground=[("disabled", "#5b6773")],
        )

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = tk.Frame(self, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(16, 10))
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header, text="Rangement du bureau", bg=BG, fg=TEXT,
            font=(FONT, 20, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="Classez les fichiers de ~/Bureau en un clic, sans rien perdre",
            bg=BG, fg=MUTED, font=(FONT, 9), anchor="w",
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        refresh_button = ttk.Button(
            header, text="Actualiser", style="Ghost.TButton",
            command=self.refresh,
        )
        refresh_button.grid(row=0, column=2, rowspan=2, sticky="e")

        self.icons_button = ttk.Button(
            header, text="Aligner les icônes", style="Ghost.TButton",
            command=self.align_icons,
        )
        self.icons_button.grid(
            row=0, column=1, rowspan=2, sticky="e", padx=(0, 8)
        )

        settings = tk.Frame(self, bg=CARD)
        settings.grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 12))
        settings.grid_columnconfigure(0, weight=1)

        tk.Label(
            settings, text="DESTINATION", bg=CARD, fg=MUTED,
            font=(FONT, 7, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(12, 4))

        self.home_radio = tk.Radiobutton(
            settings,
            text="Dossiers habituels du home  ·  Documents, Images, Musique, Vidéos, Archives",
            variable=self.dest_mode, value="home", command=self.on_mode_change,
            bg=CARD, fg=TEXT, activebackground=CARD, activeforeground=TEXT,
            selectcolor=CARD2, highlightthickness=0, bd=0,
            font=(FONT, 9), anchor="w", cursor="hand2",
        )
        self.home_radio.grid(row=1, column=0, sticky="w", padx=(18, 0))

        self.unique_radio = tk.Radiobutton(
            settings,
            text="Dossier unique sur le bureau  ·  ~/Bureau/Rangé",
            variable=self.dest_mode, value="unique", command=self.on_mode_change,
            bg=CARD, fg=TEXT, activebackground=CARD, activeforeground=TEXT,
            selectcolor=CARD2, highlightthickness=0, bd=0,
            font=(FONT, 9), anchor="w", cursor="hand2",
        )
        self.unique_radio.grid(row=2, column=0, sticky="w", padx=(18, 0), pady=(2, 0))

        self.info_label = tk.Label(
            settings, text="", bg=CARD, fg=MUTED, font=(FONT, 8),
            anchor="w", justify="left",
        )
        self.info_label.grid(
            row=3, column=0, sticky="w", padx=18, pady=(8, 12)
        )

        card = tk.Frame(self, bg=CARD)
        card.grid(row=2, column=0, sticky="nsew", padx=22, pady=(0, 16))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)

        toolbar = tk.Frame(card, bg=CARD)
        toolbar.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 8))

        self.select_none_button = ttk.Button(
            toolbar, text="Tout désélectionner", style="Ghost.TButton",
            command=self.select_none,
        )
        self.select_none_button.pack(side="right")
        self.select_all_button = ttk.Button(
            toolbar, text="Tout sélectionner", style="Ghost.TButton",
            command=self.select_all,
        )
        self.select_all_button.pack(side="right", padx=(0, 6))

        heading = tk.Frame(toolbar, bg=CARD)
        heading.pack(side="left", fill="x", expand=True)
        tk.Label(
            heading, text="Fichiers", bg=CARD, fg=TEXT,
            font=(FONT, 11, "bold"),
        ).pack(side="left")
        self.count_label = tk.Label(
            heading, text="", bg=CARD, fg=MUTED, font=(FONT, 9),
        )
        self.count_label.pack(side="left", padx=(8, 0))

        table_frame = tk.Frame(card, bg=CARD)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=16)
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        columns = ("sel", "name", "category", "size", "date", "dest")
        self.tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", selectmode="browse"
        )
        self.tree.heading("sel", text="Sél.", anchor="center")
        self.tree.heading("name", text="Fichier", anchor="w")
        self.tree.heading("category", text="Type", anchor="w")
        self.tree.heading("size", text="Taille", anchor="e")
        self.tree.heading("date", text="Modifié", anchor="e")
        self.tree.heading("dest", text="Destination", anchor="w")
        self.tree.column("sel", width=54, minwidth=48, stretch=False, anchor="center")
        self.tree.column("name", width=240, minwidth=140, stretch=True, anchor="w")
        self.tree.column("category", width=145, minwidth=90, stretch=False, anchor="w")
        self.tree.column("size", width=100, minwidth=70, stretch=False, anchor="e")
        self.tree.column("date", width=155, minwidth=120, stretch=False, anchor="e")
        self.tree.column("dest", width=240, minwidth=150, stretch=False, anchor="w")
        self.tree.tag_configure("even", background=CARD2)
        self.tree.tag_configure("odd", background=ROW_ALT)
        self.tree.tag_configure("unchecked", foreground=MUTED)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<space>", self.on_space)
        self.tree.bind("<Double-1>", self.on_double_click)

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.tree.yview,
            style="Vertical.TScrollbar",
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.scrollbar = scrollbar
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.empty_label = tk.Label(
            table_frame,
            text="Le bureau est déjà rangé.\n\n"
            "Déposez des fichiers puis cliquez sur Actualiser.",
            bg=CARD2, fg=MUTED, font=(FONT, 10), justify="center",
        )
        self.empty_label.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.empty_label.grid_remove()

        footer = tk.Frame(card, bg=CARD)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 12))

        self.range_button = ttk.Button(
            footer, text="Ranger", style="Accent.TButton",
            command=self.sort_selected,
        )
        self.range_button.pack(side="right")
        self.trash_button = ttk.Button(
            footer, text="Corbeille", style="Ghost.TButton",
            command=self.trash_selected,
        )
        self.trash_button.pack(side="right", padx=(0, 6))
        self.archive_button = ttk.Button(
            footer, text="Archiver", style="Ghost.TButton",
            command=self.archive_selected,
        )
        self.archive_button.pack(side="right", padx=(0, 6))
        self.undo_button = ttk.Button(
            footer, text="Annuler", style="Ghost.TButton",
            command=self.undo_last,
        )
        self.undo_button.pack(side="right", padx=(0, 6))

        self.summary_label = tk.Label(
            footer, text="", bg=CARD, fg=MUTED, font=(FONT, 8),
            anchor="w", width=1,
        )
        self.summary_label.pack(side="left", fill="x", expand=True)

    def scan(self, previous):
        items = []
        directories = 0
        shortcuts = 0
        hidden = 0
        try:
            entries = list(DESKTOP.iterdir())
        except OSError:
            entries = []

        for entry in entries:
            name = entry.name
            if name.startswith("."):
                hidden += 1
                continue
            try:
                if entry.is_dir():
                    directories += 1
                    continue
                if name.lower().endswith(".desktop"):
                    shortcuts += 1
                    continue
                if not entry.is_file():
                    continue
                stat = entry.stat()
            except OSError:
                continue

            category = category_for(entry)
            checked = previous.get(name, category != "Autres")
            items.append(
                {
                    "name": name,
                    "path": entry,
                    "category": category,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "checked": checked,
                }
            )

        items.sort(
            key=lambda item: (
                CATEGORY_ORDER.index(item["category"]), item["name"].casefold()
            )
        )
        return items, directories, shortcuts, hidden

    def refresh(self):
        previous = {item["name"]: item["checked"] for item in self.items}
        self.items, self.dir_count, self.shortcut_count, self.hidden_count = self.scan(
            previous
        )
        self.populate()
        self.update_summary()

        details = [
            f"{self.dir_count} dossier(s)",
            f"{self.shortcut_count} raccourci(s)",
        ]
        if self.hidden_count:
            details.append(f"{self.hidden_count} fichier(s) caché(s) ignoré(s)")
        self.info_label.configure(
            text=(
                "Décochez un fichier pour le garder sur le bureau. "
                "Les dossiers et raccourcis ne sont jamais déplacés.\n"
                + " · ".join(details)
            )
        )

    def align_icons(self):
        dcop = shutil.which("dcop") or "/opt/trinity/bin/dcop"
        try:
            result = subprocess.run(
                [dcop, "kdesktop", "KDesktopIface", "rearrangeIcons", "true"],
                capture_output=True, text=True, timeout=5,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            messagebox.showerror(
                "Icônes du bureau",
                f"Impossible de réorganiser les icônes :\n{exc}",
                parent=self,
            )
            return
        if result.returncode != 0:
            detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or "Le bureau Trinity n'a pas répondu."
            )
            messagebox.showerror(
                "Icônes du bureau",
                f"Impossible de réorganiser les icônes :\n{detail}",
                parent=self,
            )
            return
        self.icons_button.configure(text="Icônes alignées ✓")
        self.after(
            2000,
            lambda: self.icons_button.configure(text="Aligner les icônes"),
        )

    def populate(self):
        focused = self.tree.focus()
        self.tree.delete(*self.tree.get_children(""))
        for index, item in enumerate(self.items):
            tags = ["even" if index % 2 == 0 else "odd"]
            if not item["checked"]:
                tags.append("unchecked")
            self.tree.insert(
                "", "end", iid=item["name"],
                values=self.row_values(item), tags=tags,
            )
        if focused and self.tree.exists(focused):
            self.tree.focus(focused)
        self.count_label.configure(text=f"({len(self.items)})")

        if self.items:
            self.empty_label.grid_remove()
            self.tree.grid(row=0, column=0, sticky="nsew")
            self.scrollbar.grid(row=0, column=1, sticky="ns")
        else:
            self.tree.grid_remove()
            self.scrollbar.grid_remove()
            self.empty_label.grid(row=0, column=0, columnspan=2, sticky="nsew")
        list_state = ["!disabled"] if self.items else ["disabled"]
        self.select_all_button.state(list_state)
        self.select_none_button.state(list_state)

    def row_values(self, item):
        checked = item["checked"]
        destination = self.destination_for(item)
        modified = time.localtime(item["mtime"])
        if modified.tm_year == time.localtime().tm_year:
            date_text = time.strftime("%d/%m · %H:%M", modified)
        else:
            date_text = time.strftime("%d/%m/%Y", modified)
        return (
            "☑" if checked else "☐",
            item["name"],
            item["category"],
            format_size(item["size"]),
            date_text,
            pretty(destination),
        )

    def destination_for(self, item):
        if self.dest_mode.get() == "unique":
            return UNIQUE_DIR
        return DESTINATIONS.get(item["category"], UNIQUE_DIR)

    def selected_items(self):
        return [item for item in self.items if item["checked"]]

    def toggle(self, name, value=None):
        for item in self.items:
            if item["name"] == name:
                item["checked"] = (not item["checked"]) if value is None else value
                break
        else:
            return
        self.populate()
        self.update_summary()

    def on_tree_click(self, event):
        if self.tree.identify("region", event.x, event.y) != "cell":
            return None
        if self.tree.identify_column(event.x) != "#1":
            return None
        name = self.tree.identify_row(event.y)
        if name:
            self.toggle(name)
            return "break"
        return None

    def on_double_click(self, event):
        name = self.tree.identify_row(event.y)
        if name:
            self.toggle(name)
            return "break"
        return None

    def on_space(self, _event):
        name = self.tree.focus()
        if name:
            self.toggle(name)
        return "break"

    def select_all(self):
        for item in self.items:
            item["checked"] = True
        self.populate()
        self.update_summary()

    def select_none(self):
        for item in self.items:
            item["checked"] = False
        self.populate()
        self.update_summary()

    def update_summary(self):
        selected = self.selected_items()
        if selected:
            total = sum(item["size"] for item in selected)
            word = "fichier" if len(selected) == 1 else "fichiers"
            self.summary_label.configure(
                text=f"{len(selected)} {word} · {format_size(total)}"
            )
        else:
            self.summary_label.configure(text="Aucun fichier sélectionné")

        state = ["!disabled"] if selected else ["disabled"]
        for button in (self.range_button, self.archive_button, self.trash_button):
            button.state(state)
        undo_state = ["!disabled"] if self.load_journal() else ["disabled"]
        self.undo_button.state(undo_state)

    def on_mode_change(self):
        self.populate()
        self.update_summary()

    def preview(self, items, destination_for):
        lines = []
        for item in items[:12]:
            lines.append(
                f"• {item['name']}  →  {pretty(destination_for(item))}"
            )
        if len(items) > 12:
            lines.append(f"… et {len(items) - 12} autre(s)")
        return "\n".join(lines)

    def sort_selected(self):
        items = self.selected_items()
        if not items:
            return
        message = (
            f"Déplacer {len(items)} fichier(s) ?\n\n"
            + self.preview(items, self.destination_for)
        )
        if not messagebox.askyesno(
            "Ranger la sélection", message, parent=self
        ):
            return
        self.perform_move(items, self.destination_for, "Rangement terminé")

    def archive_selected(self):
        items = self.selected_items()
        if not items:
            return
        message = (
            f"Archiver {len(items)} fichier(s) dans {pretty(ARCHIVES)} ?\n\n"
            + self.preview(items, lambda _item: ARCHIVES)
        )
        if not messagebox.askyesno("Archiver", message, parent=self):
            return
        self.perform_move(
            items, lambda _item: ARCHIVES, "Archivage terminé"
        )

    def perform_move(self, items, destination_for, title):
        self.configure(cursor="watch")
        self.update_idletasks()
        moves = []
        errors = []
        try:
            for item in items:
                source = item["path"]
                directory = destination_for(item)
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                    target = unique_path(directory / source.name)
                    shutil.move(str(source), str(target))
                    moves.append([str(source), str(target)])
                except OSError as exc:
                    errors.append(f"• {source.name} : {exc.strerror or exc}")
        finally:
            self.configure(cursor="")

        if moves:
            self.save_journal(moves)
        self.refresh()

        if errors:
            messagebox.showwarning(
                "Opération partielle",
                f"{len(moves)} fichier(s) déplacé(s), "
                f"{len(errors)} erreur(s) :\n\n"
                + "\n".join(errors[:8]),
                parent=self,
            )
        elif moves:
            messagebox.showinfo(
                title, f"{len(moves)} fichier(s) déplacé(s).", parent=self
            )

    def trash_selected(self):
        items = self.selected_items()
        if not items:
            return
        if not messagebox.askyesno(
            "Mettre à la corbeille",
            f"Mettre {len(items)} fichier(s) à la corbeille ?\n\n"
            "Vous pourrez les restaurer depuis la Corbeille.",
            parent=self,
        ):
            return
        paths = [str(item["path"]) for item in items]
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            result = subprocess.run(
                ["gio", "trash", "--", *paths],
                capture_output=True, text=True,
            )
        except OSError as exc:
            result = None
            error = str(exc)
        finally:
            self.configure(cursor="")

        if result is None or result.returncode != 0:
            detail = error if result is None else (result.stderr.strip() or "échec")
            messagebox.showerror(
                "Corbeille",
                f"Impossible de mettre les fichiers à la corbeille :\n{detail}",
                parent=self,
            )
            self.refresh()
            return

        self.refresh()
        messagebox.showinfo(
            "Corbeille", f"{len(paths)} fichier(s) mis à la corbeille.",
            parent=self,
        )

    def load_journal(self):
        try:
            data = json.loads(JOURNAL.read_text(encoding="utf-8"))
            moves = data.get("moves", [])
        except (OSError, ValueError, AttributeError):
            return []
        result = []
        for entry in moves:
            if (
                isinstance(entry, list)
                and len(entry) == 2
                and all(isinstance(value, str) for value in entry)
            ):
                result.append(entry)
        return result

    def save_journal(self, moves):
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            JOURNAL.write_text(
                json.dumps(
                    {"time": time.time(), "moves": moves},
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def undo_last(self):
        moves = self.load_journal()
        if not moves:
            messagebox.showinfo(
                "Annuler", "Aucun rangement à annuler.", parent=self
            )
            return
        if not messagebox.askyesno(
            "Annuler le dernier rangement",
            f"Remettre {len(moves)} fichier(s) à leur emplacement d'origine ?",
            parent=self,
        ):
            return

        remaining = []
        errors = []
        restored = 0
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            for source_name, target_name in reversed(moves):
                source = Path(source_name)
                target = Path(target_name)
                if not target.exists():
                    continue
                if source.exists():
                    remaining.append([source_name, target_name])
                    errors.append(f"• {source.name} : emplacement déjà occupé")
                    continue
                try:
                    source.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(target), str(source))
                    restored += 1
                except OSError as exc:
                    remaining.append([source_name, target_name])
                    errors.append(f"• {source.name} : {exc.strerror or exc}")
        finally:
            self.configure(cursor="")

        self.save_journal(list(reversed(remaining)))
        self.refresh()

        if errors:
            messagebox.showwarning(
                "Annulation partielle",
                f"{restored} fichier(s) remis en place, "
                f"{len(errors)} problème(s) :\n\n" + "\n".join(errors[:8]),
                parent=self,
            )
        else:
            messagebox.showinfo(
                "Annuler",
                f"{restored} fichier(s) remis à leur emplacement d'origine.",
                parent=self,
            )


if __name__ == "__main__":
    app = DesktopSorter()
    app.mainloop()
