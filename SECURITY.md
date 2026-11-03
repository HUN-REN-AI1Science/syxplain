# Security policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report them privately through GitHub's
[private vulnerability reporting](https://github.com/HUN-REN-AI1Science/syxplain/security/advisories/new)
(the **Security** tab → **Report a vulnerability**). Include:

- what is affected (component, endpoint, version or commit)
- how to reproduce it, and the impact you expect
- any suggested fix

We aim to acknowledge reports within a week and to keep you informed until the issue is
fixed. We are happy to credit you in the advisory.

## Supported versions

Security fixes go into the latest release on `main`.

## Deployment notes

If you run your own instance:

- Change every default credential: `KEYCLOAK_ADMIN_PASSWORD`, `POSTGRES_PASSWORD`,
  `KC_DB_PASSWORD` and `WORKER_CALLBACK_TOKEN`. The development defaults are public.
- Set `KEYCLOAK_ISSUER` and restrict `CORS_ORIGINS` to your domain.
- The slurmrestd token (`SLURM_AUTH_TOKEN`) can submit jobs as its user. Give it the
  shortest lifetime you can manage, and keep `.env` out of version control.
- Users' own LLM keys are used for their runs only and are not stored with the results.
