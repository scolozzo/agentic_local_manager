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
    ensure_manual_login_fallback,
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
        self.git_status = tk.StringVar(value="Todavia no validado.")
        self.summary_text = tk.StringVar()
        self.install_warning = tk.StringVar()

        self.service_vars: dict[str, dict] = {}
        self.role_default_vars = {
            "developers": tk.StringVar(),
            "qa": tk.StringVar(),
            "orchestrator": tk.StringVar(),
            "pm": tk.StringVar(),
        }
        self.role_boxes: dict[str, ttk.Combobox] = {}

        self.settings = build_default_settings(Path(self.install_dir.get()))
        self.profile_labels: list[str] = []
        self.profile_index_by_label: dict[str, str] = {}
        self.step_frames: list[ttk.Frame] = []
        self.current_step = 0
        self.steps = [
            "1. Instalacion",
            "2. Git",
            "3. Servicios LLM",
            "4. Perfiles por rol",
            "5. Confirmacion",
        ]

        self._build_ui()
        self._refresh_profile_dropdowns()
        self._show_step(0)

    def _build_ui(self) -> None:
        wrapper = ttk.Frame(self.root, padding=16)
        wrapper.pack(fill="both", expand=True)

        ttk.Label(wrapper, text="Agentic Local Manager Windows Installer", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            wrapper,
            text="El instalador ahora funciona paso a paso. Cada pantalla muestra ayuda simple debajo de cada campo.",
            wraplength=920,
        ).pack(anchor="w", pady=(4, 12))

        self.step_label = ttk.Label(wrapper, text="", font=("Segoe UI", 11, "bold"))
        self.step_label.pack(anchor="w", pady=(0, 8))

        self.content = ttk.Frame(wrapper)
        self.content.pack(fill="both", expand=True)

        self.step_frames = [
            ttk.Frame(self.content, padding=16),
            ttk.Frame(self.content, padding=16),
            ttk.Frame(self.content, padding=16),
            ttk.Frame(self.content, padding=16),
            ttk.Frame(self.content, padding=16),
        ]
        for frame in self.step_frames:
            frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._build_install_step(self.step_frames[0])
        self._build_git_step(self.step_frames[1])
        self._build_llm_step(self.step_frames[2])
        self._build_defaults_step(self.step_frames[3])
        self._build_confirm_step(self.step_frames[4])

        action_bar = ttk.Frame(wrapper)
        action_bar.pack(fill="x", pady=(12, 0))
        self.back_button = ttk.Button(action_bar, text="Anterior", command=self._go_back)
        self.back_button.pack(side="left")
        self.next_button = ttk.Button(action_bar, text="Siguiente", command=self._go_next)
        self.next_button.pack(side="right")
        self.install_button = ttk.Button(action_bar, text="Instalar", command=self.run_install)

    def _build_install_step(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Directorio de instalacion", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(4, 0))
        ttk.Entry(row, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Examinar", command=self._browse_install_dir).pack(side="left", padx=(8, 0))
        ttk.Label(
            parent,
            text="Elegí la carpeta donde se copiará el gestor. El acceso directo del escritorio apuntará al lanzador en esa carpeta.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 18))

        ttk.Label(parent, text="Que hara este instalador", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            parent,
            text=(
                "- copiar el repositorio a la carpeta elegida\n"
                "- validar credenciales git\n"
                "- validar servicios LLM por API cuando corresponda\n"
                "- guardar configuracion y .env\n"
                "- crear un acceso directo en el escritorio"
            ),
            justify="left",
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 0))

    def _build_git_step(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Proveedor Git", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        provider_combo = ttk.Combobox(parent, values=["github", "gitlab"], textvariable=self.git_provider, state="readonly")
        provider_combo.pack(fill="x", pady=(4, 0))
        provider_combo.bind("<<ComboboxSelected>>", lambda _event: self._sync_git_host())
        ttk.Label(
            parent,
            text="Elegí GitHub si trabajás con github.com o GitHub Enterprise. Elegí GitLab si usás gitlab.com o una instancia propia.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 14))

        ttk.Label(parent, text="Host o API base", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Entry(parent, textvariable=self.git_host).pack(fill="x", pady=(4, 0))
        ttk.Label(
            parent,
            text="Ejemplos: https://api.github.com o https://gitlab.com. Para GitLab self-hosted podés usar la URL raíz.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 14))

        ttk.Label(parent, text="Token de acceso", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Entry(parent, textvariable=self.git_token, show="*").pack(fill="x", pady=(4, 0))
        ttk.Label(
            parent,
            text=(
                "GitHub: Settings -> Developer settings -> Personal access tokens.\n"
                "GitLab: User Settings -> Access Tokens."
            ),
            justify="left",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 10))

        ttk.Button(parent, text="Validar credenciales Git", command=self.validate_git_credentials).pack(anchor="w")
        ttk.Label(parent, textvariable=self.git_status, foreground="#0f766e").pack(anchor="w", pady=(8, 0))

    def _build_llm_step(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="En este paso elegís qué servicios LLM vas a dejar disponibles. Los servicios por API se pueden validar antes de habilitarlos.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 12))

        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        scroll_frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for service_id, service in self.settings["llm_services"].items():
            box = ttk.LabelFrame(scroll_frame, text=service["label"], padding=12)
            box.pack(fill="x", pady=(0, 10))

            enabled_var = tk.BooleanVar(value=bool(service.get("available")))
            api_key_var = tk.StringVar()
            status_var = tk.StringVar(value="Deshabilitado")

            ttk.Checkbutton(box, text="Habilitar servicio", variable=enabled_var).pack(anchor="w")
            ttk.Label(
                box,
                text=self._service_help_text(service_id, service),
                wraplength=780,
                foreground="#555555",
                justify="left",
            ).pack(anchor="w", pady=(6, 8))

            if service.get("mode") == "api":
                ttk.Label(box, text="API key", font=("Segoe UI", 9, "bold")).pack(anchor="w")
                ttk.Entry(box, textvariable=api_key_var, show="*").pack(fill="x", pady=(4, 0))
                ttk.Label(
                    box,
                    text="Pegá la API key emitida por el portal del proveedor. El instalador hará una validación mínima antes de marcar el servicio como disponible.",
                    wraplength=780,
                    foreground="#555555",
                ).pack(anchor="w", pady=(6, 8))
                ttk.Button(box, text="Validar servicio", command=lambda sid=service_id: self.validate_service_credentials(sid)).pack(anchor="w")
            else:
                ttk.Label(
                    box,
                    text="Este servicio usa login manual y no puede validarse por API desde el instalador.",
                    foreground="#555555",
                ).pack(anchor="w")

            ttk.Label(box, textvariable=status_var, foreground="#0f766e").pack(anchor="w", pady=(8, 0))
            self.service_vars[service_id] = {
                "enabled": enabled_var,
                "api_key": api_key_var,
                "status": status_var,
            }

    def _build_defaults_step(self, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Estos perfiles quedarán como defaults. Los tres developers comparten un mismo perfil. QA normalmente debería usar el perfil validado más económico.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(0, 14))

        labels = {
            "developers": "Perfil de Developers",
            "qa": "Perfil de QA",
            "orchestrator": "Perfil de Orchestrator",
            "pm": "Perfil de PM",
        }
        helps = {
            "developers": "Los tres developers del grupo de trabajo usarán este mismo perfil por defecto.",
            "qa": "Conviene elegir el perfil validado más económico que mantenga calidad suficiente de revisión.",
            "orchestrator": "El orquestador puede usar un perfil distinto al de los developers.",
            "pm": "El PM conviene que use el perfil más económico o free disponible.",
        }
        for key in ("developers", "qa", "orchestrator", "pm"):
            ttk.Label(parent, text=labels[key], font=("Segoe UI", 10, "bold")).pack(anchor="w")
            combo = ttk.Combobox(parent, textvariable=self.role_default_vars[key], state="readonly")
            combo.pack(fill="x", pady=(4, 0))
            ttk.Label(parent, text=helps[key], wraplength=860, foreground="#555555").pack(anchor="w", pady=(6, 14))
            self.role_boxes[key] = combo

    def _build_confirm_step(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Confirmacion final", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(
            parent,
            text="Revisá el resumen. Si está correcto, usá el botón Instalar.",
            wraplength=860,
            foreground="#555555",
        ).pack(anchor="w", pady=(6, 12))
        ttk.Label(parent, textvariable=self.summary_text, justify="left", wraplength=860).pack(anchor="w")
        ttk.Label(parent, textvariable=self.install_warning, justify="left", wraplength=860, foreground="#b45309").pack(anchor="w", pady=(12, 0))

    def _browse_install_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.install_dir.get() or str(Path.home()))
        if selected:
            self.install_dir.set(selected)

    def _sync_git_host(self) -> None:
        self.git_host.set("https://api.github.com" if self.git_provider.get() == "github" else "https://gitlab.com")

    def _service_help_text(self, service_id: str, service: dict) -> str:
        lookup = {
            "chatgpt_login": "Usalo si el usuario va a trabajar con una sesión interactiva de ChatGPT. Se guarda como opción manual y no se valida por API.",
            "openai_api": "Creá una API key en la plataforma de OpenAI. Esto habilita modelos por API como gpt-4.1 u o4-mini.",
            "codex_api": "Usa la misma API key de OpenAI, pero expone opciones Codex como codex-5.3 y codex-5.4.",
            "zai_api": "Creá una API key en el portal de Z.AI. El instalador valida el servicio usando la base configurada.",
            "qwen_api": "Usá la API key del portal del proveedor Qwen. La URL por defecto apunta al endpoint compatible de DashScope.",
            "minimax_api": "Creá una API key en el portal de MiniMax. El instalador valida el endpoint con una llamada mínima.",
        }
        return lookup.get(service_id, service.get("label", service_id))

    def _show_step(self, index: int) -> None:
        self.current_step = index
        for frame in self.step_frames:
            frame.lower()
        self.step_frames[index].lift()
        self.step_label.config(text=self.steps[index])
        self.back_button.config(state="normal" if index > 0 else "disabled")
        if index == len(self.step_frames) - 1:
            self.next_button.pack_forget()
            self.install_button.pack(side="right")
            self._update_summary()
        else:
            self.install_button.pack_forget()
            self.next_button.pack(side="right")

    def _go_back(self) -> None:
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    def _go_next(self) -> None:
        if self.current_step == 2:
            self._finalize_llm_step()
            if not self.profile_labels:
                self._show_step(4)
                return
        if self.current_step < len(self.step_frames) - 1:
            self._show_step(self.current_step + 1)

    def _update_summary(self) -> None:
        enabled_services = []
        for service_id, service in self.settings["llm_services"].items():
            enabled = self.service_vars.get(service_id, {}).get("enabled")
            if enabled and enabled.get():
                enabled_services.append(f"- {service['label']}")
        defaults = []
        for role, variable in self.role_default_vars.items():
            defaults.append(f"- {role}: {variable.get() or 'sin seleccionar'}")
        fallback = ""
        if not self.profile_labels:
            fallback = "\n\nFallback activo:\n- ChatGPT Login quedará como perfil por defecto para todos los agentes."
        self.summary_text.set(
            "Carpeta de instalacion:\n"
            f"- {self.install_dir.get()}\n\n"
            "Git:\n"
            f"- proveedor: {self.git_provider.get()}\n"
            f"- host: {self.git_host.get()}\n"
            f"- estado: {self.git_status.get()}\n\n"
            "Servicios habilitados:\n"
            f"{chr(10).join(enabled_services) if enabled_services else '- ninguno'}\n\n"
            "Perfiles por rol:\n"
            f"{chr(10).join(defaults)}{fallback}"
        )

    def validate_git_credentials(self) -> None:
        provider = self.git_provider.get().strip()
        host = self.git_host.get().strip()
        token = self.git_token.get().strip()
        if not token:
            messagebox.showerror("Validacion Git", "Primero cargá un token de acceso.")
            return

        def worker() -> None:
            self.git_status.set("Validando...")
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
            self.git_status.set(f"Validado para {result.get('username') or self.git_provider.get()}.")
        else:
            self.settings["git"]["validated"] = False
            self.git_status.set(result.get("error", "La validacion Git fallo."))

    def validate_service_credentials(self, service_id: str) -> None:
        field_state = self.service_vars[service_id]
        service = self.settings["llm_services"][service_id]
        if not field_state["enabled"].get():
            messagebox.showerror("Validacion LLM", f"Primero habilitá {service['label']}.")
            return
        if service.get("mode") == "manual_login":
            service["available"] = True
            service["validated"] = False
            field_state["status"].set("Guardado como opción de login manual.")
            self._refresh_profile_dropdowns()
            return
        token = field_state["api_key"].get().strip()
        if not token:
            messagebox.showerror("Validacion LLM", "Primero cargá una API key.")
            return

        def worker() -> None:
            field_state["status"].set("Validando...")
            result = validate_service(service_id, service, token)
            self.root.after(0, lambda: self._finish_service_validation(service_id, result))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_service_validation(self, service_id: str, result: dict) -> None:
        field_state = self.service_vars[service_id]
        service = self.settings["llm_services"][service_id]
        if result.get("ok"):
            service["available"] = True
            service["validated"] = True
            service["validated_at"] = result.get("validated_at", "")
            field_state["status"].set("Validado y disponible.")
        else:
            service["available"] = False
            service["validated"] = False
            field_state["status"].set(result.get("error") or result.get("message") or "La validacion fallo.")
        self._refresh_profile_dropdowns()

    def _refresh_profile_dropdowns(self) -> None:
        for service_id, service in self.settings["llm_services"].items():
            field_state = self.service_vars.get(service_id)
            if service.get("mode") == "manual_login" and field_state and field_state["enabled"].get():
                service["available"] = True
        profiles = available_profiles(self.settings, include_manual=False)
        self.profile_labels = [item["label"] for item in profiles]
        self.profile_index_by_label = {item["label"]: item["id"] for item in profiles}
        for key, combo in self.role_boxes.items():
            combo["values"] = self.profile_labels
            if self.profile_labels:
                if self.role_default_vars[key].get() not in self.profile_labels:
                    self.role_default_vars[key].set(self.profile_labels[0])
                combo.state(["!disabled"])
            else:
                self.role_default_vars[key].set("")
                combo.state(["disabled"])

    def _finalize_llm_step(self) -> None:
        self._refresh_profile_dropdowns()
        if self.profile_labels:
            return
        ensure_manual_login_fallback(self.settings)
        manual_service = self.service_vars.get("chatgpt_login")
        if manual_service:
            manual_service["enabled"].set(True)
            manual_service["status"].set("Fallback manual habilitado por defecto.")
        self.install_warning.set(
            "No se validó ninguna API key. El instalador usará ChatGPT Login como fallback para todos los agentes."
        )

    def run_install(self) -> None:
        target_root = Path(self.install_dir.get().strip()).expanduser().resolve()
        if target_root == SOURCE_ROOT:
            messagebox.showerror("Instalacion", "Elegí una carpeta de instalación distinta al repositorio actual.")
            return
        if not self.settings["git"].get("validated"):
            if not messagebox.askyesno("Instalacion", "Las credenciales Git no están validadas. ¿Continuar igual?"):
                return
        self._finalize_llm_step()

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

        if self.profile_labels:
            for role, variable in self.role_default_vars.items():
                settings["role_defaults"][role] = self.profile_index_by_label.get(variable.get(), "")
        else:
            ensure_manual_login_fallback(settings)

        overwrite = False
        if target_root.exists():
            overwrite = messagebox.askyesno("Instalacion", f"{target_root} ya existe. ¿Sobrescribir contenido instalable?")

        def worker() -> None:
            try:
                copy_repo(SOURCE_ROOT, target_root, overwrite=overwrite)
                write_json(target_root / "config" / "system_settings.json", settings)
                write_env(target_root / ".env", env_values)
                shortcut_warning = create_desktop_shortcut(target_root / "Iniciar_Agentic_Manager.cmd", target_root)
                message = f"Instalación completada en:\n{target_root}"
                if shortcut_warning:
                    message += f"\n\nNo se pudo crear el acceso directo automáticamente:\n{shortcut_warning}"
                self.root.after(0, lambda: messagebox.showinfo("Instalacion", message))
            except Exception as exc:
                self.root.after(0, lambda: messagebox.showerror("Instalacion", str(exc)))

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
