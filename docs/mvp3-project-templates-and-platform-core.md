# MVP 3 - Project Templates And Platform Core

## Objetivo

Convertir el sistema en una base reusable para distintos tipos de proyecto, manteniendo software delivery como template principal y mejor soportado.

## Problema que resuelve

Aunque el sistema ya tenga agentes y tablero, sigue estando orientado a un caso puntual. Falta:

- templates de proyecto
- desacople entre core y adapters
- workflows configurables por proyecto
- una base realmente reusable

## Resultado esperado

Al finalizar este MVP, el sistema debe poder operar como plataforma base con:

- core de board y workflow desacoplado
- adapters externos enchufables
- templates de proyecto versionados
- software backend, software web y software mobile como templates iniciales

## Alcance funcional

- separar core, adapters y templates
- convertir el flujo actual en template `software_delivery_default`
- permitir que cada proyecto seleccione template
- mantener compatibilidad con el tablero local como repositorio principal

## No incluye

- soporte completo para todos los dominios posibles
- reemplazo obligatorio de Telegram, GitLab o dashboard
- multitenancy compleja

## Cambios de arquitectura

### Core

Separar modulos en:

```text
core/
  board/
  workflow/
  assignment/
  agents/
  prompts/
```

### Adapters

Crear borde de integracion para:

- storage
- messaging
- repository
- llm
- dashboard

### Templates

Primeros templates:

- `software_delivery_default`
- `software_backend`
- `software_web`
- `software_mobile`

Cada template define:

- workflow base
- stacks permitidos
- roles requeridos
- presets sugeridos
- reglas de artefactos esperados

## Cambios por modulo

### Core board

- centralizar entidades de task, sprint, comment, transition y artifact

### Workflow

- convertir estados y transiciones actuales en definicion reusable

### Dashboard

- selector de template de proyecto
- visualizacion de workflow activo

### Configuracion

- nuevo catalogo de templates
- mapeo entre proyecto y template

## Criterios de aceptacion

- el sistema puede correr usando `software_delivery_default` sin cambio funcional respecto al comportamiento actual
- debe existir template separado para backend, web y mobile
- los adapters deben estar desacoplados del core
- el tablero local debe seguir siendo la fuente de verdad por defecto

## Riesgos

- intentar abstraer demasiado pronto
- romper compatibilidad con el software delivery actual
- dispersar la configuracion entre demasiados archivos

## Mitigacion

- usar el workflow actual como template fundador
- no introducir nuevos estados sin necesidad
- mantener un template default obligatorio

## Plan de ejecucion

1. Extraer core de board y workflow.
2. Definir interfaces de adapters.
3. Mover integraciones externas a adapters.
4. Crear templates iniciales.
5. Conectar dashboard y configuracion al selector de template.
6. Validar equivalencia funcional con el flujo actual.

## Definition of done

- core desacoplado y reusable
- adapters identificados y separados
- templates iniciales versionados
- workflow actual representado como template principal
- base lista para extender a otros tipos de proyecto por configuracion

## Estado actual

Estado: `completado`

Quedo incorporado en `develop` con:

- `config/project_templates.json` como catalogo versionado
- `app_core/project_templates.py` y `app_core/project_context.py`
- validacion de configuracion de proyecto por familias de repositorio
- dashboard con selector de proyecto y template
- persistencia de `template_id` y `project_id` en el storage local
- tablero filtrado por proyecto

Extension agregada despues del cierre base de MVP 3:

- runtime state por proyecto con restore del ultimo sprint
- sprint asociado a `project_id + team_id + substack`
- equipos reutilizables por stack/substack desacoplados del proyecto
