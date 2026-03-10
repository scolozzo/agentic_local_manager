# MVP 2 - Generalización de Equipos y Asignación

## Objetivo

Generalizar la configuración de equipos y la asignación automática de trabajo preservando el comportamiento original de asignación sobre el tablero local.

## Problema que resuelve

El comportamiento original asumía una estructura de equipo bastante fija. Eso limitaba:

- la cantidad de developers por stack
- el escalado de QA por stack
- los patrones de equipo reutilizables entre proyectos
- la evolución futura sin tocar la lógica central de orquestación

## Resultado esperado

Al finalizar MVP 2, el sistema debía soportar:

- múltiples developers por stack
- múltiples QA por stack
- presets de equipos reutilizables
- elegibilidad de asignación por `role + stack + enabled`
- la estrategia original como política por defecto

## Alcance

- encapsular el comportamiento original de asignación
- hacer configurable la elegibilidad de agentes
- soportar múltiples equipos reutilizables sin hardcode
- preservar el workflow del tablero local

## No incluye

- rediseño amplio del workflow
- generalización por templates de proyecto
- desacople total de adapters

## Cambio de arquitectura

### Política de asignación

Se introduce:

- `LocalBoardDefaultAssignmentPolicy`

Esta política preserva:

- respeto por dependencias
- prioridad de fix tasks
- manejo de tareas secuenciales
- uso de developers habilitados
- exclusión de sprints pausados

### Modelo de equipo

Se introducen presets reutilizables como:

- `default_software_team`
- `backend_only_team`
- `web_team`
- `mobile_team`

Cada preset define:

- agentes incluidos o elegibilidad
- stacks soportados
- reglas de elegibilidad
- cantidades sugeridas por rol

## Criterios de aceptación

- la asignación sigue siendo equivalente al baseline original
- el sistema soporta múltiples developers del mismo stack
- el sistema soporta QA por stack
- la selección de equipo es driven por configuración
- el preset base sigue siendo utilizable

## Estado

Estado: `completado`

Implementado en `develop` con:

- [app_core/assignment_policy.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/assignment_policy.py)
- presets reutilizables en [config/agent_presets.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/agent_presets.json)
- elegibilidad configurable en [app_core/agent_manager.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/agent_manager.py)
- dashboard mostrando elegibilidad y activación por stack

## Evolución posterior

Después del cierre base de MVP 2, la plataforma evolucionó así:

- el equipo activo ya no se cambia manualmente como setting global
- los equipos se asignan al crear cada sprint
- el runtime deriva el equipo activo desde el sprint seleccionado
- la creación de developers queda restringida por los skills del equipo del sprint activo

