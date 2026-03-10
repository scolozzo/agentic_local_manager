from __future__ import annotations

import json
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from install_support import (
    GIT_TOKEN_ENV,
    SOURCE_ROOT,
    available_profiles,
    build_default_settings,
    copy_repo,
    create_desktop_shortcut,
    validate_git,
    validate_service,
    write_env,
    write_json,
)


class InstallerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Agentic Local Manager Installer")
        self.root.geometry("980x760")
        self.root.minsize(920, 700)

        self.install_dir = tk.StringVar(value=str((Path.home() / "AgenticLocalManager").resolve()))
        self.git_provider = tk.StringVar(value="github")
        self.git_host = tk.StringVar(value="https://api.github.com")
        self.git_token = tk.StringVar()
        self.git_status = tk.StringVar(value="Not validated yet.")

        self.service_vars: dict[str, dict] = {}
        self.role_default_vars = {
            "developers": tk.StringVar(),
            "qa": tk.StringVar(),
            "orchestrator": tk.StringVar(),
            "pm": tk.StringVar(),
        }

        self.settings = build_default_settings(Path(self.install_dir.get()))
        self.profile_labels: list[str] = []
        self.profile_index_by_label: dict[str, str] = {}

        self._build_ui()
        self._refresh_profile_dropdowns()

    def _build_ui(self) -> None:
        wrapper = ttk.Frame(self.root, padding=16)
        wrapper.pack(fill="both", expand=True)

        title = ttk.Label(wrapper, text="Agentic Local Manager Windows Installer", font=("Segoe UI", 18, "bold"))
        title.pack(anchor="w")
        subtitle = ttk.Label(
            wrapper,
            text="Run this installer only when you want to configure or install the system. Help text is shown below every field.",
            wraplength=920,
        )
        subtitle.pack(anchor="w", pady=(4, 12))

        notebook = ttk.Notebook(wrapper)
        notebook.pack(fill="both", expand=True)

        install_tab = ttk.Frame(notebook, padding=16)
        git_tab = ttk.Frame(notebook, padding=16)
        llm_tab = ttk.Frame(notebook, padding=16)
        defaults_tab = ttk.Frame(notebook, padding=16)

        notebook.add(install_tab, text="Install")
        notebook.add(git_tab, text="Git")
        notebook.add(llm_tab, text="LLM Services")
        notebook.add(defaults_tab, text="Role Defaults")

        self._build_install_tab(install_tab)
        self._build_git_tab(git_tab)
        self._build_llm_tab(llm_tab)
        self._build_defaults_tab(defaults_tab)

        action_bar = ttk.Frame(wrapper)
        action_bar.pack(fill="x", pady=(12, 0))

        ttk.Button(action_bar, text="Validate Git", command=self.validate_git_credentials).pack(side="left")
        ttk.Button(action_bar, text="Refresh Profiles", command=self._refresh_profile_dropdowns).pack(side="left", padx=(8, 0))
        ttk.Button(action_bar, text="Install", command=self.run_install).pack(side="right")

    def _build_install_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Install directory", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 0))
        ttk.Entry(row, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse", command=self._browse_install_dir).pack(side="left", padx=(8, 0))
        ttk.Label(
            parent,
            text="Choose the folder where the manager will be copied. The desktop shortcut will target the launcher in this folder.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 18))

        ttk.Label(parent, text="What this installer will do", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            parent,
            text=(
                "- copy the repository to the selected folder\n"
                "- validate git credentials\n"
                "- validate API-based LLM services\n"
                "- save placeholder-safe settings and .env\n"
                "- create a desktop shortcut for the launcher"
            ),
            justify="left",
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 0))

    def _build_git_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Git provider", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        provider_combo = ttk.Combobox(parent, values=["github", "gitlab"], textvariable=self.git_provider, state="readonly")
        provider_combo.pack(fill="x", pady=(4, 0))
        provider_combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_git_host())
        ttk.Label(
            parent,
            text="Choose GitHub when using github.com or GitHub Enterprise. Choose GitLab when using gitlab.com or a self-hosted GitLab instance.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 14))

        ttk.Label(parent, text="Git API host", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Entry(parent, textvariable=self.git_host).pack(fill="x", pady=(4, 0))
        ttk.Label(
            parent,
            text="Examples: https://api.github.com or https://gitlab.com. For self-hosted GitLab, use the root URL and the installer will normalize /api/v4.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 14))

        ttk.Label(parent, text="Access token", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Entry(parent, textvariable=self.git_token, show="*").pack(fill="x", pady=(4, 0))
        ttk.Label(
            parent,
            text=(
                "GitHub: create a personal access token from Settings -> Developer settings -> Personal access tokens.\n"
                "GitLab: create an access token from User Settings -> Access Tokens."
            ),
            justify="left",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 10))

        ttk.Button(parent, text="Validate Git credentials", command=self.validate_git_credentials).pack(anchor="w")
        ttk.Label(parent, textvariable=self.git_status, foreground="#0f766e").pack(anchor="w", pady=(8, 0))

    def _build_llm_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Enable each service you want to make available. API-based services can be validated immediately. Manual login services are stored as available but cannot be auto-verified.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 12))

        for service_id, service in self.settings["llm_services"].items():
            box = ttk.LabelFrame(parent, text=service["label"], padding=12)
            box.pack(fill="x", pady=(0, 10))

            enabled_var = tk.BooleanVar(value=bool(service.get("available")))
            api_key_var = tk.StringVar()
            status_var = tk.StringVar(value="Disabled")

            ttk.Checkbutton(box, text="Enable service", variable=enabled_var).pack(anchor="w")
            ttk.Label(
                box,
                text=self._service_help_text(service_id, service),
                wraplength=820,
                foreground="#555555",
                justify="left",
            ).pack(anchor="w", pady=(6, 8))

            if service.get("mode") == "api":
                ttk.Label(box, text="API key", font=("Segoe UI", 9, "bold")).pack(anchor="w")
                ttk.Entry(box, textvariable=api_key_var, show="*").pack(fill="x", pady=(4, 0))
                ttk.Label(
                    box,
                    text="Paste the API key issued by the provider portal. The installer will test the endpoint before enabling the service.",
                    wraplength=820,
                    foreground="#555555",
                ).pack(anchor="w", pady=(6, 8))
                ttk.Button(box, text="Validate service", command=lambda sid=service_id: self.validate_service_credentials(sid)).pack(anchor="w")
            else:
                ttk.Label(box, text="This service uses manual login and cannot be validated by API from the installer.", foreground="#555555").pack(anchor="w")

            ttk.Label(box, textvariable=status_var, foreground="#0f766e").pack(anchor="w", pady=(8, 0))
            self.service_vars[service_id] = {
                "enabled": enabled_var,
                "api_key": api_key_var,
                "status": status_var,
            }

    def _build_defaults_tab(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="These selections become the default profiles after installation. The three developers share one model profile. QA should usually use the cheapest validated profile.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 14))

        self.role_boxes: dict[str, ttk.Combobox] = {}
        labels = {
            "developers": "Developers profile",
            "qa": "QA profile",
            "orchestrator": "Orchestrator profile",
            "pm": "PM profile",
        }
        helps = {
            "developers": "All three developers in a work group will use the same default model profile.",
            "qa": "Prefer the cheapest validated model that still gives acceptable review quality.",
            "orchestrator": "The orchestrator can use a different model profile from the developers.",
            "pm": "The PM should usually use the cheapest or free validated option.",
        }
        for key in ("developers", "qa", "orchestrator", "pm"):
            ttk.Label(parent, text=labels[key], font=("Segoe UI", 10, "bold")).pack(anchor="w")
            combo = ttk.Combobox(parent, textvariable=self.role_default_vars[key], state="readonly")
            combo.pack(fill="x", pady=(4, 0))
            ttk.Label(parent, text=helps[key], wraplength=860, foreground="#555555").pack(anchor="w", pady=(6, 14))
            self.role_boxes[key] = combo

    def _browse_install_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.install_dir.get() or str(Path.home()))
        if selected:
            self.install_dir.set(selected)

    def _sync_git_host(self) -> None:
        if self.git_provider.get() == "github":
            self.git_host.set("https://api.github.com")
        else:
            self.git_host.set("https://gitlab.com")

    def _service_help_text(self, service_id: str, service: dict) -> str:
        lookup = {
            "chatgpt_login": "Use this when the user plans to work with an interactive ChatGPT login flow. This is stored as a manual option and is not API-validated here.",
            "openai_api": "Create an API key in the OpenAI platform dashboard. This enables OpenAI API models such as gpt-4.1 or o4-mini.",
            "codex_api": "Uses the same OpenAI API key as the OpenAI API service, but exposes Codex model options such as codex-5.3 and codex-5.4.",
            "zai_api": "Create a Z.AI API key in the provider console. The installer validates the service using the configured API base.",
            "qwen_api": "Use the Qwen-compatible API key from the provider portal. The default base URL targets the DashScope compatible endpoint.",
            "minimax_api": "Create a MiniMax API key in the provider portal. The installer validates the chat endpoint with a minimal request.",
        }
        return lookup.get(service_id, service.get("label", service_id))

    def validate_git_credentials(self) -> None:
        provider = self.git_provider.get().strip()
        host = self.git_host.get().strip()
        token = self.git_token.get().strip()
        if not token:
            messagebox.showerror("Git validation", "Please enter a git access token first.")
            return

        def worker() -> None:
            self.git_status.set("Validating...")
            result = validate_git(provider, token, host)
            self.root.after(0, lambda: self._finish_git_validation(result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_git_validation(self, result: dict) -> None:
        if result.get("ok"):
            self.settings["git"] = {
                "provider": self.git_provider.get().strip(),
                "host": result.get("host", self.git_host.get().strip()),
                "username": result.get("username", ""),
                "validated": True,
                "validated_at": result.get("validated_at", ""),
            }
            self.git_status.set(f"Validated for {result.get('username') or self.git_provider.get()}.")
        else:
            self.settings["git"]["validated"] = False
            self.git_status.set(result.get("error", "Git validation failed."))

    def validate_service_credentials(self, service_id: str) -> None:
        field_state = self.service_vars[service_id]
        service = self.settings["llm_services"][service_id]
        if not field_state["enabled"].get():
            messagebox.showerror("LLM validation", f"Enable {service['label']} before validating it.")
            return
        if service.get("mode") == "manual_login":
            service["available"] = True
            service["validated"] = False
            field_state["status"].set("Stored as manual login option.")
            self._refresh_profile_dropdowns()
            return
        token = field_state["api_key"].get().strip()
        if not token:
            messagebox.showerror("LLM validation", "Please enter an API key first.")
            return

        def worker() -> None:
            field_state["status"].set("Validating...")
            result = validate_service(service_id, service, token)
            self.root.after(0, lambda: self._finish_service_validation(service_id, token, result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_service_validation(self, service_id: str, token: str, result: dict) -> None:
        field_state = self.service_vars[service_id]
        service = self.settings["llm_services"][service_id]
        if result.get("ok"):
            service["available"] = True
            service["validated"] = True
            service["validated_at"] = result.get("validated_at", "")
            field_state["status"].set("Validated and available.")
            if service.get("api_key_env"):
                service["_captured_api_key"] = token
        else:
            service["available"] = False
            service["validated"] = False
            field_state["status"].set(result.get("error") or result.get("message") or "Validation failed.")
        self._refresh_profile_dropdowns()

    def _refresh_profile_dropdowns(self) -> None:
        for service_id, service in self.settings["llm_services"].items():
            if service.get("mode") == "manual_login" and self.service_vars.get(service_id, {}).get("enabled") and self.service_vars[service_id]["enabled"].get():
                service["available"] = True
        profiles = available_profiles(self.settings)
        self.profile_labels = [item["label"] for item in profiles]
        self.profile_index_by_label = {item["label"]: item["id"] for item in profiles}
        for key, combo in self.role_boxes.items():
            combo["values"] = self.profile_labels
            if not self.role_default_vars[key].get() and self.profile_labels:
                self.role_default_vars[key].set(self.profile_labels[0])

    def run_install(self) -> None:
        target_root = Path(self.install_dir.get().strip()).expanduser().resolve()
        if not self.settings["git"].get("validated"):
            if not messagebox.askyesno("Install", "Git credentials are not validated yet. Continue anyway?"):
                return

        settings = build_default_settings(target_root)
        settings["git"] = dict(self.settings["git"])
        settings["llm_services"] = json.loads(json.dumps(self.settings["llm_services"]))
        env_values: dict[str, str] = {}
        if self.settings["git"].get("provider") and self.git_token.get().strip():
            env_key = GIT_TOKEN_ENV.get(self.settings["git"]["provider"])
            if env_key:
                env_values[env_key] = self.git_token.get().strip()

        for service_id, service in settings["llm_services"].items():
            field_state = self.service_vars.get(service_id)
            if not field_state:
                continue
            service["available"] = bool(field_state["enabled"].get()) and bool(service.get("available"))
            if service.get("mode") == "manual_login" and field_state["enabled"].get():
                service["available"] = True
                service["validated"] = False
                service["manual_only"] = True
            elif service.get("api_key_env") and service.get("available"):
                token = field_state["api_key"].get().strip()
                if token:
                    env_values[service["api_key_env"]] = token

        for role, variable in self.role_default_vars.items():
            settings["role_defaults"][role] = self.profile_index_by_label.get(variable.get(), "")

        overwrite = False
        if target_root.exists():
            overwrite = messagebox.askyesno("Install", f"{target_root} already exists. Overwrite installable content?")

        def worker() -> None:
            try:
                copy_repo(SOURCE_ROOT, target_root, overwrite=overwrite)
                write_json(target_root / "config" / "system_settings.json", settings)
                write_env(target_root / ".env", env_values)
                create_desktop_shortcut(target_root / "Iniciar_Agentic_Manager.cmd", target_root)
                self.root.after(0, lambda: messagebox.showinfo("Install", f"Installation completed in:\n{target_root}"))
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("Install", str(exc)))

        threading.Thread(target=worker, daemon=True).start()


def main() -> int:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    InstallerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
