# MVP 1 - Clean Prompts And Stack Agents

## Objetivo

Separar reglas generales de rol, especializacion tecnica por stack y contexto runtime, manteniendo intacta la logica actual del tablero local y el flujo operativo existente.

## Problema que resuelve

Hoy los prompts y la configuracion de agentes estan demasiado acoplados al sistema actual. Esto dificulta:

- reutilizar agentes en otros proyectos
- crear agentes nuevos por stack tecnologico
- mantener prompts limpios y consistentes
- escalar el sistema sin duplicar instrucciones

## Resultado esperado

Al finalizar este MVP, el sistema debe permitir definir agentes por:

- `role`
- `stack`
- `specialization`
- `provider`
- `model`

Y debe construir el prompt final del agente como composicion de:

- prompt base por rol
- prompt tecnico por stack
- prompt opcional de especializacion
- contexto dinamico de la tarea y el proyecto

## Alcance funcional

- Crear estructura de prompts por capas.
- Reestructurar `config/agents.json` para soportar composicion de prompts.
- Conservar los agentes actuales como preset por defecto.
- Permitir crear agentes nuevos con stack especifico para backend, front web y front movil.
- Mantener compatibilidad hacia atras con la configuracion actual.

## No incluye

- reescritura de la politica de asignacion
- cambio de estados del tablero
- cambio del workflow base PM -> Orchestrator -> Dev -> QA
- templates de proyecto

## Cambios de arquitectura

### Nueva estructura de prompts

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

### Nuevo modelo de agente

Cada agente debe soportar estos campos:

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
- `login` cuando aplique

### Regla de composicion de prompt

`final_prompt = base_prompt + stack_prompt + specialization_prompt + runtime_context`

## Cambios por modulo

### Configuracion

- Redefinir `config/agents.json`.
- Crear `config/agent_presets.json`.
- Mantener mapeo de especializaciones ya existentes.

### PM, Dev, QA y Orchestrator

- Reemplazar carga de prompts hardcodeada por una funcion comun de composicion.
- Eliminar referencias absolutas a archivos externos.
- Resolver prompts siempre desde rutas relativas del repo.

### Dashboard

- Mostrar `role`, `stack` y `specialization` de cada agente.
- Permitir alta y edicion de agentes con stack especifico.

## Presets iniciales

### default_software_team

- 1 PM
- 1 Orchestrator
- 3 Dev backend por defecto
- 1 QA backend

### special_presets

- backend_team
- front_web_team
- front_mobile_team

## Criterios de aceptacion

- Los prompts base no deben mencionar el sistema actual ni detalles del proyecto actual.
- Los prompts tecnicos deben mantener reglas especificas de stack.
- Debe ser posible crear al menos:
  - 1 dev backend
  - 1 dev front web
  - 1 dev front movil
  - 1 qa backend
  - 1 qa front web
  - 1 qa front movil
- El equipo actual debe seguir siendo representable sin cambios funcionales.
- Ningun modulo debe depender de rutas absolutas para cargar prompts.

## Riesgos

- romper compatibilidad con agentes actuales
- mezclar especializacion con stack
- duplicar reglas entre prompts base y prompts tecnicos

## Mitigacion

- mantener adaptador de compatibilidad para el formato viejo de `agents.json`
- validar prompts compuestos con snapshots
- conservar los prompts tecnicos actuales como casos especiales

## Plan de ejecucion

1. Crear estructura `base`, `stacks` y `specializations`.
2. Definir esquema nuevo de agente.
3. Implementar helper comun de composicion de prompts.
4. Migrar `pm_integration.py`, `developer_integration.py`, `qa_integration.py` y `orchestrator_integration.py`.
5. Agregar presets por defecto.
6. Validar compatibilidad con el equipo actual.

## Definition of done

- esquema de agentes nuevo versionado
- prompts separados por capa
- composicion de prompts centralizada
- agentes configurables por stack listos para backend, front web y front movil
- preset actual preservado

## Estado actual

Estado: `completado`

Quedo incorporado en `develop` con:

- `config/prompts/base`, `config/prompts/stacks` y `config/prompts/specializations`
- composicion de prompts centralizada desde `app_core/agent_config.py`
- `config/agents.json` versionado y desacoplado por `role`, `stack`, `specialization`, `provider`, `model`
- dashboard mostrando metadata de agentes por stack y especializacion
