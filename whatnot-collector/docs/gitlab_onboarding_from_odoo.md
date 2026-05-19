# GitLab Onboarding From Odoo Users

## Purpose
This file maps the Odoo users found in the local `AethrixProd` database to a practical GitLab onboarding plan for this project.

Project remote:
- `git@code.cybertechnainc.com:sajeeds4/project_hjay9672-wn.git`

## Source
User list was extracted from:
- PostgreSQL database `AethrixProd`
- Odoo config: [/home/cybertechna/AethrixSystems_Portable/Aethrix Systems/odoo/odoo.conf](/home/cybertechna/AethrixSystems_Portable/Aethrix%20Systems/odoo/odoo.conf)

## Odoo Users Found

### System or template accounts
These should usually not be added to GitLab unless there is a very specific reason.

1. `__system__`
2. `default`
3. `public`
4. `portaltemplate`

### Human or likely human accounts
These are the human accounts found in Odoo. Not all of them are currently approved for GitLab access.

1. `admin`
   - Name: Mitchell Admin
   - Email: `admin@yourcompany.example.com`
   - Active: `true`
   - Odoo groups:
     - Access Rights
     - Access to export feature
     - Bypass HTML Field Sanitize
     - Contact Creation
     - Internal User
     - Settings
     - Technical Features

2. `demo`
   - Name: Marc Demo
   - Email: `mark.brown23@example.com`
   - Active: `true`
   - Odoo groups:
     - Access to export feature
     - Contact Creation
     - Internal User
     - Technical Features
   - GitLab status:
     - not approved
     - GitLab account removed on `2026-04-05`

3. `portal`
   - Name: Joel Willis
   - Email: `joel.willis63@example.com`
   - Active: `true`
   - Odoo groups:
     - Portal
   - GitLab status:
     - not approved
     - GitLab account removed on `2026-04-05`

## Recommended GitLab Access Plan

### Maintainer
Use for people who will:
- merge code
- manage CI/CD
- change settings
- control releases

Recommended:
- `admin`

### Developer
Use for interns or contributors who will:
- clone the repo
- push branches
- open merge requests
- work on assigned tasks

Recommended:
- `demo`

### Reporter or Guest
Use for people who need visibility but should not push code.

Possible:
- `portal`

## Recommended Git Workflow For Interns

1. Clone the repo.
2. Create a personal feature branch.
3. Work only in assigned areas.
4. Open merge requests instead of pushing directly to `main`.
5. Keep backups before changing live operational data.

Suggested branch naming:
- `feature/<name>-<task>`
- `fix/<name>-<task>`
- `docs/<name>-<task>`

## Provisioned GitLab Accounts
These accounts were created and added to the project on `2026-04-05`.

1. Odoo `admin`
   - GitLab username: `mitchell.admin`
   - Access level: `Maintainer`

Project members now include:
- `sajeeds4` -> Owner
- `mitchell.admin` -> Maintainer

## Credentials Handling
Temporary passwords were generated during provisioning, but they are intentionally not stored in the repository.

Local credential handoff file:
- [gitlab_user_credentials_2026-04-05.txt](/home/cybertechna/Downloads/gitlab_user_credentials_2026-04-05.txt)

Recommended next step:
1. hand each user their temporary password securely
2. have them sign in
3. change their password immediately
4. optionally enable 2FA
