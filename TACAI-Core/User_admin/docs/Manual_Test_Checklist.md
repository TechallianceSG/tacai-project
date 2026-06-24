# TACAI User Management Manual Test Checklist

Use this checklist for the runnable local app on port 8006.

## Sprint 1 Checks

- App starts locally on port 8006.
- `/health` returns OK.
- Login page renders in English.
- Login page renders in Japanese.
- User can login with valid email/password.
- Invalid password increases failed login count.
- Account locks after configured failed attempts.
- Password policy rejects weak passwords.
- Plaintext password is never stored.

## Sprint 2 Checks

- System Admin can view roles.
- System Admin can assign roles to users from the user edit form.
- User can have multiple roles.
- Permission checks resolve through role-permission mapping.
- System Admin can manage permissions for non-System Admin roles.
- System Admin role permissions are read-only in the local MVP.
- Session is created on login.
- Session is invalidated on logout.
- Expired session is rejected.

## Sprint 3 Checks

- Check Permission helper returns correct result.
- Check Role helper returns correct result.
- Check Module Access helper returns correct result.
- Business module integration contract is documented.

## Sprint 4 Checks

- Audit log records user login.
- Audit log records logout.
- Audit log records password change.
- Audit log records user creation/deactivation.
- Audit log records role assignment.
- Audit log records role-permission changes.
- Audit log records session revocation after user deactivation.
- Audit log records are read-only and not deleted.
- Admin dashboard shows total users.
- Admin dashboard shows active and locked users.
- Admin dashboard shows recent logins and failed logins.
- Admin dashboard shows role distribution.

## Admin Workflow Checks

- `/users` shows Create, Edit, and Deactivate actions.
- `/users/new` creates a valid user.
- `/users/new` rejects weak passwords.
- `/users/new` rejects duplicate username/email.
- `/users/edit?user_id=...` updates profile fields.
- `/users/edit?user_id=...` updates role assignments.
- Self-deactivation is blocked.
- Removing or deactivating the last active System Admin is blocked.
- Deactivated users cannot log in.
- `/roles` shows permission counts and Manage Permissions links.
- `/roles/permissions?role_id=...` updates permission assignments for non-System Admin roles.
- Permission assignment changes affect `/api/check-permission` results.
- New UI labels render in English, Japanese, and Simplified Chinese where `zh` resources are available.
