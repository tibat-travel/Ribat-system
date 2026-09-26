# Ribat System Backend

Backend and frontend for the Ribat Travel & Tourism management system.

## Default administrator
- Username: `admin`
- Temporary password: `123456`

Change the administrator password from the system after the first login.

## Roles
- `admin` — full permissions
- `team_leader` — قائد الفريق
- `marketing_captain` — كابتن التسويق
- `sales`
- `operations`
- `accountant`
- `viewer`
- `custom` — permissions selected by the administrator

## Deployment
Render start command:
`gunicorn server:app`

The frontend file is `index.html` and is served by the same Flask service.
The database is stored at the persistent Render disk path configured by `RIBAT_DB_PATH`.
