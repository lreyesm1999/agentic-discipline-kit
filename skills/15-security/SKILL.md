# 15 — Security Verification

## Purpose
Run deterministic security checks and abuse-case tests.

## Trigger
Security-sensitive change or required risk profile.

## Inputs
- diff
- dependencies
- security policy

## Outputs
- SAST/dependency/secret scan results
- security test results

## Procedure
1. Run dependency scan.
2. Run secret scan.
3. Run SAST.
4. Add auth/input/injection/data-leak tests where relevant.
5. Triage by severity and exploitability.
6. Fix high/critical or obtain explicit risk acceptance.

## Evidence required
- tool outputs
- severity counts

## Forbidden
- suppressing findings without acceptance

## Stop conditions
- unresolved critical/high finding

## Definition of done
- no unresolved blocking security findings
