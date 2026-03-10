# MVP 1 - Limpieza de Prompts y Agentes por Stack

## Objetivo

Separar reglas por rol, especialización técnica por stack y contexto runtime, preservando el flujo actual del tablero local.

## Problema que resuelve

Los prompts originales y la configuración de agentes estaban demasiado acoplados a una única forma del sistema. Eso dificultaba:

- reutilizar agentes entre proyectos
- crear agentes especializados por stack
- mantener prompts limpios y mantenibles
- escalar el modelo de configuración sin duplicar instrucciones

## Resultado esperado

Al finalizar MVP 1, el sistema debía definir agentes por:

- `role`
- `stack`
- `specialization`
- `provider`
- `model`

El prompt final debía componerse con:

- prompt base por rol
- prompt por stack
- prompt opcional de especialización
- contexto runtime de tarea y proyecto

## Alcance

- crear una estructura de prompts por capas
- reestructurar [config/agents.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agents.json) para composición de prompts
- conservar el equipo actual como preset por defecto
- permitir nuevos agentes específicos para backend, web y mobile
- mantener compatibilidad hacia atrás

## No incluye

- rediseño de la política de asignación
- rediseño de estados del tablero
- rediseño del workflow
- arquitectura de templates de proyecto

## Cambio de arquitectura

### Estructura de prompts

```text
config/prompts/
  base/
    pm.md
    developer.md
    qa.md
    orchestrator.md
  stacks/
    backend.md
    front_web.md
    front_mobile.md
    db.md
    qa_backend.md
    qa_front_web.md
    qa_front_mobile.md
  specializations/
    dev_back.md
    dev_bo_frontend.md
    dev_mob_android.md
    qa_back.md
    qa_bo.md
    qa_mob.md
```

### Modelo de agente

Cada agente soporta:

- `id`
- `name`
- `type`
- `role`
- `stack`
- `stack_key`
- `specialization`
- `base_prompt`
- `stack_prompt`
- `specialization_prompt`
- `provider`
- `model`
- `enabled`
- `removable`
- `login` cuando aplica

### Regla de composición

`final_prompt = base_prompt + stack_prompt + specialization_prompt + runtime_context`

## Criterios de aceptación

- los prompts base no hardcodean un proyecto específico
- los prompts técnicos preservan las reglas propias de cada stack
- el sistema representa al menos:
  - un developer backend
  - un developer web
  - un developer mobile
  - un QA backend
  - un QA web
  - un QA mobile
- ningún módulo depende de rutas absolutas para cargar prompts
- el equipo actual sigue siendo representable sin regresiones funcionales

## Estado

Estado: `completado`

Implementado en `develop` con:

- estructura de prompts en [config/prompts](/C:/Trabajo/AgenticLocalManager_Proyect/config/prompts)
- composición centralizada en [app_core/agent_config.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/agent_config.py)
- catálogo de agentes versionado en [config/agents.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agents.json)
- visibilidad en dashboard de rol, stack y especialización

