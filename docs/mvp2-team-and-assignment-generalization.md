# MVP 2 - Team And Assignment Generalization

## Objetivo

Generalizar la configuracion del equipo y la asignacion automatica de trabajo sin perder la politica actual de distribucion implementada en el tablero local.

## Problema que resuelve

Hoy la asignacion esta pensada principalmente para un conjunto fijo de agentes. Eso limita:

- la cantidad de agentes por stack
- el uso de QA por stack
- la creacion de equipos distintos segun tipo de proyecto
- la evolucion de la politica actual sin tocar el core

## Resultado esperado

Al finalizar este MVP, el sistema debe permitir:

- multiples developers por stack
- multiples QA por stack
- plantillas de equipo reutilizables
- elegibilidad de asignacion por `role + stack + enabled`
- mantener la politica actual como politica por defecto

## Alcance funcional

- encapsular la politica actual de asignacion
- hacer configurable la elegibilidad de agentes
- soportar equipos distintos sin hardcode
- conservar el flujo actual del tablero

## No incluye

- redefinicion general de workflows
- templates de proyecto multiproposito
- desacople total de adapters externos

## Cambios de arquitectura

### Politica de asignacion

Introducir una interfaz tipo:

- `AssignmentPolicy`

Implementacion inicial:

- `LocalBoardDefaultAssignmentPolicy`

Esta politica debe replicar exactamente el comportamiento actual:

- respeto por dependencias
- prioridad de fix tasks
- manejo de tareas secuenciales
- uso de developers habilitados
- exclusion de sprints pausados

### Modelo de equipo

Introducir plantillas de equipo configurables:

- `default_software_team`
- `backend_only_team`
- `web_team`
- `mobile_team`

Cada plantilla debe definir:

- agentes incluidos
- stacks soportados
- reglas de elegibilidad
- cantidad sugerida por rol

## Cambios por modulo

### Orchestrator

- extraer logica de asignacion a una politica inyectable
- dejar el modulo actual como consumidor de la politica, no como implementacion total

### Agent manager

- soportar plantillas de equipo
- permitir activar o desactivar agentes por stack
- listar agentes elegibles por stack y rol

### Dashboard

- mostrar por que un agente es elegible o no
- permitir elegir plantilla de equipo
- permitir activar agentes para BACK, BO o MOB

## Criterios de aceptacion

- la asignacion actual debe seguir produciendo los mismos resultados sobre el workflow vigente
- debe ser posible tener varios devs del mismo stack
- debe ser posible tener QA especializado por stack
- debe ser posible cambiar de plantilla sin tocar codigo
- el preset actual debe seguir funcionando como referencia base

## Riesgos

- introducir divergencia entre la politica nueva y la actual
- romper el orden de prioridad entre fix tasks y todo tasks
- hacer demasiado abstracta la elegibilidad en esta fase

## Mitigacion

- congelar la politica actual como baseline
- agregar pruebas de regresion sobre escenarios del tablero local
- no cambiar estados ni transiciones en este MVP

## Plan de ejecucion

1. Extraer la politica actual del orchestrator.
2. Definir interfaz de asignacion.
3. Crear `LocalBoardDefaultAssignmentPolicy`.
4. Mover reglas de elegibilidad de agentes a configuracion.
5. Crear plantillas de equipo.
6. Validar escenarios BACK, BO y MOB.

## Definition of done

- politica actual encapsulada y reutilizable
- soporte para multiples agentes por stack
- soporte para QA por stack
- plantillas de equipo activables
- asignacion actual preservada como comportamiento por defecto
