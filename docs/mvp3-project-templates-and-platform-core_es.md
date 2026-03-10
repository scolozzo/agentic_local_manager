# MVP 3 - Templates de Proyecto y Núcleo de Plataforma

## Objetivo

Convertir el sistema en una base reutilizable para múltiples formas de proyectos de software, manteniendo software delivery como template principal.

## Problema que resuelve

Aun con agentes y tablero local, el sistema seguía centrado en un único patrón de proyecto. Faltaba:

- templates de proyecto
- contexto de proyecto reutilizable
- separación más clara entre core de plataforma e integraciones
- visibilidad de workflow por proyecto

## Resultado esperado

Al finalizar MVP 3, la plataforma debía soportar:

- templates de proyecto versionados
- workflow y validación de stack dependientes del proyecto
- contexto runtime reutilizable por proyecto
- una base estable para backend, web y mobile

## Alcance

- introducir templates de proyecto
- mapear proyectos a templates
- preservar el tablero local como storage runtime por defecto
- exponer proyecto y workflow activo en dashboard

## No incluye

- abstracción total para cualquier dominio posible
- reemplazo obligatorio de Telegram, GitLab o dashboard
- multitenancy compleja

## Cambio de arquitectura

### Catálogo de templates

El catálogo inicial incluye:

- `software_delivery_default`
- `software_backend`
- `software_web`
- `software_mobile`

Cada template define:

- workflow
- stacks permitidos
- roles requeridos
- preset sugerido
- artefactos esperados

### Contexto runtime de proyecto

Los proyectos hoy se resuelven a través de:

- [app_core/project_templates.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_templates.py)
- [app_core/project_context.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_context.py)
- [app_core/project_validation.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_validation.py)

## Criterios de aceptación

- el sistema sigue corriendo con `software_delivery_default` sin regresión funcional
- existen variantes de template para backend, web y mobile
- la selección de proyecto y visualización de workflow están visibles en dashboard
- el tablero local sigue siendo la fuente de verdad por defecto

## Estado

Estado: `completado`

Implementado en `develop` con:

- catálogo versionado en [config/project_templates.json](/C:/Trabajo/AgenticLocalManager_Proyect/config/project_templates.json)
- restauración de contexto de proyecto en [app_core/project_context.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/project_context.py)
- soporte de runtime de proyecto en [app_core/memory_store.py](/C:/Trabajo/AgenticLocalManager_Proyect/app_core/memory_store.py)
- selección de proyecto y visibilidad de template en [dashboard.py](/C:/Trabajo/AgenticLocalManager_Proyect/dashboard.py)

## Evolución posterior

Después de fusionar MVP 3, la plataforma agregó:

- restauración persistente del último `project + sprint + team + subproject`
- configuración de repos por subproyecto
- asociación de sprint a `project_id + subproject_id + team_id`
- equipos reutilizables por stack y substack
- instalador Windows y persistencia de configuración global de git y LLM
- onboarding de dashboard que oculta tablero y agentes hasta que existan proyecto y subproyecto

