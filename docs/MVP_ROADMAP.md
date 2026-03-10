# MVP Roadmap

Este documento organiza la evolucion del sistema en 3 MVP secuenciales.

## Objetivo general

Generalizar el sistema actual de gestion multiagente sin perder:

- la logica ya implementada de tablero local
- la politica actual de distribucion de trabajo
- los roles base PM, Orchestrator, Dev y QA
- los stacks actuales BACK, BO y MOB
- los prompts tecnicos ya creados como casos especiales reutilizables

## Principios de migracion

- Compatibilidad primero, extension despues.
- No romper el flujo actual del tablero local.
- No hardcodear reglas del sistema dentro de prompts estaticos.
- Convertir el comportamiento actual en configuracion y presets.
- Separar claramente rol, stack, especializacion y contexto runtime.

## Fases

### MVP 1

Limpieza de prompts y nuevo modelo configurable de agentes por stack.

Documento detallado: `docs/mvp1-clean-prompts-and-stack-agents.md`

### MVP 2

Generalizacion del equipo y de la asignacion sin perder la politica actual.

Documento detallado: `docs/mvp2-team-and-assignment-generalization.md`

### MVP 3

Plataforma base por templates de proyecto con adapters desacoplados.

Documento detallado: `docs/mvp3-project-templates-and-platform-core.md`

## Orden de ejecucion

1. Ejecutar MVP 1 y validar compatibilidad total con el equipo actual.
2. Ejecutar MVP 2 y validar que la asignacion siga replicando el comportamiento actual.
3. Ejecutar MVP 3 solo cuando MVP 1 y MVP 2 queden estables.

## Estado actual

Actualizado al `2026-03-10`.

- `MVP 1` completado y fusionado en `develop`
- `MVP 2` completado y fusionado en `develop`
- `MVP 3` completado en su base de templates/contexto y fusionado en `develop`
- feature adicional de manager fusionada en `develop`:
  - proyecto activo persistente con restore por proyecto
  - sprint obligatorio asociado a proyecto
  - sprint obligatorio asociado a equipo reusable
  - equipos reutilizables por `stack/substack`
  - skills reutilizables por equipo
  - restriccion de alta de devs segun skills del equipo activo
  - bloqueo de borrado para devs ya asociados al equipo del sprint

## Estado del sistema en `develop`

- prompts por rol, stack y especializacion ya separados
- politica de asignacion encapsulada
- presets/equipos reutilizables disponibles
- templates de proyecto versionados disponibles
- dashboard con seleccion de proyecto, creacion de proyecto y creacion de sprint con equipo
- persistencia local de contexto por proyecto y ultimo sprint seleccionado

## Entregable esperado al final de los 3 MVP

- prompts base por rol limpios y reutilizables
- prompts tecnicos por stack y especializacion
- agentes configurables por stack y rol
- presets de equipo reutilizables
- politica de asignacion actual encapsulada como politica por defecto
- soporte para multiples tipos de proyecto sin perder software delivery como caso principal
