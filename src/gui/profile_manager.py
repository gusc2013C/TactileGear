"""配置存取 UI。"""

from __future__ import annotations

import customtkinter as ctk

from src.core.config_manager import (
    get_active_profile_name,
    load_profiles,
    save_profiles,
    set_active_profile_name,
)


class ProfileManager(ctk.CTkFrame):
    """配置文件管理面板。"""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        # 标题
        title = ctk.CTkLabel(self, text="配置管理", font=ctk.CTkFont(weight="bold"))
        title.pack(side="left", padx=(10, 20))

        # 配置名称输入
        self._name_entry = ctk.CTkEntry(self, placeholder_text="配置名称", width=150)
        self._name_entry.pack(side="left", padx=5)

        # 保存按钮
        save_btn = ctk.CTkButton(self, text="保存", width=70, command=self._save_profile)
        save_btn.pack(side="left", padx=5)

        # 加载按钮
        load_btn = ctk.CTkButton(self, text="加载", width=70, command=self._load_profile)
        load_btn.pack(side="left", padx=5)

        # 配置列表下拉
        self._profile_var = ctk.StringVar(value=get_active_profile_name())
        self._profile_combo = ctk.CTkComboBox(
            self,
            values=self._get_profile_names(),
            variable=self._profile_var,
            width=150,
        )
        self._profile_combo.pack(side="left", padx=5)

        # 刷新按钮
        refresh_btn = ctk.CTkButton(
            self, text="刷新", width=70, command=self._refresh_profiles,
        )
        refresh_btn.pack(side="left", padx=5)

    def _save_profile(self) -> None:
        """保存当前配置。"""
        name = self._name_entry.get().strip()
        if not name:
            name = self._profile_var.get()
        if not name:
            return

        # TODO: 从当前参数和模式收集数据并保存
        set_active_profile_name(name)
        self._refresh_profiles()
        self._profile_var.set(name)

    def _load_profile(self) -> None:
        """加载选中的配置。"""
        name = self._profile_var.get()
        if not name:
            return
        # TODO: 加载配置并通知物理线程
        set_active_profile_name(name)

    def _refresh_profiles(self) -> None:
        """刷新配置列表。"""
        names = self._get_profile_names()
        self._profile_combo.configure(values=names)

    @staticmethod
    def _get_profile_names() -> list[str]:
        """获取所有配置名称。"""
        profiles = load_profiles()
        return list(profiles.keys()) if profiles else ["Default"]
