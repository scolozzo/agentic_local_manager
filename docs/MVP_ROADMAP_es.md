# Roadmap de MVP

Este documento sigue la evolución de la plataforma a través de los tres MVP originales y del feature set adicional de manager que hoy forma parte de `develop`.

## Objetivo general

Generalizar el sistema original multiagente local sin perder:

- el modelo de ejecución sobre tablero local
- la separación de roles PM, Orchestrator, Developer y QA
- el comportamiento de asignación por defecto
- los prompts especializados por stack
- git-integración como flujo principal de entrega de software

## Principios de migración

- preservar compatibilidad primero, extender comportamiento después
- mantener el tablero local como fuente de verdad por defecto
- mover comportamiento hardcodeado a configuración cuando sea razonable
- separar claramente rol, stack, especialización, contexto de proyecto y contexto de equipo
- mantener las reglas globales de plataforma independientes del estado del proyecto

## Secuencia de MVP

### MVP 1

Limpieza de prompts y agentes configurables por stack.

Referencia:

- [mvp1-clean-prompts-and-stack-agents_es.md](/C:/Trabajo/AgenticLocalManager_Proyect/docs/mvp1-clean-prompts-and-stack-agents_es.md)

### MVP 2

Equipos reutilizables y generalización de asignación.

Referencia:

- [mvp2-team-and-assignment-generalization_es.md](/C:/Trabajo/AgenticLocalManager_Proyect/docs/mvp2-team-and-assignment-generalization_es.md)

### MVP 3

Templates de proyecto y núcleo de plataforma.

Referencia:

- [mvp3-project-templates-and-platform-core_es.md](/C:/Trabajo/AgenticLocalManager_Proyect/docs/mvp3-project-templates-and-platform-core_es.md)

## Orden de ejecución

1. Completar MVP 1 preservando el comportamiento del equipo y prompts actuales.
2. Completar MVP 2 preservando la política de asignación base.
3. Completar MVP 3 sólo cuando MVP 1 y MVP 2 estén estables.

## Estado actual

Actualizado al `2026-03-10`.

- `MVP 1`: completado y fusionado en `develop`
- `MVP 2`: completado y fusionado en `develop`
- `MVP 3`: completado y fusionado en `develop`
- feature set adicional de manager: completado y fusionado en `develop`
- instalador Windows y lanzador: implementados en `develop`
- onboarding guiado por proyecto y subproyecto: implementado en `develop`

## Estado actual del sistema en `develop`

El sistema actual incluye:

- composición de prompts por rol, stack y especialización
- política de asignación reutilizable con el comportamiento original como baseline
- presets de equipos reutilizables por stack y substack
- templates de proyecto y restauración de contexto de proyecto
- creación de sprint asociada a `project + subproject + team`
- restricción de skills de developers según el equipo del sprint activo
- reglas globales de codificación, git y optimización de tokens
- configuración global de git y LLM gestionada por instalador
- dashboard que bloquea el uso del tablero hasta que existan proyecto y subproyecto

## Entregable actual

En este punto la plataforma ya provee:

- prompts base y prompts técnicos reutilizables
- agentes configurables y presets de equipo reutilizables
- contexto runtime por proyecto y subproyecto
- ejecución de sprint persistida en storage local
- filtrado y restauración contextual en dashboard
- soporte de instalación segura para Windows

## Dirección posterior

La principal brecha de plataforma pendiente es la abstracción runtime de proveedores. El instalador y `system_settings` ya persisten elecciones multi-provider, pero PM, Developer, QA y Orchestrator todavía necesitan una integración runtime más profunda para usar plenamente esa configuración.

