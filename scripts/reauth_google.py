"""
Re-autenticación local de Google OAuth para Drive + YouTube.

Por qué este script:
    El callback OAuth de producción está hardcodeado a localhost. Cuando
    cambian los scopes (como ahora que sumamos YouTube), hay que generar
    un token.json nuevo y subirlo a Render como Secret File. La forma más
    simple y robusta es correr este script en tu PC y dejar que abra el
    browser, autenticar con la cuenta de BCR, y guardar el token nuevo.

Uso:
    1. Asegurate de tener client_secret.json en esta misma carpeta (o en
       backend/). Si no lo tenés, bajalo desde Google Cloud Console →
       Credentials → tu OAuth 2.0 Client ID → Download JSON.
    2. Activá el venv:
           venv\\Scripts\\activate
    3. Corré:
           python scripts/reauth_google.py
    4. Se va a abrir el browser. Logueate con la cuenta de Gmail de BCR
       (la que tiene Drive y permisos en el canal de YouTube).
    5. Aprobá los permisos (Drive + YouTube). Si te dice "esta app no
       está verificada", click en "Avanzado" → "Ir a la app" y aceptá.
    6. Cuando termine, se guarda token.json en la raíz del repo.
    7. Subí ese token.json a Render como Secret File reemplazando el actual.

Los scopes que se solicitan están en backend/utils/drive.py (SCOPES).
"""
import os
import sys
import json

from google_auth_oauthlib.flow import InstalledAppFlow


# Mismos scopes que el backend en producción
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    backend_dir = os.path.join(repo_root, "backend")

    # Buscar client_secret.json en varios lugares razonables
    candidates = [
        os.path.join(here, "client_secret.json"),
        os.path.join(repo_root, "client_secret.json"),
        os.path.join(backend_dir, "client_secret.json"),
    ]
    client_secret = next((p for p in candidates if os.path.exists(p)), None)
    if not client_secret:
        print("ERROR: no encontré client_secret.json en:")
        for p in candidates:
            print(f"  - {p}")
        print("\nBajalo desde Google Cloud Console → Credentials → tu OAuth Client ID → Download JSON.")
        sys.exit(1)

    print(f"Usando client_secret.json desde: {client_secret}")
    print(f"Scopes solicitados:")
    for s in SCOPES:
        print(f"  - {s}")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(client_secret, SCOPES)
    # Abre el browser y escucha en un puerto local
    creds = flow.run_local_server(
        port=0,
        prompt="consent",  # fuerza el consent screen para garantizar refresh_token
        access_type="offline",
    )

    token_path = os.path.join(repo_root, "token.json")
    with open(token_path, "w") as f:
        f.write(creds.to_json())

    # Verificación rápida del token guardado
    data = json.loads(creds.to_json())
    has_refresh = bool(data.get("refresh_token"))

    print()
    print(f"✅ Token guardado en: {token_path}")
    print(f"   Refresh token presente: {'sí' if has_refresh else '¡NO!  (volvé a correr el script)'}")
    print(f"   Scopes: {data.get('scopes', [])}")
    print()
    print("Próximo paso: subí ese token.json a Render como Secret File")
    print("reemplazando el actual.")


if __name__ == "__main__":
    main()
