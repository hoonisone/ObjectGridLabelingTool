from __future__ import annotations

import copy
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from .app_config import AppConfig
from .grid_types import GridObject, ImageLabelState
from .label_store import list_images, load_image_state, save_image_state, sidecar_path_for


class GridLabelingApp:
    def __init__(self, root: tk.Tk, config: AppConfig) -> None:
        self.root = root
        self.config = config
        self.root.title("Wine Grid Labeling Tool")
        self.root.geometry("1360x860")

        self.folder_path: Path | None = None
        self.image_paths: list[Path] = []
        self.current_index: int = -1
        self.current_state: ImageLabelState | None = None
        self.edited_images: set[Path] = set()

        self.scale = 1.0
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.base_offset_x = 0.0
        self.base_offset_y = 0.0
        self.draw_size: tuple[int, int] = (0, 0)
        self.canvas_size: tuple[int, int] = (0, 0)
        self.image_size: tuple[int, int] = (0, 0)
        self.image_tk: ImageTk.PhotoImage | None = None
        self.source_image: Image.Image | None = None
        self.source_image_path: Path | None = None
        self.cached_draw_size: tuple[int, int] | None = None
        self.redraw_after_id: str | None = None
        self.nudge_step_px = 1.0
        self.grid_preview_size = (280, 280)
        self.grid_preview_tk: ImageTk.PhotoImage | None = None

        self.selected_ids: set[str] = set()
        self.undo_stack: list[list[GridObject]] = []
        self.redo_stack: list[list[GridObject]] = []
        self.next_manual_id = 0
        self.drag_anchor: tuple[float, float] | None = None
        self.drag_rect_id: int | None = None
        self.drag_lasso_id: int | None = None
        self.drag_lasso_close_id: int | None = None
        self.drag_lasso_points: list[tuple[float, float]] = []
        self.drag_additive: bool = False
        self.point_drag_ids: set[str] | None = None
        self.point_drag_offsets: dict[str, tuple[float, float]] | None = None
        self.pan_anchor: tuple[float, float] | None = None
        self.pan_anchor_offset: tuple[float, float] | None = None

        self.mode_var = tk.StringVar(value="select")
        self.drag_select_mode_var = tk.StringVar(value="bbox")
        self.col_var = tk.StringVar(value="")
        self.row_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="폴더를 선택하세요.")
        self.show_col_row_var = tk.BooleanVar(value=True)
        self.show_grid_var = tk.BooleanVar(value=False)
        self.show_grid_mixed_links_var = tk.BooleanVar(value=True)
        self.quick_assign_target_var = tk.StringVar(value="col")
        self.total_points_var = tk.StringVar(value="전체 점 수: 0")
        self.missing_col_var = tk.StringVar(value="col 미지정 점 수: 0")
        self.missing_row_var = tk.StringVar(value="row 미지정 점 수: 0")
        self.focus_info_var = tk.StringVar(value="focus: -")
        self.copied_objects: list[GridObject] = []
        self.paste_serial = 0
        self.paste_offset_px = (12.0, 12.0)
        self.live_apply_suspended = False
        self.live_apply_after_id: str | None = None
        self.quick_input_buffer = ""
        self.quick_input_after_id: str | None = None
        # Keycode fallback for shortcuts across different layouts/IME states.
        # Windows VK + macOS ANSI keycodes.
        self.shortcut_keycodes: dict[str, set[int]] = {
            "a": {65, 0},
            "c": {67, 8},
            "d": {68, 2},
            "e": {69, 14},
            "f": {70, 3},
            "r": {82, 15},
            "s": {83, 1},
            "v": {86, 9},
            "y": {89, 16},
            "z": {90, 6},
        }
        # Korean 2-set IME fallback chars for the same physical keys.
        self.shortcut_hangul_chars: dict[str, set[str]] = {
            "a": {"ㅁ"},
            "c": {"ㅊ"},
            "d": {"ㅇ"},
            "e": {"ㄷ", "ㄸ"},
            "f": {"ㄹ"},
            "r": {"ㄱ", "ㄲ"},
            "s": {"ㄴ"},
            "v": {"ㅍ"},
            "y": {"ㅛ"},
            "z": {"ㅋ"},
        }

        self._build_ui()

    def _build_ui(self) -> None:
        root = self.root
        root.rowconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)

        left = ttk.Frame(root, padding=8)
        left.grid(row=0, column=0, sticky="nsw")
        left.rowconfigure(2, weight=1)

        ttk.Button(left, text="폴더 열기", command=self.choose_folder).grid(row=0, column=0, sticky="ew")

        nav = ttk.Frame(left, padding=(0, 8, 0, 8))
        nav.grid(row=1, column=0, sticky="ew")
        nav.columnconfigure((0, 1), weight=1)
        ttk.Button(nav, text="이전", command=self.prev_image).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(nav, text="다음", command=self.next_image).grid(row=0, column=1, sticky="ew")

        list_container = ttk.Frame(left)
        list_container.grid(row=2, column=0, sticky="nsew")
        list_container.rowconfigure(0, weight=1)
        list_container.columnconfigure(0, weight=1)
        self.image_listbox = tk.Listbox(list_container, width=32)
        self.image_listbox.grid(row=0, column=0, sticky="nsew")
        self.image_scrollbar = ttk.Scrollbar(
            list_container, orient="vertical", command=self.image_listbox.yview
        )
        self.image_scrollbar.grid(row=0, column=1, sticky="ns")
        self.image_listbox.configure(yscrollcommand=self.image_scrollbar.set)
        self.image_listbox.bind("<<ListboxSelect>>", self._on_image_selected)
        self.image_listbox.bind("<Up>", lambda e: self._on_listbox_arrow(e, dx=0, dy=-1))
        self.image_listbox.bind("<Down>", lambda e: self._on_listbox_arrow(e, dx=0, dy=1))
        self.image_listbox.bind("<Left>", lambda e: self._on_listbox_arrow(e, dx=-1, dy=0))
        self.image_listbox.bind("<Right>", lambda e: self._on_listbox_arrow(e, dx=1, dy=0))

        ttk.Button(left, text="현재 이미지 저장", command=self.save_current).grid(
            row=3, column=0, sticky="ew", pady=(8, 0)
        )

        center = ttk.Frame(root, padding=8)
        center.grid(row=0, column=1, sticky="nsew")
        center.rowconfigure(1, weight=1)
        center.columnconfigure(0, weight=1)

        mode_row = ttk.Frame(center)
        mode_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(mode_row, text="모드:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="편집 (E)", value="select", variable=self.mode_var).pack(side=tk.LEFT)
        ttk.Radiobutton(mode_row, text="점 추가 (R)", value="add", variable=self.mode_var).pack(side=tk.LEFT)

        self.canvas = tk.Canvas(center, bg="#202020", highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Button-1>", self._on_canvas_press)
        self.canvas.bind("<Double-Button-1>", self._on_canvas_double_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Configure>", lambda _e: self._draw_scene())
        # Route all keyboard shortcuts from one consistent entrypoint.
        self.root.bind("<KeyPress>", self._on_global_keypress, add="+")
        self.root.bind_all("<FocusIn>", self._on_focus_changed)
        self.root.bind_all("<FocusOut>", self._on_focus_changed)

        right = ttk.Frame(root, padding=8)
        right.grid(row=0, column=2, sticky="nse")

        ttk.Label(right, text="선택 객체 일괄 편집").grid(row=0, column=0, sticky="w")
        editor = ttk.Frame(right, padding=(0, 6, 0, 8))
        editor.grid(row=1, column=0, sticky="ew")
        ttk.Label(editor, text="col").grid(row=0, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.col_var, width=10).grid(row=0, column=1, sticky="ew")
        ttk.Label(editor, text="row").grid(row=1, column=0, sticky="w")
        ttk.Entry(editor, textvariable=self.row_var, width=10).grid(row=1, column=1, sticky="ew")
        ttk.Label(editor, text="(값 변경 시 즉시 적용)").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        quick_target = ttk.Frame(editor)
        quick_target.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(quick_target, text="숫자 키 입력 대상:").pack(side=tk.LEFT)
        ttk.Radiobutton(
            quick_target,
            text="col",
            value="col",
            variable=self.quick_assign_target_var,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Radiobutton(
            quick_target,
            text="row",
            value="row",
            variable=self.quick_assign_target_var,
        ).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Separator(right, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=8)

        ttk.Label(right, text="일괄 설정 (객체 선택 후)").grid(row=3, column=0, sticky="w")
        batch = ttk.Frame(right, padding=(0, 6, 0, 8))
        batch.grid(row=4, column=0, sticky="ew")
        ttk.Button(batch, text="선택 영역 row 자동", command=self.apply_batch_column).grid(
            row=0, column=0, sticky="ew"
        )

        option_frame = ttk.LabelFrame(right, text="옵션", padding=(8, 6))
        option_frame.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(option_frame, text="드래그 선택 방식").grid(row=0, column=0, sticky="w")
        drag_mode_row = ttk.Frame(option_frame)
        drag_mode_row.grid(row=1, column=0, sticky="w", pady=(2, 4))
        ttk.Radiobutton(
            drag_mode_row,
            text="bbox",
            value="bbox",
            variable=self.drag_select_mode_var,
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            drag_mode_row,
            text="올가미",
            value="lasso",
            variable=self.drag_select_mode_var,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(
            option_frame,
            text="col,row 보기",
            variable=self.show_col_row_var,
            command=self._draw_scene,
        ).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(
            option_frame,
            text="show_grid",
            variable=self.show_grid_var,
            command=self._draw_scene,
        ).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(
            option_frame,
            text="polygon-point 연결 표시",
            variable=self.show_grid_mixed_links_var,
            command=self._draw_scene,
        ).grid(row=4, column=0, sticky="w")

        stats_frame = ttk.LabelFrame(right, text="통계", padding=(8, 6))
        stats_frame.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(stats_frame, textvariable=self.total_points_var).grid(row=0, column=0, sticky="w")
        ttk.Label(stats_frame, textvariable=self.missing_col_var).grid(row=1, column=0, sticky="w")
        ttk.Label(stats_frame, textvariable=self.missing_row_var).grid(row=2, column=0, sticky="w")

        preview_frame = ttk.LabelFrame(right, text="Grid Preview", padding=(8, 6))
        preview_frame.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        self.grid_preview_canvas = tk.Canvas(
            preview_frame,
            width=self.grid_preview_size[0],
            height=self.grid_preview_size[1],
            bg="#000000",
            highlightthickness=1,
            highlightbackground="#3a3a3a",
        )
        self.grid_preview_canvas.grid(row=0, column=0, sticky="nsew")

        self.col_var.trace_add("write", self._on_live_edit_changed)
        self.row_var.trace_add("write", self._on_live_edit_changed)

        status_row = ttk.Frame(root, padding=(8, 4))
        status_row.grid(row=1, column=0, columnspan=3, sticky="ew")
        status_row.columnconfigure(0, weight=1)
        ttk.Label(status_row, textvariable=self.status_var, anchor="w").grid(row=0, column=0, sticky="ew")
        ttk.Label(status_row, textvariable=self.focus_info_var, anchor="e").grid(row=0, column=1, sticky="e")

        # Promote the toplevel bindtag ahead of class tags so app shortcuts can run
        # before widget class bindings consume the event.
        self._promote_root_bindtag(self.root)
        self.root.after_idle(self._update_focus_info)

    def _promote_root_bindtag(self, widget: tk.Misc) -> None:
        root_tag = str(self.root)
        tags = list(widget.bindtags())
        if root_tag in tags:
            tags = [tag for tag in tags if tag != root_tag]
            # Put toplevel tag first so app shortcuts are not blocked by
            # widget-specific bindings returning "break".
            tags.insert(0, root_tag)
            widget.bindtags(tuple(tags))
        for child in widget.winfo_children():
            self._promote_root_bindtag(child)

    def choose_folder(self) -> None:
        folder = filedialog.askdirectory(title="이미지 폴더 선택")
        if not folder:
            return
        folder_path = Path(folder)
        if not folder_path.exists():
            messagebox.showerror("오류", "선택한 폴더가 존재하지 않습니다.")
            return

        self.folder_path = folder_path
        self.image_paths = list_images(folder_path)
        self.edited_images = {p for p in self.image_paths if sidecar_path_for(p).exists()}
        self._refresh_image_list(preserve_scroll=False)

        if not self.image_paths:
            self.current_index = -1
            self.current_state = None
            self.selected_ids.clear()
            self._draw_scene()
            self.status_var.set("이미지가 없습니다.")
            return

        self.load_index(0)
        self._restore_keyboard_focus()

    def load_index(self, index: int) -> None:
        if index < 0 or index >= len(self.image_paths):
            return
        self._autosave_if_needed()

        self.current_index = index
        image_path = self.image_paths[index]
        self.current_state = load_image_state(image_path)
        self.source_image = None
        self.source_image_path = None
        self.cached_draw_size = None
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.selected_ids.clear()
        self.next_manual_id = self._compute_next_manual_id()

        self._refresh_image_list(preserve_scroll=True)
        self.image_listbox.selection_clear(0, tk.END)
        self.image_listbox.selection_set(index)
        self.image_listbox.activate(index)
        self.image_listbox.see(index)

        self._draw_scene()
        self.status_var.set(f"{image_path.name} 로드 완료 ({len(self.current_state.objects)} objects)")
        self._restore_keyboard_focus()

    def prev_image(self) -> None:
        if self.current_index <= 0:
            return
        self.load_index(self.current_index - 1)

    def next_image(self) -> None:
        if self.current_index < 0 or self.current_index >= len(self.image_paths) - 1:
            return
        self.load_index(self.current_index + 1)

    def save_current(self) -> None:
        if not self.current_state:
            return
        save_image_state(self.current_state)
        self.edited_images.add(self.current_state.image_path)
        self._refresh_image_list(preserve_scroll=True)
        self.status_var.set(f"저장됨: {self.current_state.image_path.name}")

    def _autosave_if_needed(self) -> None:
        if self.current_state and self.current_state.dirty:
            save_image_state(self.current_state)
            self.edited_images.add(self.current_state.image_path)
            self._refresh_image_list(preserve_scroll=True)

    def _on_image_selected(self, _event: tk.Event) -> None:
        selection = self.image_listbox.curselection()
        if not selection:
            return
        target_index = int(selection[0])
        if target_index != self.current_index:
            self.load_index(target_index)
        self.canvas.focus_set()
        self._update_focus_info()

    def _on_listbox_arrow(self, event: tk.Event, dx: int, dy: int) -> str:
        self._on_nudge_key(event, dx=dx, dy=dy)
        # Prevent Listbox default Up/Down behavior (image selection change).
        return "break"

    def _draw_scene(self) -> None:
        self.canvas.delete("all")
        state = self.current_state
        if not state:
            self._update_side_panels([])
            return

        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)
        if canvas_w < 20 or canvas_h < 20:
            return

        image = self._get_source_image(state.image_path)
        if image is None:
            self.status_var.set(f"이미지 로드 실패: {state.image_path.name}")
            self._update_side_panels(state.objects)
            return
        self.image_size = (image.width, image.height)

        scale_w = canvas_w / image.width
        scale_h = canvas_h / image.height
        fit_scale = min(scale_w, scale_h)
        self.scale = fit_scale * self.zoom_factor
        draw_w = max(1, int(image.width * self.scale))
        draw_h = max(1, int(image.height * self.scale))
        self.canvas_size = (canvas_w, canvas_h)
        self.draw_size = (draw_w, draw_h)
        self.base_offset_x = (canvas_w - draw_w) / 2
        self.base_offset_y = (canvas_h - draw_h) / 2
        raw_offset_x = self.base_offset_x + self.pan_x
        raw_offset_y = self.base_offset_y + self.pan_y
        self.offset_x, self.offset_y = self._clamp_offset(raw_offset_x, raw_offset_y, canvas_w, canvas_h, draw_w, draw_h)
        self.pan_x = self.offset_x - self.base_offset_x
        self.pan_y = self.offset_y - self.base_offset_y

        if self.cached_draw_size != (draw_w, draw_h) or self.image_tk is None:
            resized = image.resize((draw_w, draw_h), Image.Resampling.BILINEAR)
            self.image_tk = ImageTk.PhotoImage(resized)
            self.cached_draw_size = (draw_w, draw_h)
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.image_tk, anchor=tk.NW)

        if self.show_grid_var.get():
            self._draw_grid_connections(state.objects)

        for obj in state.objects:
            cx, cy = self._to_canvas(obj.px, obj.py)
            is_selected = obj.object_id in self.selected_ids
            fill = "#ff4d4f" if is_selected else "#4ea1ff"
            if obj.source == "manual":
                fill = "#ffd166" if not is_selected else "#ff4d4f"
            r = 5 if is_selected else 4
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline="")

            if self.show_col_row_var.get() and (obj.col is not None or obj.row is not None):
                grid_text = f"{obj.col if obj.col is not None else '-'}, {obj.row if obj.row is not None else '-'}"
                self.canvas.create_text(cx + 8, cy - 8, text=grid_text, fill="#e6e6e6", anchor=tk.W, font=("Arial", 9))

        self._update_side_panels(state.objects)

    def _draw_grid_connections(self, objects: list[GridObject]) -> None:
        eligible = [obj for obj in objects if obj.col is not None and obj.row is not None]
        allow_mixed_links = self.show_grid_mixed_links_var.get()
        for i in range(len(eligible)):
            a = eligible[i]
            for j in range(i + 1, len(eligible)):
                b = eligible[j]
                if not allow_mixed_links and a.shape_type != b.shape_type:
                    continue
                same_col = a.col == b.col and abs((a.row or 0) - (b.row or 0)) == 1
                same_row = a.row == b.row and abs((a.col or 0) - (b.col or 0)) == 1
                if not (same_col or same_row):
                    continue
                x1, y1 = self._to_canvas(a.px, a.py)
                x2, y2 = self._to_canvas(b.px, b.py)
                self.canvas.create_line(x1, y1, x2, y2, fill="#6effa7", width=1)

    def _update_side_panels(self, objects: list[GridObject]) -> None:
        total = len(objects)
        missing_col = sum(1 for obj in objects if obj.col is None)
        missing_row = sum(1 for obj in objects if obj.row is None)
        self.total_points_var.set(f"전체 점 수: {total}")
        self.missing_col_var.set(f"col 미지정 점 수: {missing_col}")
        self.missing_row_var.set(f"row 미지정 점 수: {missing_row}")
        self._draw_grid_preview(objects)

    def _draw_grid_preview(self, objects: list[GridObject]) -> None:
        width, height = self.grid_preview_size
        img = Image.new("RGB", (width, height), "#000000")
        draw = ImageDraw.Draw(img)

        eligible = [obj for obj in objects if obj.col is not None and obj.row is not None]
        if eligible:
            cols = [int(obj.col) for obj in eligible if obj.col is not None]
            rows = [int(obj.row) for obj in eligible if obj.row is not None]
            min_col, max_col = min(cols), max(cols)
            min_row, max_row = min(rows), max(rows)

            margin = 20
            span_col = max(max_col - min_col, 1)
            span_row = max(max_row - min_row, 1)

            def to_preview_xy(obj: GridObject) -> tuple[float, float]:
                col = int(obj.col) if obj.col is not None else min_col
                row = int(obj.row) if obj.row is not None else min_row
                px = margin + ((col - min_col) / span_col) * (width - margin * 2)
                # row 0 at bottom
                py = height - margin - ((row - min_row) / span_row) * (height - margin * 2)
                return (px, py)

            # Always show grid links in preview.
            for i in range(len(eligible)):
                a = eligible[i]
                for j in range(i + 1, len(eligible)):
                    b = eligible[j]
                    same_col = a.col == b.col and abs((a.row or 0) - (b.row or 0)) == 1
                    same_row = a.row == b.row and abs((a.col or 0) - (b.col or 0)) == 1
                    if not (same_col or same_row):
                        continue
                    x1, y1 = to_preview_xy(a)
                    x2, y2 = to_preview_xy(b)
                    draw.line((x1, y1, x2, y2), fill="#6effa7", width=1)

            for obj in eligible:
                x, y = to_preview_xy(obj)
                color = "#ffd166" if obj.source == "manual" else "#4ea1ff"
                r = 3
                draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline=color)

        self.grid_preview_tk = ImageTk.PhotoImage(img)
        self.grid_preview_canvas.delete("all")
        self.grid_preview_canvas.create_image(0, 0, image=self.grid_preview_tk, anchor=tk.NW)

    def _on_canvas_press(self, event: tk.Event) -> None:
        if not self.current_state:
            return
        self.canvas.focus_set()
        self._update_focus_info()
        mode = self.mode_var.get()
        ctrl_pressed = bool(event.state & 0x0004)
        shift_pressed = bool(event.state & 0x0001)
        x_img, y_img = self._to_image(event.x, event.y)

        if ctrl_pressed:
            self._start_pan(event.x, event.y)
            return

        if mode == "select" and x_img is None:
            if not shift_pressed:
                self._clear_selection("선택 해제")
            return

        if x_img is None:
            return

        if mode == "add":
            self._add_manual_point(x_img, y_img)
            self._request_redraw()
            return

        if mode == "select":
            hovered = self._find_nearest_object(x_img, y_img)
            if shift_pressed and hovered is not None:
                if hovered.object_id in self.selected_ids:
                    self.selected_ids.remove(hovered.object_id)
                else:
                    self.selected_ids.add(hovered.object_id)
                self._sync_editor_with_selection()
                self._draw_scene()
                self.status_var.set(f"총 {len(self.selected_ids)}개 객체 선택됨")
                return

            if not shift_pressed:
                if hovered is not None and self._is_position_editable(hovered):
                    if hovered.object_id in self.selected_ids:
                        drag_ids = {
                            obj.object_id
                            for obj in self.current_state.objects
                            if obj.object_id in self.selected_ids and self._is_position_editable(obj)
                        }
                        if not drag_ids:
                            return
                    else:
                        drag_ids = {hovered.object_id}
                        self.selected_ids = {hovered.object_id}
                    self._start_point_drag(drag_ids, x_img, y_img)
                    return
            self._start_drag_box(event.x, event.y, additive=shift_pressed)
            return

    def _on_canvas_drag(self, event: tk.Event) -> None:
        if self.pan_anchor is not None and self.pan_anchor_offset is not None:
            dx = event.x - self.pan_anchor[0]
            dy = event.y - self.pan_anchor[1]
            target_offset_x = self.pan_anchor_offset[0] + dx
            target_offset_y = self.pan_anchor_offset[1] + dy
            canvas_w, canvas_h = self.canvas_size
            draw_w, draw_h = self.draw_size
            self.offset_x, self.offset_y = self._clamp_offset(
                target_offset_x,
                target_offset_y,
                canvas_w,
                canvas_h,
                draw_w,
                draw_h,
            )
            self.pan_x = self.offset_x - self.base_offset_x
            self.pan_y = self.offset_y - self.base_offset_y
            self._draw_scene()
            return

        if self.point_drag_ids is not None and self.point_drag_offsets is not None and self.current_state is not None:
            x_img, y_img = self._to_image(event.x, event.y)
            if x_img is None or y_img is None:
                return
            width, height = self.image_size
            for obj in self.current_state.objects:
                if obj.object_id not in self.point_drag_ids:
                    continue
                offset = self.point_drag_offsets.get(obj.object_id)
                if offset is None:
                    continue
                target_x = min(max(x_img + offset[0], 0.0), max(width - 1.0, 0.0))
                target_y = min(max(y_img + offset[1], 0.0), max(height - 1.0, 0.0))
                obj.px = target_x
                obj.py = target_y
                obj.points = [[target_x, target_y]]
            self.current_state.dirty = True
            self._request_redraw()
            return

        if self.drag_anchor is None:
            return
        if self.drag_select_mode_var.get() == "lasso":
            self._update_lasso_drag(event.x, event.y)
            return
        if self.drag_rect_id is None:
            return
        x0, y0 = self.drag_anchor
        self.canvas.coords(self.drag_rect_id, x0, y0, event.x, event.y)

    def _on_canvas_release(self, event: tk.Event) -> None:
        if self.pan_anchor is not None:
            self.pan_anchor = None
            self.pan_anchor_offset = None
            self.canvas.configure(cursor="")
            return

        if self.point_drag_ids is not None:
            self.point_drag_ids = None
            self.point_drag_offsets = None
            self.canvas.configure(cursor="")
            self._sync_editor_with_selection()
            self._request_redraw()
            return

        if self.drag_anchor is None:
            return
        x0, y0 = self.drag_anchor
        x1, y1 = event.x, event.y
        self.drag_anchor = None

        if not self.current_state:
            return

        if self.drag_select_mode_var.get() == "lasso":
            selected = self._finalize_lasso_selection(x1, y1)
        else:
            selected = self._finalize_bbox_selection(x0, y0, x1, y1)

        if self.drag_additive:
            self.selected_ids |= selected
        else:
            self.selected_ids = selected
        self.drag_additive = False
        self._sync_editor_with_selection()
        self._draw_scene()
        self.status_var.set(f"총 {len(self.selected_ids)}개 객체 선택됨")

    def _finalize_bbox_selection(self, x0: float, y0: float, x1: float, y1: float) -> set[str]:
        if self.drag_rect_id is not None:
            self.canvas.delete(self.drag_rect_id)
            self.drag_rect_id = None

        ix0, iy0 = self._to_image(x0, y0)
        ix1, iy1 = self._to_image(x1, y1)
        if ix0 is None or iy0 is None or ix1 is None or iy1 is None or not self.current_state:
            return set()

        min_x, max_x = sorted((ix0, ix1))
        min_y, max_y = sorted((iy0, iy1))
        x_span = abs(x1 - x0)
        y_span = abs(y1 - y0)
        if x_span < 4 and y_span < 4:
            picked = self._find_nearest_object(ix1, iy1)
            return set() if picked is None else {picked.object_id}
        return {
            obj.object_id
            for obj in self.current_state.objects
            if min_x <= obj.px <= max_x and min_y <= obj.py <= max_y
        }

    def _finalize_lasso_selection(self, x1: float, y1: float) -> set[str]:
        if not self.current_state:
            return set()
        self._update_lasso_drag(x1, y1)
        points = list(self.drag_lasso_points)
        self._clear_lasso_overlay()

        if len(points) < 3:
            ix, iy = self._to_image(x1, y1)
            if ix is None or iy is None:
                return set()
            picked = self._find_nearest_object(ix, iy)
            return set() if picked is None else {picked.object_id}

        xs = [pt[0] for pt in points]
        ys = [pt[1] for pt in points]
        if (max(xs) - min(xs)) < 4 and (max(ys) - min(ys)) < 4:
            ix, iy = self._to_image(x1, y1)
            if ix is None or iy is None:
                return set()
            picked = self._find_nearest_object(ix, iy)
            return set() if picked is None else {picked.object_id}

        selected: set[str] = set()
        for obj in self.current_state.objects:
            cx, cy = self._to_canvas(obj.px, obj.py)
            if self._point_in_polygon(cx, cy, points):
                selected.add(obj.object_id)
        return selected

    def _on_canvas_motion(self, event: tk.Event) -> None:
        x_img, y_img = self._to_image(event.x, event.y)
        if x_img is None:
            self.canvas.configure(cursor="")
            return
        hovered = self._find_nearest_object(x_img, y_img)
        self.canvas.configure(cursor="hand2" if hovered else "")

    def _on_canvas_double_click(self, event: tk.Event) -> None:
        if not self.current_state:
            return
        x_img, y_img = self._to_image(event.x, event.y)
        if x_img is None or y_img is None:
            return
        obj = self._find_nearest_object(x_img, y_img)
        if obj is None:
            return
        self._open_point_editor(obj)

    def _on_mouse_wheel(self, event: tk.Event) -> str | None:
        if not self.current_state:
            return None

        steps = event.delta / 120.0
        if steps == 0:
            return "break"

        ctrl_pressed = bool(event.state & 0x0004)
        shift_pressed = bool(event.state & 0x0001)

        if ctrl_pressed:
            factor_step = 1.0 + self.config.zoom_sensitivity
            new_zoom = self.zoom_factor * (factor_step ** steps)
            self.zoom_factor = min(max(new_zoom, self.config.zoom_min), self.config.zoom_max)
            self._request_redraw()
            return "break"

        wheel_pan_px = 45.0
        if shift_pressed:
            self._pan_by_pixels(-steps * wheel_pan_px, 0.0)
        else:
            self._pan_by_pixels(0.0, steps * wheel_pan_px)
        return "break"

    def _on_undo_shortcut(self, _event: tk.Event) -> str:
        self.undo_last_action()
        return "break"

    def _on_redo_shortcut(self, _event: tk.Event) -> str:
        self.redo_last_action()
        return "break"

    def _event_matches_shortcut(self, event: tk.Event, key: str) -> bool:
        key_lower = key.lower()
        keysym = (event.keysym or "").lower()
        if keysym == key_lower:
            return True
        char = (event.char or "").lower()
        if char == key_lower:
            return True
        raw_keysym = event.keysym or ""
        if raw_keysym in self.shortcut_hangul_chars.get(key_lower, set()):
            return True
        raw_char = event.char or ""
        if raw_char in self.shortcut_hangul_chars.get(key_lower, set()):
            return True
        return event.keycode in self.shortcut_keycodes.get(key_lower, set())

    def _on_global_keypress(self, event: tk.Event) -> str | None:
        self._update_focus_info()
        keysym = (event.keysym or "").lower()

        if self._is_shortcut_modifier_pressed(event):
            if self._event_matches_shortcut(event, "z"):
                return self._on_undo_shortcut(event)
            if self._event_matches_shortcut(event, "y"):
                return self._on_redo_shortcut(event)
            if self._event_matches_shortcut(event, "c"):
                return self._on_copy_shortcut(event)
            if self._event_matches_shortcut(event, "v"):
                return self._on_paste_shortcut(event)
            if self._event_matches_shortcut(event, "s"):
                return self._on_save_shortcut(event)
            if keysym == "left":
                return self._on_grid_nudge_shortcut(event, dx=-1, dy=0)
            if keysym == "right":
                return self._on_grid_nudge_shortcut(event, dx=1, dy=0)
            if keysym == "up":
                return self._on_grid_nudge_shortcut(event, dx=0, dy=-1)
            if keysym == "down":
                return self._on_grid_nudge_shortcut(event, dx=0, dy=1)
            return None

        # Unmodified key handling.
        if keysym == "left":
            return self._on_nudge_key(event, dx=-1, dy=0)
        if keysym == "right":
            return self._on_nudge_key(event, dx=1, dy=0)
        if keysym == "up":
            return self._on_nudge_key(event, dx=0, dy=-1)
        if keysym == "down":
            return self._on_nudge_key(event, dx=0, dy=1)
        if keysym in {"delete", "backspace"}:
            return self._on_delete_selected(event)

        # Mode/navigation shortcuts should work regardless of current focus.
        if self._event_matches_shortcut(event, "r"):
            return self._on_shortcut_add_mode(event)
        if self._event_matches_shortcut(event, "e"):
            return self._on_shortcut_select_mode(event)
        if self._event_matches_shortcut(event, "f"):
            return self._on_shortcut_fit_view(event)
        if self._event_matches_shortcut(event, "a"):
            return self._on_prev_image_shortcut(event)
        if self._event_matches_shortcut(event, "d"):
            return self._on_next_image_shortcut(event)

        # Numeric quick-assign/select should not interfere while typing in inputs.
        if self._is_text_input_focused():
            return None
        return self._on_quick_numeric_input(event)

    def _on_grid_nudge_shortcut(self, event: tk.Event, dx: int, dy: int) -> str | None:
        return self._on_nudge_key(event, dx=dx, dy=dy, force_grid_edit=True)

    def _on_shortcut_add_mode(self, _event: tk.Event) -> str:
        self._set_mode("add", "모드: 점 추가")
        return "break"

    def _on_shortcut_select_mode(self, _event: tk.Event) -> str:
        self._set_mode("select", "모드: 선택/편집")
        return "break"

    def _on_shortcut_fit_view(self, _event: tk.Event) -> str | None:
        self.zoom_factor = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._request_redraw()
        self.status_var.set("화면 맞춤 보기")
        return "break"

    def _on_prev_image_shortcut(self, _event: tk.Event) -> str | None:
        self.prev_image()
        return "break"

    def _on_next_image_shortcut(self, _event: tk.Event) -> str | None:
        self.next_image()
        return "break"

    def _on_save_shortcut(self, _event: tk.Event) -> str:
        self.save_current()
        return "break"

    def _on_delete_selected(self, _event: tk.Event) -> str | None:
        if not self.current_state or not self.selected_ids:
            return None
        if self._is_text_input_focused():
            return None

        selected_ids = set(self.selected_ids)
        kept_objects: list[GridObject] = []
        kept_selected_ids: set[str] = set()
        removed = 0
        protected = 0
        for obj in self.current_state.objects:
            if obj.object_id not in selected_ids:
                kept_objects.append(obj)
                continue
            if self._is_delete_protected_object(obj):
                kept_objects.append(obj)
                kept_selected_ids.add(obj.object_id)
                protected += 1
                continue
            removed += 1

        if removed <= 0:
            if protected > 0:
                self.selected_ids = kept_selected_ids
                self._sync_editor_with_selection()
                self.status_var.set("병뚜껑 객체는 Delete로 삭제할 수 없습니다.")
            return "break"

        self._push_undo_state()
        self.current_state.objects = kept_objects
        self.current_state.dirty = True
        self.selected_ids = kept_selected_ids
        self._sync_editor_with_selection()
        self._clear_quick_input_buffer()
        self.next_manual_id = self._compute_next_manual_id()
        self._draw_scene()
        if protected > 0:
            self.status_var.set(f"{removed}개 객체 삭제됨 (병뚜껑 {protected}개 보호)")
        else:
            self.status_var.set(f"{removed}개 객체 삭제됨")
        return "break"

    def _on_copy_shortcut(self, _event: tk.Event) -> str | None:
        if not self.current_state or not self.selected_ids:
            return None
        if self._is_text_input_focused():
            return None

        selected_objects = [
            obj
            for obj in self.current_state.objects
            if obj.object_id in self.selected_ids and obj.shape_type == "point"
        ]
        if not selected_objects:
            self.status_var.set("복사할 수 있는 point 객체가 선택되어 있지 않습니다.")
            return "break"

        selected_objects.sort(key=lambda o: (o.py, o.px, o.object_id))
        self.copied_objects = [copy.deepcopy(obj) for obj in selected_objects]
        self.paste_serial = 0
        self.status_var.set(f"{len(self.copied_objects)}개 점 객체 복사됨")
        return "break"

    def _on_paste_shortcut(self, _event: tk.Event) -> str | None:
        if not self.current_state:
            return None
        if self._is_text_input_focused():
            return None
        if not self.copied_objects:
            messagebox.showinfo("붙여넣기 불가", "먼저 Ctrl+C로 복사하세요.")
            return "break"

        self._push_undo_state()
        self.paste_serial += 1
        dx = self.paste_offset_px[0] * self.paste_serial
        dy = self.paste_offset_px[1] * self.paste_serial
        width, height = self.image_size
        if width <= 0 or height <= 0:
            source_img = self._get_source_image(self.current_state.image_path)
            if source_img is not None:
                width, height = source_img.width, source_img.height

        new_selected_ids: set[str] = set()
        for src in self.copied_objects:
            raw_x = src.px + dx
            raw_y = src.py + dy
            if width > 0 and height > 0:
                new_x = min(max(raw_x, 0.0), width - 1.0)
                new_y = min(max(raw_y, 0.0), height - 1.0)
            else:
                new_x = raw_x
                new_y = raw_y

            new_id = f"m{self.next_manual_id}"
            self.next_manual_id += 1
            new_obj = GridObject(
                object_id=new_id,
                px=new_x,
                py=new_y,
                col=src.col,
                row=src.row,
                source="manual",
                label=src.label or "empty_slot",
                shape_type="point",
                points=[[new_x, new_y]],
                original_shapes=[],
            )
            self.current_state.objects.append(new_obj)
            new_selected_ids.add(new_id)

        self.current_state.dirty = True
        self.selected_ids = new_selected_ids
        self._clear_quick_input_buffer()
        self._sync_editor_with_selection()
        self._draw_scene()
        self.status_var.set(f"{len(new_selected_ids)}개 점 객체 붙여넣기 완료")
        return "break"

    def _on_quick_numeric_input(self, event: tk.Event) -> str | None:
        if not self.current_state:
            return None
        if event.state & 0x0004:
            return None

        if self._is_text_input_focused():
            return None

        char = event.char or ""
        if not char.isdigit():
            return None

        if self.quick_input_after_id is not None:
            self.root.after_cancel(self.quick_input_after_id)
            self.quick_input_after_id = None

        # Treat quick numeric input as single-digit overwrite.
        self.quick_input_buffer = char
        value = int(char)
        target = self.quick_assign_target_var.get()
        if self.selected_ids:
            self._apply_quick_assign_value(target, value)
        else:
            self._select_objects_by_grid_value(target, value)
        self.quick_input_after_id = self.root.after(800, self._clear_quick_input_buffer)
        return "break"

    def _apply_quick_assign_value(self, target: str, value: int) -> None:
        if not self.current_state or not self.selected_ids:
            return
        selected_objects = [obj for obj in self.current_state.objects if obj.object_id in self.selected_ids]
        if not selected_objects:
            return

        if target == "row":
            if all(obj.row == value for obj in selected_objects):
                return
        else:
            if all(obj.col == value for obj in selected_objects):
                return

        self._push_undo_state()
        for obj in selected_objects:
            if target == "row":
                obj.row = value
            else:
                obj.col = value

        if target == "col":
            self._auto_assign_rows_for_columns({value})

        self.current_state.dirty = True
        if target == "row":
            self._set_editor_values(self.col_var.get(), str(value))
        else:
            self._set_editor_values(str(value), self.row_var.get())
        self._draw_scene()
        self.status_var.set(f"{len(selected_objects)}개 객체 {target}={value} 적용")

    def _clear_quick_input_buffer(self) -> None:
        self.quick_input_after_id = None
        self.quick_input_buffer = ""

    def _select_objects_by_grid_value(self, target: str, value: int) -> None:
        if not self.current_state:
            return
        if target == "row":
            matched = {obj.object_id for obj in self.current_state.objects if obj.row == value}
        else:
            matched = {obj.object_id for obj in self.current_state.objects if obj.col == value}

        self.selected_ids = matched
        self._sync_editor_with_selection()
        self._draw_scene()
        self.status_var.set(f"{target}={value} 객체 {len(matched)}개 선택됨")

    def _on_nudge_key(self, _event: tk.Event, dx: int, dy: int, force_grid_edit: bool = False) -> str | None:
        if not self.current_state or not self.selected_ids:
            return None

        if self._is_text_input_focused():
            return None

        ctrl_pressed = force_grid_edit or bool(_event.state & 0x0004)
        selected_objects = [obj for obj in self.current_state.objects if obj.object_id in self.selected_ids]
        if not selected_objects:
            return None

        if ctrl_pressed:
            self._push_undo_state()
            if dx != 0:
                affected_cols: set[int] = set()
                for obj in selected_objects:
                    if obj.col is not None:
                        affected_cols.add(obj.col)
                    base_col = obj.col if obj.col is not None else 0
                    obj.col = base_col + dx
                    affected_cols.add(obj.col)
                self._auto_assign_rows_for_columns(affected_cols)
                self.current_state.dirty = True
                self._draw_scene()
                self.status_var.set(f"{len(selected_objects)}개 객체 col {dx:+d} 적용 (row 자동)")
                return "break"

            if dy != 0:
                delta_row = -dy
                for obj in selected_objects:
                    base_row = obj.row if obj.row is not None else 0
                    obj.row = base_row + delta_row
                self.current_state.dirty = True
                self._draw_scene()
                self.status_var.set(f"{len(selected_objects)}개 객체 row {delta_row:+d} 적용")
                return "break"

            return "break"

        width, height = self.image_size
        if width <= 0 or height <= 0:
            return None

        movable = [
            obj
            for obj in self.current_state.objects
            if obj.object_id in self.selected_ids and obj.shape_type == "point"
        ]
        if not movable:
            self.status_var.set("point 객체만 방향키 이동이 가능합니다.")
            return "break"

        self._push_undo_state()
        step = self.nudge_step_px
        for obj in movable:
            next_x = min(max(obj.px + dx * step, 0.0), width - 1.0)
            next_y = min(max(obj.py + dy * step, 0.0), height - 1.0)
            obj.px = next_x
            obj.py = next_y
            obj.points = [[next_x, next_y]]

        self.current_state.dirty = True
        self._draw_scene()
        self.status_var.set(f"{len(movable)}개 point 객체 이동됨")
        return "break"

    def _open_point_editor(self, obj: GridObject) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("점 객체 편집")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        frame = ttk.Frame(dialog, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(frame, text=f"id: {obj.object_id}").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="col").grid(row=1, column=0, sticky="w", pady=(8, 0))
        col_var = tk.StringVar(value="" if obj.col is None else str(obj.col))
        col_entry = ttk.Entry(frame, textvariable=col_var, width=12)
        col_entry.grid(row=1, column=1, sticky="ew", pady=(8, 0))

        ttk.Label(frame, text="row").grid(row=2, column=0, sticky="w", pady=(6, 0))
        row_var = tk.StringVar(value="" if obj.row is None else str(obj.row))
        row_entry = ttk.Entry(frame, textvariable=row_var, width=12)
        row_entry.grid(row=2, column=1, sticky="ew", pady=(6, 0))

        button_row = ttk.Frame(frame)
        button_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        def on_apply() -> None:
            col, col_ok = self._parse_optional_int(col_var.get())
            row, row_ok = self._parse_optional_int(row_var.get())
            if not col_ok or not row_ok:
                return
            self._push_undo_state()
            prev_col = obj.col
            obj.col = col
            obj.row = row
            if col is not None and prev_col != col:
                affected_cols = {col}
                if prev_col is not None:
                    affected_cols.add(prev_col)
                self._auto_assign_rows_for_columns(affected_cols)
            self.current_state.dirty = True
            self.selected_ids = {obj.object_id}
            self._sync_editor_with_selection()
            self._draw_scene()
            self.status_var.set(f"{obj.object_id} 수정됨")
            dialog.destroy()

        ttk.Button(button_row, text="적용", command=on_apply).pack(side=tk.LEFT)
        ttk.Button(button_row, text="취소", command=dialog.destroy).pack(side=tk.LEFT, padx=(6, 0))

        col_entry.focus_set()
        dialog.bind("<Return>", lambda _e: on_apply())
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def _start_drag_box(self, x: float, y: float, additive: bool) -> None:
        self.drag_anchor = (x, y)
        self.drag_additive = additive
        if self.drag_select_mode_var.get() == "lasso":
            self._clear_lasso_overlay()
            if self.drag_rect_id is not None:
                self.canvas.delete(self.drag_rect_id)
                self.drag_rect_id = None
            self.drag_lasso_points = [(x, y)]
            self.drag_lasso_id = self.canvas.create_line(
                x, y, x, y, fill="#00d1ff", width=1, smooth=False
            )
            self.drag_lasso_close_id = self.canvas.create_line(
                x, y, x, y, fill="#00d1ff", width=1, dash=(3, 2)
            )
            return

        if self.drag_rect_id:
            self.canvas.delete(self.drag_rect_id)
        self.drag_rect_id = self.canvas.create_rectangle(x, y, x, y, outline="#00d1ff", dash=(4, 2))
        self._clear_lasso_overlay()

    def _update_lasso_drag(self, x: float, y: float) -> None:
        if not self.drag_lasso_points:
            self.drag_lasso_points = [(x, y)]
        last_x, last_y = self.drag_lasso_points[-1]
        if abs(last_x - x) + abs(last_y - y) >= 2:
            self.drag_lasso_points.append((x, y))

        if self.drag_lasso_id is not None:
            render_points = list(self.drag_lasso_points)
            # Canvas line needs at least two points (4 coordinates).
            if len(render_points) == 1:
                render_points.append((x, y))
            flat_points = [coord for pt in render_points for coord in pt]
            self.canvas.coords(self.drag_lasso_id, *flat_points)
        if self.drag_lasso_close_id is not None and self.drag_lasso_points:
            start_x, start_y = self.drag_lasso_points[0]
            self.canvas.coords(self.drag_lasso_close_id, start_x, start_y, x, y)

    def _clear_lasso_overlay(self) -> None:
        if self.drag_lasso_id is not None:
            self.canvas.delete(self.drag_lasso_id)
            self.drag_lasso_id = None
        if self.drag_lasso_close_id is not None:
            self.canvas.delete(self.drag_lasso_close_id)
            self.drag_lasso_close_id = None
        self.drag_lasso_points = []

    def _point_in_polygon(self, x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
        inside = False
        n = len(polygon)
        if n < 3:
            return False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersects = ((yi > y) != (yj > y)) and (
                x < ((xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi)
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    def _start_pan(self, x: float, y: float) -> None:
        self.pan_anchor = (x, y)
        self.pan_anchor_offset = (self.offset_x, self.offset_y)
        self.canvas.configure(cursor="fleur")

    def _start_point_drag(self, drag_ids: set[str], x_img: float, y_img: float) -> None:
        if not self.current_state:
            return
        drag_objects = [obj for obj in self.current_state.objects if obj.object_id in drag_ids]
        if not drag_objects:
            return
        self._push_undo_state()
        self.point_drag_ids = {obj.object_id for obj in drag_objects}
        self.point_drag_offsets = {
            obj.object_id: (obj.px - x_img, obj.py - y_img)
            for obj in drag_objects
        }
        self.canvas.configure(cursor="fleur")

    def _is_position_editable(self, obj: GridObject) -> bool:
        return obj.shape_type == "point"

    def _add_manual_point(self, px: float, py: float) -> None:
        if not self.current_state:
            return
        self._push_undo_state()
        new_id = f"m{self.next_manual_id}"
        self.next_manual_id += 1
        self.current_state.objects.append(
            GridObject(
                object_id=new_id,
                px=px,
                py=py,
                source="manual",
                label="empty_slot",
                shape_type="point",
                points=[[px, py]],
            )
        )
        self.current_state.dirty = True
        self.selected_ids = {new_id}
        self._sync_editor_with_selection()
        self.status_var.set("점 객체가 추가되었습니다.")

    def _find_nearest_object(self, x_img: float, y_img: float) -> GridObject | None:
        if not self.current_state or not self.current_state.objects:
            return None
        threshold = 10.0 / max(self.scale, 1e-6)
        best_obj: GridObject | None = None
        best_dist_sq = threshold * threshold
        for obj in self.current_state.objects:
            dx = obj.px - x_img
            dy = obj.py - y_img
            dist_sq = dx * dx + dy * dy
            if dist_sq <= best_dist_sq:
                best_dist_sq = dist_sq
                best_obj = obj
        return best_obj

    def apply_single_edit(self) -> None:
        if not self.current_state or not self.selected_ids:
            return
        col, col_ok = self._parse_optional_int(self.col_var.get())
        row, row_ok = self._parse_optional_int(self.row_var.get())
        if not col_ok or not row_ok:
            return

        self._push_undo_state()
        affected_cols: set[int] = set()
        col_changed = False
        for obj in self.current_state.objects:
            if obj.object_id in self.selected_ids:
                if obj.col != col:
                    col_changed = True
                    if obj.col is not None:
                        affected_cols.add(obj.col)
                    if col is not None:
                        affected_cols.add(col)
                obj.col = col
                obj.row = row
        if col_changed:
            self._auto_assign_rows_for_columns(affected_cols)

        self.current_state.dirty = True
        self._draw_scene()
        self.status_var.set(f"{len(self.selected_ids)}개 객체 수정됨")

    def apply_batch_column(self) -> None:
        if not self.current_state:
            return
        if not self.selected_ids:
            messagebox.showinfo("안내", "먼저 객체를 선택하세요.")
            return

        selected_objects = [obj for obj in self.current_state.objects if obj.object_id in self.selected_ids]
        cols = {obj.col for obj in selected_objects}
        if None in cols:
            messagebox.showinfo("불가", "선택 객체 중 col이 없는 점이 있어 row 자동 배정을 할 수 없습니다.")
            return
        if len(cols) != 1:
            messagebox.showinfo("불가", "선택 객체에 서로 다른 col 값이 섞여 있어 row 자동 배정을 할 수 없습니다.")
            return
        target_col = next(iter(cols))
        assert target_col is not None

        self._push_undo_state()
        same_col = [obj for obj in self.current_state.objects if obj.col == target_col]
        same_col.sort(key=lambda obj: obj.py, reverse=True)
        for idx, obj in enumerate(same_col):
            obj.row = idx

        self.current_state.dirty = True
        self._draw_scene()
        self.status_var.set(f"col={target_col} 기준 row 자동 지정 완료 ({len(same_col)}개 대상)")

    def _sync_editor_with_selection(self) -> None:
        if not self.current_state or len(self.selected_ids) != 1:
            self._set_editor_values("", "")
            return

        only_id = next(iter(self.selected_ids))
        obj = next((o for o in self.current_state.objects if o.object_id == only_id), None)
        if obj is None:
            self._set_editor_values("", "")
            return
        self._set_editor_values(
            "" if obj.col is None else str(obj.col),
            "" if obj.row is None else str(obj.row),
        )

    def _to_canvas(self, x_img: float, y_img: float) -> tuple[float, float]:
        return (self.offset_x + x_img * self.scale, self.offset_y + y_img * self.scale)

    def _to_image(self, x_canvas: float, y_canvas: float) -> tuple[float | None, float | None]:
        if self.scale <= 0:
            return (None, None)
        x_img = (x_canvas - self.offset_x) / self.scale
        y_img = (y_canvas - self.offset_y) / self.scale
        if self.current_state is None:
            return (None, None)
        width, height = self.image_size

        if x_img < 0 or y_img < 0 or x_img >= width or y_img >= height:
            return (None, None)
        return (x_img, y_img)

    def _parse_optional_int(self, value: str) -> tuple[int | None, bool]:
        text = value.strip()
        if not text:
            return (None, True)
        try:
            return (int(text), True)
        except ValueError:
            messagebox.showerror("입력 오류", "정수를 입력하세요.")
            return (None, False)

    def _parse_optional_int_silent(self, value: str) -> tuple[int | None, bool]:
        text = value.strip()
        if not text:
            return (None, True)
        try:
            return (int(text), True)
        except ValueError:
            return (None, False)

    def _parse_required_int(self, value: str, name: str) -> int | None:
        text = value.strip()
        if not text:
            messagebox.showerror("입력 오류", f"{name} 값을 입력하세요.")
            return None
        try:
            return int(text)
        except ValueError:
            messagebox.showerror("입력 오류", f"{name}는 정수여야 합니다.")
            return None

    def _compute_next_manual_id(self) -> int:
        if not self.current_state:
            return 0
        max_index = -1
        for obj in self.current_state.objects:
            if obj.object_id.startswith("m"):
                suffix = obj.object_id[1:]
                if suffix.isdigit():
                    max_index = max(max_index, int(suffix))
        return max_index + 1

    def on_close(self) -> None:
        if self.live_apply_after_id is not None:
            self.root.after_cancel(self.live_apply_after_id)
            self.live_apply_after_id = None
        if self.quick_input_after_id is not None:
            self.root.after_cancel(self.quick_input_after_id)
            self.quick_input_after_id = None
        if self.redraw_after_id is not None:
            self.root.after_cancel(self.redraw_after_id)
            self.redraw_after_id = None
        self._autosave_if_needed()
        self.root.destroy()

    def undo_last_action(self) -> None:
        if not self.current_state or not self.undo_stack:
            return
        self.redo_stack.append(copy.deepcopy(self.current_state.objects))
        self.current_state.objects = self.undo_stack.pop()
        self.current_state.dirty = True
        self.selected_ids.clear()
        self.next_manual_id = self._compute_next_manual_id()
        self._sync_editor_with_selection()
        self._draw_scene()
        self.status_var.set("되돌리기 완료")

    def redo_last_action(self) -> None:
        if not self.current_state or not self.redo_stack:
            return
        self.undo_stack.append(copy.deepcopy(self.current_state.objects))
        self.current_state.objects = self.redo_stack.pop()
        self.current_state.dirty = True
        self.selected_ids.clear()
        self.next_manual_id = self._compute_next_manual_id()
        self._sync_editor_with_selection()
        self._draw_scene()
        self.status_var.set("다시 실행 완료")

    def _push_undo_state(self) -> None:
        if not self.current_state:
            return
        self.undo_stack.append(copy.deepcopy(self.current_state.objects))
        self.redo_stack.clear()
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)

    def _set_mode(self, mode: str, status: str) -> None:
        self.mode_var.set(mode)
        self.status_var.set(status)

    def _clear_selection(self, status_message: str | None = None) -> None:
        self.selected_ids.clear()
        self._sync_editor_with_selection()
        self._draw_scene()
        if status_message is not None:
            self.status_var.set(status_message)

    def _on_focus_changed(self, _event: tk.Event) -> None:
        self.root.after_idle(self._update_focus_info)

    def _update_focus_info(self) -> None:
        focus_widget = self.root.focus_get()
        if focus_widget is None:
            self.focus_info_var.set("focus: none")
            return
        widget_name = str(focus_widget)
        widget_class = str(focus_widget.winfo_class())
        self.focus_info_var.set(f"focus: {widget_class} ({widget_name})")

    def _is_text_input_focused(self) -> bool:
        focus_widget = self.root.focus_get()
        if focus_widget is None:
            return False
        focus_class = str(focus_widget.winfo_class())
        return focus_class in {"Entry", "TEntry", "Text", "Spinbox", "TCombobox"}

    def _is_shortcut_modifier_pressed(self, event: tk.Event) -> bool:
        # Tk state bits: Control=0x0004, Mod1=0x0008, Mod2=0x0010.
        # On Windows/Linux we treat only Control as app-shortcut modifier.
        # On macOS, Command is usually Mod2 (and can map via Mod1 in some setups).
        if sys.platform == "darwin":
            return bool(event.state & (0x0004 | 0x0008 | 0x0010))
        return bool(event.state & 0x0004)

    def _normalize_label_token(self, label: str) -> str:
        lowered = (label or "").strip().lower()
        return lowered.replace(" ", "").replace("_", "").replace("-", "")

    def _is_delete_protected_object(self, obj: GridObject) -> bool:
        # Only `empty_slot` labels can be deleted.
        return self._normalize_label_token(obj.label) != "emptyslot"

    def _set_editor_values(self, col_text: str, row_text: str) -> None:
        self.live_apply_suspended = True
        self.col_var.set(col_text)
        self.row_var.set(row_text)
        self.live_apply_suspended = False

    def _on_live_edit_changed(self, *_args: object) -> None:
        if self.live_apply_suspended:
            return
        if self.live_apply_after_id is not None:
            self.root.after_cancel(self.live_apply_after_id)
            self.live_apply_after_id = None
        self.live_apply_after_id = self.root.after(180, self._apply_live_edit_if_valid)

    def _apply_live_edit_if_valid(self) -> None:
        self.live_apply_after_id = None
        if not self.current_state or not self.selected_ids:
            return
        col, col_ok = self._parse_optional_int_silent(self.col_var.get())
        row, row_ok = self._parse_optional_int_silent(self.row_var.get())
        if not col_ok or not row_ok:
            return

        selected_objects = [obj for obj in self.current_state.objects if obj.object_id in self.selected_ids]
        if not selected_objects:
            return
        if all(obj.col == col and obj.row == row for obj in selected_objects):
            return

        self._push_undo_state()
        affected_cols: set[int] = set()
        col_changed = False
        for obj in selected_objects:
            if obj.col != col:
                col_changed = True
                if obj.col is not None:
                    affected_cols.add(obj.col)
                if col is not None:
                    affected_cols.add(col)
            obj.col = col
            obj.row = row
        if col_changed:
            self._auto_assign_rows_for_columns(affected_cols)

        self.current_state.dirty = True
        self._draw_scene()
        self.status_var.set(f"{len(selected_objects)}개 객체 즉시 수정됨")

    def _auto_assign_rows_for_columns(self, columns: set[int]) -> None:
        if not self.current_state:
            return
        for col in columns:
            same_col = [obj for obj in self.current_state.objects if obj.col == col]
            same_col.sort(key=lambda obj: obj.py, reverse=True)
            for idx, obj in enumerate(same_col):
                obj.row = idx

    def _pan_by_pixels(self, dx: float, dy: float) -> None:
        canvas_w, canvas_h = self.canvas_size
        draw_w, draw_h = self.draw_size
        if canvas_w <= 0 or canvas_h <= 0 or draw_w <= 0 or draw_h <= 0:
            return
        next_offset_x = self.offset_x + dx
        next_offset_y = self.offset_y + dy
        self.offset_x, self.offset_y = self._clamp_offset(
            next_offset_x,
            next_offset_y,
            canvas_w,
            canvas_h,
            draw_w,
            draw_h,
        )
        self.pan_x = self.offset_x - self.base_offset_x
        self.pan_y = self.offset_y - self.base_offset_y
        self._request_redraw()

    def _clamp_offset(
        self,
        offset_x: float,
        offset_y: float,
        canvas_w: int,
        canvas_h: int,
        draw_w: int,
        draw_h: int,
    ) -> tuple[float, float]:
        if draw_w <= canvas_w:
            clamped_x = (canvas_w - draw_w) / 2
        else:
            min_x = canvas_w - draw_w
            max_x = 0.0
            clamped_x = min(max(offset_x, min_x), max_x)

        if draw_h <= canvas_h:
            clamped_y = (canvas_h - draw_h) / 2
        else:
            min_y = canvas_h - draw_h
            max_y = 0.0
            clamped_y = min(max(offset_y, min_y), max_y)
        return (clamped_x, clamped_y)

    def _get_source_image(self, image_path: Path) -> Image.Image | None:
        if self.source_image is not None and self.source_image_path == image_path:
            return self.source_image
        try:
            loaded = Image.open(image_path).convert("RGB")
        except OSError:
            return None
        self.source_image = loaded
        self.source_image_path = image_path
        return self.source_image

    def _request_redraw(self) -> None:
        if self.redraw_after_id is not None:
            return
        self.redraw_after_id = self.root.after_idle(self._perform_scheduled_redraw)

    def _perform_scheduled_redraw(self) -> None:
        self.redraw_after_id = None
        self._draw_scene()

    def _refresh_image_list(self, preserve_scroll: bool = True) -> None:
        yview = self.image_listbox.yview() if preserve_scroll else None
        self.image_listbox.delete(0, tk.END)
        for idx, path in enumerate(self.image_paths):
            edited = path in self.edited_images
            prefix = "✓ " if edited else ""
            self.image_listbox.insert(tk.END, f"{prefix}[{idx}] {path.name}")
            if edited:
                self.image_listbox.itemconfig(idx, foreground="#22aa22")
        if yview and len(yview) == 2:
            self.image_listbox.yview_moveto(yview[0])

    def _restore_keyboard_focus(self) -> None:
        self.root.after_idle(self.root.focus_set)
        self.root.after_idle(self.canvas.focus_set)
