# ADMIN_GLOSSARY.md

Status: initial baseline  
Date: 2026-04-14  
Phase: `Phase C`

## Purpose

Provide the first human-readable naming baseline for the admin UI and reduce dependence on raw internal identifiers.

## Preferred visible language

- `Servers` -> `Servers`
  - Meaning: runtime environments that carry their own configuration bundle and operational status.
- `Laws` -> `Law Sources and Law Sets`
  - Meaning: legal source inputs, processed bundles, and bindings to servers.
- `Templates` -> `Document Templates`
  - Meaning: reusable text and structure used by generated outputs.
- `Features` -> `Capabilities`
  - Meaning: runtime switches or platform capabilities visible to admins.
- `Rules` -> `Validation Rules`
  - Meaning: checks that gate publishability or runtime behavior.
- `Catalog` -> `Configuration Catalog`
  - Meaning: the versioned inventory of admin-managed entities.
- `Publication workflow` -> `Draft, review, publish, rollback`
  - Meaning: lifecycle of a configuration change.
- `Audit` -> `Change History`
  - Meaning: who changed what and when.

## Copy rules

- Prefer human-readable labels over raw entity keys.
- If an internal key must be shown, place it in secondary text.
- Use `Change History` instead of `audit` in visible headings unless the audience is clearly technical.
- Use `Law Sources and Law Sets` instead of plain `laws` when there is room for a clearer label.
- Use `Capabilities` or `Validation Rules` where `features` or `rules` would otherwise be ambiguous.

## Terms to avoid as primary labels

- raw route names
- raw event names
- internal workflow state ids without explanation
- database-oriented names such as `entity_type`, `payload_json`, `content_key`

## Immediate application in Phase C

- Catalog-domain pages should show a domain summary with user-facing labels.
- Runtime inventory and configuration inventory should be named separately.
- Existing raw ids can remain in tables as secondary metadata while the primary label uses glossary terms.
- `servers`, `laws`, `templates`, `features`, and `rules` page shells should each expose a domain map using these preferred labels.
