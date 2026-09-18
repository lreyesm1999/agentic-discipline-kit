# Data Model Draft

## Core tables

### projects
- id
- name
- root_path
- repository_url
- baseline_commit
- created_at
- updated_at

### entities
- id
- project_id
- entity_type
- canonical_name
- lifecycle_state
- authority
- confidence
- current_version
- created_at
- updated_at

### entity_versions
- entity_id
- version
- payload_json
- valid_from
- valid_to
- source_claim_id
- created_by

### edges
- id
- project_id
- source_entity_id
- edge_type
- target_entity_id
- version
- lifecycle_state

### evidence
- id
- project_id
- claim_ref
- evidence_type
- tool
- result
- code_version
- knowledge_version
- artifact_ref
- content_hash
- created_at
- stale_at

### claims
- id
- project_id
- subject_ref
- predicate
- value_json
- source_type
- source_ref
- confidence
- authority
- verification_status
- lifecycle_state

### tasks
- id
- project_id
- objective
- state
- risk_profile
- workspace_id
- knowledge_version
- created_at

### task_dependencies
- task_id
- depends_on_task_id
- dependency_type

### agents
- id
- provider
- tool_name
- capabilities_json
- status

### leases
- id
- task_id
- agent_id
- acquired_at
- heartbeat_at
- expires_at

### checkpoints
- id
- task_id
- agent_id
- state_json
- git_commit
- knowledge_version
- created_at

### changesets
- id
- project_id
- base_knowledge_version
- status
- reason
- author
- created_at

### audit_events
- seq
- project_id
- event_type
- payload_json
- actor
- created_at

## Important indexes

- entities(project_id, entity_type)
- edges(project_id, source_entity_id, edge_type)
- edges(project_id, target_entity_id, edge_type)
- tasks(project_id, state)
- leases(task_id, expires_at)
- evidence(project_id, claim_ref, stale_at)
- claims(project_id, subject_ref, predicate)

## Constraint examples

- one active valid lease per exclusive task;
- entity version increments monotonically;
- completed task requires evidence invariant at application layer;
- edges cannot point to unknown entity IDs;
- stale evidence cannot satisfy a current completion gate.
