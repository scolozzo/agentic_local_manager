# Agentic Local Manager

Plataforma local de orquestación multiagente para flujos de entrega de software. El sistema combina un tablero local en SQLite, equipos de agentes reutilizables, contexto de proyecto y subproyecto, operación desde dashboard y ejecución integrada con git.

## Descripción general

La plataforma coordina estos roles principales:

- `PM`: recibe pedidos, crea o importa planes de ejecución y gestiona la creación de sprints.
- `Orchestrator`: asigna tareas, detecta bloqueos y gestiona el progreso hacia merge.
- `Developers`: ejecutan trabajo dentro del sprint y subproyecto activo.
- `QA`: revisa entregables, crea fix tasks y certifica salidas.

La rama `develop` actual soporta:

- composición reutilizable de prompts por `role + stack + specialization`
- presets de equipos reutilizables por `stack + substack`
- templates de proyecto y restauración de contexto runtime
- subproyectos por proyecto con repo, skills y perfiles de modelo por defecto
- reglas globales de plataforma aplicadas a todos los agentes
- flujo de instalación y lanzador para Windows

## Modelo actual de plataforma

El modelo runtime es:

`project -> subproject -> sprint -> team -> agents`

Reglas clave:

- debe existir un proyecto antes de habilitar el tablero operativo
- un proyecto pasa a estar operativo cuando tiene al menos un subproyecto
- cada sprint pertenece a un proyecto y a un subproyecto
- cada sprint queda asociado a un equipo reutilizable
- los developers agregados a un sprint quedan limitados a los skills permitidos por ese equipo
- el PM es global; el Orchestrator es global por defecto; los perfiles por defecto de Developers y QA pueden asociarse a cada subproyecto

## Instalación

### Instalador Windows

Usar:

```powershell
.\Instalar_Agentic_Manager.ps1
```

El instalador actualmente:

- permite elegir la carpeta de instalación
- copia el gestor a esa ubicación
- valida credenciales de GitHub o GitLab
- permite habilitar servicios LLM soportados
- valida por API los servicios cuando es posible
- escribe configuración segura y `.env`
- crea un acceso directo en el escritorio que apunta al lanzador

Archivos involucrados:

- [Instalar_Agentic_Manager.ps1](/C:/Trabajo/AgenticLocalManager_Proyect/Instalar_Agentic_Manager.ps1)
- [tools/install_windows.py](/C:/Trabajo/AgenticLocalManager_Proyect/tools/install_windows.py)
- [Iniciar_Agentic_Manager.cmd](/C:/Trabajo/AgenticLocalManager_Proyect/Iniciar_Agentic_Manager.cmd)

### Inicio manual local

```powershell
python dashboard.py
```

Luego abrir `http://localhost:8888`.

## Capas de configuración

### Configuración global de plataforma

Las reglas globales se guardan en:

- [config/platform_settings.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/platform_settings.json)
- [config/system_settings.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/system_settings.json)

Incluyen:

- políticas de codificación
- políticas de git y ramas
- reglas de optimización de tokens
- configuración validada del proveedor git
- servicios LLM disponibles
- perfiles de modelo por defecto para roles globales

### Placeholders de entorno

El repositorio no guarda secretos reales. Usar:

- [.env.example](/C:/Trabajo/AgenticLocalManager_Proyect/.env.example)

Variables esperadas:

- `GITHUB_TOKEN`
- `GITLAB_TOKEN`
- `OPENAI_API_KEY`
- `ZAI_API_KEY`
- `QWEN_API_KEY`
- `MINIMAX_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### Catálogo de agentes y presets de equipo

La metadata de agentes y los equipos reutilizables se guardan en:

- [config/agents.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agents.json)
- [config/agent_presets.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agent_presets.json)

## Comportamiento del dashboard

El dashboard vive en [dashboard.py](/C:/Trabajo/AgenticLocalManager_Proyect/dashboard.py).

Comportamiento actual:

- si no existe proyecto, el dashboard sólo expone la creación de proyecto
- si existe proyecto pero no subproyectos, guía el alta del primer subproyecto
- cuando existe un subproyecto, se habilitan tablero y agentes
- restaura el último contexto activo `project + sprint + team + subproject`
- muestra la lógica activa de plataforma y las reglas globales directamente en la UI

## Modelo de proyecto y subproyecto

Los proyectos ahora guardan:

- `project_id`
- `name`
- `description`
- `template_id`
- `git_dirs` como configuración de repos basada en subproyectos

Los subproyectos actualmente definen:

- label
- directorio del repo
- stack key
- substack
- conjunto de skills
- perfil de modelo por defecto para developers
- perfil de modelo por defecto para QA

Módulos relevantes:

- [app_core/project_context.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_context.py)
- [app_core/project_subprojects.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_subprojects.py)
- [app_core/project_templates.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_templates.py)
- [app_core/project_validation.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_validation.py)

## Módulos principales

### Runtime y storage

- [app_core/memory_store.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/memory_store.py)
- [app_core/state_manager.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/state_manager.py)
- [app_core/sprint_manager.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/sprint_manager.py)
- [app_core/status_router.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/status_router.py)

### Configuración y políticas de agentes

- [app_core/agent_config.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/agent_config.py)
- [app_core/agent_manager.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/agent_manager.py)
- [app_core/assignment_policy.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/assignment_policy.py)
- [app_core/platform_settings.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/platform_settings.py)
- [app_core/system_settings.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/system_settings.py)
- [app_core/provider_validation.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/provider_validation.py)

### Integraciones

- [pm_integration.py](/C:/Trabajo/AgenticLocalManager_Proyect/pm_integration.py)
- [orchestrator_integration.py](/C:/Trabajo/AgenticLocalManager_Proyect/orchestrator_integration.py)
- [developer_integration.py](/C:/Trabajo/AgenticLocalManager_Proyect/developer_integration.py)
- [qa_integration.py](/C:/Trabajo/AgenticLocalManager_Proyect/qa_integration.py)
- [app_core/git_tools.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/git_tools.py)

## Límite actual

La capa de instalador y settings ya soporta un modelo más amplio de proveedores, pero los loops runtime siguen mayormente conectados a los caminos actuales de Z.AI y MiniMax. El sistema ya persiste la selección multi-provider, pero el routing runtime completo para todos los proveedores declarados sigue siendo un paso posterior.

## Tests

Conjunto validado actual:

```powershell
python -m pytest test_project_templates.py test_system_settings.py test_agent_config.py test_assignment_policy.py test_agent_teams.py
```

## Estado

Al `2026-03-10`, `develop` incluye:

- `MVP 1` completado
- `MVP 2` completado
- `MVP 3` completado
- feature set adicional de manager completado
- instalador y lanzador Windows agregados
- onboarding guiado por proyecto y subproyecto

