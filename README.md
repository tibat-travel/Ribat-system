# Ribat System Backend

Backend for the Ribat Travel & Tourism management system.

## Default administrator
- Username: `admin`
- Temporary password: `123456`

Change the administrator password from the system after the first login.

## Deployment
Render start command:
`gunicorn server:app`

Upload the frontend as `index.html` in the same repository so the backend and frontend share one address.
