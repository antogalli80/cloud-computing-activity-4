"""Host-run recovery evidence; credentials exist in memory only, backups are temporary."""

import asyncio
import base64
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx


def docker(*args, data=None):
    result = subprocess.run(
        ["docker", "compose", *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode:
        raise RuntimeError(
            "Docker recovery command failed: " + result.stderr.decode(errors="replace")[-800:]
        )
    return result.stdout


async def main():
    auth = "http://127.0.0.1:8101"
    files = "http://127.0.0.1:8102"
    results = []
    async with httpx.AsyncClient(timeout=30) as client:
        credentials = {
            "email": f"recovery-{uuid4().hex}@example.com",
            "password": "synthetic-recovery-password",
        }
        response = await client.post(auth + "/authentication/register", json=credentials)
        assert response.status_code == 200, response.text
        token = (await client.post(auth + "/authentication/login", json=credentials)).json()[
            "token"
        ]
        headers = {"Auth": token}
        item = (
            await client.post(files + "/files", json={"filename": "recovery.txt"}, headers=headers)
        ).json()["file"]
        content = b"Synthetic recovery evidence; no personal data."
        assert (
            await client.post(
                files + f"/files/{item['id']}",
                files={"file_content": ("recovery.txt", content, "text/plain")},
                headers=headers,
            )
        ).status_code == 200
        docker("restart", "postgres", "authentication-api", "files-api")
        ready = False
        for _ in range(45):
            try:
                if (await client.get(auth + "/ready")).status_code == 200 and (
                    await client.get(files + "/ready")
                ).status_code == 200:
                    ready = True
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        assert ready
        response = await client.get(files + f"/files/{item['id']}", headers=headers)
        assert (
            response.status_code == 200
            and base64.b64decode(response.json()["content_base64"]) == content
        )
        results.append(
            {
                "check": "Database and both API restarts preserve session, metadata and content",
                "result": "PASS",
            }
        )
        # Passwords/token digests in backups are sensitive: never included in deliverables.
        backup = docker("exec", "-T", "postgres", "pg_dump", "-U", "cloud_admin", "-Fc", "cloud3")
        restore_name = "cloud3_restore_" + uuid4().hex[:8]
        docker("exec", "-T", "postgres", "createdb", "-U", "cloud_admin", restore_name)
        docker(
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            "cloud_admin",
            "--no-owner",
            "--exit-on-error",
            "-d",
            restore_name,
            data=backup,
        )
        query = "SELECT (SELECT count(*) FROM users), (SELECT count(*) FROM files), (SELECT count(*) FROM audit_events);"
        original = docker(
            "exec", "-T", "postgres", "psql", "-U", "cloud_admin", "-d", "cloud3", "-Atc", query
        )
        restored = docker(
            "exec", "-T", "postgres", "psql", "-U", "cloud_admin", "-d", restore_name, "-Atc", query
        )
        assert original == restored
        results.append(
            {
                "check": "Database dump restored into independent database with matching counts",
                "result": "PASS",
                "counts_users_files_audit": original.decode().strip(),
            }
        )
        # Scope is deliberately limited to the database this script just created.
        docker("exec", "-T", "postgres", "dropdb", "-U", "cloud_admin", restore_name)
        docker("stop", "authentication-api")
        denied = await client.get(files + "/files", headers=headers)
        assert denied.status_code == 503
        results.append(
            {"check": "Authentication outage fails closed with HTTP 503", "result": "PASS"}
        )
        docker("start", "authentication-api")
        Path("artifacts/recovery.json").write_text(
            json.dumps({"checks": results, "passed": len(results)}, indent=2)
        )
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
