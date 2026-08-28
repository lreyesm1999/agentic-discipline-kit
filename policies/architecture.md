# Architecture Policy v2

Architecture boundaries should be executable.

Preferred tools:
- TypeScript/JS: dependency-cruiser / madge / custom AST rules
- .NET: NetArchTest / ArchUnitNET
- Python: import-linter / custom import graph checks

Required:
- no unapproved dependency cycles
- no forbidden direction violations
- no cross-module access outside declared boundaries
- no new infrastructure coupling inside protected core/domain code
