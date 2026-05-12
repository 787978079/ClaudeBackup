"""设置对话框：定时时间 / 主题 / 自启动 / 通知 / 系统集成."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QTimeEdit, QVBoxLayout, QWidget,
)

from . import dialogs, i18n
from .workers import run_async
from .. import config, core, paths, system_integration as si
from .widgets import PrimaryButton, SecondaryButton, make_label, make_separator


class _IntegrationRow(QWidget):
    """一行：[标题] [状态] [启用/禁用按钮]，封装系统集成的检测+开关."""

    def __init__(self, parent: QWidget | None,
                 title: str, hint: str,
                 check_fn, install_fn, uninstall_fn):
        super().__init__(parent)
        self._check = check_fn
        self._install = install_fn
        self._uninstall = uninstall_fn

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 6)
        outer.setSpacing(2)

        row = QHBoxLayout()
        row.setSpacing(10)
        title_lb = QLabel(title)
        title_lb.setObjectName("Body")
        row.addWidget(title_lb, 1)

        self._status = QLabel("…")
        self._status.setObjectName("Dim")
        row.addWidget(self._status)

        self._btn = SecondaryButton("…")
        self._btn.clicked.connect(self._toggle)
        row.addWidget(self._btn)
        outer.addLayout(row)

        if hint:
            hint_lb = QLabel(hint)
            hint_lb.setObjectName("Mini")
            hint_lb.setWordWrap(True)
            outer.addWidget(hint_lb)

        self._refresh()

    def _refresh(self):
        installed = self._check()
        self._status.setText("✅ 已启用" if installed else "未启用")
        self._btn.setText("禁用" if installed else "启用")

    def _toggle(self):
        installed = self._check()
        self._btn.setEnabled(False)
        self._btn.setText("处理中…")
        QApplication.processEvents()  # 让"处理中…"立刻显示出来

        op_fn = self._uninstall if installed else self._install

        def on_ok(result):
            try:
                ok, output = result
            except (TypeError, ValueError):
                ok, output = True, ""
            if not ok:
                dialogs.error(self, "操作失败",
                              f"PowerShell 脚本返回失败：\n\n{(output or '')[:1500]}")
            self._btn.setEnabled(True)
            self._refresh()

        def on_err(msg: str):
            dialogs.error(self, "操作失败", msg)
            self._btn.setEnabled(True)
            self._refresh()

        # run_async 把 PowerShell 调用丢到后台 QThread，UI 不卡
        run_async(self, op_fn, on_ok, on_err)


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(i18n.TOPBAR_SETTINGS)
        self.setMinimumWidth(520)
        self._cfg = config.load()
        self._build()

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(16)

        # ---------- 基础 ----------
        form = QFormLayout()
        form.setSpacing(12)

        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        # 解析 cfg.schedule_time（HH:MM）
        try:
            hh, mm = self._cfg.schedule_time.split(":")
            self.time_edit.setTime(QTime(int(hh), int(mm)))
        except (ValueError, AttributeError):
            self.time_edit.setTime(QTime(23, 30))
        self.time_edit.setMinimumWidth(120)
        form.addRow("每日定时备份时间", self.time_edit)

        self.pause_check = QCheckBox("暂停每日自动备份")
        self.pause_check.setChecked(self._cfg.schedule_paused)
        form.addRow("", self.pause_check)

        self.theme_box = QComboBox()
        self.theme_box.addItems(["dark", "light"])
        self.theme_box.setCurrentText(self._cfg.theme)
        form.addRow("主题", self.theme_box)

        self.autostart_check = QCheckBox("登录时自动启动托盘（与下方系统集成同步）")
        self.autostart_check.setChecked(self._cfg.autostart_tray)
        form.addRow("", self.autostart_check)

        self.notify_check = QCheckBox("备份完成时弹托盘通知")
        self.notify_check.setChecked(self._cfg.show_tray_notifications)
        form.addRow("", self.notify_check)

        lay.addLayout(form)

        # ---------- 备份位置 ----------
        lay.addWidget(make_separator())
        lay.addWidget(make_label("📂 备份位置", "H3"))
        loc_row = QHBoxLayout()
        cur_root = paths._resolve_nas_root()
        self._loc_label = QLabel(str(cur_root) if cur_root else "（未配置）")
        self._loc_label.setObjectName("Body")
        self._loc_label.setWordWrap(True)
        loc_row.addWidget(self._loc_label, 1)
        test_btn = SecondaryButton("🧪 测试")
        test_btn.setToolTip("测试备份位置是否可读可写 + 显示可用空间")
        test_btn.clicked.connect(self._on_test_location)
        loc_row.addWidget(test_btn)
        change_btn = SecondaryButton("修改…")
        change_btn.clicked.connect(self._on_change_location)
        loc_row.addWidget(change_btn)
        lay.addLayout(loc_row)
        loc_hint = QLabel(
            "所有项目的备份数据（git 镜像 / 时间快照 / 完整目录拷贝）都存这里。"
            "改路径后，旧位置的数据需要手动拷过去（或在弹窗里选自动迁移）。"
        )
        loc_hint.setObjectName("Mini")
        loc_hint.setWordWrap(True)
        lay.addWidget(loc_hint)

        # ---------- 保留策略 ----------
        lay.addWidget(make_separator())
        lay.addWidget(make_label("保留策略（避免 NAS 爆盘）", "H3"))
        ret_form = QFormLayout()
        ret_form.setSpacing(8)
        self.keep_dir_edit = QLineEdit(str(self._cfg.retention_keep_last_dir_snapshots))
        self.keep_dir_edit.setMaximumWidth(80)
        ret_form.addRow("最多保留目录快照数（0=不限）", self.keep_dir_edit)
        self.keep_bundle_edit = QLineEdit(str(self._cfg.retention_keep_last_bundles))
        self.keep_bundle_edit.setMaximumWidth(80)
        ret_form.addRow("最多保留时间快照数（0=不限）", self.keep_bundle_edit)
        lay.addLayout(ret_form)

        # ---------- 系统集成 ----------
        lay.addWidget(make_separator())
        lay.addWidget(make_label("系统集成", "H3"))
        if not si.is_packaged():
            warn = make_label(
                "💡 当前用源码运行，已自动生成 dev-run.cmd 包装器。"
                "打包成 .exe 后会切到正式路径。",
                "Mini",
            )
            warn.setWordWrap(True)
            lay.addWidget(warn)

        self._row_ctx = _IntegrationRow(
            self,
            "📂 资源管理器右键菜单",
            "在文件夹上右键能直接看到 ClaudeBackup 子菜单",
            si.context_menu_installed,
            si.install_context_menu,
            si.uninstall_context_menu,
        )
        lay.addWidget(self._row_ctx)

        self._row_auto = _IntegrationRow(
            self,
            "🚀 登录时自启托盘",
            "下次登录 Windows 会自动启动托盘图标",
            si.autostart_installed,
            si.install_autostart,
            si.uninstall_autostart,
        )
        lay.addWidget(self._row_auto)

        self._row_task = _IntegrationRow(
            self,
            "⏰ 每日定时备份（Windows 任务计划）",
            f"每天在上方设置的时间自动跑一次备份（当前 {self._cfg.schedule_time}）",
            si.task_scheduler_installed,
            lambda: si.install_task_scheduler(self._current_time_str()),
            si.uninstall_task_scheduler,
        )
        lay.addWidget(self._row_task)

        # ---------- 底部 ----------
        lay.addWidget(make_separator())
        btns = QHBoxLayout()
        btns.addStretch()
        cancel = SecondaryButton(i18n.BTN_CANCEL)
        ok = PrimaryButton("保存")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._on_save)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)

    def _current_time_str(self) -> str:
        return self.time_edit.time().toString("HH:mm")

    def _on_test_location(self):
        """诊断备份位置 — 读 / 写 / 删 + 可用空间."""
        import shutil
        cur = paths._resolve_nas_root()
        if cur is None:
            dialogs.warn(self, "未配置", "还没选过备份位置 — 点旁边的「修改」选一个。")
            return
        lines: list[str] = [f"路径：{cur}"]
        # 存在性
        if not cur.exists():
            lines.append("❌ 路径不存在 — 检查盘符 / NAS 挂载 / 外置硬盘是否连接")
            dialogs.error(self, "备份位置测试", "\n".join(lines))
            return
        lines.append("✅ 路径存在")
        # 可写
        probe = cur / ".claude-backup-write-test"
        try:
            probe.write_text("ok", encoding="utf-8")
            content = probe.read_text(encoding="utf-8")
            assert content == "ok"
            probe.unlink()
            lines.append("✅ 可读 / 可写 / 可删")
        except (OSError, AssertionError) as e:
            lines.append(f"❌ 读写测试失败：{e}")
            dialogs.error(self, "备份位置测试", "\n".join(lines))
            return
        # 空间
        try:
            usage = shutil.disk_usage(cur)
            free_gb = usage.free / (1 << 30)
            total_gb = usage.total / (1 << 30)
            used_gb = (usage.total - usage.free) / (1 << 30)
            lines.append(
                f"💾 容量：{total_gb:.1f} GB 总 / {used_gb:.1f} GB 已用 / {free_gb:.1f} GB 可用"
            )
            if free_gb < 1:
                lines.append("⚠️ 可用空间低于 1 GB — 备份很快会失败")
        except OSError as e:
            lines.append(f"⚠️ 无法读取容量：{e}")
        dialogs.info(self, "✅ 备份位置测试", "\n".join(lines))

    def _on_change_location(self):
        cur = paths._resolve_nas_root()
        start = str(cur) if cur and cur.exists() else ""
        chosen = QFileDialog.getExistingDirectory(self, "选个文件夹存放备份数据", start)
        if not chosen:
            return
        new_path = Path(chosen)
        if cur and new_path.resolve() == cur.resolve():
            return
        # 校验可写
        try:
            new_path.mkdir(parents=True, exist_ok=True)
            probe = new_path / ".claude-backup-write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
        except OSError as e:
            dialogs.error(self, "该位置不可用", f"无法写入：{e}")
            return

        # 之前没配过：直接 set_nas_root 即可，无需迁移
        if cur is None:
            try:
                paths.set_nas_root(new_path)
            except OSError as e:
                dialogs.error(self, "保存配置失败", str(e))
                return
            self._loc_label.setText(str(new_path))
            return

        # 已有旧位置：问用户是否自动迁移旧数据
        choice = dialogs.confirm(
            self, "迁移旧备份数据？",
            f"要把备份位置改成：\n  {new_path}\n\n旧位置：\n  {cur}\n\n"
            "**自动迁移**会把旧位置下所有 git 镜像 + 时间快照 + 完整目录拷贝复制到新位置，"
            "并自动更新所有项目的 git remote 指向。完成后旧数据**保留**（不删，让你手动确认）。\n\n"
            "项目数据较大时可能要几分钟到几十分钟。",
            ok_text="自动迁移", cancel_text="取消",
        )
        if not choice:
            return

        # 用 ProgressDialog 展示迁移进度
        from .progress_dialog import ProgressDialog
        prog = ProgressDialog(self, title="迁移备份位置",
                              subtitle=f"{cur} → {new_path}")
        prog.show()

        def on_ok(res: core.MigrationResult):
            summary_parts = [
                f"✅ 已迁移 {res.files_copied} 个文件 ({res.bytes_copied / 1024 / 1024:.1f} MB)",
                f"更新了 {res.projects_updated} 个项目的路径",
                f"更新了 {res.git_remotes_updated} 个项目的 git remote",
            ]
            if res.errors:
                summary_parts.append(f"⚠️ {len(res.errors)} 个非致命错误")
            prog.finish(success=True, summary="；".join(summary_parts))
            self._loc_label.setText(str(new_path))
            if res.errors:
                dialogs.info(
                    self, "迁移完成（带警告）",
                    "迁移本体已成功，以下条目失败但不影响新位置使用：\n\n"
                    + "\n".join("• " + e for e in res.errors[:10]),
                )

        def on_err(msg: str):
            prog.finish(success=False, summary=msg)

        t = run_async(self, core.migrate_nas_root, on_ok, on_err,
                      str(new_path), on_progress=prog.add_stage)
        # 防止 worker 被 GC（QThread 的 worker 必须有 Python 强引用）
        self._mig_thread = t

    def _on_save(self):
        new_time = self._current_time_str()
        time_changed = (new_time != self._cfg.schedule_time)
        old_theme = self._cfg.theme
        self._cfg.schedule_time = new_time
        self._cfg.schedule_paused = self.pause_check.isChecked()
        self._cfg.theme = self.theme_box.currentText()
        self._cfg.autostart_tray = self.autostart_check.isChecked()
        self._cfg.show_tray_notifications = self.notify_check.isChecked()
        theme_changed = (self._cfg.theme != old_theme)
        try:
            self._cfg.retention_keep_last_dir_snapshots = max(0, int(self.keep_dir_edit.text()))
        except ValueError:
            self._cfg.retention_keep_last_dir_snapshots = 30
        try:
            self._cfg.retention_keep_last_bundles = max(0, int(self.keep_bundle_edit.text()))
        except ValueError:
            self._cfg.retention_keep_last_bundles = 30
        config.save(self._cfg)

        if theme_changed:
            # 改了主题 → 实时刷新 QApplication 样式表，无需重启
            from . import theme as _theme
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(_theme.stylesheet(self._cfg.theme))

        installed = si.task_scheduler_installed()
        if installed:
            # 已启用 → 重新注册让新时间生效（不论是否改了，幂等）
            ok, _ = si.install_task_scheduler(self._cfg.schedule_time)
            if not ok:
                dialogs.error(
                    self, "定时任务时间更新失败",
                    "已保存其它设置，但 Windows 任务计划没成功更新到新时间。"
                    "请打开「设置」→「系统集成」→ 禁用再启用「每日定时备份」。",
                )
        elif time_changed:
            # 用户改了时间但任务从未启用 — 主动提示
            ask_enable = dialogs.confirm(
                self, "现在启用每日定时备份？",
                f"你设置的时间是 {self._cfg.schedule_time}，"
                "但「每日定时备份」开关还没启用 —— Windows 现在不会到点跑备份。\n\n"
                "现在启用吗？（用户级任务，不需要管理员权限）",
                ok_text="启用",
                cancel_text="先不",
            )
            if ask_enable:
                ok, output = si.install_task_scheduler(self._cfg.schedule_time)
                if ok:
                    dialogs.info(
                        self, "✅ 已启用",
                        f"每日定时备份已开 — 下次触发：每天 {self._cfg.schedule_time}",
                    )
                else:
                    dialogs.error(
                        self, "启用失败",
                        f"PowerShell 脚本返回失败：\n{(output or '')[:1500]}",
                    )
        self.accept()
